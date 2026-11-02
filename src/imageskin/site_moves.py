"""Each existing host's files move to their own site (roadmap R61e, feature item 66).

Before R61 every host shared the one site at the main address. When the server starts, every
host who has no site yet gets one, named from their email, and what they added, by
`owners.json` (R192), moves there: their photos and recordings, with the files made from them
(each photo's prepared face; the voice sample is joined again from the recordings each site
has). The chosen photo goes with its owner, with what was prepared from it. The host who signed
up first (the earliest in hosts.json) also gets what no host added: the photos and recordings
from before host accounts, the conversation and the rest of the person chosen at the main
address. So no host's site is at the main address, which keeps the administrator and, with R62,
the sign-up (Larry, 2026-11-02). What every host could see and change before, the settings and
the Customization, is copied to each new site. The PDFs move in R61f.

It runs at every start and moves only what is still to move, so a start cut short carries on.
"""

import json
import logging
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from imageskin.host_disk import FILENAME as OWNERS_FILE
from imageskin.hosts import DEFAULT_SITE, HostAccounts
from imageskin.photoreal_library import library_key
from imageskin.sites import RESERVED, SiteDirectory, SiteError, site_home
from imageskin.uploads import MEDIA_TYPE

logger = logging.getLogger(__name__)

# What every host shared, copied to each new site as it was (the settings, the LLM chosen with
# its keys, the ChatGPT sign-in, the Customization with its history).
SHARED_FILES = (
    "ui-settings.json",
    "llm.json",
    "chatgpt.json",
    "customization.json",
    "customization.history.json",
)
# What was prepared from the chosen photo, which goes with it.
PREPARED = ("chosen-photo.json", "prepare.json", "review.json", "clips")
PERSON_KINDS = ("photos", "sounds")
# What the main address's site kept that no host added: the first host's site gets it, as they
# had it before (the conversation, the visitors' consent, the default person chosen, the accent
# and ready-made voice chosen, and how far the setup wizard got).
FIRST_HOSTS = (
    "conversation.json",
    "consent.json",
    "default-person.json",
    "accent.json",
    "ready-voice.json",
    "wizard.json",
)


@dataclass(frozen=True)
class Moved:
    site: str
    host: str
    files: int


def site_name(email: str, taken: set[str]) -> str:
    """A subdomain from the email's name, made unique: ann@example.com is ann, then ann-2."""
    base = re.sub(r"[^a-z0-9]+", "-", email.split("@")[0].lower()).strip("-")[:50] or "site"
    name, n = base, 1
    while name in taken or name in RESERVED:
        n += 1
        name = f"{base}-{n}"
    return name


def _read_owners(home: Path) -> dict[str, dict[str, str]]:
    path = home / OWNERS_FILE
    try:
        data: dict[str, dict[str, str]] = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return data


def _write_owners(home: Path, data: dict[str, Any]) -> None:
    home.mkdir(parents=True, exist_ok=True)
    writing = home / f"{OWNERS_FILE}.writing"
    writing.write_text(json.dumps(data, indent=1), encoding="utf-8")
    writing.replace(home / OWNERS_FILE)


def _move(source: Path, target: Path) -> int:
    """Move a file or folder, leaving one already there as it is; the files moved."""
    if not source.exists():
        return 0
    if target.exists():
        logger.warning("Already in the site; left where it was", extra={"path": str(source)})
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    count = sum(1 for p in source.rglob("*") if p.is_file()) if source.is_dir() else 1
    shutil.move(str(source), str(target))
    return count


def _unowned(main: Path, owners: dict[str, dict[str, str]], kind: str) -> list[str]:
    """The ids of the photos or recordings no host added: from before host accounts."""
    folder = main / "uploads" / kind
    stored = sorted(p.stem for p in folder.glob("*.json")) if folder.is_dir() else []
    return [item for item in stored if item not in owners.get(kind, {})]


def _move_person(main: Path, site: Path, email: str, first: bool = False) -> int:
    """Move the host's photos and recordings, with each photo's prepared face, and the chosen
    photo with what was prepared from it when it is theirs. The first host also gets the files
    no host added, the conversation and the rest of the person chosen at the main address. The
    files moved."""
    owners = _read_owners(main)
    theirs = {
        kind: [item for item, who in owners.get(kind, {}).items() if who == email]
        for kind in PERSON_KINDS
    }
    unowned = {kind: _unowned(main, owners, kind) if first else [] for kind in PERSON_KINDS}
    moved = 0
    chosen = _chosen_photo(main)
    for kind in PERSON_KINDS:
        items = theirs[kind] + unowned[kind]
        for item in items:
            for path in sorted((main / "uploads" / kind).glob(f"{item}.*")):
                if kind == "photos" and path.suffix in MEDIA_TYPE:
                    face = main / "photoreal" / library_key(path)
                    moved += _move(face, site / "photoreal" / face.name)
                moved += _move(path, site / "uploads" / kind / path.name)
    if first:
        for name in FIRST_HOSTS:
            moved += _move(main / name, site / name)
    if chosen is not None and chosen in theirs["photos"] + unowned["photos"]:
        for name in PREPARED:
            source = main / "uploads" / name if name == "chosen-photo.json" else main / name
            moved += _move(source, site / source.relative_to(main))
        logger.info("Chosen photo moved with its host", extra={"email": email, "photo": chosen})
    if theirs["sounds"] or unowned["sounds"]:
        # Joined again from the recordings each site has, the next time it is needed.
        (main / "uploads" / "voice-sample.wav").unlink(missing_ok=True)
    # The record of who added them moves with them, so each site counts its host's files.
    kept = {k: {i: w for i, w in v.items() if w != email} for k, v in owners.items()}
    if kept != owners:
        target = _read_owners(site)
        for kind in PERSON_KINDS:
            target.setdefault(kind, {}).update({item: email for item in theirs[kind]})
        _write_owners(site, target)
        _write_owners(main, kept)
    return moved


def _chosen_photo(home: Path) -> str | None:
    try:
        chosen = json.loads((home / "uploads" / "chosen-photo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = chosen.get("id") if isinstance(chosen, dict) else None
    return value if isinstance(value, str) else None


def _copy_shared(main: Path, site: Path) -> int:
    copied = 0
    for name in SHARED_FILES:
        source, target = main / name, site / name
        if source.is_file() and not target.exists():
            site.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied += 1
    return copied


def move_hosts_to_sites(home: Path, hosts: HostAccounts, sites: SiteDirectory) -> list[Moved]:
    """Give every host a site of their own, and move what they added there."""
    start = time.perf_counter()
    try:
        accounts = hosts.accounts()
    except Exception:
        logger.exception("Hosts not moved to their sites: the host accounts can't be read")
        return []
    ordered = sorted(accounts, key=lambda e: (accounts[e].get("created_at", 0), e))
    taken = set(sites.names())
    done: list[Moved] = []
    for n, email in enumerate(ordered):
        site = str(accounts[email].get("site", DEFAULT_SITE))
        copied = 0
        if site == DEFAULT_SITE:
            site = site_name(email, taken)
            try:
                folder = sites.add(site, email)
            except SiteError as e:
                logger.error("Host not moved to a site", extra={"email": email, "error": str(e)})
                continue
            taken.add(site)
            # Once, as the site is made: later, its host's own settings are theirs to change.
            copied = _copy_shared(home, folder)
        folder = site_home(site, home)
        try:
            files = _move_person(home, folder, email, first=n == 0)
        except (OSError, ValueError) as e:
            logger.error(
                "Host's files not moved", extra={"email": email, "site": site, "error": str(e)}
            )
            continue
        if files or copied:
            logger.info(
                "Site moved",
                extra={"site": site, "host": email, "files": files, "shared_copied": copied},
            )
            done.append(Moved(site, email, files))
    if done:
        logger.info(
            "Hosts moved to their sites",
            extra={
                "sites": len(done),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
    return done
