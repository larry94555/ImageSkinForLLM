"""Checking the hosted default people (roadmap R32a)."""

import hashlib
import io
import json
import logging
import threading
import urllib.error
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from imageskin import hosted_packs as hp
from imageskin import start_now
from imageskin.cli import main
from imageskin.start_now import URL_VARIABLE


def info_of(data: bytes) -> dict[str, Any]:
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


@pytest.fixture
def site(tmp_path: Path) -> Iterator[str]:
    """A folder of packs served over HTTP, as Caddy serves deploy/default-people."""
    (tmp_path / "anna.zip").write_bytes(b"anna's pack")
    (tmp_path / "bob.zip").write_bytes(b"bob's pack")
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *args: None  # type: ignore[attr-defined]
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()


def test_a_matching_pack_is_ok(site: str) -> None:
    check = hp.check_pack(site, "anna", info_of(b"anna's pack"))
    assert check.problem is None
    assert check.bytes == len(b"anna's pack")
    assert hp.line(check).startswith("ok    anna  0.0 MB")


def test_a_missing_pack_is_named(site: str) -> None:
    check = hp.check_pack(site, "carol", info_of(b"x"))
    assert check.problem == "not on the site (404)"
    assert hp.line(check) == "WRONG carol: not on the site (404)"


def test_a_pack_of_the_wrong_size_or_contents_is_named(site: str) -> None:
    assert hp.check_pack(site, "anna", {"bytes": 3, "sha256": "0"}).problem == (
        "11 bytes, expected 3"
    )
    other = info_of(b"anna's pacK")
    assert hp.check_pack(site, "anna", other).problem == "SHA-256 differs"


def test_other_http_errors_and_no_connection_are_named() -> None:
    def forbidden(url: str, timeout: float) -> BinaryIO:
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)  # type: ignore[arg-type]

    def offline(url: str, timeout: float) -> BinaryIO:
        raise urllib.error.URLError("Name or service not known")

    assert hp.check_pack("https://x", "anna", info_of(b""), forbidden).problem == "HTTP 401"
    problem = hp.check_pack("https://x", "anna", info_of(b""), offline).problem
    assert problem is not None and problem.startswith("could not download")


def test_every_pack_is_checked_and_each_wrong_one_logged(
    site: str, caplog: pytest.LogCaptureFixture
) -> None:
    packs = {"bob": info_of(b"bob's pack"), "anna": info_of(b"anna's pack"), "carol": info_of(b"")}
    seen: list[str] = []
    with caplog.at_level(logging.INFO):
        checks = hp.check_all(site, packs, report=lambda c: seen.append(c.name))
    assert seen == ["anna", "bob", "carol"]
    assert [c.problem is None for c in checks] == [True, True, False]
    wrong = [r for r in caplog.records if r.message == "Hosted pack is wrong"]
    assert [r.person for r in wrong] == ["carol"]  # type: ignore[attr-defined]
    done = next(r for r in caplog.records if r.message == "Checked hosted packs")
    assert (done.ok, done.wrong) == (2, 1)  # type: ignore[attr-defined]


def test_the_opener_sends_a_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[Any] = []

    def urlopen(request: Any, timeout: float) -> BinaryIO:
        asked.append((request.full_url, request.get_header("User-agent"), timeout))
        return io.BytesIO(b"")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    hp._open("https://x/anna.zip", 5.0)
    assert asked == [("https://x/anna.zip", "imageskin", 5.0)]


def write_packs(tmp_path: Path, packs: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "packs.json"
    file.write_text(json.dumps(packs))
    load = start_now.load_packs
    monkeypatch.setattr(start_now, "load_packs", lambda: load(file))


def test_the_command_passes_when_every_pack_matches(
    site: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_packs(tmp_path, {"anna": info_of(b"anna's pack")}, monkeypatch)
    monkeypatch.setenv(URL_VARIABLE, site)  # the address Start now uses
    assert main(["check-packs"]) == 0
    out = capsys.readouterr().out
    assert f"Checking the default people at {site}" in out
    assert "1 of 1 packs match" in out


def test_the_command_fails_when_a_pack_is_wrong(
    site: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_packs(tmp_path, {"anna": info_of(b"anna's pack"), "dan": info_of(b"")}, monkeypatch)
    assert main(["check-packs", "--url", site]) == 1
    out = capsys.readouterr().out
    assert "WRONG dan: not on the site (404)" in out
    assert "1 of 2 packs match" in out
