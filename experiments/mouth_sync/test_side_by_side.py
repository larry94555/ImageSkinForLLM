import os
import time
from pathlib import Path

import numpy as np
import pytest
from side_by_side import before_weights, face_box, join, label_args, newest_library

from imageskin.visemes import ShapeTiming, frame_weights


def test_before_weights_open_the_mouth_early_as_before_r128() -> None:
    shapes = [ShapeTiming("rest", 0.0, 0.5), ShapeTiming("AA", 0.5, 1.0)]
    before = before_weights(shapes, None, 16000, 30, 30.0)
    now = frame_weights(shapes, 30, 30.0)
    assert before[14].get("AA", 0) > 0.1  # 0.467 s, before the sound
    assert "AA" not in now[14]
    # Within speech the two agree but for the half frame they are sampled at.
    assert before[20]["AA"] == pytest.approx(1.0) and now[20]["AA"] == pytest.approx(1.0)


def test_face_box_is_the_crop_on_the_photo_kept_inside_it() -> None:
    half = np.array([[0.5, 0, 100], [0, 0.5, 50]])  # the 512 px crop at half size
    assert face_box(half, (1000, 800)) == (100, 50, 256, 256)
    assert face_box(np.array([[1.0, 0, -20], [0, 1.0, 0]]), (300, 300)) == (0, 0, 300, 300)


def test_label_args_crops_both_and_names_them() -> None:
    graph = label_args("Before", "After R128", (10, 20, 100, 100))
    assert graph.count("crop=100:100:10:20") == 2
    assert "text='Before'" in graph and "text='After R128'" in graph and "hstack" in graph


def test_newest_library_is_the_face_prepared_last(tmp_path: Path) -> None:
    for name, age in (("old", 100), ("new", 0)):
        folder = tmp_path / "photoreal" / name
        folder.mkdir(parents=True)
        (folder / "library.json").write_text("{}")
        t = time.time() - age
        os.utime(folder / "library.json", (t, t))
    (tmp_path / "photoreal" / "unfinished").mkdir()
    assert newest_library(tmp_path).name == "new"
    with pytest.raises(SystemExit, match="No prepared face"):
        newest_library(tmp_path / "nothing")


def test_join_puts_the_two_faces_side_by_side_with_the_voice(tmp_path: Path) -> None:
    import wave

    from imageskin.video import write_mp4

    wav = tmp_path / "v.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    frames = [bytes(64 * 64 * 3)] * 25
    for name in ("before", "after"):
        write_mp4(iter(frames), (64, 64), wav, tmp_path / f"{name}.mp4", 60)
    out = tmp_path / "joined.mp4"
    join(tmp_path / "before.mp4", tmp_path / "after.mp4", wav, out, (0, 0, 64, 64))
    join(
        tmp_path / "before.mp4",
        tmp_path / "after.mp4",
        wav,
        tmp_path / "half.mp4",
        (0, 0, 64, 64),
        0.5,
    )
    assert out.stat().st_size > 0 and (tmp_path / "half.mp4").stat().st_size > 0
