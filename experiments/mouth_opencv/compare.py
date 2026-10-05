"""Side-by-side test: can the OpenCV mouth from PR #7 look natural?

Renders one photo speaking one text three ways, next to each other, with the voice:
  1. "PR #7": the current engine (mouth opens with loudness, wide dark opening).
  2. "Softer": opens less, eases in and out, lighter opening with a hint of upper teeth.
  3. "Sounds": the softer mouth driven by the phonemes Kokoro speaks: it closes on m, b and p,
     rounds on "oo" and "w", and opens on "ah".

Speech comes from Kokoro's ONNX build (kokoro-onnx), downloaded from GitHub, not Hugging Face.
Its graph is patched once to also return how long each phoneme lasts.

    python experiments/mouth_opencv/compare.py --photo me.jpg
"""

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

sys.path.insert(0, str(Path(__file__).parent))
from visemes import frame_shapes, segments  # noqa: E402

from imageskin.mouth_warp import (  # noqa: E402
    MouthWarpEngine,
    draw_frame,
    frame_weights,
    load_photo,
)
from imageskin.sample import SAMPLE_SCRIPT  # noqa: E402
from imageskin.video import FPS, Face, mouth_openness  # noqa: E402

log = logging.getLogger("compare")
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_DIR = Path(__file__).parent / "models"
SAMPLE_RATE = 24000
SAMPLES_PER_DURATION_UNIT = 600  # Kokoro predicts phoneme lengths in units of 25 ms
SOFT_DROP = 0.2  # share of lips-to-chin the lower lip drops at full opening (PR #7 uses 0.35)
Image = NDArray[np.uint8]


def ensure_models() -> tuple[Path, Path]:
    """Download Kokoro's ONNX model and voices once, and add a phoneme-duration output."""
    MODEL_DIR.mkdir(exist_ok=True)
    for name in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        path = MODEL_DIR / name
        if not path.exists():
            log.info("Downloading %s (once)", name)
            urllib.request.urlretrieve(RELEASE + name, path)
    patched = MODEL_DIR / "kokoro-durations.onnx"
    if not patched.exists():
        import onnx

        model = onnx.load(str(MODEL_DIR / "kokoro-v1.0.onnx"))
        # The rounded, clipped phoneme durations inside the model, in 25 ms units.
        model.graph.output.append(
            onnx.helper.make_tensor_value_info(
                "/encoder/Clip_output_0", onnx.TensorProto.FLOAT, None
            )
        )
        onnx.save(model, str(patched))
    return patched, MODEL_DIR / "voices-v1.0.bin"


def speak(text: str, voice: str) -> tuple[NDArray[np.float32], str, list[float]]:
    """Speak text sentence by sentence; return audio, phonemes and each phoneme's seconds."""
    import onnxruntime
    from kokoro_onnx import Kokoro

    model, voices = ensure_models()
    kokoro = Kokoro(str(MODEL_DIR / "kokoro-v1.0.onnx"), str(voices))
    session = onnxruntime.InferenceSession(str(model))
    audio: list[NDArray[np.float32]] = []
    phonemes, durations = "", []
    for sentence in split_sentences(text):
        ph = kokoro.tokenizer.phonemize(sentence, "en-us")
        tokens = kokoro.tokenizer.tokenize(ph)
        kept = "".join(ch for ch in ph if ch in kokoro.tokenizer.vocab)
        style = kokoro.get_voice_style(voice)[len(tokens)]
        wav, dur = session.run(
            None,
            {"tokens": [[0, *tokens, 0]], "style": style, "speed": np.ones(1, dtype=np.float32)},
        )
        units = dur.ravel()
        seconds = [u * SAMPLES_PER_DURATION_UNIT / SAMPLE_RATE for u in units]
        # The padding tokens at each end are silence.
        phonemes += "." + kept + "."
        durations += [seconds[0], *seconds[1:-1], seconds[-1]]
        audio.append(wav.astype(np.float32))
    return np.concatenate(audio), phonemes, durations


def split_sentences(text: str) -> list[str]:
    out, cur = [], ""
    for ch in text:
        cur += ch
        if ch in ".!?":
            out.append(cur.strip())
            cur = ""
    if cur.strip():
        out.append(cur.strip())
    return out


def soft_frame(
    image: Image,
    face: Face,
    region: tuple[int, int, int, int],
    weights: NDArray[np.float32],
    o: float,
    width: float = 1.0,
) -> Image:
    """The softer mouth: a smaller drop, optional rounding, and a lighter opening."""
    frame = image.copy()
    drop = o * SOFT_DROP * face.jaw_h
    x, y, w, h = region
    roi = image[y : y + h, x : x + w]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    map_x = gx
    if width != 1.0:
        # Rounding: pull the lips toward the middle, strongest at the mouth line.
        cx = face.mouth_x - x
        ys = np.arange(y, y + h, dtype=np.float32) - face.mouth_y
        band = np.exp(-((ys / (0.45 * face.jaw_h)) ** 2))[:, None]
        map_x = (cx + (gx - cx) / (1 + (width - 1) * band)).astype(np.float32)
    map_y = (gy - drop * weights).astype(np.float32)
    if drop < 0.5 and width == 1.0:
        return frame
    frame[y : y + h, x : x + w] = cv2.remap(
        roi, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )
    if drop < 0.5:
        return frame
    half_w = max(1, int(0.36 * face.mouth_w * width))
    center = (face.mouth_x, face.mouth_y + int(drop / 2))
    mask = np.zeros(frame.shape[:2], dtype=np.float32)
    cv2.ellipse(mask, center, (half_w, max(1, int(drop / 2))), 0, 0, 360, 1.0, -1)
    alpha = 0.8 * cv2.GaussianBlur(mask, (0, 0), max(1.0, drop / 4))[..., None]
    inside = np.array([45, 40, 70], dtype=np.float32)  # BGR, a dark warm red
    out = frame * (1 - alpha) + inside * alpha
    if o > 0.4:
        # A faint band of upper teeth just under the upper lip.
        teeth = np.zeros(frame.shape[:2], dtype=np.float32)
        th = max(1, int(drop * 0.18))
        cv2.ellipse(
            teeth, (face.mouth_x, face.mouth_y + th), (int(half_w * 0.7), th), 0, 0, 180, 1.0, -1
        )
        t_alpha = 0.45 * (o - 0.4) / 0.6 * cv2.GaussianBlur(teeth, (0, 0), 1.0)[..., None]
        out = out * (1 - t_alpha) + np.array([200, 205, 215], dtype=np.float32) * t_alpha
    return out.astype(np.uint8)


def refine_lip_line(image: Image, face: Face) -> Face:
    """Move the mouth line onto the darkest row near it: the seam between closed lips.

    PR #7 finds the lips by their redness, which can land a few pixels off on pale lips.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float64)
    reach = max(3, face.jaw_h // 3)
    top = max(0, face.mouth_y - reach // 2)  # not far up: the shadow under the nose is dark too
    half = max(2, face.mouth_w // 4)
    band = gray[top : face.mouth_y + reach + 1, face.mouth_x - half : face.mouth_x + half]
    rows = np.convolve(band.mean(axis=1), np.ones(3) / 3, mode="same")
    rows[0] = rows[-1] = np.inf
    mouth_y = top + int(np.argmin(rows))
    return replace(face, mouth_y=mouth_y, jaw_h=face.jaw_h + face.mouth_y - mouth_y)


def label(frame: Image, text: str) -> Image:
    out = frame.copy()
    cv2.putText(out, text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(out, text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    return out


def crop_box(face: Face) -> tuple[int, int, int, int]:
    """A square around the face, so the mouth is large enough to judge."""
    side = min(face.width, face.height, int(face.jaw_h * 7))
    x0 = min(max(0, face.mouth_x - side // 2), face.width - side)
    y0 = min(max(0, face.mouth_y - int(side * 0.62)), face.height - side)
    return x0, y0, side, side


def render(photo: Path, text: str, voice: str, output: Path, panel: int) -> None:
    start = time.perf_counter()
    image = load_photo(photo)
    face = refine_lip_line(image, MouthWarpEngine().prepare(photo))
    audio, phonemes, durations = speak(text, voice)
    log.info(
        "Spoke %.1f s of audio in %.1f s", len(audio) / SAMPLE_RATE, time.perf_counter() - start
    )

    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    loud = mouth_openness(pcm.tolist(), SAMPLE_RATE)  # type: ignore[arg-type]
    shapes = frame_shapes(segments(phonemes, durations), len(loud), FPS)
    region, weights = frame_weights(face)
    x0, y0, side, _ = crop_box(face)

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg not found; see the README's ffmpeg steps")
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "speech.wav"
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm.tobytes())
        cmd = [ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24"]
        cmd += ["-s", f"{panel * 3}x{panel}", "-r", str(FPS), "-i", "-", "-i", str(wav_path)]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
        cmd += ["-c:a", "aac", "-shortest", "-movflags", "+faststart", str(output)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        assert proc.stdin is not None
        render_start = time.perf_counter()
        for f, o_loud in enumerate(loud):
            o_shape, width = shapes[f]
            # Loudness scales the phoneme shape, so quiet syllables open less.
            o_sound = o_shape * (0.55 + 0.45 * o_loud)
            frames = [
                draw_frame(image, face, region, weights, o_loud),
                soft_frame(image, face, region, weights, 0.75 * o_loud),
                soft_frame(image, face, region, weights, o_sound, width),
            ]
            tiles = [
                label(cv2.resize(fr[y0 : y0 + side, x0 : x0 + side], (panel, panel)), name)
                for fr, name in zip(frames, ("1. PR #7", "2. Softer", "3. Sounds"), strict=True)
            ]
            proc.stdin.write(np.hstack(tiles).tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise SystemExit("ffmpeg failed")
    log.info(
        "Wrote %s: %d frames, rendered in %.1f s (all three versions)",
        output.resolve(),
        len(loud),
        time.perf_counter() - render_start,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--text", default=SAMPLE_SCRIPT)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument("-o", "--output", type=Path, default=Path("mouth_compare.mp4"))
    parser.add_argument("--panel", type=int, default=480, help="size of each panel in pixels")
    args = parser.parse_args()
    render(args.photo, args.text, args.voice, args.output, args.panel)


if __name__ == "__main__":
    main()
