"""Structured logging: one JSON object per line on stderr."""

import json
import logging
import sys
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has, plus uvicorn's ANSI-colored copy of the message.
# Anything else came from `extra=` and is logged as a field.
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "color_message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS:
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # A line per HTTP request while models download, and Hugging Face's advice to sign in, buried
    # the app's own lines (Larry, 2026-10-08). Their errors still show.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)


@contextmanager
def quiet_library_warnings() -> Iterator[None]:
    """Hide the warnings model libraries print while they load and run (deprecations, Hugging
    Face's cache and sign-in advice), which are not ours to act on and read like errors."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        warnings.simplefilter("ignore", DeprecationWarning)
        warnings.filterwarnings("ignore", message=".*(pkg_resources|symlinks|unauthenticated)")
        yield
