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
    key_frames,
    library_key,
    load_library,
    morph,
    mouth_mask,
    optical_flow,
    prepare_library,
    to_gray,
    write_idle_preview,
)
from imageskin.video import VideoError
from imageskin.visemes import SHAPES

__all__ = ["short_loop"]  # a fixture, used by name


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
    first = FakePortrait(fail_after=len(SHAPES) + 2)
    with pytest.raises(KeyboardInterrupt):
        build_library(tmp_path / "me.png", folder, lambda _: first)
    assert sorted(p.name for p in (folder / "loop").glob("*.npy")) == ["0000.npy", "0004.npy"]
    assert not (folder / "library.json").exists()

    second = FakePortrait()
    steps: list[tuple[str, int, int]] = []
    build_library(tmp_path / "me.png", folder, lambda _: second, lambda *s: steps.append(s))
    assert second.renders == 1  # shapes and the first frames are kept; only frame 8 is left
    # Progress starts from the frames already there and ends with every step complete.
    assert steps[:3] == [("models", 0, 1), ("models", 1, 1), ("shapes", 10, 10)]
    assert ("loop", 2, 3) in steps and ("loop", 3, 3) in steps  # frames 0, 4 and 8
    assert steps[-1] == ("align", 1, 1)
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


def test_key_frames_are_every_fourth_and_each_blink() -> None:
    keys = key_frames(200)  # 8 s at 25 fps, blinks at 2.0 s and 5.6 s
    assert len(keys) == 60
    assert keys[:4] == [0, 4, 8, 12]
    assert set(range(48, 55)) <= set(keys)  # the first blink, frames 49 to 53, and either side
    assert 46 not in keys and 55 not in keys


def test_morph_follows_the_motion() -> None:
    a = texture()
    b = np.roll(a, 8, axis=1)  # the face moved 8 px to the right
    there, back = optical_flow(to_gray(a), to_gray(b)), optical_flow(to_gray(b), to_gray(a))
    half = morph(a, b, there, back, 0.5)
    truth = np.roll(a, 4, axis=1)
    inner = (slice(64, -64), slice(64, -64))
    assert np.abs(half[inner].astype(int) - truth[inner].astype(int)).mean() < 6
    cross_fade = (a.astype(int) + b.astype(int)) // 2
    assert np.abs(cross_fade[inner] - truth[inner].astype(int)).mean() > 12
    assert morph(a, b, there, back, 0.0) is a and morph(a, b, there, back, 1.0) is b
