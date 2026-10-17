"""Unit tests for the R24a default person test, with fake models (nothing downloaded)."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from default_person import (
    PEOPLE,
    REALISM,
    ROLE_LOOKS,
    VOICES,
    Person,
    Result,
    build_page,
    exit_status,
    prompt,
    run_person,
    run_videos,
    voices_for,
    write_results,
)


def fake_picture(text: str, seed: int, path: Path) -> None:
    path.write_bytes(b"png")


def passes(photo: Path) -> tuple[list[str], int | None]:
    return [], 87


def fake_render(face: Any, lang: str, voice: str, output: Path) -> None:
    output.write_text(f"{face} {lang} {voice}")


def test_people_cover_each_gender_and_realism_with_different_roles() -> None:
    kinds = {(p.gender, p.realism) for p in PEOPLE}
    assert kinds == {(g, r) for g in ("female", "male") for r in REALISM}
    assert {p.role for p in PEOPLE} == set(ROLE_LOOKS)
    assert len({p.name for p in PEOPLE}) == len(PEOPLE)


def test_every_gender_has_an_american_and_a_british_voice() -> None:
    for gender in ("female", "male"):
        assert VOICES[(gender, "American")][0] == "a"
        assert VOICES[(gender, "British")][0] == "b"
        # Kokoro's names start with the language code and f or m.
        for accent in ("American", "British"):
            lang, voice = VOICES[(gender, accent)]
            assert voice[:2] == lang + gender[0]


def test_prompt_fits_the_choices() -> None:
    text = prompt(Person("female", "animated", "Teenager"))
    assert "3D animated" in text and "girl aged sixteen" in text and "hoodie" in text
    text = prompt(Person("male", "photoreal", "Professor"))
    assert "photograph" in text and "a man in their late fifties" in text
    assert "facing the camera" in text


def test_run_person_makes_checks_prepares_and_renders_both_accents(tmp_path: Path) -> None:
    made: list[int] = []
    r = run_person(
        Person("male", "photoreal", "Boss", seed=7),
        tmp_path,
        lambda text, seed, path: made.append(seed) or fake_picture(text, seed, path),
        passes,
        lambda photo: "face",
        fake_render,
    )
    assert made == [7]
    assert r.picture == "photoreal_male_boss.png" and r.score == 87 and not r.error
    assert r.videos == {
        "American": "photoreal_male_boss_american.mp4",
        "British": "photoreal_male_boss_british.mp4",
    }
    assert (tmp_path / r.videos["British"]).read_text() == "face b bm_george"
    assert set(r.render_ms) == {"American", "British"}


def test_run_person_makes_a_picture_again_by_default(tmp_path: Path) -> None:
    # An old picture from another prompt, seed or model must not pass as this one.
    (tmp_path / "animated_female_parent.png").write_bytes(b"old")
    made: list[tuple[str, int]] = []

    def record(text: str, seed: int, path: Path) -> None:
        made.append((text, seed))
        path.write_bytes(b"new")

    person = Person("female", "animated", "Parent", seed=7)
    r = run_person(person, tmp_path, record, passes, None, None)
    assert made == [(prompt(person), 7)] and not r.reused
    assert (tmp_path / "animated_female_parent.png").read_bytes() == b"new"
    assert "earlier run" not in build_page([r])


def test_run_person_keeps_a_picture_already_made_when_asked(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "animated_female_parent.png").write_bytes(b"old")

    def never(text: str, seed: int, path: Path) -> None:
        raise AssertionError("made again")

    person = Person("female", "animated", "Parent")
    with caplog.at_level(logging.INFO, logger="default_person_test"):
        r = run_person(person, tmp_path, never, passes, None, None, reuse_picture=True)
    assert r.picture == "animated_female_parent.png" and r.reused
    assert not r.videos and not r.error
    assert [rec.getMessage() for rec in caplog.records] == ["Default person done"]
    assert caplog.records[0].reused_picture is True
    assert "kept from an earlier run" in build_page([r])

    # Asked to keep, but none there yet: it is made.
    r = run_person(
        Person("male", "animated", "Parent"), tmp_path, fake_picture, passes, None, None, True
    )
    assert not r.reused and (tmp_path / "animated_male_parent.png").exists()


def test_a_picture_that_fails_the_checks_is_not_prepared(tmp_path: Path) -> None:
    def prepare(photo: Path) -> str:
        raise AssertionError("prepared")

    r = run_person(
        Person("female", "photoreal", "Boss"),
        tmp_path,
        fake_picture,
        lambda photo: (["The face is turned too far."], None),
        prepare,
        fake_render,
    )
    assert r.problems == ["The face is turned too far."] and not r.videos and not r.error


def test_a_failed_step_is_recorded_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def no_face(photo: Path) -> str:
        raise RuntimeError("no face found")

    with caplog.at_level(logging.INFO, logger="default_person_test"):
        r = run_person(
            Person("male", "animated", "Boss"), tmp_path, fake_picture, passes, no_face, fake_render
        )
    assert r.error == "Could not prepare: no face found"
    messages = [rec.getMessage() for rec in caplog.records]
    assert "Default person failed" in messages and "Default person done" in messages


def test_page_and_results(tmp_path: Path) -> None:
    results = [
        Result(
            "photoreal_male_boss",
            "a <man>",
            "photoreal_male_boss.png",
            score=90,
            videos={"American": "a.mp4", "British": "b.mp4"},
        ),
        Result("animated_male_boss", "p", "animated_male_boss.png", problems=["Too dark."]),
        Result("animated_female_boss", "p", error="Could not make the picture: out of memory"),
    ]
    page = write_results(tmp_path, results)
    html = page.read_text(encoding="utf-8")
    assert "1 of 3 pictures passed" in html
    assert "a &lt;man&gt;" in html and 'src="b.mp4"' in html
    assert "Photo checks failed:</b> Too dark." in html and "out of memory" in html
    saved = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert saved[0]["videos"]["British"] == "b.mp4"
    assert build_page([]).startswith("<!doctype html>")


def test_exit_status_is_0_only_when_everyone_passed_and_talked() -> None:
    def full(p: Person) -> Result:
        accents = [a for a, _, _ in voices_for(p.gender)]
        return Result(p.name, "", "x.png", score=90, videos={a: f"{a}.mp4" for a in accents})

    everyone = [full(p) for p in PEOPLE]
    assert exit_status(everyone, pictures_only=False) == 0
    pictures = [Result(p.name, "", f"{p.name}.png", score=90) for p in PEOPLE]
    assert exit_status(pictures, pictures_only=True) == 0
    # Pictures only, but videos were asked for.
    assert exit_status(pictures, pictures_only=False) == 1
    # One person missing, failed the checks, had an error, or talked in one voice only.
    assert exit_status(everyone[:-1], pictures_only=False) == 1
    for change in (
        {"problems": ["Too dark"]},
        {"error": "Could not prepare: boom"},
        {"picture": ""},
        {"videos": {"American": "a.mp4"}},
    ):
        broken = [full(p) for p in PEOPLE]
        for key, value in change.items():
            setattr(broken[3], key, value)
        assert exit_status(broken, pictures_only=False) == 1, change


def test_video_pass_keeps_a_failed_picture_pass_and_never_makes_a_picture(
    tmp_path: Path,
) -> None:
    person = Person("female", "animated", "Parent")

    def boom(text: str, seed: int, path: Path) -> None:
        raise RuntimeError("out of memory")

    first = run_person(person, tmp_path, boom, passes, None, None)
    assert first.error and not (tmp_path / f"{person.name}.png").exists()

    def no_prepare(photo: Path) -> Any:
        raise AssertionError("prepared after a failed picture pass")

    assert run_videos(person, first, tmp_path, passes, no_prepare, fake_render) is first
    failed_checks = Result(person.name, "", f"{person.name}.png", problems=["Too dark"])
    assert run_videos(person, failed_checks, tmp_path, passes, no_prepare, fake_render) is (
        failed_checks
    )


def test_video_pass_uses_the_picture_from_the_picture_pass(tmp_path: Path) -> None:
    person = Person("male", "animated", "Boss")
    first = run_person(person, tmp_path, fake_picture, passes, None, None)
    first.picture_ms, first.reused = 660000.0, True
    r = run_videos(person, first, tmp_path, passes, lambda photo: "face", fake_render)
    assert set(r.videos) == {"American", "British"} and not r.error
    assert r.picture_ms == 660000.0 and r.reused

    # The picture went missing after the picture pass: a failure, not a new picture.
    (tmp_path / f"{person.name}.png").unlink()
    r = run_videos(person, first, tmp_path, passes, lambda photo: "face", fake_render)
    assert "is gone since the picture pass" in r.error and not r.videos
