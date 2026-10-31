"""The change history of each part of the customization (roadmap R95, item 88; Larry's review on
PR #258).

Each part has its own history: the identity, the goals, and each feature's guidelines. A save
adds a change to each part it changed, and nothing to the others. Each change keeps the part's
whole value, when it was made and what made it: `shipped` (what there was before the first change
to the part), `generated` (drafted by the LLM, R93, once saved) or `saved` (an edit on the
Customization page). One change of each part is its current one. **Go back** makes an earlier
change the current one, setting only that part, and adds no change: only an edit after it does,
so the change gone back from stays in the list. All of them are kept, in
`customization.history.json` in the app's home folder *(default)*.
"""

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imageskin.customization import (
    FEATURES,
    Customization,
    as_generated,
    guidelines_of,
    is_edited,
    with_goals,
    with_guidelines,
    with_identity,
)

logger = logging.getLogger(__name__)

HISTORY_FILE = "customization.history.json"
MADE_BY = ("shipped", "generated", "saved")
PARTS = ("identity", "goals")


class NoSuchChange(KeyError):
    pass


def parts() -> list[str]:
    """Every part with its own history, in the order of the Customization page."""
    return [*PARTS, *FEATURES]


def label(part: str) -> str:
    return {"identity": "Identity", "goals": "Goals"}.get(part) or FEATURES[part].label


def value_of(customization: Customization, part: str) -> Any:
    """A part's whole value: the identity's parts, the goals, or a feature's guidelines as edited
    (None when as shipped)."""
    if part == "identity":
        return asdict(customization.identity)
    if part == "goals":
        return list(customization.goals)
    return guidelines_of(customization, part) if is_edited(customization, part) else None


def with_value(customization: Customization, part: str, value: Any, made_by: str) -> Customization:
    """`customization` with only `part` set to `value`, as a change of it made by `made_by`."""
    if part == "identity":
        return with_identity(customization, value)
    if part == "goals":
        return with_goals(customization, value)
    changed = with_guidelines(customization, part, value)
    return (
        as_generated(changed, [part]) if made_by == "generated" and value is not None else changed
    )


@dataclass(frozen=True)
class Change:
    number: int
    made_at: str  # ISO 8601, UTC
    made_by: str  # one of MADE_BY
    value: Any

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PartHistory:
    part: str
    changes: tuple[Change, ...]
    current: int

    def change(self, number: int) -> Change:
        for c in self.changes:
            if c.number == number:
                return c
        raise NoSuchChange(number)

    def shown(self) -> dict[str, Any]:
        """As the History list shows it: newest first."""
        return {
            "part": self.part,
            "label": label(self.part),
            "current": self.current,
            "changes": [c.as_dict() for c in reversed(self.changes)],
        }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


class History:
    """The history of each part, kept in `customization.history.json` in `home`."""

    def __init__(self, home: Path) -> None:
        self.path = home / HISTORY_FILE
        self._lock = threading.Lock()

    def _load(self) -> dict[str, PartHistory]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.error("Customization history can't be read", extra={"error": str(e)})
            return {}
        found = {}
        for part, kept in (data.get("parts") or {}).items() if isinstance(data, dict) else ():
            try:
                changes = tuple(
                    Change(int(c["number"]), str(c["made_at"]), c["made_by"], c.get("value"))
                    for c in kept["changes"]
                )
                if part not in parts() or any(c.made_by not in MADE_BY for c in changes):
                    raise ValueError(f"{part} is not a part, or a change has no maker")
                found[part] = PartHistory(part, changes, int(kept["current"]))
            except (KeyError, TypeError, ValueError) as e:
                logger.error(
                    "Customization history can't be read", extra={"part": part, "error": str(e)}
                )
        return found

    def _save(self, histories: dict[str, PartHistory]) -> None:
        data = {
            "parts": {
                p: {"current": h.current, "changes": [c.as_dict() for c in h.changes]}
                for p, h in histories.items()
            }
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.stem}.saving.json")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def saved(
        self,
        before: Customization,
        shipped: bool,
        after: Customization,
        made_by: str = "saved",
        gone_back: tuple[str, int] | None = None,
        **note: Any,
    ) -> list[str]:
        """Note a save: a new current change for each part it changed, the part's value before it
        kept first if the part had none; or, for a go-back, only which change is current. A
        history that can't be written is logged and the save stands. The parts changed."""
        start = time.perf_counter()
        changed = [p for p in parts() if value_of(before, p) != value_of(after, p)]
        if gone_back is None and not changed:
            return []
        try:
            with self._lock:
                histories = self._load()
                if gone_back is not None:
                    part, number = gone_back
                    h = histories[part]
                    histories[part] = PartHistory(part, h.changes, number)
                else:
                    for part in changed:
                        histories[part] = self._added(histories.get(part), part, before, shipped)
                        h = histories[part]
                        new = Change(
                            h.changes[-1].number + 1, _now(), made_by, value_of(after, part)
                        )
                        histories[part] = PartHistory(part, (*h.changes, new), new.number)
                self._save(histories)
        except (OSError, KeyError) as e:
            logger.error("Customization change can't be kept", extra={"error": str(e)})
            return changed
        if gone_back is None:
            logger.info(
                "Customization change kept",
                extra={
                    "parts": changed,
                    "made_by": made_by,
                    "numbers": [histories[p].current for p in changed],
                    "duration_ms": ms_since(start),
                },
            )
        return changed

    @staticmethod
    def _added(
        h: PartHistory | None, part: str, before: Customization, shipped: bool
    ) -> PartHistory:
        """The part's history, starting with its value before the first change to it."""
        if h is not None:
            return h
        first = value_of(before, part)
        as_shipped = shipped or first == value_of(Customization(), part)
        return PartHistory(
            part, (Change(1, _now(), "shipped" if as_shipped else "saved", first),), 1
        )

    def histories(self) -> list[PartHistory]:
        """The parts that have changed, in the order of the page."""
        found = self._load()
        return [found[p] for p in parts() if p in found]

    def part(self, part: str) -> PartHistory:
        found = self._load().get(part)
        if found is None:
            raise NoSuchChange(part)
        return found
