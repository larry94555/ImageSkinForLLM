"""Unit tests for the default people's catalogue and packs (roadmap R24b)."""

import json
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from imageskin import default_people as dp
from imageskin.photoreal_library import LIBRARY_VERSION, key_frames, library_key, mouth_key

FIRST = [p for p in dp.people() if p.face == 1 and p.gender in dp.BINARY]
SECOND = [p for p in dp.people() if p.face == 2]
NONBINARY = [p for p in dp.people() if p.gender == dp.NONBINARY]


def test_there_is_one_person_for_each_gender_realism_and_role() -> None:
    assert len(FIRST) == 36
    assert {(p.gender, p.realism, p.role) for p in FIRST} == {
        (g, r, role) for g in dp.BINARY for r in dp.REALISMS for role in dp.ROLES
    }
    assert len({p.name for p in dp.people()}) == 68


def test_looks_are_spread_over_roles_and_realisms() -> None:
    for role in dp.ROLES:
        # A role's four people all look different.
        assert len({p.look for p in FIRST if p.role == role}) == 4
    for g in dp.BINARY:
        for r in dp.REALISMS:
            # Each gender and realism shows every look once.
            group = [p.look for p in FIRST if p.gender == g and p.realism == r]
            assert Counter(group) == Counter(dp.LOOKS)


OLDER_ROLES = {"Professor", "Parent", "Boss", "Office Manager", "High School Teacher"}
OLDER_ROLES |= {"Business Consultant"}


def test_second_faces_are_six_for_each_gender_and_realism() -> None:
    assert len(SECOND) == 24
    assert Counter((p.gender, p.realism) for p in SECOND) == {
        (g, r): 6 for g in dp.BINARY for r in dp.REALISMS
    }
    # Each is a second face for a different one of the 36 choices.
    assert len({(p.gender, p.realism, p.role) for p in SECOND}) == 24
    for g in dp.BINARY:
        for r in dp.REALISMS:
            group = [p for p in SECOND if p.gender == g and p.realism == r]
            # What the prompts ask for in each group; the pictures are checked by
            # tools/default_people/looks_shown.json.
            assert sum("Indigenous" in p.look for p in group) >= 1
            assert sum("glasses" in p.look for p in group) >= 3
            assert sum("wheelchair" in p.look or "hearing aid" in p.look for p in group) >= 2
            older = [p for p in group if p.age]
            assert len(older) >= 3 and all(p.role in OLDER_ROLES for p in older)


HERITAGES = (
    "white",
    "Black",
    "East Asian",
    "South Asian",
    "Latino",
    "Middle Eastern",
    "Southeast Asian",
    "Indigenous",
)


def test_nonbinary_people_are_four_for_each_realism_with_a_range() -> None:
    assert len(NONBINARY) == 8
    assert Counter(p.realism for p in NONBINARY) == {"photoreal": 4, "animated": 4}
    assert all(p.face == 1 for p in NONBINARY)
    assert len({p.name for p in NONBINARY}) == 8
    # Each heritage once across the 8 (Larry, 2026-10-21); the pictures are checked by
    # tools/default_people/looks_shown.json.
    assert all(
        sum(p.look.startswith(h) or f", {h}," in p.look for p in NONBINARY) == 1 for h in HERITAGES
    )
    for r in dp.REALISMS:
        group = [p for p in NONBINARY if p.realism == r]
        assert sum("glasses" in p.look for p in group) == 1
        older = [p for p in group if dp.age(p) == "older"]
        assert len(older) == 1 and older[0].role in OLDER_ROLES


def test_names() -> None:
    assert dp.Person("female", "animated", "Teaching Assistant", "x").name == (
        "animated_female_teaching_assistant"
    )
    assert dp.Person("male", "photoreal", "Boss", "x", face=2).name == "photoreal_male_boss_2"
    assert dp.Person("nonbinary", "animated", "Boss", "x").name == "animated_nonbinary_boss"


# Kokoro-82M's American and British voices (hexgrad/Kokoro-82M, voices/, 2026-10-22).
KOKORO = {
    *(f"af_{v}" for v in "alloy aoede bella heart jessica kore nicole nova river".split()),
    "af_sarah",
    "af_sky",
    *(f"am_{v}" for v in "adam echo eric fenrir liam michael onyx puck santa".split()),
    *(f"bf_{v}" for v in "alice emma isabella lily".split()),
    *(f"bm_{v}" for v in "daniel fable george lewis".split()),
}


def test_every_person_has_a_voice_for_each_accent_that_kokoro_has() -> None:
    for person in dp.people():
        found = dp.voices_for(person)
        assert [(a, lang) for a, lang, _ in found] == [("American", "a"), ("British", "b")]
        for _, _, voice in found:
            parts = voice.split(",")
            assert set(parts) <= KOKORO, voice
            # A nonbinary voice blends a woman's and a man's (R24b3); the others are all of the
            # person's gender, though a British voice may blend in an American one (R24e).
            kinds = sorted(v[1] for v in parts)
            if person.gender == dp.NONBINARY:
                assert kinds == ["f", "m"]
            else:
                assert set(kinds) == {person.gender[0]}


def test_young_adults_sound_younger_and_older_people_older() -> None:
    for person in dp.people():
        for accent, _, voice in dp.voices_for(person):
            older = "older" if person.age in (dp.SIXTIES, dp.SEVENTIES) else "adult"
            expected = "younger" if person.role == "Young Adult" else older
            assert voice in dp.VOICE_CHOICES[(person.gender, accent, expected)]
    assert dp.age(dp.Person("female", "animated", "Young Adult", "x")) == "younger"
    assert dp.age(dp.Person("male", "animated", "Boss", "x", age=dp.SIXTIES)) == "older"
    assert dp.age(dp.Person("male", "animated", "Boss", "x")) == "adult"
    # Asked for older so as to look adult, not as an older person.
    assert dp.age(dp.Person("male", "animated", "Student", "x", age=dp.LATE_TWENTIES)) == "adult"


def test_every_default_person_is_an_adult() -> None:
    # Larry, 2026-10-24: no default person is, or looks, under 18.
    assert "Teenager" not in dp.ROLES
    named = {p.name: p for p in dp.people()}
    assert not [n for n in named if "teen" in n]
    for name, age in dp.LOOKED_YOUNG.items():
        assert named[name].age == age


def test_faces_near_each_other_on_the_avatar_page_sound_different() -> None:
    # The page shows one look at a time, women, men and nonbinary people taking turns.
    for realism in dp.REALISMS:
        shown = dp.page_order([p for p in dp.people() if p.realism == realism])
        for accent in dp.ACCENT_LANGS:
            voices = [dp.voice_of(p.name, accent)[1] for p in shown]
            for i in range(len(voices)):
                assert voices[i] not in voices[i + 1 : i + 3], (shown[i].name, accent)


def test_the_adults_of_a_gender_and_accent_dont_all_share_a_voice() -> None:
    for gender in dp.BINARY:
        for accent in dp.ACCENT_LANGS:
            used = {
                dp.voice_of(p.name, accent)[1]
                for p in dp.people()
                if p.gender == gender and dp.age(p) == "adult"
            }
            assert used == set(dp.VOICE_CHOICES[(gender, accent, "adult")])


def test_each_voice_belongs_to_one_kind_and_has_a_label() -> None:
    every = [v for vs in dp.VOICE_CHOICES.values() for v in vs]
    assert len(every) == len(set(every))
    assert dp.voice_label("af_heart") == "American woman 1"
    assert dp.voice_label("bf_emma,af_kore") == "British woman, older 1"
    assert dp.voice_label("af_bella,am_fenrir") == "American nonbinary, younger"
    assert len({dp.voice_label(v) for v in every}) == len(every)
    with pytest.raises(ValueError):
        dp.voice_label("af_nobody")


def test_the_voices_from_before_r24e_are_still_offered() -> None:
    every = {v for vs in dp.VOICE_CHOICES.values() for v in vs}
    old = {"af_heart", "am_michael", "bf_emma", "bm_george"}
    assert old | {"af_heart,am_michael", "bf_emma,bm_george"} <= every


def test_the_page_order_goes_by_role_then_face_then_gender() -> None:
    a = dp.Person("male", "animated", "Professor", "x")
    b = dp.Person("female", "animated", "Professor", "x", face=2)
    c = dp.Person("female", "animated", "Professor", "x")
    d = dp.Person("nonbinary", "animated", "Student", "x")
    assert dp.page_order([d, b, a, c]) == [c, a, b, d]


N_LOOP = 12  # a short loop: key frames 0, 4 and 8


def fake_library(folder: Path, rng: np.random.Generator) -> None:
    """A library as build_library leaves it, with small random pictures."""
    (folder / "loop").mkdir(parents=True)

    def image() -> np.ndarray:
        return rng.integers(0, 256, (16, 16, 3), np.uint8)

    np.save(folder / "photo.npy", rng.integers(0, 256, (24, 20, 3), np.uint8))
    np.save(folder / "paste_template.npy", image())
    np.save(folder / "crop_landmarks.npy", rng.random((68, 2)).astype(np.float32))
    np.save(folder / "crop_to_photo.npy", rng.random((2, 3)))
    np.save(folder / "shapes.npy", np.stack([image() for _ in range(10)]))
    np.save(folder / "eyes.npy", np.stack([image() for _ in range(4)]))
    np.save(folder / "align.npy", rng.random((N_LOOP, 2, 3)))
    np.save(folder / "eye_align.npy", rng.random((N_LOOP, 2, 3)))
    for i in range(N_LOOP):
        # Smooth frames, so the filled-in ones match closely.
        np.save(folder / "loop" / f"{i:04d}.npy", np.full((16, 16, 3), 10 * i, np.uint8))
    (folder / "shapes.json").write_text(json.dumps({"mouth": mouth_key()}))
    (folder / "library.json").write_text(
        json.dumps(
            {"version": LIBRARY_VERSION, "photo": "x", "loop_frames": N_LOOP, "mouth": mouth_key()}
        )
    )


@pytest.fixture
def packed(tmp_path: Path) -> tuple[Path, Path, Path]:
    library = tmp_path / "lib"
    fake_library(library, np.random.default_rng(1))
    picture = tmp_path / "pic.png"
    picture.write_bytes(b"picture bytes")
    out = tmp_path / "person.zip"
    person = dp.people()[0]
    size = dp.pack(person, picture, library, out)
    assert size == out.stat().st_size > 0
    return library, picture, out


def test_pack_holds_the_picture_and_only_the_key_frames(packed: tuple[Path, Path, Path]) -> None:
    _, _, out = packed
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        info = json.loads(z.read("person.json"))
    assert "picture.png" in names and "shapes.json" in names
    assert {n for n in names if n.startswith("loop/")} == {
        f"loop/{i:04d}.png" for i in key_frames(N_LOOP)
    }
    assert len([n for n in names if n.startswith("shapes/")]) == 10
    assert len([n for n in names if n.startswith("eyes/")]) == 4
    assert info["name"] == dp.people()[0].name and info["loop_frames"] == N_LOOP


def test_unpack_restores_the_library(packed: tuple[Path, Path, Path], tmp_path: Path) -> None:
    library, picture, out = packed
    home = tmp_path / "home"
    got = dp.unpack(out, home)
    assert got.read_bytes() == picture.read_bytes()
    folder = home / "photoreal" / library_key(got)
    for name in ("photo", "paste_template", "crop_landmarks", "crop_to_photo", "shapes", "eyes"):
        np.testing.assert_array_equal(
            np.load(folder / f"{name}.npy"), np.load(library / f"{name}.npy")
        )
    for i in key_frames(N_LOOP):  # the key frames exactly, through PNG
        np.testing.assert_array_equal(
            np.load(folder / "loop" / f"{i:04d}.npy"), np.load(library / "loop" / f"{i:04d}.npy")
        )
    assert len(list((folder / "loop").glob("*.npy"))) == N_LOOP  # the rest filled in
    meta = json.loads((folder / "library.json").read_text())
    assert meta["photo"] == str(got) and meta["mouth"] == mouth_key()


def test_unpacked_library_loads_without_preparing(
    packed: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    from imageskin.photoreal_library import prepare_library

    _, _, out = packed
    home = tmp_path / "home"
    got = dp.unpack(out, home)

    def no_model(photo: Path) -> None:
        raise AssertionError("prepared again")

    lib = prepare_library(got, home, no_model)  # type: ignore[arg-type]
    assert len(lib.loop) == N_LOOP and len(lib.shapes) == 10


def test_unpack_refuses_a_bad_pack(tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(dp.PackError, match="could not be unpacked"):
        dp.unpack(bad, tmp_path / "home")


def test_unpack_refuses_other_versions_and_mouth_settings(
    packed: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, _, out = packed
    changes = (
        ({"pack_version": 99}, "pack version 99"),
        ({"library_version": LIBRARY_VERSION - 1}, f"library version {LIBRARY_VERSION - 1}"),
        ({"mouth": "x"}, "mouth"),
    )
    for change, message in changes:
        with zipfile.ZipFile(out) as z:
            info = json.loads(z.read("person.json"))
            items = {n: z.read(n) for n in z.namelist() if n != "person.json"}
        other = tmp_path / "other.zip"
        with zipfile.ZipFile(other, "w") as z:
            z.writestr("person.json", json.dumps({**info, **change}))
            for n, data in items.items():
                z.writestr(n, data)
        with pytest.raises(dp.PackError, match=message):
            dp.unpack(other, tmp_path / "home")


def test_a_frame_that_is_not_a_png_is_refused(
    packed: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, _, out = packed
    with zipfile.ZipFile(out) as z:
        items = {n: z.read(n) for n in z.namelist()}
    items["loop/0000.png"] = b"junk"
    other = tmp_path / "junk.zip"
    with zipfile.ZipFile(other, "w") as z:
        for n, data in items.items():
            z.writestr(n, data)
    with pytest.raises(dp.PackError, match="not a PNG"):
        dp.unpack(other, tmp_path / "home")


def test_a_failed_unpack_leaves_the_library_already_there(
    packed: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, _, out = packed
    home = tmp_path / "home"
    got = dp.unpack(out, home)
    folder = home / "photoreal" / library_key(got)
    before = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    # A pack that fails late, after the picture, arrays and stacks are read.
    with zipfile.ZipFile(out) as z:
        items = {n: z.read(n) for n in z.namelist()}
    items[f"loop/{key_frames(N_LOOP)[-1]:04d}.png"] = b"junk"
    broken = tmp_path / "person.zip"
    broken.parent.mkdir(exist_ok=True)
    out.rename(tmp_path / "good.zip")
    with zipfile.ZipFile(broken, "w") as z:
        for n, data in items.items():
            z.writestr(n, data)
    with pytest.raises(dp.PackError):
        dp.unpack(broken, home)
    after = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    assert after == before
    assert got.exists()
    assert [p.name for p in (home / "photoreal").iterdir()] == [folder.name]  # no work folder


def test_unpacking_again_replaces_the_library(
    packed: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, _, out = packed
    home = tmp_path / "home"
    got = dp.unpack(out, home)
    folder = home / "photoreal" / library_key(got)
    (folder / "loop" / "0001.npy").unlink()  # as if damaged
    assert dp.unpack(out, home) == got
    assert len(list((folder / "loop").glob("*.npy"))) == N_LOOP


def test_a_failed_swap_puts_the_library_back(
    packed: tuple[Path, Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    _, _, out = packed
    home = tmp_path / "home"
    got = dp.unpack(out, home)
    folder = home / "photoreal" / library_key(got)
    before = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    replace = os.replace

    def fail_new_into_place(src: Path, dst: Path) -> None:
        if Path(src).name == "library":  # the finished work folder moving into place
            raise OSError("disk full")
        replace(src, dst)

    monkeypatch.setattr("imageskin.default_people.os.replace", fail_new_into_place)
    with pytest.raises(dp.PackError, match="disk full"):
        dp.unpack(out, home)
    after = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    assert after == before
    assert [p.name for p in (home / "photoreal").iterdir()] == [folder.name]


def test_check_pack(packed: tuple[Path, Path, Path], tmp_path: Path) -> None:
    _, _, out = packed
    name = dp.people()[0].name
    dp.check_pack(out, name)
    with pytest.raises(dp.PackError, match="not someone_else"):
        dp.check_pack(out, "someone_else")
    data = out.read_bytes()
    at = data.index(b"picture bytes")
    damaged = tmp_path / "damaged.zip"
    damaged.write_bytes(data[:at] + b"X" + data[at + 1 :])
    with pytest.raises(dp.PackError, match="picture.png in the pack is damaged"):
        dp.check_pack(damaged, name)
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"junk")
    with pytest.raises(dp.PackError, match="not a usable pack"):
        dp.check_pack(junk, name)


def test_check_pack_needs_every_member(packed: tuple[Path, Path, Path], tmp_path: Path) -> None:
    _, _, out = packed
    with zipfile.ZipFile(out) as z:
        items = {n: z.read(n) for n in z.namelist()}
    assert set(dp.required_members(N_LOOP)) <= set(items)
    for gone in ("shapes.json", "eye_align.npy", "eyes/03.png", f"loop/{N_LOOP - 4:04d}.png"):
        other = tmp_path / f"without-{gone.replace('/', '-')}.zip"
        with zipfile.ZipFile(other, "w") as z:
            for n, data in items.items():
                if n != gone:
                    z.writestr(n, data)
        with pytest.raises(dp.PackError, match=f"missing {gone}"):
            dp.check_pack(other, dp.people()[0].name)
