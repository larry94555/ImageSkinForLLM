"""The machine's network use this month (roadmap R153)."""

import json
import logging
import time
from collections import namedtuple
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest
from fastapi.testclient import TestClient

from imageskin.app import create_app
from imageskin.network import (
    FILENAME,
    FREE_OUTBOUND,
    Counters,
    NetworkMonth,
    month_fraction,
    parse_net_dev,
    read_counters,
)
from imageskin.resources import RECOMMENDED, ResourceReader

# The hosted machine's /proc/1/net/dev as Docker leaves it: the real card is ens3.
ZEROS = " 0" * 6  # the other columns: packets, errors and so on


def card(name: str, received: int, sent: int) -> str:
    return f"{name}: {received} 0{ZEROS} {sent} 0{ZEROS}"


NET_DEV = "\n".join(
    [
        "Inter-|   Receive                                                |  Transmit",
        " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets ...",
        card("    lo", 5288160112, 5288160112),
        card("  ens3", 9000000000, 3000000000),
        card("docker0", 500000, 800000),
        card("veth1a2b3c", 700000, 900000),
        card("br-0f9e8d", 100, 200),
    ]
)


def test_only_the_real_card_counts() -> None:
    assert parse_net_dev(NET_DEV) == Counters(sent=3_000_000_000, received=9_000_000_000)


def test_the_hosts_card_is_read_when_mounted(tmp_path: Path) -> None:
    net_dev = tmp_path / "net_dev"
    net_dev.write_text(NET_DEV)
    assert read_counters(net_dev) == (Counters(3_000_000_000, 9_000_000_000), "machine")


def test_without_the_hosts_card_psutil_reads_this_computers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Card = namedtuple("Card", "bytes_sent bytes_recv")
    cards = {"lo": Card(50, 50), "eth0": Card(10, 20), "wlan0": Card(1, 2), "docker0": Card(7, 7)}
    monkeypatch.setattr(psutil, "net_io_counters", lambda pernic: cards)
    assert read_counters(tmp_path / "none") == (Counters(11, 22), "this computer")


class Machine:
    """A network card's counters and the time, moved on by the tests."""

    def __init__(self) -> None:
        self.counters = Counters(1000, 5000)
        self.time = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    def read(self) -> tuple[Counters, str]:
        return self.counters, "machine"

    def send(self, sent: int, received: int = 0) -> None:
        self.counters = Counters(self.counters.sent + sent, self.counters.received + received)


def month(home: Path, machine: Machine) -> NetworkMonth:
    return NetworkMonth(home, counters=machine.read, now=lambda: machine.time)


def test_traffic_is_added_up_from_the_first_sample(tmp_path: Path) -> None:
    machine = Machine()
    network = month(tmp_path, machine)
    assert network.sample()["sent"] == 0  # nothing is known of what came before
    machine.send(300, 700)
    network.sample()
    machine.send(200)
    data = network.sample()
    assert (data["sent"], data["received"], data["month"]) == (500, 700, "2026-10")
    assert json.loads((tmp_path / FILENAME).read_text())["sent"] == 500


def test_the_totals_survive_a_restart_of_the_app_and_of_the_machine(tmp_path: Path) -> None:
    machine = Machine()
    month(tmp_path, machine).sample()
    machine.send(400)
    month(tmp_path, machine).sample()  # a new app, reading the file
    machine.counters = Counters(90, 10)  # the machine restarted: its counters began again
    data = month(tmp_path, machine).sample()
    assert (data["sent"], data["received"]) == (490, 10)
    machine.send(10)
    assert month(tmp_path, machine).sample()["sent"] == 500


def test_a_new_month_starts_again(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    machine = Machine()
    network = month(tmp_path, machine)
    network.sample()
    machine.send(400)
    network.sample()
    machine.time = datetime(2026, 11, 1, 0, 5, tzinfo=UTC)
    machine.send(25)
    with caplog.at_level(logging.INFO):
        data = network.sample()
    assert (data["month"], data["sent"]) == ("2026-11", 25)
    started = [r for r in caplog.records if r.message == "Network month started"]
    assert [(r.__dict__["last_month"], r.__dict__["sent"]) for r in started] == [("2026-10", 400)]


@pytest.mark.parametrize("text", ["{not json", "[]", '{"sent": "a lot"}'])
def test_a_file_that_cant_be_used_starts_again(
    tmp_path: Path, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / FILENAME).write_text(text)
    assert month(tmp_path, Machine()).sample()["sent"] == 0
    assert "network month" in caplog.text.lower()


def test_how_much_of_the_month_has_gone() -> None:
    assert month_fraction(datetime(2026, 10, 1, tzinfo=UTC)) == 0
    assert month_fraction(datetime(2026, 10, 16, 12, tzinfo=UTC)) == 0.5  # 31 days
    assert month_fraction(datetime(2026, 2, 15, tzinfo=UTC)) == 0.5  # 28 days


def test_the_reading_has_the_rate_and_the_months_end(tmp_path: Path) -> None:
    machine = Machine()
    network = month(tmp_path, machine)
    first = network.reading()
    assert first["sent_per_s"] == 0 and first["source"] == "machine"
    time.sleep(0.05)
    machine.send(2_000_000, 1_000_000)
    reading = network.reading()
    assert reading["sent"] == 2_000_000 and reading["received"] == 1_000_000
    assert reading["sent_per_s"] > 1_000_000  # 2 MB in about 50 ms
    assert reading["projected_sent"] == 4_000_000  # half the month gone
    machine.time = datetime(2026, 10, 1, 0, 30, tzinfo=UTC)  # too early to tell
    machine.send(1)
    assert network.reading()["projected_sent"] is None


def test_the_dashboard_colours_whats_left_of_the_10_tb(tmp_path: Path) -> None:
    machine = Machine()
    network = month(tmp_path, machine)
    network.sample()
    machine.send(8_000 * 1000**3)  # 8 TB
    entry = ResourceReader(tmp_path, network=network).network(network, RECOMMENDED)
    assert entry.available == FREE_OUTBOUND and entry.remaining == 2_000 * 1000**3
    assert entry.percent_remaining == 20.0 and entry.colour == "orange"
    assert entry.basis == "free tier" and entry.details["received"] == 0


def test_counters_that_cant_be_read_show_as_unknown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def fails() -> tuple[Counters, str]:
        raise OSError("Permission denied: /host/proc/1/net/dev")

    network = NetworkMonth(tmp_path, counters=fails)
    entry = ResourceReader(tmp_path, network=network).network(network, RECOMMENDED)
    assert entry.colour == "unknown" and entry.remaining is None
    assert "Could not read a resource" in caplog.text


def test_sampling_in_the_background(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    machine = Machine()
    calls = []

    def read() -> tuple[Counters, str]:
        calls.append(1)
        if len(calls) == 2:
            raise OSError("gone for a moment")
        return machine.read()

    network = NetworkMonth(tmp_path, counters=read)
    with caplog.at_level(logging.INFO):
        thread = network.keep_sampling(every_s=0.01)
        deadline = time.monotonic() + 5
        while len(calls) < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        network.stop()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(calls) >= 4  # it went on after the error
    assert "Network month sampling" in caplog.text
    assert "Could not read the network counters" in caplog.text


def test_the_api_has_the_network(tmp_path: Path) -> None:
    (tmp_path / "admin.toml").write_text('password = "secret"\n')
    browser = TestClient(create_app(tmp_path))
    browser.post("/api/admin/sign-in", json={"password": "secret"})
    resources = browser.get("/api/admin/resources").json()["resources"]
    network = resources[-1]
    assert network["name"] == "network" and network["available"] == FREE_OUTBOUND
    assert network["details"]["month"] == datetime.now(UTC).strftime("%Y-%m")
    assert (tmp_path / FILENAME).exists()
