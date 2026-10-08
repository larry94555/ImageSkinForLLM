import json
import logging

import pytest

from imageskin.logging_setup import JsonFormatter, setup_logging


def make_record(**extra: object) -> logging.LogRecord:
    record = logging.makeLogRecord(
        {"name": "imageskin.test", "levelname": "INFO", "msg": "hello %s", "args": ("there",)}
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formats_one_json_object_with_extra_fields() -> None:
    entry = json.loads(JsonFormatter().format(make_record(duration_ms=12.5)))
    assert entry["level"] == "INFO"
    assert entry["logger"] == "imageskin.test"
    assert entry["message"] == "hello there"
    assert entry["duration_ms"] == 12.5
    assert "time" in entry


def test_includes_exception_text() -> None:
    try:
        raise ValueError("bad")
    except ValueError:
        import sys

        record = make_record()
        record.exc_info = sys.exc_info()
    entry = json.loads(JsonFormatter().format(record))
    assert "ValueError: bad" in entry["exception"]


def test_setup_logging_writes_json_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging("WARNING")
    logging.getLogger("imageskin.test").info("hidden")
    logging.getLogger("imageskin.test").warning("shown")
    lines = capsys.readouterr().err.strip().splitlines()
    assert [json.loads(line)["message"] for line in lines] == ["shown"]


def test_setup_logging_quiets_http_and_hugging_face_lines() -> None:
    setup_logging("INFO")
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("huggingface_hub.utils._http").getEffectiveLevel() == logging.ERROR
    assert logging.getLogger("imageskin.cli").getEffectiveLevel() == logging.INFO


def test_quiet_library_warnings_hides_only_library_noise() -> None:
    import warnings

    from imageskin.logging_setup import quiet_library_warnings

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        with quiet_library_warnings():
            warnings.warn("old API", FutureWarning, stacklevel=1)
            warnings.warn("pkg_resources is deprecated as an API", UserWarning, stacklevel=1)
            warnings.warn("cache-system uses symlinks by default", UserWarning, stacklevel=1)
            warnings.warn("something the app should show", UserWarning, stacklevel=1)
    assert [str(w.message) for w in seen] == ["something the app should show"]
