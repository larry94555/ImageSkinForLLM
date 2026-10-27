"""The machine's network use this month, for the admin dashboard (roadmap R153, item 124).

Oracle Cloud's Always Free tier allows 10 TB of outbound data a month; inbound is free. A network
card's counters start again at zero when the machine restarts, so the bytes sent and received
are added up into `network-month.json` in the app's home folder each minute, and the month's
totals survive a restart of the app or the machine. They start again on the 1st of each month,
in UTC, as Oracle counts.

In the app's container the network card is the container's own, so `compose.yaml` mounts the
host's `/proc` at `/host/proc`, and the machine's card is read from its first process's
`net/dev`. Without it (a laptop), psutil reads the computer's own cards.
"""

import calendar
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

logger = logging.getLogger(__name__)

FILENAME = "network-month.json"
FREE_OUTBOUND = 10 * 1000**4  # 10 TB a month
HOST_NET_DEV = Path("/host/proc/1/net/dev")
SAMPLE_S = 60.0
# Not the machine's own traffic to the internet: loopback, Docker's and other virtual cards, and
# tunnels, whose traffic is counted again on the real card.
VIRTUAL = (
    "lo",
    "docker",
    "veth",
    "br-",
    "ifb",
    "virbr",
    "cni",
    "flannel",
    "tun",
    "wg",
    "tailscale",
)


@dataclass(frozen=True)
class Counters:
    sent: int
    received: int


def is_virtual(name: str) -> bool:
    return name.startswith(VIRTUAL)


def parse_net_dev(text: str) -> Counters:
    """The bytes sent and received on the real cards in a `/proc/<pid>/net/dev` file."""
    sent = received = 0
    for line in text.splitlines()[2:]:
        name, _, fields = line.partition(":")
        values = fields.split()
        if is_virtual(name.strip()) or len(values) < 9:
            continue
        received += int(values[0])
        sent += int(values[8])
    return Counters(sent, received)


def read_counters(host_net_dev: Path = HOST_NET_DEV) -> tuple[Counters, str]:
    """The machine's counters, and where from: "machine" through the host's /proc, or "this
    computer" through psutil."""
    if host_net_dev.exists():
        return parse_net_dev(host_net_dev.read_text()), "machine"
    cards = psutil.net_io_counters(pernic=True)
    real = [c for name, c in cards.items() if not is_virtual(name)]
    return Counters(
        sum(c.bytes_sent for c in real), sum(c.bytes_recv for c in real)
    ), "this computer"


def month_of(now: datetime) -> str:
    return now.strftime("%Y-%m")


def month_fraction(now: datetime) -> float:
    """How much of the month (UTC) has gone."""
    days = calendar.monthrange(now.year, now.month)[1]
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (now - start).total_seconds() / (days * 86400)


class NetworkMonth:
    """This month's totals, kept in a file in the app's home folder."""

    def __init__(
        self,
        home: Path,
        counters: Callable[[], tuple[Counters, str]] = read_counters,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.path = home / FILENAME
        self.counters = counters
        self.now = now
        self._lock = threading.Lock()
        self._previous: tuple[float, Counters] | None = None  # for the rate now
        self._rate = Counters(0, 0)
        self._source = ""
        self._stop = threading.Event()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and all(
                isinstance(data.get(k), int)
                for k in ("sent", "received", "last_sent", "last_received")
            ):
                return data
            logger.error(
                "Network month file is not valid; starting again", extra={"path": str(self.path)}
            )
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            logger.error(
                "Could not read the network month", extra={"path": str(self.path), "error": str(e)}
            )
        return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        part = self.path.with_suffix(".part")
        part.write_text(json.dumps(data), encoding="utf-8")
        os.replace(part, self.path)

    def sample(self) -> dict[str, Any]:
        """Add what was sent and received since the last sample to this month's totals."""
        with self._lock:
            counters, self._source = self.counters()
            now = self.now()
            month = month_of(now)
            data = self._load()
            if not data:
                # The first sample: nothing is known of the traffic before it.
                data = {"month": month, "sent": 0, "received": 0}
            else:
                last = Counters(data["last_sent"], data["last_received"])
                # Counters lower than last time started again (a restart): all of them are new.
                sent = counters.sent - last.sent if counters.sent >= last.sent else counters.sent
                got = (
                    counters.received - last.received
                    if counters.received >= last.received
                    else counters.received
                )
                if data.get("month") != month:
                    logger.info(
                        "Network month started",
                        extra={
                            "month": month,
                            "last_month": data.get("month"),
                            "sent": data["sent"],
                        },
                    )
                    data = {"month": month, "sent": 0, "received": 0}
                data["sent"] += sent
                data["received"] += got
            data["last_sent"], data["last_received"] = counters.sent, counters.received
            self._save(data)
            clock = time.monotonic()
            if self._previous is not None:
                seconds, before = clock - self._previous[0], self._previous[1]
                if (
                    seconds > 0
                    and counters.sent >= before.sent
                    and counters.received >= before.received
                ):
                    self._rate = Counters(
                        round((counters.sent - before.sent) / seconds),
                        round((counters.received - before.received) / seconds),
                    )
            self._previous = (clock, counters)
            return data

    def reading(self) -> dict[str, Any]:
        """This month's totals now, for the dashboard."""
        data = self.sample()
        fraction = month_fraction(self.now())
        # Too early in the month for a fair guess at its end.
        projected = round(data["sent"] / fraction) if fraction >= 1 / 720 else None
        return {
            "month": data["month"],
            "sent": data["sent"],
            "received": data["received"],
            "sent_per_s": self._rate.sent,
            "received_per_s": self._rate.received,
            "projected_sent": projected,
            "source": self._source,
        }

    def keep_sampling(self, every_s: float = SAMPLE_S) -> threading.Thread:
        """Sample in the background, so little is lost if the machine restarts."""

        def run() -> None:
            while True:
                try:
                    self.sample()
                except Exception:
                    logger.exception("Could not read the network counters")
                if self._stop.wait(every_s):
                    return

        thread = threading.Thread(target=run, name="network-month", daemon=True)
        thread.start()
        logger.info("Network month sampling", extra={"path": str(self.path), "every_s": every_s})
        return thread

    def stop(self) -> None:
        """Stop sampling in the background (tests)."""
        self._stop.set()
