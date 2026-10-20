"""Check the hosted default people (roadmap R32a).

Downloads every pack in default_people_packs.json from the address Start now uses and compares
its size and SHA-256 with the file, without keeping it: `imageskin check-packs`.
"""

import hashlib
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, BinaryIO

from imageskin.download import CHUNK, MB

logger = logging.getLogger(__name__)

Open = Callable[[str, float], BinaryIO]  # url, timeout: the response


@dataclass(frozen=True)
class PackCheck:
    name: str
    problem: str | None  # None when the pack matches
    bytes: int = 0
    seconds: float = 0.0


def _open(url: str, timeout: float) -> BinaryIO:
    request = urllib.request.Request(url, headers={"User-Agent": "imageskin"})
    response: BinaryIO = urllib.request.urlopen(request, timeout=timeout)
    return response


def check_pack(
    base_url: str, name: str, info: dict[str, Any], opener: Open = _open, timeout: float = 30.0
) -> PackCheck:
    """Download one pack and say what is wrong with it, if anything."""
    url = f"{base_url.rstrip('/')}/{name}.zip"
    digest = hashlib.sha256()
    size = 0
    start = time.perf_counter()
    try:
        with opener(url, timeout) as response:
            while chunk := response.read(CHUNK):
                digest.update(chunk)
                size += len(chunk)
    except urllib.error.HTTPError as e:
        problem = "not on the site (404)" if e.code == 404 else f"HTTP {e.code}"
        return PackCheck(name, problem)
    except (OSError, urllib.error.URLError) as e:
        return PackCheck(name, f"could not download: {e}")
    seconds = time.perf_counter() - start
    if size != int(info["bytes"]):
        return PackCheck(name, f"{size} bytes, expected {info['bytes']}", size, seconds)
    if digest.hexdigest() != info["sha256"]:
        return PackCheck(name, "SHA-256 differs", size, seconds)
    return PackCheck(name, None, size, seconds)


def check_all(
    base_url: str,
    packs: dict[str, dict[str, Any]],
    opener: Open = _open,
    report: Callable[[PackCheck], None] = lambda check: None,
) -> list[PackCheck]:
    """Check every pack in turn, telling `report` about each as it is done."""
    logger.info("Checking hosted packs", extra={"url": base_url, "packs": len(packs)})
    start = time.perf_counter()
    checks = []
    for name in sorted(packs):
        check = check_pack(base_url, name, packs[name], opener)
        if check.problem:
            logger.error(
                "Hosted pack is wrong",
                extra={"person": name, "url": base_url, "problem": check.problem},
            )
        report(check)
        checks.append(check)
    total = sum(c.bytes for c in checks)
    seconds = time.perf_counter() - start
    logger.info(
        "Checked hosted packs",
        extra={
            "url": base_url,
            "ok": sum(c.problem is None for c in checks),
            "wrong": sum(c.problem is not None for c in checks),
            "mb": round(total / MB, 1),
            "duration_s": round(seconds, 1),
        },
    )
    return checks


def line(check: PackCheck) -> str:
    """One line of the report, such as `ok    animated_female_boss  26.1 MB  3.2 s`."""
    if check.problem:
        return f"WRONG {check.name}: {check.problem}"
    return f"ok    {check.name}  {check.bytes / MB:.1f} MB  {check.seconds:.1f} s"
