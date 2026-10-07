"""LivePortrait (MIT) on the CPU: download the models once, then render edits of one photo.

Only the photoreal engine's one-time setup uses this module; rendering a reply does not.
Face finding uses MediaPipe (Apache 2.0) instead of LivePortrait's InsightFace detector,
whose models are non-commercial. Needs the photoreal extra: pip install -e ".[photoreal]".
"""

import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from imageskin.download import MB, DownloadError, download
from imageskin.face_checks import FACE_MODEL_SHA256, FACE_MODEL_SIZE, FACE_MODEL_URL
from imageskin.liveportrait_edits import (
    BLINK_CLOSED,
    MP_TO_68,
    UPPER_LIP_KP,
    expression_delta,
)
from imageskin.video import VideoError

logger = logging.getLogger(__name__)

LP_REPO = "https://github.com/KwaiVGI/LivePortrait"
LP_COMMIT = "9b294b3d0536135442ea73cb01e6cb3ca7029dd3"  # main on 2026-06-02
HF_REPO = "KlingTeam/LivePortrait"  # formerly KwaiVGI; MIT license on the model card
HF_REVISION = "82a4fa6735ca58432b6ce39301b4b9ee066dea47"  # main on 2026-10-05
# Only the human base models and the stitching/retargeting model, as (path, bytes, sha256).
# The InsightFace and animal (X-Pose) files are skipped: their licenses are non-commercial.
HF_FILES = [
    (
        "liveportrait/base_models/appearance_feature_extractor.pth",
        3387959,
        "5279bb8654293dbdf327030b397f107237dd9212fb11dd75b83dfb635211ceb5",
    ),
    (
        "liveportrait/base_models/motion_extractor.pth",
        112545506,
        "251e6a94ad667a1d0c69526d292677165110ef7f0cf0f6d199f0e414e8aa0ca5",
    ),
    (
        "liveportrait/base_models/spade_generator.pth",
        221813590,
        "4780afc7909a9f84e24c01d73b31a555ef651521a1fe3b2429bd04534d992aee",
    ),
    (
        "liveportrait/base_models/warping_module.pth",
        182180086,
        "2f61a6f265fe344f14132364859a78bdbbc2068577170693da57fb96d636e282",
    ),
    (
        "liveportrait/retargeting_models/stitching_retargeting_module.pth",
        2393098,
        "3652d5a3f95099141a56986aaddec92fadf0a73c87a20fac9a2c07c32b28b611",
    ),
]
GIT_STALL_SECONDS = 60  # git gives up when the transfer stays under 1 KB/s this long
MAX_SIDE = 1280  # longest side of the video, in pixels
INSTALL_HINT = 'the photoreal engine is not installed; run: pip install -e ".[photoreal]"'

Image = NDArray[np.uint8]


def fetch_code(lp_dir: Path, retries: int = 5) -> None:
    """Get the pinned LivePortrait commit only (no history), with git's progress shown."""
    git = ["git", "-C", str(lp_dir)]
    if (lp_dir / ".git").exists():
        head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True)
        if head.stdout.strip() == LP_COMMIT:
            return
    else:
        lp_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run([*git, "init", "--quiet"], check=True)
    fetch = [*git, "-c", "http.lowSpeedLimit=1000", "-c", f"http.lowSpeedTime={GIT_STALL_SECONDS}"]
    fetch += ["fetch", "--depth", "1", "--progress", LP_REPO, LP_COMMIT]
    for attempt in range(1, retries + 2):
        logger.info("Fetching LivePortrait code, about 40 MB (try %d)", attempt)
        if subprocess.run(fetch).returncode == 0:
            break
        if attempt > retries:
            raise DownloadError(f"git fetch of {LP_REPO} failed {attempt} times")
        logger.warning("git fetch failed or stalled; retrying in %d s", 2**attempt)
        time.sleep(2**attempt)
    subprocess.run([*git, "checkout", "--quiet", "--force", "FETCH_HEAD"], check=True)


def ensure_models(lp_dir: Path) -> None:
    """Download LivePortrait's code and weights and MediaPipe's face model, once (~500 MB).

    Files already there are checked and skipped; an interrupted download resumes.
    """
    start = time.perf_counter()
    weights = lp_dir / "pretrained_weights"
    total = sum(size for _, size, _ in HF_FILES) + FACE_MODEL_SIZE
    logger.info("Checking photoreal models (about %.0f MB) in %s", total / MB, lp_dir)
    try:
        fetch_code(lp_dir)
        for path, size, sha in HF_FILES:
            url = f"https://huggingface.co/{HF_REPO}/resolve/{HF_REVISION}/{path}"
            download(url, weights / path, size, sha)
        download(
            FACE_MODEL_URL,
            weights / "face_landmarker.task",
            FACE_MODEL_SIZE,
            FACE_MODEL_SHA256,
        )
    except (DownloadError, OSError, subprocess.CalledProcessError) as e:
        raise VideoError(f"could not download the photoreal models: {e}") from e
    logger.info("Photoreal models ready in %.1f s", time.perf_counter() - start)


def load_photo_rgb(photo: Path) -> Image:
    """Read a photo as RGB, shrunk so the longest side is at most MAX_SIDE, with even sides."""
    data = np.fromfile(photo, dtype=np.uint8) if photo.is_file() else np.zeros(0, np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if bgr is None:
        raise VideoError(f"could not read {photo} as an image (use JPEG or PNG)")
    scale = min(1.0, MAX_SIDE / max(bgr.shape[:2]))
    if scale < 1.0:
        bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    bgr = bgr[: bgr.shape[0] // 2 * 2, : bgr.shape[1] // 2 * 2]  # even size for H.264
    return np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def find_landmarks(photo_rgb: Image, face_model: Path) -> NDArray[np.float32]:
    """MediaPipe's 478 face landmarks, in pixels."""
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(face_model)), num_faces=2
    )
    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=photo_rgb))
    if not result.face_landmarks:
        raise VideoError("no face found in the photo; use a front-facing photo of one person")
    if len(result.face_landmarks) > 1:
        raise VideoError("found more than one face; use a photo with exactly one face")
    h, w = photo_rgb.shape[:2]
    return np.array([[p.x * w, p.y * h] for p in result.face_landmarks[0]], np.float32)


class Portrait:
    """One photo prepared for LivePortrait: features are extracted once, then each frame is
    an edit of the face keypoints followed by LivePortrait's warp and decode (a few seconds
    per frame on a laptop CPU)."""

    def __init__(self, lp_dir: Path, photo: Path) -> None:
        try:
            import torch
        except ImportError as e:
            raise VideoError(INSTALL_HINT) from e
        self._torch = torch
        sys.path.insert(0, str(lp_dir))
        from src.config.crop_config import CropConfig
        from src.config.inference_config import InferenceConfig
        from src.live_portrait_wrapper import LivePortraitWrapper
        from src.utils.camera import get_rotation_matrix
        from src.utils.crop import crop_image

        self._rotation = get_rotation_matrix
        cfg = InferenceConfig(flag_force_cpu=True, flag_use_half_precision=False)
        crop_cfg = CropConfig(flag_force_cpu=True)
        self.lp: Any = LivePortraitWrapper(cfg)
        self.photo = load_photo_rgb(photo)

        points = find_landmarks(self.photo, lp_dir / "pretrained_weights" / "face_landmarker.task")
        # Inner-lip gap over inner mouth width (0 when the lips touch).
        self.lip_ratio = float(
            np.linalg.norm(points[13] - points[14]) / np.linalg.norm(points[78] - points[308])
        )
        face68 = points[list(MP_TO_68)]
        crop = crop_image(
            self.photo,
            face68,
            dsize=crop_cfg.dsize,
            scale=crop_cfg.scale,
            vx_ratio=crop_cfg.vx_ratio,
            vy_ratio=crop_cfg.vy_ratio,
            flag_do_rot=crop_cfg.flag_do_rot,
        )
        self.crop_to_photo: NDArray[np.float64] = np.asarray(crop["M_c2o"][:2], np.float64)
        self.crop_landmarks: NDArray[np.float32] = cv2.transform(
            face68[None], np.asarray(crop["M_o2c"][:2], np.float64)
        )[0]
        self.paste_template: Image = np.asarray(cfg.mask_crop[..., 0], np.uint8)

        source = self.lp.prepare_source(
            cv2.resize(crop["img_crop"], (256, 256), interpolation=cv2.INTER_AREA)
        )
        self.info = self.lp.get_kp_info(source)
        self.features = self.lp.extract_feature_3d(source)
        self.x_s = self.lp.transform_keypoint(self.info)
        self.t = self.info["t"].clone()
        self.t[..., 2] = 0

    def render(
        self,
        controls: dict[str, float],
        ratio: float | None = None,
        upper: float = 1.0,
        pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
        eye_open: float = 1.0,
    ) -> Image:
        """One 512x512 RGB face crop.

        `controls` and `ratio` shape the mouth (see liveportrait_edits); `upper` scales how
        far the upper lip moves; `pose` turns the head by (pitch, yaw, roll) degrees and
        `eye_open` closes the eyes (0 closed, 1 as in the photo).
        """
        torch = self._torch
        with torch.no_grad():
            info = self.info
            if eye_open < 1.0:
                controls = {**controls, "blink": BLINK_CLOSED * (1.0 - eye_open)}
            rot = self._rotation(
                info["pitch"] + pose[0], info["yaw"] + pose[1], info["roll"] + pose[2]
            )
            x_rest = info["scale"] * (info["kp"] @ rot + info["exp"]) + self.t
            delta = torch.tensor(expression_delta(controls)).view(1, -1, 3)
            x_d = x_rest + info["scale"] * delta
            if ratio is not None:
                lip = torch.tensor([[self.lip_ratio, ratio]], dtype=torch.float32)
                x_d = x_d + self.lp.retarget_lip(self.x_s, lip)
            motion = x_d - x_rest
            motion[:, UPPER_LIP_KP] *= upper
            x_d = self.lp.stitching(self.x_s, x_rest + motion)
            out = self.lp.warp_decode(self.features, self.x_s, x_d)
            return np.asarray(self.lp.parse_output(out["out"])[0], np.uint8)
