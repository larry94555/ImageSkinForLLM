"""A reason and a reference when something fails (roadmap R134)."""

import errno
import logging
import re
import subprocess
import urllib.error
from pathlib import Path

import pytest

from imageskin import __version__
from imageskin.download import DownloadError
from imageskin.failure import REASONS, Failure, classify, new_reference, report, without_paths
from imageskin.video import INSTALL_HINT, VideoError
from imageskin.voice import VoiceError


class UnidentifiedImageError(OSError):
    """Pillow's, by name."""


def caused(error: Exception, cause: Exception) -> Exception:
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ModuleNotFoundError("No module named 'cv2'"), "missing"),
        (VideoError(INSTALL_HINT), "missing"),
        (VoiceError("chatterbox not installed; see the README"), "missing"),
        (FileNotFoundError("ffmpeg"), "missing"),
        (MemoryError(), "memory"),
        (RuntimeError("CUDA out of memory. Tried to allocate 2 GiB"), "memory"),
        (OSError(errno.ENOMEM, "Cannot allocate memory"), "memory"),
        (OSError(errno.ENOSPC, "No space left on device"), "disk"),
        (VideoError("ffmpeg could not write sample.mp4 (No space left on device)"), "disk"),
        (DownloadError("stalled"), "download"),
        (urllib.error.URLError("unreachable"), "download"),
        (VoiceError("model gated; Hugging Face said: 401"), "download"),
        (UnidentifiedImageError("cannot identify image file"), "unreadable"),
        (VoiceError("the voice sample /x/voice.wav is silent"), "unreadable"),
        (TimeoutError(), "timeout"),
        (subprocess.TimeoutExpired("ffmpeg", 60), "timeout"),
        (VideoError("ffmpeg took longer than 60 seconds"), "timeout"),
        (RuntimeError("boom"), "unexpected"),
        # The cause decides when the error itself doesn't say.
        (caused(VoiceError("could not load the voice"), MemoryError()), "memory"),
    ],
)
def test_each_error_gets_its_reason(error: Exception, reason: str) -> None:
    assert classify(error) == reason


def test_a_cycle_of_causes_ends() -> None:
    a, b = RuntimeError("a"), RuntimeError("b")
    a.__context__, b.__context__ = b, a
    assert classify(a) == "unexpected"


def test_references_are_short_and_different() -> None:
    references = {new_reference() for _ in range(200)}
    assert len(references) == 200
    assert all(re.fullmatch(r"P-[A-HJ-NP-Z2-9]{6}", r) for r in references)


def test_the_data_folder_and_home_are_taken_out(tmp_path: Path) -> None:
    home = tmp_path / ".imageskin"
    text = f"could not read '{home}/uploads/photos/abc.jpg': denied; see {Path.home()}/notes"
    shown = without_paths(text, home)
    assert shown == "could not read '<data folder>': denied; see ~/notes"


def test_report_logs_everything_under_the_reference(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    error = VoiceError(f"could not read the voice sample {tmp_path}/voice.wav: denied")
    log = logging.getLogger("test")
    with caplog.at_level(logging.ERROR):
        failure = report(error, log, "Prepare job failed", tmp_path, "Get the voice ready", x=1)
    assert failure == Failure(
        failure.reference,
        "Get the voice ready",
        "unreadable",
        REASONS["unreadable"][0],
        False,
        "VoiceError: could not read the voice sample <data folder>: denied",
        __version__,
    )
    [logged] = caplog.records
    assert logged.getMessage() == "Prepare job failed" and logged.exc_info
    fields = vars(logged)
    assert fields["reference"] == failure.reference and fields["step"] == "Get the voice ready"
    assert fields["reason"] == "unreadable" and fields["error"] == str(error) and fields["x"] == 1


def test_a_message_that_says_what_to_do_is_kept(tmp_path: Path) -> None:
    failure = report(RuntimeError("x"), logging.getLogger("t"), "Failed", tmp_path, None, "Fix it.")
    assert (failure.reason, failure.message, failure.retry) == ("setup", "Fix it.", False)
    assert failure.summary() == f"Fix it. Reference for support: {failure.reference}."


def test_the_summary_says_to_try_again_when_it_may_help(tmp_path: Path) -> None:
    failure = report(MemoryError(), logging.getLogger("t"), "Failed", tmp_path)
    assert failure.details == "MemoryError"
    assert failure.summary() == (
        f"{REASONS['memory'][0]} Click Try again. Reference for support: {failure.reference}."
    )
