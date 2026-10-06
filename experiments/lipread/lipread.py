"""Lip-reading test: can someone follow the words from the lips alone?

Renders a photo speaking four test sentences with LivePortrait (MIT) on the CPU. Each sound
Kokoro speaks maps to one of 10 mouth shapes, timed to Kokoro's own per-sound timings.

  setup (once per photo): render the 10 mouth shapes with LivePortrait, and the optical
      flow between every pair of them.
  per reply (fast): speak, turn sounds into per-frame shape weights, morph between the two
      strongest shapes along the flow (no ghosting), paste into the photo, encode.

`--direct` also renders every frame with LivePortrait from the blended shape (minutes, not
seconds), as a reference for what the fast path should look like.

Run experiments/photoreal/setup_liveportrait.py first.
"""

import argparse
import json
import logging
import os
import platform
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "photoreal"))
sys.path.insert(0, str(HERE))
from face_points import VISEMES as OLD_SHAPES  # noqa: E402
from face_points import expression_delta  # noqa: E402
from lip_shapes import SHAPES, frame_weights, mix, segments, soften, top_two  # noqa: E402
from liveportrait_cpu import Portrait, contact_sheet  # noqa: E402
from sound_timings import SAMPLE_RATE, Voice  # noqa: E402

log = logging.getLogger("lipread")
UPPER_LIP_KP = 20  # LivePortrait keypoint that lifts the upper lip (found by rendering each)

SENTENCES = (
    "Hello, my name is Mary. Would you like some more popcorn? "
    "Please move the blue boat. I see three green trees."
)


def lip_gap_ratio(photo_rgb: np.ndarray, face_model: Path) -> float:
    """Inner-lip gap over inner mouth width in the photo (0 when the lips touch)."""
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(face_model)), num_faces=1
    )
    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=photo_rgb))
    h, w = photo_rgb.shape[:2]
    p = np.array([[q.x * w, q.y * h] for q in result.face_landmarks[0]], np.float32)
    return float(np.linalg.norm(p[13] - p[14]) / np.linalg.norm(p[78] - p[308]))


class LipPortrait(Portrait):
    """Portrait whose mouth opening goes through LivePortrait's lip retargeting model."""

    def __init__(self, lp_dir: Path, photo: Path, face_model: Path) -> None:
        super().__init__(lp_dir, photo, face_model)
        self.photo_ratio = lip_gap_ratio(self.photo, face_model)
        log.info("Lips in the photo: gap ratio %.3f", self.photo_ratio)

    @torch.no_grad()
    def render_mouth(
        self, controls: dict[str, float], ratio: float | None, upper: float = 1.0
    ) -> np.ndarray:
        """One 512x512 RGB face crop with the head still and the given mouth.

        `upper` scales how far the upper lip moves (LivePortrait keypoint 20), separately
        from the lower lip and jaw.
        """
        info = self.info
        rot = self._rotation(info["pitch"], info["yaw"], info["roll"])
        x_rest = info["scale"] * (info["kp"] @ rot + info["exp"]) + self.t
        delta = torch.tensor(expression_delta(controls)).view(1, -1, 3)
        x_d = x_rest + info["scale"] * delta
        if ratio is not None:
            lip = torch.tensor([[self.photo_ratio, ratio]], dtype=torch.float32)
            x_d = x_d + self.lp.retarget_lip(self.x_s, lip)
        motion = x_d - x_rest
        motion[:, UPPER_LIP_KP] *= upper
        x_d = self.lp.stitching(self.x_s, x_rest + motion)
        out = self.lp.warp_decode(self.features, self.x_s, x_d)
        return self.lp.parse_output(out["out"])[0]  # type: ignore[no-any-return]


def pair_flows(faces: dict[str, np.ndarray]) -> dict[tuple[str, str], np.ndarray]:
    """Optical flow between every ordered pair of mouth shapes (setup step)."""
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    gray = {k: cv2.cvtColor(v, cv2.COLOR_RGB2GRAY) for k, v in faces.items()}
    return {(a, b): dis.calc(gray[a], gray[b], None) for a in gray for b in gray if a != b}


def morph(
    faces: dict[str, np.ndarray],
    flows: dict[tuple[str, str], np.ndarray],
    a: str,
    b: str,
    t: float,
    grid: np.ndarray,
) -> np.ndarray:
    """A frame t of the way from shape a to shape b: both warped to meet, then blended."""
    if a == b or t <= 0.0:
        return faces[a]
    from_a = grid + t * flows[(b, a)]
    from_b = grid + (1.0 - t) * flows[(a, b)]
    warped_a = cv2.remap(faces[a], from_a, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    warped_b = cv2.remap(faces[b], from_b, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return cv2.addWeighted(warped_a, 1.0 - t, warped_b, t, 0.0)


def write_wav(audio: np.ndarray, path: Path) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


def write_mp4(frames: list[np.ndarray], fps: float, path: Path, audio: Path | None) -> None:
    h, w = frames[0].shape[:2]
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
    ]  # fmt: skip
    if audio is not None:
        cmd += ["-i", str(audio), "-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "veryfast"]
    proc = subprocess.run(
        [*cmd, str(path)], input=b"".join(f.tobytes() for f in frames), check=False
    )
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg failed writing {path} (exit {proc.returncode})")


def mouth_crop(face: np.ndarray) -> np.ndarray:
    """The lower middle of a 512x512 face crop, where the mouth is."""
    return face[256:512, 128:384]


def before_after(portrait: LipPortrait, new: dict[str, np.ndarray], path: Path) -> None:
    """Old single-keypoint open shapes (top) next to the new ones (bottom)."""
    tiles = {}
    for name in ("AA", "OH", "OO"):
        old = portrait.render_mouth(OLD_SHAPES[name], None)
        tiles[f"before {name}"] = mouth_crop(old)
    for name in ("AA", "OH", "OO"):
        tiles[f"after {name}"] = mouth_crop(new[name])
    rows = []
    for row in (list(tiles.items())[:3], list(tiles.items())[3:]):
        cells = []
        for label, img in row:
            tile = cv2.cvtColor(cv2.resize(img, (320, 320)), cv2.COLOR_RGB2BGR)
            cv2.putText(tile, label, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cells.append(tile)
        rows.append(np.hstack(cells))
    cv2.imwrite(str(path), np.vstack(rows))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--text", default=SENTENCES)
    parser.add_argument("--voice", default="af_heart", help="Kokoro voice, e.g. am_adam")
    parser.add_argument("--lp-dir", type=Path, default=HERE.parent / "photoreal" / "LivePortrait")
    parser.add_argument("--out", type=Path, default=Path("lipread_out"))
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument(
        "--strength",
        type=float,
        default=0.45,
        help="how far lips move from rest, 0..1 (1 = full shapes; lower is softer)",
    )
    parser.add_argument(
        "--upper", type=float, default=0.3, help="upper-lip movement relative to the rest, 0..1"
    )
    parser.add_argument(
        "--smooth", type=float, default=0.06, help="seconds that neighbouring sounds blend over"
    )
    parser.add_argument(
        "--lead", type=float, default=0.03, help="seconds the lips move ahead of the sound"
    )
    parser.add_argument("--direct", action="store_true", help="also render every frame (slow)")
    parser.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    torch.set_num_threads(args.threads)
    args.out.mkdir(parents=True, exist_ok=True)
    face_model = args.lp_dir / "pretrained_weights" / "face_landmarker.task"
    timings: dict[str, Any] = {
        "cpu": platform.processor() or platform.machine(),
        "threads": args.threads,
        "strength": args.strength,
        "upper": args.upper,
        "smooth_s": args.smooth,
        "lead_s": args.lead,
    }

    # Setup, once per photo: mouth shapes and the flow between them.
    start = time.perf_counter()
    portrait = LipPortrait(args.lp_dir, args.photo, face_model)
    log.info(
        "Mouth strength %.2f, upper lip %.2f, sounds blend over %.3f s, lips lead by %.3f s",
        args.strength,
        args.upper,
        args.smooth,
        args.lead,
    )
    faces = {}
    for name in SHAPES:
        controls, ratio = soften(name, args.strength, portrait.photo_ratio)
        faces[name] = portrait.render_mouth(controls, None if name == "rest" else ratio, args.upper)
    contact_sheet({k: mouth_crop(v) for k, v in faces.items()}, args.out / "mouth_shapes.png")
    flows = pair_flows(faces)
    timings["setup_s"] = round(time.perf_counter() - start, 1)
    log.info(
        "Setup done: %d mouth shapes and %d flows in %.1f s",
        len(faces),
        len(flows),
        timings["setup_s"],
    )
    before_after(portrait, faces, args.out / "before_after.png")

    # Per reply: speech, sound timings, frames, encode.
    voice = Voice()
    start = time.perf_counter()
    audio, phonemes, seconds = voice.speak(args.text, args.voice)
    speech_s = time.perf_counter() - start
    wav_path = args.out / "voice.wav"
    write_wav(audio, wav_path)
    segs = segments(phonemes, seconds)
    n_frames = int(round(len(audio) / SAMPLE_RATE * args.fps))
    weights = frame_weights(segs, n_frames, args.fps, args.smooth, args.lead)
    (args.out / "sounds.json").write_text(
        json.dumps(
            [{"shape": s.shape, "start": round(s.start, 3), "end": round(s.end, 3)} for s in segs],
            indent=1,
        )
    )

    start = time.perf_counter()
    h, w = next(iter(faces.values())).shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    grid = np.dstack([gx, gy])
    frames = [portrait.paste(morph(faces, flows, *top_two(wt), grid)) for wt in weights]
    assemble_s = time.perf_counter() - start
    write_mp4(frames, args.fps, args.out / "lipread_voice.mp4", wav_path)
    reply_s = time.perf_counter() - start
    write_mp4(frames, args.fps, args.out / "lipread_muted.mp4", None)
    clip_s = len(audio) / SAMPLE_RATE
    timings["reply"] = {
        "clip_s": round(clip_s, 2),
        "frames": n_frames,
        "speech_s": round(speech_s, 2),
        "frames_s": round(assemble_s, 2),
        "frames_and_encode_s": round(reply_s, 2),
    }
    log.info(
        "Reply clip built: %.2f s of video, speech %.2f s, frames + encode %.2f s",
        clip_s,
        speech_s,
        reply_s,
    )

    if args.direct:
        start = time.perf_counter()
        direct = []
        for i, wt in enumerate(weights):
            controls, ratio = mix(wt, portrait.photo_ratio, args.strength)
            direct.append(portrait.paste(portrait.render_mouth(controls, ratio, args.upper)))
            if i % 30 == 0:
                log.info("Direct render: frame %d of %d", i, n_frames)
        write_mp4(direct, args.fps, args.out / "direct_voice.mp4", wav_path)
        write_mp4(direct, args.fps, args.out / "direct_muted.mp4", None)
        timings["direct_s"] = round(time.perf_counter() - start, 1)
        log.info("Direct clip built in %.1f s", timings["direct_s"])

    (args.out / "timings.json").write_text(json.dumps(timings, indent=2))
    print(json.dumps(timings, indent=2))
    print(
        f"Wrote lipread_voice.mp4, lipread_muted.mp4, mouth_shapes.png, before_after.png, "
        f"sounds.json and timings.json to {args.out.resolve()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
