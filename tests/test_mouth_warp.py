import json
import subprocess
import wave
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from imageskin.mouth_warp import (
    MAX_SIDE,
    MouthWarpEngine,
    detect_faces,
    draw_frame,
    find_lip_line,
    frame_weights,
    load_photo,
    refine_lip_line,
)
from imageskin.video import Face, VideoError

SKIN = (150, 170, 220)  # BGR
LIPS = (90, 80, 200)
SEAM = (40, 35, 90)


def face_photo(path: Path, size: tuple[int, int] = (200, 160), lips_y: int = 130) -> Path:
    """A skin-coloured picture with red lips, enough for the lip finder (not the face detector)."""
    w, h = size
    image = np.zeros((h, w, 3), dtype=np.uint8)
    image[:] = SKIN
    image[lips_y - 4 : lips_y + 4, 80:120] = LIPS
    image[lips_y, 80:120] = SEAM  # the dark line where closed lips meet
    cv2.imwrite(str(path), image)
    return path


def fixed_box(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    return [(50, 20, 100, 125)]


def two_boxes(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    return [(10, 10, 20, 20), (50, 20, 100, 125)]


def write_wav(path: Path, seconds: float = 0.5) -> None:
    t = np.arange(int(seconds * 24000))
    pcm = (8000 * np.sin(t / 10)).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm.tobytes())


def test_load_photo_shrinks_to_even_sides(tmp_path: Path) -> None:
    image = load_photo(face_photo(tmp_path / "big.png", size=(1441, 1001)))
    assert max(image.shape[:2]) <= MAX_SIDE
    assert image.shape[0] % 2 == 0 and image.shape[1] % 2 == 0


def test_load_photo_errors(tmp_path: Path) -> None:
    with pytest.raises(VideoError, match="file not found"):
        load_photo(tmp_path / "missing.jpg")
    (tmp_path / "bad.jpg").write_text("not an image")
    with pytest.raises(VideoError, match="could not read"):
        load_photo(tmp_path / "bad.jpg")
    (tmp_path / "empty.jpg").write_bytes(b"")
    with pytest.raises(VideoError, match="could not read"):
        load_photo(tmp_path / "empty.jpg")


def test_find_lip_line_finds_the_red_rows(tmp_path: Path) -> None:
    image = load_photo(face_photo(tmp_path / "f.png", lips_y=125))
    assert abs(find_lip_line(image, (50, 20, 100, 125)) - 125) <= 1


def test_find_lip_line_without_lips_guesses(tmp_path: Path) -> None:
    image = np.full((160, 200, 3), SKIN, dtype=np.uint8)
    assert find_lip_line(image, (50, 20, 100, 100)) == 100


def test_refine_lip_line_moves_to_the_seam(tmp_path: Path) -> None:
    image = load_photo(face_photo(tmp_path / "f.png", lips_y=120))
    # Start a few rows below the seam, as the redness centre can on pale lips.
    assert abs(refine_lip_line(image, 100, 123, 42, 30) - 120) <= 1


def test_refine_lip_line_does_not_climb_to_the_nose(tmp_path: Path) -> None:
    image = load_photo(face_photo(tmp_path / "f.png", lips_y=120))
    image[100:104, 80:120] = 0  # a dark nostril shadow well above the lips
    assert abs(refine_lip_line(image, 100, 120, 42, 30) - 120) <= 1


def test_refine_lip_line_keeps_the_line_at_the_edge(tmp_path: Path) -> None:
    image = load_photo(face_photo(tmp_path / "f.png", lips_y=120))
    assert refine_lip_line(image, 100, 159, 42, 4) == 159


def test_detect_faces_finds_nothing_in_a_blank_picture() -> None:
    assert detect_faces(np.full((120, 160), 128, dtype=np.uint8)) == []


def test_detect_faces_reports_a_missing_detector() -> None:
    with patch("imageskin.mouth_warp.CASCADE", "missing.xml"):
        with pytest.raises(VideoError, match="face detector"):
            detect_faces(np.full((120, 160), 128, dtype=np.uint8))


def test_prepare_finds_the_mouth(tmp_path: Path) -> None:
    photo = face_photo(tmp_path / "f.png", lips_y=125)
    face = MouthWarpEngine(detect=fixed_box).prepare(photo)
    assert (face.width, face.height, face.mouth_x) == (200, 160, 100)
    assert abs(face.mouth_y - 125) <= 1
    assert face.mouth_w == 42
    assert face.jaw_h == 20 + int(1.02 * 125) - face.mouth_y  # chin just below the face box


def test_prepare_rejects_more_than_one_face(tmp_path: Path) -> None:
    with pytest.raises(VideoError, match="found 2 faces .* exactly one face"):
        MouthWarpEngine(detect=two_boxes).prepare(face_photo(tmp_path / "f.png"))


def test_prepare_without_a_face(tmp_path: Path) -> None:
    with pytest.raises(VideoError, match="no face found"):
        MouthWarpEngine().prepare(face_photo(tmp_path / "f.png"))


def test_closed_mouth_frame_is_the_photo(tmp_path: Path) -> None:
    image = load_photo(face_photo(tmp_path / "f.png"))
    face = Face(tmp_path / "f.png", 200, 160, 100, 130, 42, 30)
    region, weights = frame_weights(face)
    assert np.array_equal(draw_frame(image, face, region, weights, 0.0), image)


def test_open_mouth_changes_only_below_the_lips(tmp_path: Path) -> None:
    image = load_photo(face_photo(tmp_path / "f.png", lips_y=100))
    face = Face(tmp_path / "f.png", 200, 160, 100, 100, 42, 40)
    region, weights = frame_weights(face)
    frame = draw_frame(image, face, region, weights, 1.0)
    changed = np.argwhere((frame != image).any(axis=2))
    # Nothing above the lips moves; only the soft edge of the opening reaches a little higher.
    assert changed[:, 0].min() >= 100 - 12
    # The middle of the opening is dark red, and the upper teeth show just under the lip.
    middle = frame[102, 100].astype(int)
    assert middle.sum() < 300 and middle[2] > middle[0]
    assert frame[101, 100].sum() > middle.sum()


def test_quiet_sound_shows_no_teeth(tmp_path: Path) -> None:
    image = load_photo(face_photo(tmp_path / "f.png", lips_y=100))
    face = Face(tmp_path / "f.png", 200, 160, 100, 100, 42, 40)
    region, weights = frame_weights(face)
    frame = draw_frame(image, face, region, weights, 0.5)
    assert frame[101, 100].sum() <= frame[102, 100].sum() + 30


def test_render_writes_mp4(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    photo = face_photo(tmp_path / "f.png")
    wav = tmp_path / "s.wav"
    write_wav(wav)
    face = Face(photo, 200, 160, 100, 130, 42, 29)
    out = tmp_path / "out.mp4"
    with caplog.at_level("INFO"):
        assert MouthWarpEngine().render(face, wav, out) == pytest.approx(0.5)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,width,height",
            "-of",
            "json",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    assert {s["codec_name"] for s in streams} == {"h264", "aac"}
    assert any(s.get("width") == 200 and s.get("height") == 160 for s in streams)
    assert "Rendered video" in caplog.text


def test_render_rejects_a_changed_photo(tmp_path: Path) -> None:
    photo = face_photo(tmp_path / "f.png")
    write_wav(tmp_path / "s.wav")
    face = Face(photo, 100, 80, 50, 60, 20, 10)
    with pytest.raises(VideoError, match="changed since it was prepared"):
        MouthWarpEngine().render(face, tmp_path / "s.wav", tmp_path / "out.mp4")


def test_render_rejects_empty_audio(tmp_path: Path) -> None:
    write_wav(tmp_path / "s.wav", seconds=0)
    face = Face(tmp_path / "f.png", 200, 160, 100, 130, 42, 29)
    with pytest.raises(VideoError, match="has no audio"):
        MouthWarpEngine().render(face, tmp_path / "s.wav", tmp_path / "out.mp4")


def test_render_without_ffmpeg(tmp_path: Path) -> None:
    write_wav(tmp_path / "s.wav")
    face = Face(face_photo(tmp_path / "f.png"), 200, 160, 100, 130, 42, 29)
    with patch("imageskin.mouth_warp.shutil.which", return_value=None):
        with pytest.raises(VideoError, match="ffmpeg not found"):
            MouthWarpEngine().render(face, tmp_path / "s.wav", tmp_path / "out.mp4")


def test_prepare_without_ffmpeg_fails_first(tmp_path: Path) -> None:
    with patch("imageskin.mouth_warp.shutil.which", return_value=None):
        with pytest.raises(VideoError, match="winget install Gyan.FFmpeg"):
            MouthWarpEngine(detect=fixed_box).prepare(face_photo(tmp_path / "f.png"))


def test_render_reports_ffmpeg_errors(tmp_path: Path) -> None:
    write_wav(tmp_path / "s.wav")
    face = Face(face_photo(tmp_path / "f.png"), 200, 160, 100, 130, 42, 29)
    out = tmp_path / "missing-dir" / "out.mp4"
    with pytest.raises(VideoError, match="ffmpeg could not write out.mp4"):
        MouthWarpEngine().render(face, tmp_path / "s.wav", out)


def test_render_failure_removes_partial_output(tmp_path: Path) -> None:
    write_wav(tmp_path / "s.wav")
    face = Face(face_photo(tmp_path / "f.png"), 200, 160, 100, 130, 42, 29)
    out = tmp_path / "out.mp4"
    out.write_bytes(b"partial")
    with patch("imageskin.mouth_warp.subprocess.Popen") as popen:
        proc = popen.return_value
        proc.communicate.return_value = (None, b"Conversion failed!")
        proc.returncode = 1
        with pytest.raises(VideoError, match="Conversion failed"):
            MouthWarpEngine().render(face, tmp_path / "s.wav", out)
    assert not out.exists()


def test_render_timeout_kills_ffmpeg(tmp_path: Path) -> None:
    write_wav(tmp_path / "s.wav")
    face = Face(face_photo(tmp_path / "f.png"), 200, 160, 100, 130, 42, 29)
    out = tmp_path / "o.mp4"
    out.write_bytes(b"partial")
    with patch("imageskin.mouth_warp.subprocess.Popen") as popen:
        proc = popen.return_value
        proc.communicate.side_effect = [subprocess.TimeoutExpired("ffmpeg", 1), (None, b"")]
        with pytest.raises(VideoError, match="longer than 1 seconds"):
            MouthWarpEngine(timeout_s=1).render(face, tmp_path / "s.wav", out)
    proc.kill.assert_called_once()
    assert proc.communicate.call_count == 2  # the killed process is reaped
    assert not out.exists()
