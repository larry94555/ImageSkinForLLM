from array import array
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from photoreal_fakes import (
    EYES,
    MOUTH,
    FakePortrait,
    landmarks,
    photo_file,
    short_loop,
    write_speech,
)

from imageskin import photoreal
from imageskin.liveportrait_edits import eye_track
from imageskin.photoreal import (
    Compositor,
    EyeMorph,
    PhotorealEngine,
    ShapeMorph,
    audio_seed,
    reach,
    read_shapes,
)
from imageskin.photoreal_library import build_library, load_library, mouth_mask
from imageskin.video import VideoError, read_pcm16
from imageskin.visemes import SHAPES

__all__ = ["short_loop"]  # a fixture, used by name


def test_mouth_morph_goes_from_one_shape_to_the_other() -> None:
    portrait = FakePortrait()
    shapes = {name: portrait.render({}, 0.3 if name == "AA" else None) for name in SHAPES}
    window = mouth_mask(landmarks())[1]
    morph = ShapeMorph(shapes, window)
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


def test_eye_morph_closes_the_eyes_part_way(tmp_path: Path, short_loop: object) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    lib = load_library(tmp_path / "lib")
    eyes = EyeMorph(lib)
    x0, y0, x1, y1 = lib.eye_window
    assert np.array_equal(eyes(1.0), lib.shapes["rest"][y0:y1, x0:x1])
    assert np.array_equal(eyes(0.4), lib.eyes[1][y0:y1, x0:x1])
    assert np.array_equal(eyes(0.0), lib.eyes[-1][y0:y1, x0:x1])
    assert np.array_equal(eyes(-0.1), eyes(0.0)) and np.array_equal(eyes(1.2), eyes(1.0))
    x, y = EYES[0]
    eye = (slice(y - y0 - 8, y - y0 + 9), slice(x - x0 - 10, x - x0 + 11))
    light = [float(eyes(level)[eye].mean()) for level in (1.0, 0.55, 0.0)]
    assert light[0] < light[1] < light[2]  # the dark eye goes as the lids close


def test_frame_blinks(tmp_path: Path, short_loop: object) -> None:
    build_library(tmp_path / "me.png", tmp_path / "lib", lambda _: FakePortrait())
    comp = Compositor(load_library(tmp_path / "lib"))
    opened = comp.frame({"rest": 1.0}, 3)
    shut = comp.frame({"rest": 1.0}, 3, eye_open=0.0)
    x, y = EYES[0]
    eye = (slice(16 + y // 4 - 1, 16 + y // 4 + 2), slice(36 + x // 4 - 2, 36 + x // 4 + 3))
    assert shut[eye].mean() > opened[eye].mean() + 20
    mouth = (slice(16 + 370 // 4 - 3, 16 + 370 // 4 + 3), slice(36 + 60, 36 + 68))
    assert np.array_equal(shut[mouth], opened[mouth])  # the blink leaves the mouth alone


def test_reach_covers_where_the_window_moves() -> None:
    still = np.eye(2, 3)
    shifted = np.array([[1.0, 0.0, 3.0], [0.0, 1.0, -2.0]])
    assert reach((10, 10, 20, 20), np.stack([still, shifted])) == (6, 6, 24, 24)
    assert reach((0, 500, 30, 512), np.stack([shifted])) == (0, 496, 34, 512)  # inside the crop


def test_render_blinks_on_the_eye_track(tmp_path: Path, short_loop: object) -> None:
    engine = PhotorealEngine(home=tmp_path / "home", make_portrait=lambda _: FakePortrait())
    lib = engine.prepare(photo_file(tmp_path))
    wav = tmp_path / "speech.wav"
    write_speech(wav)
    seen: list[float] = []
    real_frame = Compositor.frame

    def frame(self: Compositor, w: dict[str, float], i: int, eye_open: float = 1.0) -> object:
        seen.append(eye_open)
        return real_frame(self, w, i, eye_open)

    track = [1.0, 0.5, 0.0, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    with (
        patch.object(photoreal, "eye_track", return_value=track) as eye_track,
        patch.object(Compositor, "frame", frame),
    ):
        engine.render(lib, wav, tmp_path / "reply.mp4")
    assert seen == track
    assert eye_track.call_args.args[:2] == (10, 25)
    assert eye_track.call_args.kwargs["seed"] == audio_seed(read_pcm16(wav)[0])


def test_blinks_are_seeded_by_the_speech_not_its_length() -> None:
    a, b = array("h", [0, 1, 2, 3] * 1000), array("h", [0, 1, 2, 4] * 1000)
    assert audio_seed(a) == audio_seed(array("h", [0, 1, 2, 3] * 1000))
    assert audio_seed(a) != audio_seed(b)
    assert eye_track(250, 25.0, audio_seed(a)) != eye_track(250, 25.0, audio_seed(b))


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
