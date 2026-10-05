"""Download one file with progress logging, a stall timeout and resume on retry.

Bytes land in `<dest>.part`. When a connection stalls or drops, the next try asks the
server for the rest of the file (an HTTP Range request) instead of starting over, and
an interrupted run picks up the same `.part` file when it is started again.
"""

import hashlib
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("compare.download")

CHUNK = 256 * 1024
MB = 1024 * 1024


class DownloadError(RuntimeError):
    pass


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download(
    url: str,
    dest: Path,
    size: int,
    sha256: str,
    *,
    timeout: float = 30.0,
    retries: int = 5,
    log_every: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Fetch `url` into `dest` unless a verified copy is already there.

    `timeout` is how long a connect or a single read may hang before the try counts as
    stalled. `retries` is how many tries in a row may fail without any new bytes before
    giving up; a try that made progress resets the count.
    """
    name = dest.name
    if dest.exists() and dest.stat().st_size == size and sha256_of(dest) == sha256:
        log.info("%s: already downloaded (%.1f MB), skipping", name, size / MB)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    start = time.perf_counter()
    failures = 0
    while True:
        have = part.stat().st_size if part.exists() else 0
        if have > size:
            log.warning("%s: partial file is larger than expected; starting over", name)
            part.unlink()
            have = 0
        if have < size:
            if have:
                log.info("%s: resuming at %.1f of %.1f MB", name, have / MB, size / MB)
            else:
                log.info("%s: downloading %.1f MB from %s", name, size / MB, url.split("?")[0])
            try:
                _fetch(url, part, have, size, timeout, log_every)
            except (OSError, urllib.error.URLError, DownloadError) as exc:
                got = part.stat().st_size if part.exists() else 0
                failures = 0 if got > have else failures + 1
                if failures > retries:
                    raise DownloadError(
                        f"{name}: gave up after {retries} tries with no progress "
                        f"({got / MB:.1f} of {size / MB:.1f} MB saved in {part}; "
                        f"run again to resume): {exc}"
                    ) from exc
                wait = min(2.0 ** max(failures, 1), 60.0)
                log.warning(
                    "%s: download interrupted at %.1f of %.1f MB (%s); retrying in %.0f s",
                    name,
                    got / MB,
                    size / MB,
                    exc,
                    wait,
                )
                sleep(wait)
                continue
        actual = sha256_of(part)
        if actual != sha256:
            part.unlink()
            raise DownloadError(
                f"{name}: checksum mismatch (got {actual}, expected {sha256}); "
                "the partial file was deleted, run again to download it fresh"
            )
        part.replace(dest)
        log.info("%s: done in %.1f s", name, time.perf_counter() - start)
        return


def _fetch(url: str, part: Path, have: int, size: int, timeout: float, log_every: float) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "imageskin-mouth-compare"})
    if have:
        request.add_header("Range", f"bytes={have}-")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if have and response.status != 206:
            # Server ignored the Range header and sent the whole file; start over.
            log.info("%s: server cannot resume; restarting from 0 MB", part.name)
            have = 0
        mode = "ab" if have else "wb"
        done = have
        t0 = last = time.perf_counter()
        with part.open(mode) as f:
            while chunk := response.read(CHUNK):
                f.write(chunk)
                done += len(chunk)
                now = time.perf_counter()
                if now - last >= log_every:
                    speed = (done - have) / (now - t0)
                    left = (size - done) / speed if speed else 0.0
                    log.info(
                        "%s: %.1f of %.1f MB (%d%%), %.2f MB/s, about %.0f s left",
                        part.name.removesuffix(".part"),
                        done / MB,
                        size / MB,
                        100 * done // size,
                        speed / MB,
                        left,
                    )
                    last = now
    if done < size:
        raise DownloadError(f"connection closed early at {done / MB:.1f} MB")
