"""Download what the LivePortrait CPU test needs, once (about 500 MB).

- LivePortrait code (MIT) from GitHub at a pinned commit, via git.
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
import urllib.request
from pathlib import Path

log = logging.getLogger("photoreal.setup")
HERE = Path(__file__).resolve().parent

LP_REPO = "https://github.com/KwaiVGI/LivePortrait"
LP_COMMIT = "9b294b3d0536135442ea73cb01e6cb3ca7029dd3"  # main on 2026-06-02
HF_REPO = "KlingTeam/LivePortrait"  # formerly KwaiVGI; MIT license on the model card
HF_PATTERNS = [
    "liveportrait/base_models/*",
    "liveportrait/retargeting_models/*",
]
FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lp-dir", type=Path, default=HERE / "LivePortrait")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lp_dir: Path = args.lp_dir

    start = time.perf_counter()
    if not (lp_dir / ".git").exists():
        log.info("Cloning LivePortrait code into %s", lp_dir)
        subprocess.run(["git", "clone", "--quiet", LP_REPO, str(lp_dir)], check=True)
    subprocess.run(["git", "-C", str(lp_dir), "checkout", "--quiet", LP_COMMIT], check=True)

    from huggingface_hub import snapshot_download

    weights = lp_dir / "pretrained_weights"
    log.info("Downloading LivePortrait weights from huggingface.co/%s", HF_REPO)
    try:
        snapshot_download(HF_REPO, allow_patterns=HF_PATTERNS, local_dir=weights)
    except Exception:
        log.exception("Weights download failed; check access to huggingface.co")
        return 1

    face_model = weights / "face_landmarker.task"
    if not face_model.exists():
        log.info("Downloading MediaPipe face model")
        urllib.request.urlretrieve(FACE_MODEL_URL, face_model)

    log.info("Setup done in %.1f s; files are in %s", time.perf_counter() - start, lp_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
