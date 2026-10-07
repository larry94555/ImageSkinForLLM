import io
import json
import logging
import shutil
import subprocess
import wave
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from sound_fakes import speechlike, wav_of

from imageskin import sound_checks, uploads
from imageskin.audio import AudioError
from imageskin.sound_checks import SoundResult
from imageskin.uploads import (
    PhotoChoice,
    PhotoResult,
    UploadError,
    UploadStore,
    VoiceSample,
    detect_format,
    display_name,
)

JPG = b"\xff\xd8\xff\xe0" + b"\0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 100
SMALL = PhotoResult(["Your face is too small."])
GOOD = PhotoResult([], 80)
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def wav_bytes(seconds: float = 0.5, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))
    return buf.getvalue()


def encoded(tmp_path: Path, suffix: str) -> bytes:
    """A short sound encoded by ffmpeg, as M4A or MP3."""
    src, out = tmp_path / "in.wav", tmp_path / f"out{suffix}"
    src.write_bytes(wav_bytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), str(out)], check=True)
    return out.read_bytes()


@pytest.mark.parametrize(
    ("head", "fmt"),
    [
        (JPG, "jpg"),
        (PNG, "png"),
        (b"RIFF\0\0\0\0WAVEfmt ", "wav"),
        (b"\0\0\0\x18ftypheic\0\0\0\0", "heic"),
        (b"\0\0\0\x18ftypmif1\0\0\0\0", "heic"),
        (b"\0\0\0\x18ftypM4A \0\0\0\0", "m4a"),
        (b"\0\0\0\x18ftypqt  \0\0\0\0", None),
        (b"ID3\x04\0", "mp3"),
        (b"\xff\xfb\x90\x00", "mp3"),
        (b"%PDF-1.7", None),
        (b"", None),
    ],
)
def test_format_comes_from_the_first_bytes(head: bytes, fmt: str | None) -> None:
    assert detect_format(head[:16]) == fmt


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("me.jpg", "me.jpg"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\photo.png", "photo.png"),
        ("bad\nname.jpg", "badname.jpg"),
        (None, "unnamed"),
        ("x" * 300, "x" * 100),
    ],
)
def test_display_name_is_only_the_last_part(name: str | None, shown: str) -> None:
    assert display_name(name) == shown


def test_photo_is_stored_under_a_generated_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = UploadStore(tmp_path)
    with caplog.at_level(logging.INFO, logger="imageskin.uploads"):
        upload = store.save("photos", "../me.jpg", io.BytesIO(JPG))
    stored = next(r for r in caplog.records if r.getMessage() == "Upload stored")
    assert vars(stored)["id"] == upload.id and vars(stored)["duration_ms"] >= 0
    assert upload.name == "me.jpg" and upload.format == "jpg" and upload.size == len(JPG)
    path = store.path("photos", upload.id)
    assert path == tmp_path / "uploads" / "photos" / f"{upload.id}.jpg"
    assert path.read_bytes() == JPG
    assert store.list("photos") == [upload]
    assert store.list("sounds") == []
    assert list((tmp_path / "uploads" / "tmp").iterdir()) == []


def test_list_is_oldest_first_and_skips_broken_info(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = UploadStore(tmp_path)
    first = store.save("photos", "a.png", io.BytesIO(PNG))
    second = store.save("photos", "b.jpg", io.BytesIO(JPG))
    info = tmp_path / "uploads" / "photos" / f"{first.id}.json"
    info.write_text(json.dumps({**json.loads(info.read_text()), "uploaded_at": "2000"}))
    (tmp_path / "uploads" / "photos" / "junk.json").write_text("not json")
    with caplog.at_level(logging.ERROR, logger="imageskin.uploads"):
        assert [u.id for u in store.list("photos")] == [first.id, second.id]
    assert any(r.getMessage() == "Could not read upload info" for r in caplog.records)


def test_renamed_file_is_refused_with_the_reason_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = UploadStore(tmp_path)
    with caplog.at_level(logging.WARNING, logger="imageskin.uploads"):
        with pytest.raises(UploadError, match="not a JPG, PNG or HEIC photo") as e:
            store.save("photos", "notes.jpg", io.BytesIO(b"%PDF-1.7 not a photo"))
    assert e.value.status == 415
    refused = next(r for r in caplog.records if r.getMessage() == "Upload refused")
    assert vars(refused)["upload_name"] == "notes.jpg"
    assert "not a JPG" in vars(refused)["reason"]
    assert store.list("photos") == []
    assert list((tmp_path / "uploads" / "tmp").iterdir()) == []


def test_photo_sent_as_a_sound_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UploadError, match="not a WAV, M4A or MP3 recording"):
        UploadStore(tmp_path).save("sounds", "me.wav", io.BytesIO(JPG))


def test_empty_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UploadError, match="empty"):
        UploadStore(tmp_path).save("photos", "me.jpg", io.BytesIO(b""))


def test_oversized_file_is_refused(tmp_path: Path) -> None:
    with patch.dict(uploads.MAX_BYTES, {"photos": 50}), patch.object(uploads, "CHUNK", 16):
        with pytest.raises(UploadError, match="larger than") as e:
            UploadStore(tmp_path).save("photos", "big.jpg", io.BytesIO(JPG))
    assert e.value.status == 413
    assert list((tmp_path / "uploads" / "tmp").iterdir()) == []


def test_total_limit_is_enforced(tmp_path: Path) -> None:
    store = UploadStore(tmp_path)
    store.save("photos", "a.jpg", io.BytesIO(JPG))
    with patch.object(uploads, "MAX_TOTAL_BYTES", len(JPG) * 2 - 1):
        with pytest.raises(UploadError, match="in total") as e:
            store.save("photos", "b.jpg", io.BytesIO(JPG))
    assert e.value.status == 413


def test_total_limit_counts_only_stored_uploads(tmp_path: Path) -> None:
    # The file being received must not count twice: an upload that exactly fills the
    # limit is accepted.
    store = UploadStore(tmp_path)
    store.save("photos", "a.jpg", io.BytesIO(JPG))
    stored = sum(p.stat().st_size for p in (tmp_path / "uploads" / "photos").iterdir())
    (tmp_path / "uploads" / "tmp" / "stray.upload").write_bytes(b"x" * 1000)
    with patch.object(uploads, "MAX_TOTAL_BYTES", stored + len(JPG)):
        store.save("photos", "b.jpg", io.BytesIO(JPG))


def test_total_limit_uses_the_converted_size(tmp_path: Path) -> None:
    # A small compressed recording becomes a much larger WAV; the WAV is what is stored.
    def grows(src: Path, dst: Path, timeout_s: float) -> None:
        dst.write_bytes(wav_bytes(seconds=1.0))

    small_upload = wav_bytes(seconds=0.1)
    store = UploadStore(tmp_path)
    with (
        patch("imageskin.uploads.to_wav", side_effect=grows),
        patch.object(uploads, "MAX_TOTAL_BYTES", len(small_upload) * 2),
    ):
        with pytest.raises(UploadError, match="in total") as e:
            store.save("sounds", "a.mp3", io.BytesIO(small_upload))
    assert e.value.status == 413
    assert store.list("sounds") == []
    assert list((tmp_path / "uploads" / "tmp").iterdir()) == []


def test_failed_conversion_leaves_no_working_files(tmp_path: Path) -> None:
    def half_written(src: Path, dst: Path, timeout_s: float) -> None:
        dst.write_bytes(b"partial")
        raise AudioError("ffmpeg stopped")

    store = UploadStore(tmp_path)
    with patch("imageskin.uploads.to_wav", side_effect=half_written):
        with pytest.raises(UploadError, match="could not be read"):
            store.save("sounds", "a.wav", io.BytesIO(wav_bytes()))
    assert list((tmp_path / "uploads" / "tmp").iterdir()) == []
    assert store.list("sounds") == []


def test_upload_without_its_info_file_is_not_kept(tmp_path: Path) -> None:
    store = UploadStore(tmp_path)
    with patch("imageskin.uploads.json.dumps", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            store.save("photos", "a.jpg", io.BytesIO(JPG))
    assert list((tmp_path / "uploads" / "photos").iterdir()) == []
    assert list((tmp_path / "uploads" / "tmp").iterdir()) == []


def test_remove_deletes_the_file_and_its_info(tmp_path: Path) -> None:
    store = UploadStore(tmp_path)
    upload = store.save("photos", "a.jpg", io.BytesIO(JPG))
    assert store.remove("photos", upload.id)
    assert not store.remove("photos", upload.id)
    assert list((tmp_path / "uploads" / "photos").iterdir()) == []


@pytest.mark.parametrize("bad_id", ["..", "../consent", "A" * 32, "0" * 31, "*" * 32])
def test_only_generated_ids_are_looked_up(tmp_path: Path, bad_id: str) -> None:
    store = UploadStore(tmp_path)
    assert store.path("photos", bad_id) is None
    assert not store.remove("photos", bad_id)


@needs_ffmpeg
@pytest.mark.parametrize("fmt", ["wav", "m4a", "mp3"])
def test_sound_is_converted_to_wav(tmp_path: Path, fmt: str) -> None:
    data = wav_bytes() if fmt == "wav" else encoded(tmp_path, f".{fmt}")
    store = UploadStore(tmp_path / "home")
    upload = store.save("sounds", f"voice.{fmt}", io.BytesIO(data))
    assert upload.format == fmt
    assert upload.seconds is not None and 0.4 < upload.seconds < 0.7
    path = store.path("sounds", upload.id)
    assert path is not None and path.suffix == ".wav"
    with wave.open(str(path), "rb") as w:
        assert (w.getframerate(), w.getnchannels()) == (24000, 1)


@needs_ffmpeg
def test_too_long_sound_is_refused(tmp_path: Path) -> None:
    store = UploadStore(tmp_path)
    with patch.object(uploads, "MAX_SOUND_SECONDS", 0.25):
        with pytest.raises(UploadError, match="Recordings are limited to") as e:
            store.save("sounds", "long.wav", io.BytesIO(wav_bytes()))
    assert e.value.status == 413
    assert store.list("sounds") == []
    assert list((tmp_path / "uploads" / "tmp").iterdir()) == []


@needs_ffmpeg
def test_unreadable_sound_is_refused(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="imageskin.uploads"):
        with pytest.raises(UploadError, match="could not be read"):
            UploadStore(tmp_path).save("sounds", "x.mp3", io.BytesIO(b"ID3" + b"\0" * 64))
    assert any(r.getMessage() == "Sound conversion failed" for r in caplog.records)


def test_heic_without_the_extra_says_how_to_add_it(tmp_path: Path) -> None:
    heic = b"\0\0\0\x18ftypheic" + b"\0" * 64
    with patch.object(uploads, "heic_supported", return_value=False):
        with pytest.raises(UploadError, match=r"\.\[heic\]") as e:
            UploadStore(tmp_path).save("photos", "me.heic", io.BytesIO(heic))
    assert e.value.status == 415


def test_heic_photo_is_converted_to_jpg(tmp_path: Path) -> None:
    pillow_heif = pytest.importorskip("pillow_heif")
    from PIL import Image

    src = tmp_path / "me.heic"
    pillow_heif.from_pillow(Image.new("RGB", (64, 48), "red")).save(src, quality=90)
    store = UploadStore(tmp_path / "home")
    upload = store.save("photos", "me.heic", io.BytesIO(src.read_bytes()))
    assert upload.format == "heic"
    path = store.path("photos", upload.id)
    assert path is not None and path.suffix == ".jpg"
    with Image.open(path) as image:
        assert (image.format, image.size) == ("JPEG", (64, 48))


def test_broken_heic_is_refused(tmp_path: Path) -> None:
    pytest.importorskip("pillow_heif")
    heic = b"\0\0\0\x18ftypheic" + b"\0" * 64
    with pytest.raises(UploadError, match="HEIC photo could not be read"):
        UploadStore(tmp_path).save("photos", "me.heic", io.BytesIO(heic))


def test_heic_conversion_is_stopped_after_the_timeout(tmp_path: Path) -> None:
    timeout = subprocess.TimeoutExpired(cmd="heic", timeout=60)
    with patch("imageskin.uploads.subprocess.run", side_effect=timeout):
        with pytest.raises(UploadError, match="took over 60 seconds"):
            uploads.convert_heic(tmp_path / "a.heic", tmp_path / "a.jpg")


def test_heic_command_needs_two_paths(capsys: pytest.CaptureFixture[str]) -> None:
    from imageskin import heic

    assert heic.main([]) == 2
    assert "usage" in capsys.readouterr().err


def test_heic_command_converts_and_reports_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pillow_heif = pytest.importorskip("pillow_heif")
    from PIL import Image

    from imageskin import heic

    src, dst = tmp_path / "me.heic", tmp_path / "me.jpg"
    pillow_heif.from_pillow(Image.new("RGB", (32, 32), "blue")).save(src, quality=90)
    assert heic.main([str(src), str(dst)]) == 0
    assert dst.read_bytes().startswith(b"\xff\xd8\xff")
    assert heic.main([str(tmp_path / "missing.heic"), str(dst)]) == 1
    assert "Error" in capsys.readouterr().err


def test_photos_are_checked_as_they_arrive(tmp_path: Path) -> None:
    checked: list[Path] = []

    def check(photo: Path) -> PhotoResult:
        checked.append(photo)
        return SMALL

    store = UploadStore(tmp_path, check_photo=check)
    upload = store.save("photos", "me.jpg", io.BytesIO(JPG))
    assert upload.problems == ["Your face is too small."]
    assert checked == [store.path("photos", upload.id)]
    assert store.list("photos") == [upload]
    assert len(checked) == 1  # the stored result is used, not checked again


@needs_ffmpeg
def test_sounds_are_sound_checked_not_face_checked(tmp_path: Path) -> None:
    store = UploadStore(tmp_path, check_photo=lambda p: pytest.fail("checked a sound"))
    silent = store.save("sounds", "a.wav", io.BytesIO(wav_bytes()))
    assert silent.problems == [sound_checks.TOO_SHORT.format(speech=0)]
    assert silent.checks == uploads.SOUND_CHECKS and silent.speech == 0
    spoken = store.save("sounds", "b.wav", io.BytesIO(wav_of(speechlike(30))))
    assert spoken.problems == [] and spoken.speech is not None and spoken.speech > 15


def test_a_photo_that_cannot_be_checked_is_kept_unchecked(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(photo: Path) -> PhotoResult:
        raise RuntimeError("models missing")

    store = UploadStore(tmp_path, check_photo=broken)
    with caplog.at_level(logging.ERROR):
        upload = store.save("photos", "me.jpg", io.BytesIO(JPG))
    assert upload.problems is None
    assert store.list("photos") == [upload]
    failed = [r for r in caplog.records if r.message == "Face checks failed"]
    assert failed and failed[0].error == "models missing"  # type: ignore[attr-defined]


def test_photos_stored_before_checks_are_checked_on_request(tmp_path: Path) -> None:
    old = UploadStore(tmp_path).save("photos", "old.jpg", io.BytesIO(JPG))
    assert old.problems is None

    store = UploadStore(tmp_path, check_photo=lambda p: pytest.fail("listing must not check"))
    assert [u.problems for u in store.list("photos")] == [None]

    store.check_photo = lambda p: SMALL
    checked = replace(old, problems=["Your face is too small."], checks=uploads.FACE_CHECKS)
    assert store.check("photos", old.id) == checked
    assert store.list("photos") == [checked]


def test_results_of_older_checks_are_listed_as_not_checked(tmp_path: Path) -> None:
    store = UploadStore(tmp_path, check_photo=lambda p: SMALL)
    photo = store.save("photos", "me.jpg", io.BytesIO(JPG))
    assert photo.checks == uploads.FACE_CHECKS
    with patch.object(uploads, "FACE_CHECKS", uploads.FACE_CHECKS + 1):
        assert [u.problems for u in store.list("photos")] == [None]
        store.check_photo = lambda p: GOOD
        assert store.check("photos", photo.id).problems == []  # type: ignore[union-attr]
        assert [u.problems for u in store.list("photos")] == [[]]


def test_checking_needs_a_stored_photo(tmp_path: Path) -> None:
    store = UploadStore(tmp_path, check_photo=lambda p: GOOD)
    assert store.check("photos", "f" * 32) is None
    assert store.check("photos", "not-an-id") is None


def test_a_check_that_fails_keeps_the_photo_unchecked(tmp_path: Path) -> None:
    old = UploadStore(tmp_path).save("photos", "old.jpg", io.BytesIO(JPG))
    assert UploadStore(tmp_path).check("photos", old.id) == old  # checks are off
    assert [u.problems for u in UploadStore(tmp_path).list("photos")] == [None]


def test_old_results_stay_hidden_when_the_recheck_cannot_run(tmp_path: Path) -> None:
    store = UploadStore(tmp_path, check_photo=lambda p: SMALL)
    photo = store.save("photos", "me.jpg", io.BytesIO(JPG))

    def broken(p: Path) -> PhotoResult:
        raise RuntimeError("models missing")

    with patch.object(uploads, "FACE_CHECKS", uploads.FACE_CHECKS + 1):
        assert UploadStore(tmp_path).check("photos", photo.id).problems is None  # type: ignore[union-attr]
        store.check_photo = broken
        assert store.check("photos", photo.id).problems is None  # type: ignore[union-attr]


def test_a_photo_removed_while_its_result_is_saved_leaves_no_info_file(tmp_path: Path) -> None:
    store = UploadStore(tmp_path, check_photo=lambda p: GOOD)
    photo = UploadStore(tmp_path).save("photos", "me.jpg", io.BytesIO(JPG))
    write_info = UploadStore._write_info

    def remove_then_write(stored: Path, upload: uploads.Upload) -> None:
        assert store.remove("photos", photo.id)  # DELETE lands just before the write
        write_info(stored, upload)

    with patch.object(UploadStore, "_write_info", staticmethod(remove_then_write)):
        store.check("photos", photo.id)
    assert store.list("photos") == []
    assert list((tmp_path / "uploads" / "photos").iterdir()) == []


# --- The photo used for the video (R9) ---


def test_the_best_scoring_photo_that_passed_is_picked(tmp_path: Path) -> None:
    results = [PhotoResult([], 70), PhotoResult([], 90), SMALL, PhotoResult([], 85)]
    store = UploadStore(tmp_path, check_photo=lambda p: results.pop(0))
    assert store.photo_choice() == PhotoChoice(None)
    ids = [store.save("photos", f"{n}.jpg", io.BytesIO(JPG)).id for n in range(4)]
    assert store.photo_choice() == PhotoChoice(ids[1], "app")


def test_the_users_choice_wins_while_it_is_there(tmp_path: Path) -> None:
    results = [PhotoResult([], 90), PhotoResult([], 60), SMALL]
    store = UploadStore(tmp_path, check_photo=lambda p: results.pop(0))
    best, other, failed = (store.save("photos", "me.jpg", io.BytesIO(JPG)).id for _ in range(3))
    assert store.choose_photo(other) == PhotoChoice(other, "you")
    assert UploadStore(tmp_path).photo_choice() == PhotoChoice(other, "you")  # kept on disk
    with pytest.raises(UploadError, match="passed the checks") as refused:
        store.choose_photo(failed)
    assert refused.value.status == 400
    with pytest.raises(UploadError, match="No such photo") as missing:
        store.choose_photo("f" * 32)
    assert missing.value.status == 404
    store.remove("photos", other)
    assert store.photo_choice() == PhotoChoice(best, "app")


def test_a_chosen_photo_whose_checks_are_redone_falls_back_to_the_best(tmp_path: Path) -> None:
    store = UploadStore(tmp_path, check_photo=lambda p: GOOD)
    photo = store.save("photos", "me.jpg", io.BytesIO(JPG)).id
    store.choose_photo(photo)
    with patch.object(uploads, "FACE_CHECKS", uploads.FACE_CHECKS + 1):
        assert store.photo_choice() == PhotoChoice(None)  # not checked by the new checks yet


def test_an_unreadable_choice_file_is_logged_and_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = UploadStore(tmp_path, check_photo=lambda p: GOOD)
    photo = store.save("photos", "me.jpg", io.BytesIO(JPG)).id
    (tmp_path / "uploads" / "chosen-photo.json").write_text("[not json", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        assert store.photo_choice() == PhotoChoice(photo, "app")
    assert "Could not read the chosen photo" in caplog.text


def test_the_choice_file_is_not_listed_as_a_photo(tmp_path: Path) -> None:
    store = UploadStore(tmp_path, check_photo=lambda p: GOOD)
    store.choose_photo(store.save("photos", "me.jpg", io.BytesIO(JPG)).id)
    assert len(store.list("photos")) == 1


# --- Sound checks and the voice sample (R10) ---

PASSED = SoundResult([], 20.0)
NOISY = SoundResult([sound_checks.NOISY], 20.0)


def sound_store(tmp_path: Path, results: list[SoundResult]) -> UploadStore:
    """A store whose sound checks give these results, in order."""
    queue = iter(results)
    return UploadStore(tmp_path, check_sound=lambda p: next(queue))


def stored_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def test_the_voice_sample_joins_the_recordings_that_passed(tmp_path: Path) -> None:
    store = sound_store(tmp_path, [PASSED, NOISY, PASSED])
    for seconds in (1.0, 2.0, 0.5):
        store.save("sounds", "a.wav", io.BytesIO(wav_bytes(seconds)))
    assert store.voice_sample() == VoiceSample(recordings=2, seconds=1.5, speech=40.0, problem=None)
    assert stored_seconds(store.voice_sample_file) == 1.5


def test_recordings_sent_together_keep_their_order(tmp_path: Path) -> None:
    store = sound_store(tmp_path, [PASSED] * 5)
    sent = [store.save("sounds", f"{n}.wav", io.BytesIO(wav_bytes(0.1))).id for n in range(5)]
    assert [u.id for u in store.list("sounds")] == sent


def test_the_voice_sample_says_what_it_still_needs(tmp_path: Path) -> None:
    store = sound_store(tmp_path, [NOISY, PASSED])
    assert store.voice_sample().problem == uploads.NO_VOICE
    store.save("sounds", "noisy.wav", io.BytesIO(wav_bytes()))
    assert store.voice_sample().problem == uploads.NO_VOICE
    assert not store.voice_sample_file.exists()
    store.save("sounds", "short.wav", io.BytesIO(wav_bytes()))
    assert store.voice_sample().problem == (
        "The recordings that passed the checks have 20 seconds of speech. The voice needs at"
        " least 30: add another recording."
    )


def test_removing_a_recording_updates_the_voice_sample(tmp_path: Path) -> None:
    store = sound_store(tmp_path, [PASSED, PASSED])
    first, second = (store.save("sounds", "a.wav", io.BytesIO(wav_bytes(s))) for s in (1, 2))
    assert store.remove("sounds", first.id)
    assert stored_seconds(store.voice_sample_file) == 2
    assert store.remove("sounds", second.id)
    assert not store.voice_sample_file.exists()
    assert store.voice_sample().recordings == 0


def test_sounds_stored_before_the_checks_are_checked_on_request(tmp_path: Path) -> None:
    store = UploadStore(tmp_path, check_sound=None)
    old = store.save("sounds", "old.wav", io.BytesIO(wav_bytes()))
    assert old.problems is None and store.voice_sample().recordings == 0

    store.check_sound = lambda p: PASSED
    checked = store.check("sounds", old.id)
    assert checked == replace(old, problems=[], checks=uploads.SOUND_CHECKS, speech=20.0)
    assert store.voice_sample_file.exists()
    with patch.object(uploads, "SOUND_CHECKS", uploads.SOUND_CHECKS + 1):
        assert [(u.problems, u.speech) for u in store.list("sounds")] == [(None, None)]


def test_a_sound_that_cannot_be_checked_is_kept_unchecked(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(sound: Path) -> SoundResult:
        raise ValueError("not 16-bit")

    store = UploadStore(tmp_path, check_sound=broken)
    with caplog.at_level(logging.ERROR):
        upload = store.save("sounds", "a.wav", io.BytesIO(wav_bytes()))
    assert upload.problems is None
    assert "Sound checks failed" in caplog.text


def test_a_voice_sample_that_cannot_be_joined_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = sound_store(tmp_path, [PASSED])
    with (
        patch.object(uploads, "join_wavs", side_effect=AudioError("disk full")),
        caplog.at_level(logging.ERROR),
    ):
        upload = store.save("sounds", "a.wav", io.BytesIO(wav_bytes()))
    assert store.list("sounds") == [upload]  # the recording is kept
    assert "Could not make the voice sample" in caplog.text
    assert list((tmp_path / "uploads").glob("voice-sample*")) == []
