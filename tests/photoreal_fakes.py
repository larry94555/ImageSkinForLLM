"""A stand-in for LivePortrait, shared by the photoreal tests."""

import json
import wave
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from imageskin import photoreal_library
from imageskin.photoreal_library import CROP

MOUTH = (256, 370)
EYES = ((228, 230), (284, 230))


def landmarks() -> NDArray[np.float32]:
    points = np.full((68, 2), 256.0, np.float32)
    points[48:68, 0] = np.linspace(220, 292, 20)  # mouth 72 px wide at y 370
    points[48:68, 1] = MOUTH[1]
    points[33] = (256, 327)  # nose
    points[8] = (256, 431)  # chin
    points[17:27, 0] = np.linspace(200, 312, 10)  # brows at y 205
    points[17:27, 1] = 205
    for eye, (x, y) in zip((points[36:42], points[42:48]), EYES, strict=True):
        eye[:, 0] = np.linspace(x - 16, x + 16, 6)
        eye[:, 1] = (y - 6, y - 6, y, y + 6, y + 6, y)
    return points


def texture() -> NDArray[np.uint8]:
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (CROP // 8, CROP // 8, 3), dtype=np.uint8)
    return np.asarray(cv2.resize(noise, (CROP, CROP), interpolation=cv2.INTER_CUBIC), np.uint8)


class FakePortrait:
    """Draws a dark mouth and eyes on a textured face; the head pose shifts the picture
    sideways."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.photo = np.full((160, 200, 3), 120, np.uint8)
        self.lip_ratio = 0.05
        # The 512 crop lands as a 128 px square in the photo.
        self.crop_to_photo = np.array([[0.25, 0, 36], [0, 0.25, 16]], np.float64)
        self.crop_landmarks = landmarks()
        self.paste_template = np.zeros((CROP, CROP), np.uint8)
        self.paste_template[32:-32, 32:-32] = 255
        self.renders = 0
        self.fail_after = fail_after

    def render(
        self,
        controls: dict[str, float],
        ratio: float | None = None,
        upper: float = 1.0,
        pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
        eye_open: float = 1.0,
    ) -> NDArray[np.uint8]:
        if self.fail_after is not None and self.renders >= self.fail_after:
            raise KeyboardInterrupt
        self.renders += 1
        face = texture()
        gap = round(60 * (ratio or 0.0))
        if gap:
            cv2.ellipse(face, MOUTH, (30, gap), 0, 0, 360, (20, 10, 10), -1)
        lid = round(8 * eye_open)
        for eye in EYES if lid else ():
            cv2.ellipse(face, eye, (14, lid), 0, 0, 360, (10, 10, 30), -1)
        return np.roll(face, round(pose[1]), axis=1)


def write_speech(wav: Path, seconds: float = 0.4) -> None:
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * int(24000 * seconds))
    shapes = [
        {"shape": "rest", "start": 0.0, "end": 0.1},
        {"shape": "AA", "start": 0.1, "end": 0.25},
        {"shape": "MBP", "start": 0.25, "end": 0.3},
        {"shape": "rest", "start": 0.3, "end": seconds},
    ]
    wav.with_suffix(".json").write_text(json.dumps({"shapes": shapes}))


@pytest.fixture
def short_loop() -> Iterator[None]:
    with patch.object(photoreal_library, "LOOP_SECONDS", 0.4):  # 10 frames
        yield


def photo_file(tmp_path: Path) -> Path:
    path = tmp_path / "me.png"
    cv2.imwrite(str(path), np.full((160, 200, 3), 120, np.uint8))
    return path
