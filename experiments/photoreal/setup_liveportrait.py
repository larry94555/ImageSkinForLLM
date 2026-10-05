"""Download what the LivePortrait CPU test needs, once (about 500 MB).

- LivePortrait code (MIT) from GitHub at a pinned commit, via a shallow git fetch.
- LivePortrait human weights from Hugging Face (KlingTeam/LivePortrait, MIT). Only the base
  models and the stitching/retargeting model are fetched; the
  InsightFace and animal (X-Pose) files are skipped because their licenses are
  non-commercial.
- MediaPipe Face Landmarker model (Apache 2.0) from storage.googleapis.com.
"""

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

from download import MB, DownloadError, download

log = logging.getLogger("photoreal.setup")
HERE = Path(__file__).resolve().parent

LP_REPO = "https://github.com/KwaiVGI/LivePortrait"
LP_COMMIT = "9b294b3d0536135442ea73cb01e6cb3ca7029dd3"  # main on 2026-06-02
HF_REPO = "KlingTeam/LivePortrait"  # formerly KwaiVGI; MIT license on the model card
HF_REVISION = "82a4fa6735ca58432b6ce39301b4b9ee066dea47"  # main on 2026-10-05
# Only the human base models and the stitching/retargeting model: (path, bytes, sha256).
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
FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
FACE_MODEL_SIZE = 3758596
FACE_MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
# git gives up when the transfer stays under 1 KB/s for this many seconds.
GIT_STALL_SECONDS = 60


def fetch_code(lp_dir: Path, retries: int) -> None:
    """Get the pinned LivePortrait commit only (no history), with git's progress shown."""
    git = ["git", "-C", str(lp_dir)]
    if (lp_dir / ".git").exists():
        head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True)
        if head.stdout.strip() == LP_COMMIT:
            log.info("LivePortrait code already at %s, skipping", LP_COMMIT[:12])
            return
    else:
        lp_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run([*git, "init", "--quiet"], check=True)
    fetch = [
        *git,
        "-c",
        "http.lowSpeedLimit=1000",
        "-c",
        f"http.lowSpeedTime={GIT_STALL_SECONDS}",
        "fetch",
        "--depth",
        "1",
        "--progress",
        LP_REPO,
        LP_COMMIT,
    ]
    for attempt in range(1, retries + 2):
        log.info("Fetching LivePortrait code (about 40 MB) into %s, try %d", lp_dir, attempt)
        if subprocess.run(fetch).returncode == 0:
            break
        if attempt > retries:
            raise DownloadError(f"git fetch of {LP_REPO} failed {attempt} times")
        log.warning("git fetch failed or stalled; retrying in %d s", 2**attempt)
        time.sleep(2**attempt)
    subprocess.run([*git, "checkout", "--quiet", "--force", "FETCH_HEAD"], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lp-dir", type=Path, default=HERE / "LivePortrait")
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="seconds a stalled connection may hang before a retry (30)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=5,
        help="retries in a row without progress before giving up (5)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lp_dir: Path = args.lp_dir

    start = time.perf_counter()
    weights = lp_dir / "pretrained_weights"
    total = sum(size for _, size, _ in HF_FILES) + FACE_MODEL_SIZE
    log.info(
        "Setup needs about %.0f MB of weights plus the code; progress every few seconds", total / MB
    )
    try:
        fetch_code(lp_dir, args.retries)
        for i, (path, size, sha) in enumerate(HF_FILES, 1):
            log.info("Weights file %d of %d: %s", i, len(HF_FILES), path)
            url = f"https://huggingface.co/{HF_REPO}/resolve/{HF_REVISION}/{path}"
            download(url, weights / path, size, sha, timeout=args.timeout, retries=args.retries)
        download(
            FACE_MODEL_URL,
            weights / "face_landmarker.task",
            FACE_MODEL_SIZE,
            FACE_MODEL_SHA256,
            timeout=args.timeout,
            retries=args.retries,
        )
    except DownloadError as exc:
        log.error("Setup stopped: %s", exc)
        return 1

    log.info("Setup done in %.1f s; files are in %s", time.perf_counter() - start, lp_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
