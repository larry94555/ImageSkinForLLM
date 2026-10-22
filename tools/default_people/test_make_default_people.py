"""Unit tests for the R24b maker script, with fake models (nothing downloaded)."""

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from make_default_people import (
    HERITAGES,
    MAX_SEEDS,
    OLDER_ROLES,
    ROLE_LOOKS,
    Result,
    VideoSteps,
    build_page,
    by_group,
    contact_sheet,
    exit_status,
    group_of,
    load_results,
    load_shown,
    look_counts,
    looks_missing,
    mouth_box,
    negative,
    prompt,
    run_picture,
    run_video,
    thumbnail,
    write_results,
)

from imageskin import default_people as dp
from imageskin.default_people import PACK_VERSION, Person, people
from imageskin.photoreal_library import LIBRARY_VERSION, mouth_key


def write_pack(path: Path, name: str, **change: Any) -> None:
    """A pack that check_pack accepts for `name`, with `change` made to its person.json."""
    info = {
        "pack_version": PACK_VERSION,
        "library_version": LIBRARY_VERSION,
        "mouth": mouth_key(),
        "name": name,
        "loop_frames": 8,
        **change,
    }
    leave_out = info.pop("leave_out", None)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("person.json", json.dumps(info))
        z.writestr("picture.png", "picture bytes")
        for member in dp.required_members(8)[2:]:
            if member != leave_out:
                z.writestr(member, "x")


def test_every_role_has_a_look() -> None:
    assert set(ROLE_LOOKS) == set(dp.ROLES)


def test_prompt_puts_the_person_first() -> None:
    text = prompt(Person("female", "animated", "Teenager", "Black, with deep brown skin"))
    assert text.startswith("one girl aged sixteen, Black, with deep brown skin, wearing a hoodie")
    assert "3D animated" in text and "mouth closed" in text and "bright bedroom" in text
    assert prompt(Person("male", "photoreal", "Student", "x")).startswith("one young man about")
    assert prompt(Person("male", "photoreal", "Boss", "x")).startswith("one man in their late")


def pictures(fail_seeds: set[int]) -> tuple[Any, Any, list[int]]:
    made: list[int] = []

    def make(text: str, avoid: str, seed: int, path: Path) -> None:
        made.append(seed)
        path.write_bytes(f"seed {seed}".encode())

    def check(photo: Path) -> tuple[list[str], int | None]:
        seed = int(photo.read_text().split()[1])
        return (["Head turned"], None) if seed in fail_seeds else ([], 90)

    return make, check, made


PERSON = people()[0]


def test_picture_passes_on_the_first_seed(tmp_path: Path) -> None:
    make, check, made = pictures(set())
    r = run_picture(PERSON, tmp_path, make, check, None)
    assert made == [1] and r.seed == 1 and r.score == 90 and not r.problems
    assert r.picture == f"{PERSON.name}.png"


def test_picture_tries_the_next_seed_when_a_check_fails(tmp_path: Path) -> None:
    make, check, made = pictures({1, 2})
    r = run_picture(PERSON, tmp_path, make, check, None)
    assert made == [1, 2, 3] and r.seed == 3 and not r.problems


def test_picture_that_fails_every_seed_is_reported(tmp_path: Path) -> None:
    make, check, made = pictures(set(range(1, 10)))
    r = run_picture(PERSON, tmp_path, make, check, None)
    assert len(made) == MAX_SEEDS and r.problems == ["Head turned"]


def test_picture_made_before_is_checked_not_made_again(tmp_path: Path) -> None:
    make, check, made = pictures(set())
    first = run_picture(PERSON, tmp_path, make, check, None)
    made.clear()
    again = run_picture(PERSON, tmp_path, make, check, first)
    assert made == [] and again.seed == 1


def test_picture_from_another_prompt_is_made_again(tmp_path: Path) -> None:
    make, check, made = pictures(set())
    old = Result(PERSON.name, "an old prompt", seed=1, picture=f"{PERSON.name}.png")
    (tmp_path / old.picture).write_text("seed 1")
    run_picture(PERSON, tmp_path, make, check, old)
    assert made == [1]


def test_picture_error_is_recorded(tmp_path: Path) -> None:
    def broken(text: str, avoid: str, seed: int, path: Path) -> None:
        raise RuntimeError("out of memory")

    r = run_picture(PERSON, tmp_path, broken, pictures(set())[1], None)
    assert r.error == "Could not make the picture: out of memory"


def steps(tmp_path: Path, talking: float = 4.0, idle_s: float = 8.0) -> VideoSteps:
    def prepare(picture: Path) -> Any:
        return SimpleNamespace(folder=tmp_path / "lib")

    def render(lib: Any, lang: str, voice: str, output: Path) -> None:
        output.write_text(f"{lang} {voice}")

    def idle(lib: Any, output: Path) -> float:
        output.write_text("idle")
        return idle_s

    def motion(lib: Any, video: Path) -> float:
        return 1.0 if video.name.endswith("_idle.mp4") else talking

    return VideoSteps(prepare, render, idle, motion, lambda lib: lib.folder)


@pytest.fixture
def picked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Result:
    make, check, _ = pictures(set())
    sizes = {"bytes": 30_000_000}

    def fake_pack(person: Person, picture: Path, library: Path, output: Path) -> int:
        write_pack(output, person.name)
        return sizes["bytes"]

    monkeypatch.setattr("make_default_people.pack", fake_pack)
    return run_picture(PERSON, tmp_path, make, check, None)


def test_video_pass_renders_checks_and_packs(tmp_path: Path, picked: Result) -> None:
    r = run_video(PERSON, picked, tmp_path, steps(tmp_path))
    assert r.passed and r.pack == f"packs/{PERSON.name}.zip" and r.pack_bytes == 30_000_000
    assert r.mouth_ratio == 4.0 and r.idle_seconds == 8.0
    # The check line is spoken in the person's first voice.
    _, lang, voice = dp.voices_for(PERSON)[0]
    assert (tmp_path / r.video).read_text() == f"{lang} {voice}"


def test_a_still_mouth_fails(tmp_path: Path, picked: Result) -> None:
    r = run_video(PERSON, picked, tmp_path, steps(tmp_path, talking=1.2))
    assert not r.passed and r.error.startswith("Could not check the mouth moves")


def test_an_empty_idle_loop_fails(tmp_path: Path, picked: Result) -> None:
    r = run_video(PERSON, picked, tmp_path, steps(tmp_path, idle_s=0))
    assert r.error.startswith("Could not play the idle loop")


def test_a_pack_over_budget_fails(
    tmp_path: Path, picked: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("make_default_people.pack", lambda *a: 60_000_000)
    r = run_video(PERSON, picked, tmp_path, steps(tmp_path))
    assert not r.passed and "over 50 MB" in r.error


def test_people_that_failed_their_picture_are_not_prepared(tmp_path: Path) -> None:
    failed = Result(PERSON.name, prompt(PERSON), problems=["Head turned"], picture="x.png")
    assert run_video(PERSON, failed, tmp_path, steps(tmp_path)) is failed


def test_a_packed_person_is_kept(tmp_path: Path, picked: Result) -> None:
    done = run_video(PERSON, picked, tmp_path, steps(tmp_path))

    def no_make(text: str, avoid: str, seed: int, path: Path) -> None:
        raise AssertionError("made again")

    assert run_picture(PERSON, tmp_path, no_make, pictures(set())[1], done) is done
    assert run_video(PERSON, done, tmp_path, steps(tmp_path)) is done


def test_results_round_trip_and_page(tmp_path: Path, picked: Result) -> None:
    done = run_video(PERSON, picked, tmp_path, steps(tmp_path))
    failed = Result("photoreal_male_boss", "p", error="Could not prepare: no face")
    write_results(tmp_path, [done, failed])
    assert load_results(tmp_path)[PERSON.name] == done
    page = (tmp_path / "index.html").read_text()
    assert "1 of 2 passed" in page and "Could not prepare: no face" in page
    assert "Largest pack: 30.0 MB" in build_page([done])
    assert json.loads((tmp_path / "results.json").read_text())[1]["error"]


def test_no_results_yet(tmp_path: Path) -> None:
    assert load_results(tmp_path) == {}


def test_exit_status_needs_all_68_packed(tmp_path: Path) -> None:
    ok = []
    for p in people():
        write_pack(tmp_path / f"{p.name}.zip", p.name)
        ok.append(Result(p.name, "", pack=f"{p.name}.zip"))
    assert exit_status(ok, tmp_path) == 0
    assert exit_status(ok[:-1], tmp_path) == 1
    ok[3].error = "Could not pack"
    assert exit_status(ok, tmp_path) == 1
    ok[3].error = ""
    (tmp_path / ok[3].pack).write_bytes(b"damaged")
    assert exit_status(ok, tmp_path) == 1


def test_a_run_after_an_error_tries_the_video_pass_again(tmp_path: Path, picked: Result) -> None:
    failed = run_video(PERSON, picked, tmp_path, steps(tmp_path, talking=1.2))
    assert failed.error

    def no_make(text: str, avoid: str, seed: int, path: Path) -> None:
        raise AssertionError("made again")

    again = run_picture(PERSON, tmp_path, no_make, pictures(set())[1], failed)
    assert not again.error and again.seed == 1 and again.mouth_ratio is None
    assert run_video(PERSON, again, tmp_path, steps(tmp_path)).passed


def test_a_passed_person_whose_pack_is_gone_is_packed_again(tmp_path: Path, picked: Result) -> None:
    done = run_video(PERSON, picked, tmp_path, steps(tmp_path))
    (tmp_path / done.pack).unlink()

    def no_make(text: str, avoid: str, seed: int, path: Path) -> None:
        raise AssertionError("made again")

    again = run_picture(PERSON, tmp_path, no_make, pictures(set())[1], done)
    assert again is not done and not again.pack
    assert run_video(PERSON, again, tmp_path, steps(tmp_path)).passed
    assert zipfile.is_zipfile(tmp_path / again.pack)


def test_contact_sheet(tmp_path: Path) -> None:
    import cv2

    cv2.imwrite(str(tmp_path / "a.png"), np.zeros((64, 64, 3), np.uint8))
    results = [Result("photoreal_female_professor", "", picture="a.png", pack="a.zip")]
    results.append(Result("photoreal_female_boss", "", error="x"))
    sheet = cv2.imread(str(contact_sheet(tmp_path, results, columns=2, side=50)))
    assert sheet.shape == (74, 100, 3)


def test_mouth_box_maps_the_window_into_the_photo() -> None:
    lib = SimpleNamespace(
        window=(10, 20, 30, 40),
        crop_to_photo=np.array([[2.0, 0, 5], [0, 2.0, 7]]),
        photo=np.zeros((100, 70, 3), np.uint8),
    )
    assert mouth_box(lib) == (25, 47, 65, 87)
    lib.photo = np.zeros((60, 50, 3), np.uint8)  # clipped to the photo
    assert mouth_box(lib) == (25, 47, 50, 60)


@pytest.mark.parametrize("damage", ["stale library", "corrupt member", "missing member"])
def test_a_pack_the_app_cant_use_is_made_again(tmp_path: Path, picked: Result, damage: str) -> None:
    done = run_video(PERSON, picked, tmp_path, steps(tmp_path))
    pack_file = tmp_path / done.pack
    if damage == "stale library":
        write_pack(pack_file, PERSON.name, library_version=LIBRARY_VERSION - 1)
    elif damage == "missing member":
        write_pack(pack_file, PERSON.name, leave_out="loop/0004.png")
    else:
        data = pack_file.read_bytes()
        at = data.index(b"picture bytes")
        pack_file.write_bytes(data[:at] + b"X" + data[at + 1 :])
    assert exit_status([done], tmp_path) == 1

    def no_make(text: str, avoid: str, seed: int, path: Path) -> None:
        raise AssertionError("made again")

    again = run_picture(PERSON, tmp_path, no_make, pictures(set())[1], done)
    assert again is not done and not again.pack
    assert run_video(PERSON, again, tmp_path, steps(tmp_path)).passed


def test_a_second_face_can_be_older() -> None:
    older = Person("female", "photoreal", "Professor", "x", face=2, age="in their late sixties")
    assert prompt(older).startswith("one woman in their late sixties, x, wearing a tweed")


def test_glasses_are_kept_out_of_the_negative_only_for_people_who_wear_them() -> None:
    assert "glasses," in negative(PERSON) and "tinted" not in negative(PERSON)
    wearer = Person("male", "animated", "Boss", "x, wearing clear glasses", face=2)
    avoided = negative(wearer).split(", ")
    assert "glasses" not in avoided and "glasses" in negative(PERSON).split(", ")
    assert "tinted glasses" in avoided and "sunglasses" in avoided


def test_thumbnail(tmp_path: Path) -> None:
    import cv2

    picture = tmp_path / "p.png"
    rng = np.random.default_rng(0)
    cv2.imwrite(str(picture), rng.integers(0, 256, (512, 512, 3), np.uint8))
    size = thumbnail(picture, tmp_path / "thumbs" / "p.jpg")
    small = cv2.imread(str(tmp_path / "thumbs" / "p.jpg"))
    assert small is not None and small.shape == (128, 128, 3) and 0 < size < 20_000
    with pytest.raises(ValueError, match="not a picture"):
        thumbnail(tmp_path / "missing.png", tmp_path / "x.jpg")


def every_look() -> dict[str, dict[str, Any]]:
    """Looks that meet every count: each group's people take the heritages in turn, and the
    first older-role people have red hair, blond hair, glasses, age and a disability."""
    shown: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[Person]] = {}
    for p in people():
        groups.setdefault(group_of(p), []).append(p)
    for members in groups.values():
        for i, p in enumerate(members):
            shown[p.name] = {"heritage": HERITAGES[i % len(HERITAGES)]}
        older = [p for p in members if p.role in OLDER_ROLES]
        for p in older[:3]:
            shown[p.name] |= {"older": True, "glasses": True, "disability": "hearing aid"}
        shown[older[0].name]["hair"] = "red"
        shown[older[1].name]["hair"] = "blond"
    return shown


def test_looks_counts_met() -> None:
    counts = look_counts(every_look())
    assert set(counts) == {
        "photoreal female",
        "photoreal male",
        "animated female",
        "animated male",
        "nonbinary",
    }
    # 15 women or men in each look, and the 8 nonbinary people (R24b3) as one group.
    assert {name: g["people"] for name, g in counts.items()} == {
        name: 8 if name == "nonbinary" else 15 for name in counts
    }
    assert looks_missing(counts) == []


def test_looks_missing_says_what_a_group_lacks() -> None:
    shown = every_look()
    young = next(p for p in people() if p.role == "Teenager" and p.realism == "animated")
    shown[young.name] |= {"older": True}  # a Teenager never counts as older
    indigenous = [n for n, s in shown.items() if s["heritage"] == "Indigenous"]
    for name in indigenous:
        if name.startswith("photoreal_male"):
            shown[name]["heritage"] = "white"
    older = [n for n, s in shown.items() if s.get("glasses") and n.startswith("animated_female")]
    shown[older[0]]["glasses"] = False
    assert looks_missing(look_counts(shown)) == [
        "photoreal male: no Indigenous person",
        "animated female: 2 with glasses, needs 3",
    ]


def test_looks_table_and_page(tmp_path: Path) -> None:
    page = build_page([], every_look())
    assert "Looks the pictures show" in page and "8 of 8" in page and "3 (needs 3)" in page
    assert "Looks the pictures show" not in build_page([])
    path = tmp_path / "shown.json"
    assert load_shown(path) == {}
    path.write_text(json.dumps(every_look()))
    assert load_shown(path) == every_look()


def test_contact_sheet_rows_are_groups() -> None:
    ordered = by_group([Result(p.name, "") for p in people()])
    first_row = {
        r.person.rsplit("_", 1)[0] if r.person.endswith("_2") else r.person for r in ordered[:15]
    }
    assert all(name.startswith("photoreal_female") for name in first_row)
    assert all(r.person.startswith("photoreal_nonbinary") for r in ordered[30:34])
    assert all(r.person.startswith("animated_nonbinary") for r in ordered[64:])


def test_the_pictures_show_every_look_larry_asked_for() -> None:
    """The record of what each of the 68 pictures was seen to show meets every count."""
    shown = load_shown()
    assert sorted(shown) == sorted(p.name for p in people())
    assert looks_missing(look_counts(shown)) == []


def test_a_wheelchair_gets_a_wider_picture() -> None:
    sitting = Person("male", "photoreal", "Student", f"x, {dp.WHEELCHAIR}", face=2)
    text = prompt(sitting)
    assert "wheelchair" in text and "headshot" not in text and "head and shoulders" not in text
    assert "headshot" in prompt(PERSON) and "head and shoulders" in prompt(PERSON)


def test_a_nonbinary_person_is_asked_for_as_androgynous_without_gendered_looks() -> None:
    person = Person("nonbinary", "photoreal", "Boss", f"Latino, with short dark hair, {dp.GLASSES}")
    assert prompt(person).startswith("one androgynous person in their late forties, Latino")
    teen = Person("nonbinary", "animated", "Teenager", "white, with short red hair")
    assert prompt(teen).startswith("one androgynous teenager aged sixteen")
    avoid = negative(person)
    assert avoid.startswith("feminine, masculine, makeup") and "tinted glasses" in avoid
    assert "feminine" not in negative(Person("female", "photoreal", "Boss", "x"))
