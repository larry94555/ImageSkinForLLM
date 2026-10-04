"""LivePortrait on the CPU: speed test and photoreal samples from one photo.

A test for the pre-rendered plan, not part of the app:
  setup (slow, once per photo): render base-loop frames x mouth shapes with LivePortrait.
  per reply (fast): pick cached frames from mouth-shape timings, cross-fade, paste, encode.

Face finding uses MediaPipe (Apache 2.0) instead of LivePortrait's InsightFace detector,
whose models are non-commercial. Run setup_liveportrait.py first.
"""

import argparse
import json
import logging
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from face_points import MOODS, MP_TO_68, VISEMES, expression_delta, loop_motion, viseme_frames

log = logging.getLogger("photoreal")
HERE = Path(__file__).resolve().parent

# Mouth shapes for "Hello, how are you today?" at a natural pace (hand-timed).
DEMO_SEGMENTS = [
    ("EH", 0.00, 0.12), ("rest", 0.12, 0.18), ("OH", 0.18, 0.42), ("rest", 0.42, 0.60),
    ("AA", 0.60, 0.80), ("OO", 0.80, 0.95), ("AA", 0.95, 1.15), ("EE", 1.15, 1.30),
    ("OO", 1.30, 1.55), ("rest", 1.55, 1.65), ("EH", 1.65, 1.80), ("OO", 1.80, 1.95),
    ("EH", 1.95, 2.15), ("rest", 2.15, 2.50),
]  # fmt: skip


def find_face_68(img_rgb: np.ndarray, model: Path) -> np.ndarray:
    """68 face points (pixels) from MediaPipe Face Landmarker."""
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model)), num_faces=1
    )
    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb))
    if not result.face_landmarks:
        raise SystemExit("No face found in the photo. Use a clear, front-facing photo.")
    h, w = img_rgb.shape[:2]
    points = np.array([[p.x * w, p.y * h] for p in result.face_landmarks[0]], np.float32)
    return points[list(MP_TO_68)]


class Portrait:
    """One photo prepared for LivePortrait: features are extracted once, then each frame
    is a cheap-ish edit of the keypoints followed by warp + decode."""

    def __init__(self, lp_dir: Path, photo: Path, face_model: Path) -> None:
        sys.path.insert(0, str(lp_dir))
        from src.config.crop_config import CropConfig
        from src.config.inference_config import InferenceConfig
        from src.live_portrait_wrapper import LivePortraitWrapper
        from src.utils.camera import get_rotation_matrix
        from src.utils.crop import crop_image, paste_back, prepare_paste_back
        from src.utils.human_landmark_runner import LandmarkRunner

        self._rotation = get_rotation_matrix
        self._paste_back = paste_back
        cfg = InferenceConfig(flag_force_cpu=True, flag_use_half_precision=False)
        crop_cfg = CropConfig(flag_force_cpu=True)

        start = time.perf_counter()
        self.lp = LivePortraitWrapper(cfg)
        bgr = cv2.imread(str(photo))
        if bgr is None:
            raise SystemExit(f"Cannot read photo: {photo}")
        scale = min(1.0, 1280 / max(bgr.shape[:2]))
        bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        bgr = bgr[: bgr.shape[0] // 2 * 2, : bgr.shape[1] // 2 * 2]  # even size for H.264
        self.photo = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        face68 = find_face_68(self.photo, face_model)
        crop = crop_image(
            self.photo,
            face68,
            dsize=crop_cfg.dsize,
            scale=crop_cfg.scale,
            vx_ratio=crop_cfg.vx_ratio,
            vy_ratio=crop_cfg.vy_ratio,
            flag_do_rot=crop_cfg.flag_do_rot,
        )
        runner = LandmarkRunner(ckpt_path=crop_cfg.landmark_ckpt_path, onnx_provider="cpu")
        self.lmk203 = runner.run(self.photo, face68)
        self.crop_to_photo = crop["M_c2o"]
        h, w = self.photo.shape[:2]
        self.mask = prepare_paste_back(cfg.mask_crop, self.crop_to_photo, dsize=(w, h))

        source = self.lp.prepare_source(
            cv2.resize(crop["img_crop"], (256, 256), interpolation=cv2.INTER_AREA)
        )
        self.info = self.lp.get_kp_info(source)
        self.features = self.lp.extract_feature_3d(source)
        self.x_s = self.lp.transform_keypoint(self.info)
        self.t = self.info["t"].clone()
        self.t[..., 2] = 0
        from src.utils.retargeting_utils import calc_eye_close_ratio

        self.eye_ratio = float(calc_eye_close_ratio(self.lmk203[None]).mean())
        self.prepare_s = time.perf_counter() - start
        log.info("Portrait ready from %s in %.2f s", photo, self.prepare_s)

    @torch.no_grad()
    def render(
        self,
        controls: dict[str, float],
        pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
        eye_open: float = 1.0,
    ) -> np.ndarray:
        """One 512x512 RGB face crop with the given expression, head pose and eye openness."""
        info = self.info
        delta = info["exp"] + torch.tensor(expression_delta(controls)).view(1, -1, 3)
        rot = self._rotation(info["pitch"] + pose[0], info["yaw"] + pose[1], info["roll"] + pose[2])
        x_d = info["scale"] * (info["kp"] @ rot + delta) + self.t
        if eye_open < 1.0:
            ratio = self.lp.calc_combined_eye_ratio([[self.eye_ratio * eye_open]], self.lmk203)
            x_d = x_d + self.lp.retarget_eye(self.x_s, ratio)
        x_d = self.lp.stitching(self.x_s, x_d)
        out = self.lp.warp_decode(self.features, self.x_s, x_d)
        return self.lp.parse_output(out["out"])[0]

    def paste(self, face: np.ndarray) -> np.ndarray:
        """Put a face crop back into the full photo."""
        return self._paste_back(face, self.crop_to_photo, self.photo, self.mask)  # type: ignore[no-any-return]


def write_mp4(frames: list[np.ndarray], fps: float, path: Path) -> None:
    h, w = frames[0].shape[:2]
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", str(path),
    ]  # fmt: skip
    proc = subprocess.run(cmd, input=b"".join(f.tobytes() for f in frames), check=False)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg failed writing {path} (exit {proc.returncode})")


def contact_sheet(faces: dict[str, np.ndarray], path: Path) -> None:
    tiles = []
    for name, face in faces.items():
        tile = cv2.cvtColor(cv2.resize(face, (256, 256)), cv2.COLOR_RGB2BGR)
        cv2.putText(tile, name, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        tiles.append(tile)
    while len(tiles) % 4:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i : i + 4]) for i in range(0, len(tiles), 4)]
    cv2.imwrite(str(path), np.vstack(rows))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--lp-dir", type=Path, default=HERE / "LivePortrait")
    parser.add_argument("--out", type=Path, default=Path("photoreal_out"))
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument("--loop-seconds", type=float, default=2.0)
    parser.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    torch.set_num_threads(args.threads)
    args.out.mkdir(parents=True, exist_ok=True)
    face_model = args.lp_dir / "pretrained_weights" / "face_landmarker.task"
    portrait = Portrait(args.lp_dir, args.photo, face_model)
    timings: dict[str, Any] = {
        "cpu": platform.processor() or platform.machine(),
        "threads": args.threads,
        "torch": torch.__version__,
        "prepare_photo_s": round(portrait.prepare_s, 2),
    }

    # 1. Mouth shapes on the still head.
    start = time.perf_counter()
    shapes = {name: portrait.render(controls) for name, controls in VISEMES.items()}
    per_frame = (time.perf_counter() - start) / len(shapes)
    timings["seconds_per_frame"] = round(per_frame, 3)
    contact_sheet(shapes, args.out / "mouth_shapes.png")
    log.info("Mouth shapes rendered: %.3f s per frame", per_frame)
    print(f"Seconds per frame on this CPU: {per_frame:.2f}", flush=True)

    # 2. Setup step: each mood's base loop rendered once per mouth shape.
    n_loop = round(args.loop_seconds * args.fps)
    cache: dict[str, dict[str, list[np.ndarray]]] = {}
    start = time.perf_counter()
    for mood, mood_controls in MOODS.items():
        cache[mood] = {}
        for shape, shape_controls in VISEMES.items():
            controls = {**mood_controls}
            for key, value in shape_controls.items():
                controls[key] = controls.get(key, 0.0) + value
            frames = []
            for i in range(n_loop):
                pitch, yaw, roll, eye_open = loop_motion(i, n_loop, args.fps)
                frames.append(portrait.render(controls, (pitch, yaw, roll), eye_open))
            cache[mood][shape] = frames
        loop = [portrait.paste(f) for f in cache[mood]["rest"]]
        write_mp4(loop, args.fps, args.out / f"loop_{mood}.mp4")
        log.info("Mood %s rendered: %d frames", mood, n_loop * len(VISEMES))
    setup_s = time.perf_counter() - start
    timings["setup_frames"] = n_loop * len(VISEMES) * len(MOODS)
    timings["setup_s"] = round(setup_s, 1)

    # 3. Per reply: only array blending, pasting and encoding; no model runs.
    for mood in MOODS:
        start = time.perf_counter()
        frames = []
        for i, (a, b, weight) in enumerate(viseme_frames(DEMO_SEGMENTS, args.fps)):
            face_a = cache[mood][a][i % n_loop]
            face_b = cache[mood][b][i % n_loop]
            face = cv2.addWeighted(face_a, 1.0 - weight, face_b, weight, 0.0)
            frames.append(portrait.paste(face))
        assemble_s = time.perf_counter() - start
        write_mp4(frames, args.fps, args.out / f"reply_{mood}.mp4")
        total_s = time.perf_counter() - start
        clip_s = len(frames) / args.fps
        timings[f"reply_{mood}"] = {
            "clip_s": round(clip_s, 2),
            "assemble_s": round(assemble_s, 3),
            "assemble_and_encode_s": round(total_s, 3),
        }
        log.info("Reply clip (%s) built in %.3f s", mood, total_s)

    (args.out / "timings.json").write_text(json.dumps(timings, indent=2))
    print(json.dumps(timings, indent=2))
    print(f"Wrote mouth_shapes.png, loop_*.mp4, reply_*.mp4 and timings.json to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
