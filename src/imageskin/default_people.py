"""The ready-made default people (roadmap R24b, features.md items 56 to 58).

Each of the 36 choices (gender, realism and role) is one made-up person: a picture made ahead of
time by `tools/default_people/make_default_people.py`, and the photoreal frame library prepared
from it. Accent doesn't change the picture; it picks one of Kokoro's ready-made voices.

A person's pack is one zip holding the picture and the library, so a person is downloaded only
when first chosen (item 57). The idle loop is packed as its rendered key frames only, as PNGs;
`unpack` fills in the frames between them exactly as prepare does, so an unpacked library is the
same as one prepared on the user's own machine, at a fraction of the download.
"""

import io
import json
import logging
import os
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from imageskin.photoreal_library import (
    LIBRARY_VERSION,
    fill_loop,
    key_frames,
    library_key,
    mouth_key,
)

logger = logging.getLogger(__name__)

# The largest pack: 50 MB downloads in 20 seconds at 25 Mbit/s (item 57).
MAX_PACK_BYTES = 50 * 1000 * 1000
PACK_VERSION = 1

GENDERS = ("female", "male")
REALISMS = ("photoreal", "animated")
ROLES = (
    "Professor",
    "Teaching Assistant",
    "Student",
    "Parent",
    "Teenager",
    "Boss",
    "Office Manager",
    "High School Teacher",
    "Business Consultant",
)

# Kokoro-82M's ready-made voices (Apache 2.0, hexgrad), picked in R24a: by gender and accent,
# the Kokoro language code and the voice.
VOICES: dict[tuple[str, str], tuple[str, str]] = {
    ("female", "American"): ("a", "af_heart"),
    ("male", "American"): ("a", "am_michael"),
    ("female", "British"): ("b", "bf_emma"),
    ("male", "British"): ("b", "bm_george"),
}

# A range of skin tones, heritages and hair, spread over the people so that every role and
# realism shows several (Larry, 2026-10-17). They are only for making the pictures: the app
# never shows them.
LOOKS = (
    "Black, with deep brown skin and short coily black hair",
    "East Asian, with light skin and straight black hair",
    "South Asian, with brown skin and dark wavy hair",
    "white, with fair freckled skin and red hair",
    "Latino, with olive skin and dark brown hair",
    "Middle Eastern, with light brown skin and dark curly hair",
    "white, with light skin and blond hair",
    "Southeast Asian, with tan skin and black hair",
    "mixed race, with light brown skin and curly brown hair",
)


@dataclass(frozen=True)
class Person:
    gender: str  # "female" or "male"
    realism: str  # "photoreal" or "animated"
    role: str
    look: str
    face: int = 1  # R24b2 adds faces 2 and 3 for each choice
    seed: int = 1

    @property
    def name(self) -> str:
        """For example photoreal_female_teaching_assistant, with _2 for a second face."""
        base = f"{self.realism}_{self.gender}_{self.role.lower().replace(' ', '_')}"
        return base if self.face == 1 else f"{base}_{self.face}"


def people() -> list[Person]:
    """The 36 people, one per gender, realism and role. Within each gender and realism the nine
    roles take the nine looks, each group starting two looks further on, so a role's four people
    all look different."""
    found = []
    for g, (gender, realism) in enumerate((g, r) for r in REALISMS for g in GENDERS):
        for r, role in enumerate(ROLES):
            look = LOOKS[(r + 2 * g) % len(LOOKS)]
            found.append(Person(gender, realism, role, look))
    return found


def voices_for(gender: str) -> list[tuple[str, str, str]]:
    """The accent, Kokoro language code and voice of each voice for a gender."""
    return [(a, lang, v) for (g, a), (lang, v) in VOICES.items() if g == gender]


class PackError(Exception):
    pass


def _png(image: np.ndarray) -> bytes:
    """An RGB picture as PNG bytes (OpenCV writes BGR)."""
    ok, data = cv2.imencode(".png", np.ascontiguousarray(image[..., ::-1]))
    if not ok:
        raise PackError("could not encode a frame as PNG")
    return bytes(data.tobytes())


def _from_png(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise PackError("a frame in the pack is not a PNG")
    return np.ascontiguousarray(image[..., ::-1])


def _npy(array: np.ndarray) -> bytes:
    out = io.BytesIO()
    np.save(out, array)
    return out.getvalue()


# The library's stacks of pictures, packed one PNG each.
STACKS = ("shapes", "eyes")


def pack(person: Person, picture: Path, library: Path, output: Path) -> int:
    """Write the person's pack: the picture, the library's arrays, its stacks of faces and the
    idle loop's key frames as PNGs. Returns the pack's size in bytes."""
    start = time.perf_counter()
    meta = json.loads((library / "library.json").read_text(encoding="utf-8"))
    n_loop = int(meta["loop_frames"])
    tmp = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        info = {
            "pack_version": PACK_VERSION,
            "name": person.name,
            "gender": person.gender,
            "realism": person.realism,
            "role": person.role,
            "face": person.face,
            "loop_frames": n_loop,
            "mouth": meta["mouth"],
            "library_version": meta["version"],
        }
        z.writestr("person.json", json.dumps(info, indent=2))
        z.write(picture, "picture.png", zipfile.ZIP_STORED)
        for path in sorted(library.glob("*.npy")):
            if path.stem in STACKS:
                for i, face in enumerate(np.load(path)):
                    z.writestr(f"{path.stem}/{i:02d}.png", _png(face), zipfile.ZIP_STORED)
            else:
                z.write(path, path.name)
        z.writestr("shapes.json", (library / "shapes.json").read_text(encoding="utf-8"))
        for i in key_frames(n_loop):
            frame = np.load(library / "loop" / f"{i:04d}.npy")
            z.writestr(f"loop/{i:04d}.png", _png(frame), zipfile.ZIP_STORED)
    tmp.replace(output)
    size = output.stat().st_size
    logger.info(
        "Packed default person",
        extra={
            "person": person.name,
            "pack": str(output),
            "bytes": size,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return size


def _swap_in(new: Path, folder: Path) -> None:
    """Put the finished library `new` at `folder`. A library already there is moved aside first
    and put back if the move fails, so it is removed only once the new one is in place."""
    old = folder.with_name(folder.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if folder.exists():
        os.replace(folder, old)
    try:
        os.replace(new, folder)
    except OSError:
        if old.exists():
            os.replace(old, folder)
        raise
    shutil.rmtree(old, ignore_errors=True)


def unpack(pack_file: Path, home: Path) -> Path:
    """Unpack a person into the app's home: the picture as <home>/default-people/<name>.png and
    its library where prepare would put it, with the idle loop filled in. Returns the picture,
    which `prepare_library` then loads without preparing.

    Everything is unpacked into a work folder first and moved into place only once complete, so
    a failed unpack (a broken download, say) leaves no partial library, and a library already
    there stays as it was."""
    start = time.perf_counter()
    work = home / "photoreal" / f".unpacking-{pack_file.stem}"
    shutil.rmtree(work, ignore_errors=True)
    try:
        lib = work / "library"
        (lib / "loop").mkdir(parents=True)
        with zipfile.ZipFile(pack_file) as z:
            info = json.loads(z.read("person.json"))
            if info.get("pack_version") != PACK_VERSION:
                raise PackError(f"pack version {info.get('pack_version')} is not supported")
            # Library versions are part of the folder's key; a pack made for another version
            # would be put where this one's libraries go, so it is refused.
            if info.get("library_version") != LIBRARY_VERSION:
                raise PackError(f"library version {info.get('library_version')} is not supported")
            if info.get("mouth") != mouth_key():
                raise PackError("the pack was made with other mouth settings")
            new_picture = work / "picture.png"
            new_picture.write_bytes(z.read("picture.png"))
            names = z.namelist()
            for name in names:
                if name.endswith(".npy") and "/" not in name:
                    (lib / name).write_bytes(z.read(name))
            for stack in STACKS:
                faces = sorted(n for n in names if n.startswith(f"{stack}/"))
                frames = [_from_png(z.read(n)) for n in faces]
                (lib / f"{stack}.npy").write_bytes(_npy(np.stack(frames)))
            (lib / "shapes.json").write_bytes(z.read("shapes.json"))
            n_loop = int(info["loop_frames"])
            keys = key_frames(n_loop)
            for i in keys:
                frame = _from_png(z.read(f"loop/{i:04d}.png"))
                (lib / "loop" / f"{i:04d}.npy").write_bytes(_npy(frame))
        filled = fill_loop(lib / "loop", n_loop, keys)
        picture = home / "default-people" / f"{info['name']}.png"
        (lib / "library.json").write_text(
            json.dumps(
                {
                    "version": LIBRARY_VERSION,
                    "photo": str(picture),
                    "loop_frames": n_loop,
                    "mouth": info["mouth"],
                }
            ),
            encoding="utf-8",
        )
        folder = home / "photoreal" / library_key(new_picture)
        _swap_in(lib, folder)
        picture.parent.mkdir(parents=True, exist_ok=True)
        os.replace(new_picture, picture)
    except (PackError, OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
        logger.error(
            "Could not unpack default person", extra={"pack": str(pack_file), "error": str(e)}
        )
        raise PackError(f"{pack_file.name} could not be unpacked: {e}") from e
    finally:
        shutil.rmtree(work, ignore_errors=True)
    logger.info(
        "Unpacked default person",
        extra={
            "person": info["name"],
            "folder": str(folder),
            "filled_frames": filled,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return picture
