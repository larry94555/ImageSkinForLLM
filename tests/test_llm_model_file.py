"""The local LLM's model file, for the dashboard's disk (roadmap R175)."""

import logging
import shutil
from pathlib import Path
from typing import Any

import pytest
from test_resources import Disk, by_name, machine

from imageskin import llm_model_file
from imageskin.llm_model_file import CHECK_S, ON_HOST, LlmModelFile, on_machine
from imageskin.resources import GB, ResourceReader


class Server:
    """llama-server's /props, counting the asks."""

    def __init__(self, model_path: str | None = None, error: Exception | None = None) -> None:
        self.model_path, self.error = model_path, error
        self.urls: list[str] = []

    def __call__(self, url: str) -> dict[str, Any]:
        self.urls.append(url)
        if self.error:
            raise self.error
        return {"model_path": self.model_path, "total_slots": 1}


def model(tmp_path: Path, size: int = 2_500) -> Path:
    path = tmp_path / "models" / "gemma-3-4b-it-Q4_0.gguf"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"g" * size)
    return path


def test_the_file_llama_server_loaded_with_its_size(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = model(tmp_path)
    server = Server(str(path))
    caplog.set_level(logging.INFO)
    found = LlmModelFile("http://127.0.0.1:8080/v1", ask=server).get()
    assert server.urls == ["http://127.0.0.1:8080/props"]
    assert found is not None
    assert (found.name, found.size, found.location) == ("gemma-3-4b-it-Q4_0.gguf", 2_500, str(path))
    assert found.device == path.stat().st_dev
    assert "Local LLM model file found" in caplog.text


def test_asked_at_most_once_a_minute(tmp_path: Path) -> None:
    server, now = Server(str(model(tmp_path))), [100.0]
    file = LlmModelFile("http://llama:8080/v1/", ask=server, clock=lambda: now[0])
    assert file.get() == file.get()
    now[0] += CHECK_S - 1
    file.get()
    assert server.urls == ["http://llama:8080/props"]
    now[0] += 1
    file.get()
    assert len(server.urls) == 2


@pytest.mark.parametrize(
    "server",
    [
        Server(error=ConnectionRefusedError("refused")),  # no local LLM running
        Server(model_path=""),  # none loaded
        Server(model_path="/models/gone.gguf"),  # not mounted here
    ],
)
def test_no_model_file_found_is_none_and_said_once(
    server: Server, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    now = [0.0]
    file = LlmModelFile("http://127.0.0.1:8080/v1", ask=server, clock=lambda: now[0])
    assert file.get() is None
    now[0] += CHECK_S
    assert file.get() is None
    assert caplog.text.count("No local LLM model file for the disk") == 1
    assert "ERROR" not in caplog.text


def test_where_it_is_on_the_machine() -> None:
    host = "/models:/var/lib/docker/volumes/imageskin_llama-models/_data"
    file = "/models/models--unsloth--gemma-3-4b-it-GGUF/snapshots/1/gemma-3-4b-it-Q4_0.gguf"
    assert on_machine(file, host) == (
        "/var/lib/docker/volumes/imageskin_llama-models/_data"
        "/models--unsloth--gemma-3-4b-it-GGUF/snapshots/1/gemma-3-4b-it-Q4_0.gguf"
    )
    assert on_machine("/modelsx/a.gguf", host) == "/modelsx/a.gguf"  # another folder
    assert on_machine(file, None) == file  # a laptop: the path is the machine's
    assert on_machine(file, "no colon") == file


def test_the_location_follows_the_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = model(tmp_path)
    monkeypatch.setenv(ON_HOST, f"{tmp_path}:/srv/host")
    found = LlmModelFile("http://x/v1", ask=Server(str(path))).get()
    assert found is not None and found.location == "/srv/host/models/gemma-3-4b-it-Q4_0.gguf"


def reader(tmp_path: Path, server: Server) -> ResourceReader:
    return ResourceReader(tmp_path, llm_model=LlmModelFile("http://x/v1", ask=server))


def test_the_disks_used_is_the_model_and_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch, disk=(96 * GB, 60 * GB))  # 36 GB used
    path = model(tmp_path, size=3_000)
    disk = by_name(reader(tmp_path, Server(str(path))).read())["disk"]
    details = disk["details"]
    assert details["llm_model"] == "gemma-3-4b-it-Q4_0.gguf"
    assert details["llm_location"] == str(path)
    assert details["llm_bytes"] + details["other_bytes"] == disk["used"]
    assert details["other_bytes"] == disk["used"] - 3_000


def test_no_split_without_a_model_on_this_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch)
    refused = Server(error=ConnectionRefusedError("refused"))
    assert by_name(reader(tmp_path, refused).read())["disk"]["details"] == {"path": str(tmp_path)}

    # On another disk than the data's, it isn't part of this one's Used.
    path = model(tmp_path)
    elsewhere = LlmModelFile("http://x/v1", ask=Server(str(path)))
    real = elsewhere._read()
    assert real is not None
    monkeypatch.setattr(
        elsewhere,
        "get",
        lambda: llm_model_file.ModelFile(real.name, real.size, real.location, real.device + 1),
    )
    split = ResourceReader(tmp_path, llm_model=elsewhere).read()
    assert "llm_bytes" not in by_name(split)["disk"]["details"]


def test_a_model_bigger_than_used_is_not_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = model(tmp_path, size=5_000)
    monkeypatch.setattr(shutil, "disk_usage", lambda p: Disk(10_000, 1_000, 9_000))
    machine_disk = by_name(reader(tmp_path, Server(str(path))).read())["disk"]
    assert "llm_bytes" not in machine_disk["details"]
