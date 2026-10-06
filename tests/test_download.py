import hashlib
import http.server
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from imageskin.download import DownloadError, download

DATA = bytes(range(256)) * 4096  # 1 MB
SHA = hashlib.sha256(DATA).hexdigest()


class Server(http.server.ThreadingHTTPServer):
    cut_at: int | None = None  # close the connection after this many bytes, once
    ignore_range = False
    requests: list[str | None]


class Handler(http.server.BaseHTTPRequestHandler):
    server: Server

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        rng = self.headers.get("Range")
        self.server.requests.append(rng)
        start = 0
        if rng and not self.server.ignore_range:
            start = int(rng.removeprefix("bytes=").rstrip("-"))
        body = DATA[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        cut = self.server.cut_at
        if cut is not None:
            self.server.cut_at = None
            self.wfile.write(body[:cut])
            return
        self.wfile.write(body)


@pytest.fixture
def server() -> Iterator[Server]:
    srv = Server(("127.0.0.1", 0), Handler)
    srv.requests = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()


def url(srv: Server) -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}/file.bin"


def no_sleep(_: float) -> None:
    pass


def test_downloads_and_verifies(server: Server, tmp_path: Path) -> None:
    dest = tmp_path / "sub" / "file.bin"
    download(url(server), dest, len(DATA), SHA, sleep=no_sleep)
    assert dest.read_bytes() == DATA
    assert not (tmp_path / "sub" / "file.bin.part").exists()


def test_skips_verified_file(server: Server, tmp_path: Path) -> None:
    dest = tmp_path / "file.bin"
    dest.write_bytes(DATA)
    download(url(server), dest, len(DATA), SHA, sleep=no_sleep)
    assert server.requests == []


def test_resumes_after_dropped_connection(server: Server, tmp_path: Path) -> None:
    server.cut_at = 300_000
    dest = tmp_path / "file.bin"
    download(url(server), dest, len(DATA), SHA, sleep=no_sleep, log_every=0)
    assert dest.read_bytes() == DATA
    assert server.requests == [None, "bytes=300000-"]


def test_resumes_partial_file_from_earlier_run(server: Server, tmp_path: Path) -> None:
    dest = tmp_path / "file.bin"
    (tmp_path / "file.bin.part").write_bytes(DATA[:1000])
    download(url(server), dest, len(DATA), SHA, sleep=no_sleep)
    assert dest.read_bytes() == DATA
    assert server.requests == ["bytes=1000-"]


def test_restarts_when_server_ignores_range(server: Server, tmp_path: Path) -> None:
    server.ignore_range = True
    dest = tmp_path / "file.bin"
    (tmp_path / "file.bin.part").write_bytes(DATA[:1000])
    download(url(server), dest, len(DATA), SHA, sleep=no_sleep)
    assert dest.read_bytes() == DATA


def test_discards_oversized_partial(server: Server, tmp_path: Path) -> None:
    dest = tmp_path / "file.bin"
    (tmp_path / "file.bin.part").write_bytes(DATA + b"extra")
    download(url(server), dest, len(DATA), SHA, sleep=no_sleep)
    assert dest.read_bytes() == DATA


def test_checksum_mismatch_deletes_partial(server: Server, tmp_path: Path) -> None:
    dest = tmp_path / "file.bin"
    with pytest.raises(DownloadError, match="checksum mismatch"):
        download(url(server), dest, len(DATA), "0" * 64, sleep=no_sleep)
    assert not dest.exists()
    assert not (tmp_path / "file.bin.part").exists()


def test_gives_up_after_retries_without_progress(tmp_path: Path) -> None:
    waits: list[float] = []
    with pytest.raises(DownloadError, match="gave up after 2 tries"):
        download(
            "http://127.0.0.1:9/nothing",
            tmp_path / "f.bin",
            10,
            SHA,
            timeout=1,
            retries=2,
            sleep=waits.append,
        )
    assert waits == [2.0, 4.0]
