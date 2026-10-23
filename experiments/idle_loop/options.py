"""R96e: time the idle loop's options and compare them with fully rendered frames.

Renders idle-loop frames with LivePortrait one by one (the reference): the first 49 of the
motion before R96e, and the first half (0 to 100) of the mirrored motion R96e uses, whose second
half is the first played backwards. Then fills in the frames between every 4th, 8th or 12th
rendered frame along the optical flow, as `fill_loop` does, and reports each option's frames
rendered for the whole loop and its PSNR against the fully rendered frames.

    python experiments/idle_loop/options.py photo.png out_dir

The rendered frames are kept in out_dir, so a second run only compares.
"""

import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from imageskin.liveportrait_edits import LOOP_SECONDS, idle_motion
from imageskin.photoreal_library import (
    liveportrait_factory,
    morph,
    optical_flow,
    pixel_grid,
    to_gray,
)
from imageskin.video import FPS

Frames = dict[int, np.ndarray]


def motion_before(frame: int, n_frames: int) -> tuple[float, float, float]:
    """The idle loop's motion before R96e."""
    phase = 2 * math.pi * frame / n_frames
    pitch = 0.8 * math.sin(2 * phase + 0.5)
    yaw = 1.5 * math.sin(phase) + 0.5 * math.sin(3 * phase + 1.0)
    roll = 0.6 * math.sin(phase + 2.0)
    return pitch, yaw, roll


def fill(frames: Frames, keys: list[int]) -> Frames:
    """The frames between each pair of keys, morphed along the optical flow."""
    out: Frames = {}
    grid = pixel_grid(frames[keys[0]])
    for a, b in zip(keys, keys[1:], strict=False):
        there = optical_flow(to_gray(frames[a]), to_gray(frames[b]))
        back = optical_flow(to_gray(frames[b]), to_gray(frames[a]))
        for i in range(a + 1, b):
            out[i] = morph(frames[a], frames[b], there, back, (i - a) / (b - a), grid)
    return out


def render(out: Path, name: str, motion, last: int, n: int, portrait) -> tuple[Frames, float]:
    cache = out / f"{name}.npz"
    if cache.exists():
        data = np.load(cache)
        return {int(k): data[k] for k in data.files}, json.loads((out / f"{name}.json").read_text())
    frames: Frames = {}
    start = time.perf_counter()
    for i in range(last + 1):
        frames[i] = portrait.render({}, None, 1.0, motion(i, n))
        print(name, i, flush=True)
    per = (time.perf_counter() - start) / (last + 1)
    np.savez(cache, **{str(k): v for k, v in frames.items()})
    (out / f"{name}.json").write_text(json.dumps(per))
    return frames, per


def main() -> None:
    photo, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    n = round(LOOP_SECONDS * FPS)
    mid = n // 2
    portrait = liveportrait_factory(Path.home() / ".imageskin")(photo)
    before, s_before = render(out, "before", motion_before, 48, n, portrait)
    mirrored, s_mirrored = render(out, "mirrored", idle_motion, mid, n, portrait)
    rows = []
    for every in (4, 8, 12):
        # Before R96e every `every`-th frame of the whole loop was rendered; judged on 0 to 48.
        keys = list(range(0, 48 // every * every + 1, every))
        made = fill(before, keys)
        rows.append(("before", every, len(range(0, n, every)), made, before))
        keys = sorted(set(range(0, mid, every)) | {mid})
        made = fill(mirrored, keys)
        rows.append(("mirrored", every, len(keys), made, mirrored))
        if every == 8:  # the loop R96e makes, for watching
            half = [mirrored[i] if i in keys else made[i] for i in range(mid + 1)]
            np.save(out / "mirrored_every8.npy", np.stack(half + half[-2:0:-1]))
    table = []
    for motion, every, renders, made, ref in rows:
        scores = [float(cv2.PSNR(made[i], ref[i])) for i in made]
        table.append(
            {
                "motion": motion,
                "every": every,
                "rendered": renders,
                "min_psnr_db": round(min(scores), 1),
                "mean_psnr_db": round(float(np.mean(scores)), 1),
            }
        )
        print(table[-1], flush=True)
    results = {
        "photo": str(photo),
        "loop_frames": n,
        "s_per_render": round((s_before + s_mirrored) / 2, 2),
        "options": table,
    }
    (out / "results.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
