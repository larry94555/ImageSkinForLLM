"""Every saved change to the customization kept as a version (roadmap R95, item 88).

Each version is a copy of the whole of `customization.json` (identity, goals and every feature's
guidelines), with when it was made and what made it: `shipped` (what there was before the first
save), `generated` (a draft by the LLM, R93, once saved), `saved` (an edit on the Customization
page) or `gone back to` (a copy of an earlier version). They are kept in `customization.history/`
in the app's home folder, one file a version, all of them *(default)*. Going back saves a copy of
the version as the new latest one, so it can be undone too; a feature added since that version
keeps its current guidelines.
"""

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imageskin.customization import FEATURES, Customization, from_dict

logger = logging.getLogger(__name__)

HISTORY_DIR = "customization.history"
MADE_BY = ("shipped", "generated", "saved", "gone back to")
_NAME = re.compile(r"^(\d{6})\.json$")


class NoSuchVersion(KeyError):
    pass


@dataclass(frozen=True)
class Version:
    number: int
    made_at: str  # ISO 8601, UTC
    made_by: str  # one of MADE_BY
    part: str | None  # what was saved: identity, goals, guidelines, draft
    feature: str | None  # the feature whose guidelines were saved
    back_to: int | None  # for `gone back to`, the version copied
    # The features the app had when it was made, so going back can tell one added since.
    features: tuple[str, ...]
    customization: Customization

    def listed(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "made_at": self.made_at,
            "made_by": self.made_by,
            "part": self.part,
            "feature": self.feature,
            "back_to": self.back_to,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.listed(),
            "features": list(self.features),
            "customization": self.customization.as_dict(),
        }


def _version(data: object) -> Version:
    if not isinstance(data, dict):
        raise ValueError("the version is not a JSON object")
    made_by = data.get("made_by")
    if made_by not in MADE_BY:
        raise ValueError(f"made_by is {made_by!r}")
    known = data.get("features", list(FEATURES))
    if not isinstance(known, list) or not all(isinstance(k, str) for k in known):
        raise ValueError("features is not a list of text")
    return Version(
        number=int(data["number"]),
        made_at=str(data["made_at"]),
        made_by=made_by,
        part=data.get("part"),
        feature=data.get("feature"),
        back_to=data.get("back_to"),
        features=tuple(known),
        customization=from_dict(data.get("customization")),
    )


def restored(version: Version, now: Customization) -> Customization:
    """`version`'s customization, with the guidelines of any feature added since it was made
    kept as they are `now`."""
    added = [key for key in FEATURES if key not in version.features]
    if not added:
        return version.customization
    old = version.customization
    guidelines = {k: v for k, v in old.guidelines.items() if k not in added}
    generated = [k for k in old.generated if k not in added]
    for key in added:
        if key in now.guidelines:
            guidelines[key] = now.guidelines[key]
        if key in now.generated:
            generated.append(key)
    return replace(old, guidelines=guidelines, generated=tuple(generated))


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


class History:
    """The versions in `customization.history/` in `home`, numbered from 1."""

    def __init__(self, home: Path) -> None:
        self.path = home / HISTORY_DIR
        self._lock = threading.Lock()

    def _numbers(self) -> list[int]:
        try:
            names = os.listdir(self.path)
        except FileNotFoundError:
            return []
        return sorted(int(m.group(1)) for n in names if (m := _NAME.match(n)))

    def _file(self, number: int) -> Path:
        return self.path / f"{number:06d}.json"

    def _write(
        self,
        customization: Customization,
        made_by: str,
        part: str | None = None,
        feature: str | None = None,
        back_to: int | None = None,
    ) -> Version:
        numbers = self._numbers()
        version = Version(
            number=(numbers[-1] if numbers else 0) + 1,
            made_at=datetime.now(UTC).isoformat(timespec="seconds"),
            made_by=made_by,
            part=part,
            feature=feature,
            back_to=back_to,
            features=tuple(FEATURES),
            customization=customization,
        )
        self.path.mkdir(parents=True, exist_ok=True)
        path = self._file(version.number)
        tmp = path.with_name(f"{path.stem}.saving.json")
        text = json.dumps(version.as_dict(), ensure_ascii=False, indent=1)
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
        return version

    def saved(
        self,
        before: Customization,
        shipped: bool,
        after: Customization,
        made_by: str = "saved",
        part: str | None = None,
        feature: str | None = None,
        back_to: int | None = None,
    ) -> Version | None:
        """Keep `after`, just saved, as the newest version; the first time, keep `before` as the
        first, so there is a version to go back to. A version that can't be written is logged
        and the save stands."""
        start = time.perf_counter()
        try:
            with self._lock:
                if not self._numbers():
                    self._write(before, "shipped" if shipped else "saved")
                version = self._write(after, made_by, part, feature, back_to)
        except OSError as e:
            logger.error(
                "Customization version can't be saved",
                extra={"path": str(self.path), "error": str(e)},
            )
            return None
        logger.info(
            "Customization version saved",
            extra={
                "version": version.number,
                "made_by": made_by,
                "part": part,
                "feature": feature,
                "back_to": back_to,
                "duration_ms": ms_since(start),
            },
        )
        return version

    def versions(self) -> list[Version]:
        """Every version that can be read, newest first; one that can't is logged and left out."""
        found = []
        for number in reversed(self._numbers()):
            try:
                found.append(self.version(number))
            except NoSuchVersion:
                continue
        return found

    def version(self, number: int) -> Version:
        try:
            return _version(json.loads(self._file(number).read_text(encoding="utf-8")))
        except FileNotFoundError as e:
            raise NoSuchVersion(number) from e
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.error(
                "Customization version can't be read",
                extra={"version": number, "error": str(e)},
            )
            raise NoSuchVersion(number) from e
