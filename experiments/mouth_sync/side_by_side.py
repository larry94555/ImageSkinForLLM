"""Watch the mouth against the voice, before and after R128, side by side.

Renders a few lines on a prepared face (a photoreal library, as Setup or Start now leaves it)
with the app's own voice and video engines, twice: on the left as before R128, when the mouth
opened 60 to 160 ms before the voice after a pause (R127), and on the right as the app does
now. Each is written at normal speed with the voice, and at half speed (the voice slowed
without changing its pitch), where the early opening is easier to see.

    python experiments/mouth_sync/side_by_side.py                         # Kokoro af_heart
    python experiments/mouth_sync/side_by_side.py --clone <voice-sample.wav>
    python experiments/mouth_sync/side_by_side.py --library <home>/photoreal/<folder>

With no --library it uses the face prepared last (the newest folder in the app's
photoreal folder). The videos go to `side-by-side/` and the log has `Side by side started`,
`Side by side written` for each line with the mouth's lead before and after, and
`Side by side done`.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np  # noqa: E402
from mouth_lead import clone_speaker, kokoro_speaker  # noqa: E402

from imageskin.config import default_home  # noqa: E402
from imageskin.photoreal_library import CROP  # noqa: E402
from imageskin.video import find_ffmpeg  # noqa: E402
from imageskin.visemes import CONTACT, SHAPES, ShapeTiming  # noqa: E402
from imageskin.voice import Speech, write_speech  # noqa: E402

logger = logging.getLogger("side_by_side")

LINES: tuple[tuple[str, str], ...] = (
    ("goodbye", "Goodbye."),
    ("hello", "Hello! I'm glad you asked."),
    ("cat", "Once upon a time, a cat named Milo was afraid of water."),
)


def before_weights(
    shapes: list[ShapeTiming],
    samples: object,
    rate: int,
    n_frames: int,
    fps: float,
    smooth_s: float = 0.06,
    lead_s: float = 0.03,
) -> list[dict[str, float]]:
    """The mouth's weights per frame as before R128 (`visemes.frame_weights` on main before
    it): the sound timings as the voice engine gave them, the lips 30 ms ahead with the 60 ms
    blend reaching into the pause before a word, and each frame sampled at its middle."""
    step = 0.005
    n_steps = int(math.ceil(n_frames / fps / step)) + 1
    grid = {name: [0.0] * n_steps for name in SHAPES}
    k = 0
    for i in range(n_steps):
        t = i * step
        while k < len(shapes) and shapes[k].end <= t:
            k += 1
        shape = shapes[k].shape if k < len(shapes) and shapes[k].start <= t else "rest"
        grid[shape][i] = 1.0
    radius = max(1, int(3 * smooth_s / step))
    kernel = [math.exp(-0.5 * (j * step / smooth_s) ** 2) for j in range(-radius, radius + 1)]
    out: list[dict[str, float]] = []
    for f in range(n_frames):
        centre = round(((f + 0.5) / fps + lead_s) / step)
        weights: dict[str, float] = {}
        for name, row in grid.items():
            acc = sum(
                kv * row[min(n_steps - 1, max(0, centre + j - radius))]
                for j, kv in enumerate(kernel)
            )
            if acc > 1e-6:
                weights[name] = acc
        total = sum(weights.values())
        out.append({name: w / total for name, w in weights.items()})
    for s in shapes:
        if s.shape in CONTACT and n_frames:
            f = min(n_frames - 1, max(0, int(((s.start + s.end) / 2 - lead_s) * fps)))
            out[f] = {s.shape: 1.0}
    return out


def newest_library(home: Path) -> Path:
    """The face prepared last: the newest library in the app's photoreal folder."""
    folders = [p for p in (home / "photoreal").glob("*") if (p / "library.json").exists()]
    if not folders:
        raise SystemExit(
            f"No prepared face in {home / 'photoreal'}: prepare one, or pass --library"
        )
    return max(folders, key=lambda p: (p / "library.json").stat().st_mtime)


def face_box(crop_to_photo: object, size: tuple[int, int]) -> tuple[int, int, int, int]:
    """The face in the photo, as x, y, width and height: LivePortrait's crop of it, a square
    of CROP pixels, put onto the photo, kept inside it."""
    m = np.asarray(crop_to_photo, dtype=np.float64)
    corners = np.array([[0, 0, 1], [CROP, 0, 1], [0, CROP, 1], [CROP, CROP, 1]], np.float64)
    pts = corners @ m.T
    w, h = size
    x0, y0 = max(0, int(pts[:, 0].min())), max(0, int(pts[:, 1].min()))
    x1, y1 = min(w, int(pts[:, 0].max())), min(h, int(pts[:, 1].max()))
    return x0, y0, (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2


def label_args(left: str, right: str, box: tuple[int, int, int, int]) -> str:
    """ffmpeg's filter: the face in the two videos side by side, each named at the top."""
    x, y, w, h = box
    face = f"crop={w}:{h}:{x}:{y},scale=512:512"
    text = (
        "drawtext=text='{}':x=(w-text_w)/2:y=10:fontsize=26:fontcolor=white"
        ":box=1:boxcolor=black@0.6"
    )
    return (
        f"[0:v]{face},{text.format(left)}[l];[1:v]{face},{text.format(right)}[r];"
        "[l][r]hstack=inputs=2[v]"
    )


def join(
    before: Path,
    after: Path,
    wav: Path,
    out: Path,
    box: tuple[int, int, int, int],
    speed: float = 1.0,
) -> None:
    """Write the face in `before` and `after` side by side with the voice, at `speed` (0.5 is
    half)."""
    ffmpeg = find_ffmpeg()
    graph = label_args("Before", "After R128", box)
    audio = "[2:a]anull[a]"
    if speed != 1.0:
        graph += f";[v]setpts=PTS/{speed}[vs]"
        audio = f"[2:a]atempo={speed}[a]"
    video_out = "[vs]" if speed != 1.0 else "[v]"
    cmd = [
        ffmpeg, "-y", "-v", "error", "-i", str(before), "-i", str(after), "-i", str(wav),
        "-filter_complex", f"{graph};{audio}", "-map", video_out, "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out),
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)


def render_line(
    engine: object,
    lib: object,
    name: str,
    text: str,
    speak: Callable[[str], Speech],
    folder: Path,
    out: Path,
) -> dict[str, object]:
    """Speak one line, render it before and after R128, and write it side by side."""
    start = time.perf_counter()
    wav = folder / f"{name}.wav"
    write_speech(speak(text), wav, wav.with_suffix(".json"))
    before, after = folder / f"{name}-before.mp4", folder / f"{name}-after.mp4"
    with patch("imageskin.photoreal.mouth_weights", before_weights):
        engine.render(lib, wav, before)  # type: ignore[attr-defined]
    lead_before = engine.mouth_lead_ms  # type: ignore[attr-defined]
    engine.render(lib, wav, after)  # type: ignore[attr-defined]
    lead_after = engine.mouth_lead_ms  # type: ignore[attr-defined]
    box = face_box(lib.crop_to_photo, lib.photo.shape[1::-1])  # type: ignore[attr-defined]
    join(before, after, wav, out / f"{name}-side-by-side.mp4", box)
    join(before, after, wav, out / f"{name}-side-by-side-half-speed.mp4", box, speed=0.5)
    result = {"line": name, "lead_before_ms": lead_before, "lead_after_ms": lead_after}
    logger.info(
        "Side by side written",
        extra={**result, "duration_ms": round((time.perf_counter() - start) * 1000, 1)},
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    from imageskin.logging_setup import setup_logging
    from imageskin.photoreal import PhotorealEngine
    from imageskin.photoreal_library import load_library

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--voice", default="af_heart", help="a Kokoro voice (default af_heart)")
    p.add_argument("--lang", default="a", help="Kokoro's language code: a American, b British")
    p.add_argument("--clone", type=Path, help="a voice sample WAV: speak in the cloned voice")
    p.add_argument("--pocket", action="store_true", help="clone with Pocket TTS (R22f)")
    p.add_argument("--library", type=Path, help="a prepared face (default: the newest)")
    p.add_argument("-o", "--out", type=Path, default=Path("side-by-side"))
    args = p.parse_args(argv)
    setup_logging()
    start = time.perf_counter()
    folder = args.library or newest_library(default_home())
    photo = json.loads((folder / "library.json").read_text(encoding="utf-8")).get("photo")
    if args.clone:
        speak, voice = clone_speaker(args.clone, args.pocket), str(args.clone)
    else:
        speak, voice = kokoro_speaker(args.voice, args.lang), args.voice
    logger.info(
        "Side by side started", extra={"voice": voice, "library": str(folder), "photo": photo}
    )
    args.out.mkdir(parents=True, exist_ok=True)
    engine = PhotorealEngine(default_home())
    lib = load_library(folder)
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in LINES:
            try:
                results.append(render_line(engine, lib, name, text, speak, Path(tmp), args.out))
            except Exception:
                logger.exception("Could not write a line", extra={"line": name, "voice": voice})
    logger.info(
        "Side by side done",
        extra={
            "voice": voice,
            "lines": len(results),
            "output": str(args.out),
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    for r in results:
        before, after = r["lead_before_ms"], r["lead_after_ms"]
        print(f"{r['line']}: the mouth leads the voice by {before} ms before, {after} ms after")
    return 0 if len(results) == len(LINES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
