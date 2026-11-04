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
the Customization, is copied to each new site.

Each host's PDFs move the same way (R61f), each with all made from it: what was read from it,
its wiki pages with its outline, the host's edits and the wiki's history. The lessons written
ahead cover every PDF at the main address, so they are removed there, and each site writes its
own again in the background from the PDFs it has.

It runs at every start and moves only what is still to move, so a start cut short carries on.
"""

import filecmp
import json
import logging
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from imageskin.accent import KEPT_SUFFIX
from imageskin.host_disk import FILENAME as OWNERS_FILE
from imageskin.hosts import DEFAULT_SITE, NO_SITE, HostAccounts
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
# What was prepared with the voice sample, so with every recording at the main address: dropped
# when any of those recordings isn't the chosen photo's host's (Codex's review of PR #275).
VOICE_MADE = ("clips", "prepare.json", "prepare.saving.json", "review.json")
VOICE_SAMPLE = Path("uploads") / "voice-sample.wav"
PERSON_KINDS = ("photos", "sounds")
# Where each PDF's files are (R61f): <id>.pdf with its info, what was read from it, and its wiki
# pages, edits and history (<id>.history/).
PDF_FOLDERS = ("pdfs", "read", "wiki")
# The lessons written ahead from every PDF's topics, written again by each site.
LESSONS = Path("content") / "wiki" / "lessons.json"
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
    """Move a file or folder, leaving one already there as it is; the files moved. A file
    already in the site with the same contents (a move cut short) is removed from the source."""
    if not source.exists():
        return 0
    if target.exists():
        if source.is_file() and target.is_file() and filecmp.cmp(source, target, shallow=False):
            source.unlink()
            logger.info("Already in the site; the same file removed", extra={"path": str(source)})
            return 1
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


def _left(main: Path, kind: str, item: str) -> bool:
    """Whether any of the item's files, or its prepared face, is still at the main address."""
    paths = list((main / "uploads" / kind).glob(f"{item}.*"))
    faces = [main / "photoreal" / library_key(p) for p in paths if p.suffix in MEDIA_TYPE]
    return bool(paths) or any(face.exists() for face in faces)


def _remove(path: Path) -> int:
    if path.is_dir():
        count = sum(1 for p in path.rglob("*") if p.is_file())
        shutil.rmtree(path)
        return count
    if path.exists():
        path.unlink()
        return 1
    return 0


def _drop_voice_made(main: Path, owners: dict[str, dict[str, str]], first: str | None) -> int:
    """Before anything moves: drop what was prepared with the voice sample when the sample
    holds a recording that isn't the chosen photo's host's, so no site plays another host's
    voice or shows a voice prepared from it as done. Its host prepares again. The files
    removed. Run before every move, so a start cut short decides as the first did."""
    chosen = _chosen_photo(main)
    if chosen is None or not any((main / name).exists() for name in VOICE_MADE):
        return 0
    owner = owners.get("photos", {}).get(chosen, first)
    sounds = owners.get("sounds", {})
    theirs = {item for item, who in sounds.items() if who == owner}
    if owner == first:
        theirs |= set(_unowned(main, owners, "sounds"))
    folder = main / "uploads" / "sounds"
    stored = {p.stem for p in folder.glob("*.json")} if folder.is_dir() else set()
    others = sorted(stored - theirs)
    if not others:
        return 0
    removed = sum(_remove(main / name) for name in VOICE_MADE)
    removed += _drop_voice_sample(main)
    logger.warning(
        "Prepared voice dropped: other hosts' recordings were in it",
        extra={"photo": chosen, "host": owner, "recordings": others, "files": removed},
    )
    return removed


def _drop_voice_sample(main: Path) -> int:
    """Joined again from the recordings each site has, the next time it is needed."""
    sample = main / VOICE_SAMPLE
    kept = sample.with_name(sample.name + KEPT_SUFFIX)
    return _remove(sample) + _remove(kept)


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
        _drop_voice_sample(main)
    # The record of who added them moves with them, once every file of the item has, so each
    # site counts its host's files; an item with a file left behind stays recorded where it is,
    # and is never taken for one no host added (Codex's review of PR #275).
    gone = {kind: [i for i in theirs[kind] if not _left(main, kind, i)] for kind in PERSON_KINDS}
    if any(gone.values()):
        target = _read_owners(site)
        for kind in PERSON_KINDS:
            target.setdefault(kind, {}).update({item: email for item in gone[kind]})
        _write_owners(site, target)
        kept = {
            k: {i: w for i, w in v.items() if i not in gone.get(k, [])} for k, v in owners.items()
        }
        _write_owners(main, kept)
    left = {kind: sorted(set(theirs[kind]) - set(gone[kind])) for kind in PERSON_KINDS}
    if any(left.values()):
        logger.warning("Host's files left at the main address", extra={"email": email, **left})
    return moved


def _pdf_files(main: Path, pdf_id: str) -> list[Path]:
    return [
        path
        for folder in PDF_FOLDERS
        for path in sorted((main / "content" / folder).glob(f"{pdf_id}.*"))
    ]


def _move_pdfs(main: Path, site: Path, email: str, first: bool = False) -> tuple[int, int]:
    """Move the host's PDFs, with all made from them, and, for the first host, those no host
    added. Each PDF's record of who added it moves once all its files have. The PDFs and the
    files moved."""
    owners = _read_owners(main)
    theirs = [item for item, who in owners.get("pdfs", {}).items() if who == email]
    unowned: list[str] = []
    if first:
        folder = main / "content" / "pdfs"
        stored = sorted(p.stem for p in folder.glob("*.json")) if folder.is_dir() else []
        unowned = [item for item in stored if item not in owners.get("pdfs", {})]
    pdfs = files = 0
    for pdf_id in theirs + unowned:
        paths = _pdf_files(main, pdf_id)
        moved = sum(_move(path, site / path.relative_to(main)) for path in paths)
        pdfs += 1 if moved else 0
        files += moved
    if pdfs:
        # Written from every PDF at the main address; each site writes its own again.
        (main / LESSONS).unlink(missing_ok=True)
    gone = [pdf_id for pdf_id in theirs if not _pdf_files(main, pdf_id)]
    if gone:
        target = _read_owners(site)
        target.setdefault("pdfs", {}).update({pdf_id: email for pdf_id in gone})
        _write_owners(site, target)
        kept = dict(owners)
        kept["pdfs"] = {i: w for i, w in owners["pdfs"].items() if i not in gone}
        _write_owners(main, kept)
    left = sorted(set(theirs) - set(gone))
    if left:
        logger.warning("Host's PDFs left at the main address", extra={"email": email, "pdfs": left})
    if pdfs:
        logger.info(
            "Site PDFs moved",
            extra={"site": site.name or "default", "host": email, "pdfs": pdfs, "files": files},
        )
    return pdfs, files


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
    try:
        _drop_voice_made(home, _read_owners(home), ordered[0] if ordered else None)
    except (OSError, ValueError):
        logger.exception("Hosts not moved to their sites: the prepared voice can't be checked")
        return []
    taken = set(sites.names())
    done: list[Moved] = []
    for n, email in enumerate(ordered):
        site = str(accounts[email].get("site", DEFAULT_SITE))
        if site == NO_SITE:
            continue  # their site was deleted (R69a), and stays so until they start it again
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
            files += _move_pdfs(home, folder, email, first=n == 0)[1]
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
