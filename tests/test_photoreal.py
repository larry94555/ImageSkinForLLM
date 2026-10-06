from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from photoreal_fakes import (
    MOUTH,
    FakePortrait,
    landmarks,
    photo_file,
    short_loop,
    write_speech,
)

from imageskin.photoreal import Compositor, MouthMorph, PhotorealEngine, read_shapes
from imageskin.photoreal_library import build_library, load_library, mouth_mask
from imageskin.video import VideoError
from imageskin.visemes import SHAPES

__all__ = ["short_loop"]  # a fixture, used by name


def test_mouth_morph_goes_from_one_shape_to_the_other() -> None:
    portrait = FakePortrait()
    shapes = {name: portrait.render({}, 0.3 if name == "AA" else None) for name in SHAPES}
    window = mouth_mask(landmarks())[1]
    morph = MouthMorph(shapes, window)
    x0, y0, x1, y1 = window
    assert np.array_equal(morph("rest", "AA", 0.0), shapes["rest"][y0:y1, x0:x1])
    assert np.array_equal(morph("rest", "AA", 1.0), shapes["AA"][y0:y1, x0:x1])
    centre = (
        slice(MOUTH[1] - y0 - 8, MOUTH[1] - y0 + 8),
        slice(MOUTH[0] - x0 - 20, MOUTH[0] - x0 + 20),
    )
    light = [float(morph("rest", "AA", t)[centre].mean()) for t in (0.0, 0.5, 1.0)]
    assert light[0] > light[1] > light[2]  # the mouth opens part way


def test_prepare_reuses_library_and_render_writes_video(tmp_path: Path, short_loop: object) -> None:
    portrait = FakePortrait()
    calls: list[Path] = []

    def make(photo: Path) -> FakePortrait:
        calls.append(photo)
        return portrait

    photo = photo_file(tmp_path)
    engine = PhotorealEngine(home=tmp_path / "home", make_portrait=make)
    lib = engine.prepare(photo)
    engine.prepare(photo)
    assert calls == [photo]  # the second prepare loads the finished library

    wav = tmp_path / "speech.wav"
    write_speech(wav)
    out = tmp_path / "reply.mp4"
    assert engine.render(lib, wav, out) == pytest.approx(0.4)
    video = cv2.VideoCapture(str(out))
    frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    size = (video.get(cv2.CAP_PROP_FRAME_WIDTH), video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video.release()
    assert frames == 10 and size == (200, 160)


def test_frame_shows_the_mouth_shape_in_the_photo(tmp_path: Path, short_loop: object) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    comp = Compositor(load_library(tmp_path / "lib"))
    closed = comp.frame({"rest": 1.0}, 0)
    opened = comp.frame({"AA": 1.0}, 0)
    assert closed.shape == (160, 200, 3)
    mouth = (slice(16 + 370 // 4 - 3, 16 + 370 // 4 + 3), slice(36 + 60, 36 + 68))
    assert opened[mouth].mean() < closed[mouth].mean() - 20
    assert np.array_equal(opened[:10], closed[:10])  # outside the face is the photo


def test_prepare_needs_ffmpeg(tmp_path: Path) -> None:
    engine = PhotorealEngine(home=tmp_path, make_portrait=lambda _: FakePortrait())
    with patch("imageskin.video.shutil.which", return_value=None):
        with pytest.raises(VideoError, match="ffmpeg not found"):
            engine.prepare(photo_file(tmp_path))


def test_read_shapes(tmp_path: Path) -> None:
    wav = tmp_path / "s.wav"
    write_speech(wav)
    assert read_shapes(wav.with_suffix(".json"))[1].shape == "AA"
    with pytest.raises(VideoError, match="could not read mouth shapes"):
        read_shapes(tmp_path / "missing.json")
