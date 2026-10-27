"""The machine's resources for the admin dashboard (roadmap R152, item 124).

For CPU, memory and disk: what is available, what is used and what remains, each against Oracle
Cloud's Always Free limit, where the hosted site runs, or the machine's own amount where it has
less, and a colour for what remains. In the app's container the machine's load, memory and the
disk under the data volume are the machine's own, so no more is needed to read them.
"""

import logging
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psutil

from imageskin.network import FREE_OUTBOUND, NetworkMonth

logger = logging.getLogger(__name__)

GB = 1000**3
GIB = 1024**3

# Oracle Cloud's Always Free tier: Ampere A1 cores and memory, and block storage in all.
FREE_CPU_CORES = 4
FREE_MEMORY = 24 * GIB
FREE_DISK = 200 * GB

# Where the app's container has a memory cap (cgroup v2), the app's own share is shown too.
CGROUP = Path("/sys/fs/cgroup")


@dataclass(frozen=True)
class Thresholds:
    """The colours' thresholds as the percentage remaining (item 125's recommended ones)."""

    blue_above: float = 60
    orange_below: float = 30
    red_below: float = 15


RECOMMENDED = Thresholds()


def colour(percent_remaining: float | None, thresholds: Thresholds = RECOMMENDED) -> str:
    """Blue (more than enough), green, orange (time to act) or red (running out)."""
    if percent_remaining is None:
        return "unknown"
    if percent_remaining < thresholds.red_below:
        return "red"
    if percent_remaining < thresholds.orange_below:
        return "orange"
    if percent_remaining > thresholds.blue_above:
        return "blue"
    return "green"


@dataclass
class Resource:
    name: str  # "cpu", "memory", "disk" or "network"
    unit: str  # "cores" or "bytes"
    # None when it couldn't be read: shown as unknown, never as zero.
    available: float | None
    used: float | None
    remaining: float | None
    percent_remaining: float | None
    colour: str
    # The free tier's limit, and whether `available` is it ("free tier") or the machine's own
    # smaller amount ("machine").
    free_tier: float
    basis: str
    details: dict[str, Any]


def resource(
    name: str,
    unit: str,
    free_tier: float,
    machine: float | None,
    used: float | None,
    thresholds: Thresholds,
    details: dict[str, Any],
    capped: bool = True,
) -> Resource:
    """`capped`: held to the free tier's limit when the machine has more. The disk isn't, as
    the limit is for every disk together and what matters is the space left on this one."""
    if machine is None or used is None:
        return Resource(name, unit, None, None, None, None, "unknown", free_tier, "", details)
    available = min(free_tier, machine) if capped else machine
    used = min(max(used, 0.0), available)
    remaining = available - used
    percent = round(100 * remaining / available, 1) if available else 0.0
    return Resource(
        name,
        unit,
        available,
        used,
        remaining,
        percent,
        colour(percent, thresholds),
        free_tier,
        "free tier" if capped and free_tier <= machine else "machine",
        details,
    )


class ResourceReader:
    """Reads the resources; the paths are for tests."""

    def __init__(
        self, data_home: Path, cgroup: Path = CGROUP, network: NetworkMonth | None = None
    ) -> None:
        self.data_home = data_home
        self.cgroup = cgroup
        self.network_month = network
        self._errors_logged: set[str] = set()

    def read(self, thresholds: Thresholds = RECOMMENDED) -> dict[str, Any]:
        started = time.perf_counter()
        resources = [self.cpu(thresholds), self.memory(thresholds), self.disk(thresholds)]
        if self.network_month is not None:
            resources.append(self.network(self.network_month, thresholds))
        logger.debug(
            "Resources read",
            extra={
                "colours": {r.name: r.colour for r in resources},
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return {
            "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "thresholds": asdict(thresholds),
            "resources": [asdict(r) for r in resources],
        }

    def _failed(self, what: str, error: Exception) -> None:
        """Log a reading that failed, once for each kind, as the dashboard reads every 10 s."""
        key = f"{what}: {type(error).__name__}"
        if key not in self._errors_logged:
            self._errors_logged.add(key)
            logger.error("Could not read a resource", extra={"resource": what, "error": str(error)})

    def cpu(self, thresholds: Thresholds) -> Resource:
        """Cores busy over the last 15 minutes, so a short burst doesn't change the colour."""
        details: dict[str, Any] = {}
        cores = used = None
        try:
            cores = float(psutil.cpu_count() or 0) or None
            load_1, load_5, load_15 = psutil.getloadavg()
            # Since the last read: the first read has nothing to compare with, and says 0.
            details = {
                "load_1": round(load_1, 2),
                "load_5": round(load_5, 2),
                "load_15": round(load_15, 2),
                "percent_now": psutil.cpu_percent(interval=None),
            }
            used = load_15
        except (OSError, RuntimeError) as e:
            self._failed("cpu", e)
        return resource("cpu", "cores", FREE_CPU_CORES, cores, used, thresholds, details)

    def memory(self, thresholds: Thresholds) -> Resource:
        details: dict[str, Any] = {}
        total = used = None
        try:
            memory = psutil.virtual_memory()
            total, used = float(memory.total), float(memory.total - memory.available)
            details = self._app_memory()
        except (OSError, RuntimeError) as e:
            self._failed("memory", e)
        return resource("memory", "bytes", FREE_MEMORY, total, used, thresholds, details)

    def _app_memory(self) -> dict[str, Any]:
        """The app's own use under its container's cap, when it has one (compose.yaml's)."""
        try:
            cap = (self.cgroup / "memory.max").read_text().strip()
            current = (self.cgroup / "memory.current").read_text().strip()
        except FileNotFoundError:
            return {}  # not in a container, or no cgroup v2
        except OSError as e:
            self._failed("app memory", e)
            return {}
        if cap == "max" or not cap.isdigit() or not current.isdigit():
            return {}
        return {"app_used": int(current), "app_cap": int(cap)}

    def disk(self, thresholds: Thresholds) -> Resource:
        """The disk the app's data is on; the free tier's 200 GB is for every disk together."""
        total = used = None
        try:
            usage = shutil.disk_usage(self.data_home if self.data_home.exists() else Path.home())
            # Free, not total less used, as the disk keeps some back: what can still be written.
            total, used = float(usage.total), float(usage.total - usage.free)
        except OSError as e:
            self._failed("disk", e)
        details = {"path": str(self.data_home)}
        return resource("disk", "bytes", FREE_DISK, total, used, thresholds, details, capped=False)

    def network(self, month: NetworkMonth, thresholds: Thresholds) -> Resource:
        """Sent this month against the free tier's 10 TB; inbound is free, so only shown (R153)."""
        details: dict[str, Any] = {}
        sent = None
        try:
            details = month.reading()
            sent = float(details["sent"])
        except (OSError, RuntimeError, ValueError) as e:
            self._failed("network", e)
        return resource("network", "bytes", FREE_OUTBOUND, FREE_OUTBOUND, sent, thresholds, details)
