import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from imageskin import liveportrait
from imageskin.download import DownloadError
from imageskin.liveportrait import (
    HF_FILES,
    LP_COMMIT,
    MAX_SIDE,
    Portrait,
    ensure_models,
    fetch_code,
    load_photo_rgb,
)
from imageskin.video import VideoError


def test_load_photo_rgb_shrinks_to_even_sides_in_rgb(tmp_path: Path) -> None:
    bgr = np.zeros((1501, 2001, 3), np.uint8)
    bgr[..., 0] = 255  # blue in OpenCV's BGR order
    cv2.imwrite(str(tmp_path / "big.png"), bgr)
    rgb = load_photo_rgb(tmp_path / "big.png")
    assert max(rgb.shape[:2]) <= MAX_SIDE
    assert rgb.shape[0] % 2 == 0 and rgb.shape[1] % 2 == 0
    assert tuple(rgb[0, 0]) == (0, 0, 255)


def test_load_photo_rgb_rejects_missing_or_bad_files(tmp_path: Path) -> None:
    with pytest.raises(VideoError, match="could not read"):
        load_photo_rgb(tmp_path / "missing.jpg")
    (tmp_path / "bad.jpg").write_bytes(b"not an image")
    with pytest.raises(VideoError, match="could not read"):
        load_photo_rgb(tmp_path / "bad.jpg")


def test_ensure_models_fetches_code_and_every_weights_file(tmp_path: Path) -> None:
    with (
        patch.object(liveportrait, "fetch_code") as fetch,
        patch.object(liveportrait, "download") as download,
    ):
        ensure_models(tmp_path)
    fetch.assert_called_once_with(tmp_path)
    targets = [call.args[1] for call in download.call_args_list]
    assert len(targets) == len(HF_FILES) + 1
    assert targets[-1] == tmp_path / "pretrained_weights" / "face_landmarker.task"
    assert all("insightface" not in str(t) for t in targets)  # non-commercial, never fetched


def test_ensure_models_reports_download_failure(tmp_path: Path) -> None:
    with (
        patch.object(liveportrait, "fetch_code"),
        patch.object(liveportrait, "download", side_effect=DownloadError("stalled")),
    ):
        with pytest.raises(VideoError, match="could not download the photoreal models: stalled"):
            ensure_models(tmp_path)


def test_fetch_code_skips_when_already_at_the_pinned_commit(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    done = subprocess.CompletedProcess([], 0, stdout=LP_COMMIT + "\n")
    with patch("imageskin.liveportrait.subprocess.run", return_value=done) as run:
        fetch_code(tmp_path)
    assert run.call_count == 1  # only the rev-parse check


def test_portrait_without_torch_explains_install(tmp_path: Path) -> None:
    with patch.dict(sys.modules, {"torch": None}):
        with pytest.raises(VideoError, match="photoreal"):
            Portrait(tmp_path, tmp_path / "me.jpg")
