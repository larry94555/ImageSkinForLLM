"""The local LLM's model file, for the dashboard's disk (roadmap R175): its name, its size and
where it is on the machine, so the disk's Used can be split into the model and Other.

llama-server names the file it loaded (`/props`). On a laptop that is the file's own path. On
the hosted site llama-server runs in its own container, so compose.yaml mounts the models'
volume into the app's container at the same path, and IMAGESKIN_LLM_MODELS_ON_HOST says where
that folder is on the machine itself.
"""

import json
import logging
import os
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# The dashboard reads every 10 s; the model changes only when llama-server restarts.
CHECK_S = 60.0
ASK_TIMEOUT_S = 2.0
# "<folder in the containers>:<the same folder on the machine>", set in compose.yaml.
ON_HOST = "IMAGESKIN_LLM_MODELS_ON_HOST"


@dataclass(frozen=True)
class ModelFile:
    name: str
    size: int
    location: str  # on the machine
    device: int  # the disk it is on (st_dev), to check it is the data's


def ask_props(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=ASK_TIMEOUT_S) as response:
        return dict(json.loads(response.read()))


def on_machine(path: str, mapping: str | None) -> str:
    """The path on the machine, for a path inside the containers' mounted models folder."""
    inside, _, host = (mapping or "").partition(":")
    if inside and host and (path == inside or path.startswith(inside.rstrip("/") + "/")):
        return host.rstrip("/") + path[len(inside.rstrip("/")) :]
    return path


class LlmModelFile:
    """Asks llama-server at most once a minute which file it loaded. `ask` and `clock` are for
    tests."""

    def __init__(
        self,
        llm_url: str,
        ask: Callable[[str], dict[str, Any]] = ask_props,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        # The chat's address is llama-server's OpenAI one, ending in /v1; /props is beside it.
        self._props_url = llm_url.rstrip("/").removesuffix("/v1") + "/props"
        self._ask = ask
        self._clock = clock
        self._checked_at: float | None = None
        self._file: ModelFile | None = None
        self._missing_said: str | None = None

    def get(self) -> ModelFile | None:
        now = self._clock()
        if self._checked_at is None or now - self._checked_at >= CHECK_S:
            self._checked_at = now
            self._file = self._read()
        return self._file

    def _read(self) -> ModelFile | None:
        started = time.perf_counter()
        try:
            path = str(self._ask(self._props_url).get("model_path") or "")
            if not path:
                raise ValueError("llama-server named no model file")
            stat = Path(path).stat()  # follows the -hf cache's link to the file itself
        except (OSError, ValueError) as e:
            # Normal where no local LLM runs (Claude or OpenAI chosen), so said once, not an error.
            if self._missing_said != str(e):
                self._missing_said = str(e)
                logger.info("No local LLM model file for the disk", extra={"reason": str(e)})
            return None
        found = ModelFile(
            name=path.replace("\\", "/").rsplit("/", 1)[-1],
            size=stat.st_size,
            location=on_machine(path, os.environ.get(ON_HOST)),
            device=stat.st_dev,
        )
        if self._file != found:
            logger.info(
                "Local LLM model file found",
                extra={
                    "model": found.name,
                    "bytes": found.size,
                    "location": found.location,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
        self._missing_said = None
        return found
