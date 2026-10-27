"""The machine's resources for the admin dashboard (roadmap R152)."""

import logging
import shutil
from collections import namedtuple
from pathlib import Path
from typing import Any

import psutil
import pytest
from fastapi.testclient import TestClient

from imageskin.app import create_app
from imageskin.resources import (
    FREE_DISK,
    FREE_MEMORY,
    GB,
    GIB,
    RECOMMENDED,
    ResourceReader,
    Thresholds,
    colour,
)

Memory = namedtuple("Memory", "total available")
Disk = namedtuple("Disk", "total used free")


@pytest.mark.parametrize(
    ("percent", "expected"),
    [
        (100, "blue"),
        (60.1, "blue"),
        (60, "green"),
        (30, "green"),
        (29.9, "orange"),
        (15, "orange"),
        (14.9, "red"),
        (0, "red"),
        (None, "unknown"),
    ],
)
def test_the_recommended_colours(percent: float | None, expected: str) -> None:
    assert colour(percent) == expected


def test_other_thresholds() -> None:
    assert colour(50, Thresholds(blue_above=40, orange_below=20, red_below=5)) == "blue"
    assert colour(50, Thresholds(blue_above=90, orange_below=55, red_below=10)) == "orange"


def machine(
    monkeypatch: pytest.MonkeyPatch,
    cores: int = 4,
    load: tuple[float, float, float] = (1.0, 0.8, 0.5),
    memory: tuple[float, float] = (23.4 * GIB, 16 * GIB),
    disk: tuple[float, float] = (96 * GB, 60 * GB),
) -> None:
    """A machine like the hosted one: 4 cores, about 23.4 GiB the kernel leaves, a 100 GB disk."""
    monkeypatch.setattr(psutil, "cpu_count", lambda: cores)
    monkeypatch.setattr(psutil, "getloadavg", lambda: load)
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 12.5)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: Memory(*memory))
    total, free = disk
    monkeypatch.setattr(shutil, "disk_usage", lambda path: Disk(total, total - free - 1, free))


def by_name(reading: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["name"]: r for r in reading["resources"]}


def test_the_hosted_machine_against_the_free_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch)
    reading = ResourceReader(tmp_path, cgroup=tmp_path / "none").read()
    assert reading["thresholds"] == {"blue_above": 60, "orange_below": 30, "red_below": 15}
    assert reading["read_at"].endswith("Z")
    cpu, memory, disk = by_name(reading).values()

    # The 15-minute load: half a core of 4 is busy.
    assert cpu["available"] == 4 and cpu["basis"] == "free tier" and cpu["used"] == 0.5
    assert cpu["percent_remaining"] == 87.5 and cpu["colour"] == "blue"
    assert cpu["details"] == {"load_1": 1.0, "load_5": 0.8, "load_15": 0.5, "percent_now": 12.5}

    # The machine has a little less than the free tier's 24 GB, so its own amount is used.
    assert memory["available"] == 23.4 * GIB and memory["basis"] == "machine"
    assert memory["free_tier"] == FREE_MEMORY
    assert memory["remaining"] == 16 * GIB and memory["percent_remaining"] == 68.4
    assert memory["colour"] == "blue" and memory["details"] == {}

    # The disk's free space, not its total less used.
    assert disk["available"] == 96 * GB and disk["remaining"] == 60 * GB
    assert disk["free_tier"] == FREE_DISK and disk["basis"] == "machine"
    assert disk["percent_remaining"] == 62.5 and disk["details"] == {"path": str(tmp_path)}


def test_a_bigger_machine_is_held_to_the_free_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch, cores=16, load=(9, 9, 9), memory=(64 * GIB, 40 * GIB))
    cpu, memory, _ = by_name(ResourceReader(tmp_path).read()).values()
    # Busier than the free tier's 4 cores: none left, not a negative amount.
    assert cpu["available"] == 4 and cpu["used"] == 4 and cpu["remaining"] == 0
    assert cpu["colour"] == "red" and cpu["basis"] == "free tier"
    assert memory["available"] == FREE_MEMORY and memory["remaining"] == 0
    assert memory["colour"] == "red"


def test_a_disk_bigger_than_the_free_tier_shows_its_own_free_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The free tier's 200 GB is for every disk together; what matters is what is left on this one.
    machine(monkeypatch, disk=(252 * GB, 26 * GB))
    disk = by_name(ResourceReader(tmp_path).read())["disk"]
    assert disk["available"] == 252 * GB and disk["remaining"] == 26 * GB
    assert disk["basis"] == "machine" and disk["colour"] == "red"


def test_running_low_turns_orange_then_red(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    machine(monkeypatch, memory=(20 * GIB, 5 * GIB), disk=(100 * GB, 10 * GB))
    _, memory, disk = by_name(ResourceReader(tmp_path).read()).values()
    assert memory["colour"] == "orange" and memory["percent_remaining"] == 25.0
    assert disk["colour"] == "red" and disk["percent_remaining"] == 10.0


def test_the_thresholds_given_are_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    machine(monkeypatch)
    reading = ResourceReader(tmp_path).read(
        Thresholds(blue_above=95, orange_below=90, red_below=70)
    )
    assert [r["colour"] for r in reading["resources"]] == ["orange", "red", "red"]


def test_the_apps_share_under_its_containers_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch)
    cgroup = tmp_path / "cgroup"
    cgroup.mkdir()
    (cgroup / "memory.max").write_text(f"{14 * GIB}\n")
    (cgroup / "memory.current").write_text(f"{3 * GIB}\n")
    memory = by_name(ResourceReader(tmp_path, cgroup).read())["memory"]
    assert memory["details"] == {"app_used": 3 * GIB, "app_cap": 14 * GIB}
    (cgroup / "memory.max").write_text("max\n")  # no cap: nothing to show
    assert by_name(ResourceReader(tmp_path, cgroup).read())["memory"]["details"] == {}


def test_an_unreadable_cap_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    machine(monkeypatch)
    cgroup = tmp_path / "cgroup"
    (cgroup / "memory.max").mkdir(parents=True)  # a folder where the file should be
    assert by_name(ResourceReader(tmp_path, cgroup).read())["memory"]["details"] == {}
    assert "Could not read a resource" in caplog.text


def test_a_reading_that_fails_is_unknown_not_zero_and_logged_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    machine(monkeypatch)

    def fails(*args: object, **kwargs: object) -> None:
        raise OSError("no such file: /proc/meminfo")

    monkeypatch.setattr(psutil, "virtual_memory", fails)
    monkeypatch.setattr(psutil, "getloadavg", fails)
    monkeypatch.setattr(shutil, "disk_usage", fails)
    reader = ResourceReader(tmp_path)
    for _ in range(3):
        reading = by_name(reader.read())
    for name in ("cpu", "memory", "disk"):
        assert reading[name]["colour"] == "unknown"
        assert reading[name]["available"] is None and reading[name]["remaining"] is None
    errors = [r for r in caplog.records if r.message == "Could not read a resource"]
    assert sorted(r.__dict__["resource"] for r in errors) == ["cpu", "disk", "memory"]


def test_a_data_folder_not_made_yet_reads_the_home_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch)
    seen: list[Path] = []

    def usage(path: Path) -> Disk:
        seen.append(path)
        return Disk(10, 5, 5)

    monkeypatch.setattr(shutil, "disk_usage", usage)
    ResourceReader(tmp_path / "not yet").read()
    assert seen == [Path.home()]


def test_reading_the_real_machine(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="imageskin.resources"):
        reading = by_name(ResourceReader(tmp_path).read())
    for name in ("cpu", "memory", "disk"):
        assert reading[name]["available"] > 0
        assert reading[name]["colour"] in {"blue", "green", "orange", "red"}
    assert "Resources read" in caplog.text


def test_the_api_is_for_the_administrator_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch)
    (tmp_path / "admin.toml").write_text('password = "secret"\n')
    browser = TestClient(create_app(tmp_path))
    refused = browser.get("/api/admin/resources")
    # No hint of how to get in (Larry's review of #186).
    assert refused.status_code == 401
    assert refused.json() == {"detail": "Not supported at this time."}
    browser.post("/api/admin/sign-in", json={"password": "secret"})
    reading = browser.get("/api/admin/resources").json()
    assert [r["name"] for r in reading["resources"]] == ["cpu", "memory", "disk"]
    assert reading["thresholds"] == {
        "blue_above": RECOMMENDED.blue_above,
        "orange_below": RECOMMENDED.orange_below,
        "red_below": RECOMMENDED.red_below,
    }
