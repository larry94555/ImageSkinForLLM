from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from photoreal_fakes import MOUTH, FakePortrait, landmarks, photo_file, short_loop, texture

from imageskin.photoreal_library import (
    CROP,
    Paster,
    align_loop,
    build_library,
    default_home,
    library_key,
    load_library,
    mouth_mask,
    prepare_library,
    write_idle_preview,
)
from imageskin.video import VideoError
from imageskin.visemes import SHAPES

__all__ = ["short_loop"]  # a fixture, used by name


def test_default_home_follows_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGESKIN_HOME", "/data/skin")
    assert default_home() == Path("/data/skin")
    monkeypatch.delenv("IMAGESKIN_HOME")
    assert default_home() == Path.home() / ".imageskin"


def test_library_key_depends_on_the_photo(tmp_path: Path) -> None:
    a, b = tmp_path / "a.jpg", tmp_path / "b.jpg"
    a.write_bytes(b"one")
    b.write_bytes(b"two")
    assert library_key(a) != library_key(b)
    assert library_key(a) == library_key(a)


def test_mouth_mask_covers_mouth_and_jaw_only() -> None:
    mask, (x0, y0, x1, y1) = mouth_mask(landmarks())
    assert mask[MOUTH[1], MOUTH[0]] == pytest.approx(1.0, abs=0.01)
    assert mask[431, 256] > 0.3  # chin
    assert mask[100, 256] == 0.0  # eyes and forehead stay as the idle loop has them
    assert x0 < 220 and x1 > 292 and y0 > 300 and y1 < CROP


def test_align_loop_finds_the_head_shift() -> None:
    rest = texture()
    moved = np.roll(np.roll(rest, 3, axis=1), -2, axis=0)
    mask, window = mouth_mask(landmarks())
    matrices = align_loop(rest, [rest, moved], mask, window)
    assert matrices[0] == pytest.approx(np.eye(2, 3), abs=0.05)
    assert matrices[1][:, 2] == pytest.approx([3, -2], abs=0.3)


def test_build_load_and_resume(tmp_path: Path, short_loop: object) -> None:
    folder = tmp_path / "lib"
    first = FakePortrait(fail_after=len(SHAPES) + 4)
    with pytest.raises(KeyboardInterrupt):
        build_library(tmp_path / "me.png", folder, lambda _: first)
    assert len(list((folder / "loop").glob("*.npy"))) == 4
    assert not (folder / "library.json").exists()

    second = FakePortrait()
    build_library(tmp_path / "me.png", folder, lambda _: second)
    assert second.renders == 10 - 4  # shapes and the first frames are kept
    lib = load_library(folder)
    assert len(lib.loop) == 10 and set(lib.shapes) == set(SHAPES)
    assert lib.align.shape == (10, 2, 3)
    assert not list(folder.rglob("*.tmp.npy"))


def test_prepare_library_builds_once_and_writes_preview(tmp_path: Path, short_loop: object) -> None:
    calls: list[Path] = []

    def make(photo: Path) -> FakePortrait:
        calls.append(photo)
        return FakePortrait()

    photo = photo_file(tmp_path)
    lib = prepare_library(photo, tmp_path / "home", make)
    assert lib.folder.parent == tmp_path / "home" / "photoreal"
    prepare_library(photo, tmp_path / "home", make)
    assert calls == [photo]  # the second call loads the finished library

    out = tmp_path / "idle.mp4"
    assert write_idle_preview(lib, out) == pytest.approx(0.4)
    video = cv2.VideoCapture(str(out))
    frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    size = (video.get(cv2.CAP_PROP_FRAME_WIDTH), video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video.release()
    assert frames == 10 and size == (200, 160)
    with pytest.raises(VideoError, match="file not found"):
        prepare_library(tmp_path / "missing.jpg", tmp_path / "home", make)


def test_paster_puts_the_face_into_the_photo(tmp_path: Path, short_loop: object) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    lib = load_library(tmp_path / "lib")
    paste = Paster(lib)
    frame = paste(np.zeros((CROP, CROP, 3), np.uint8))
    assert frame.shape == (160, 200, 3)
    assert frame[16 + 64, 36 + 64].max() == 0  # middle of the face: all crop
    assert np.array_equal(frame[:10], lib.photo[:10])  # outside the face: all photo
    lib = load_library(tmp_path / "lib")
    lib.paste_template[:] = 0
    with pytest.raises(VideoError, match="outside the photo"):
        Paster(lib)


def test_new_mouth_settings_rerender_only_the_shapes(tmp_path: Path, short_loop: object) -> None:
    photo = photo_file(tmp_path)
    prepare_library(photo, tmp_path, lambda _: FakePortrait())
    again = FakePortrait()
    with patch("imageskin.photoreal_library.mouth_key", return_value="new"):
        prepare_library(photo, tmp_path, lambda _: again)
        assert again.renders == len(SHAPES)  # the idle loop is kept
        third = FakePortrait()
        prepare_library(photo, tmp_path, lambda _: third)
    assert third.renders == 0
