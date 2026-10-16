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
    prompt,
    run_person,
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


def test_run_person_keeps_a_picture_already_made(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "animated_female_parent.png").write_bytes(b"old")

    def never(text: str, seed: int, path: Path) -> None:
        raise AssertionError("made again")

    with caplog.at_level(logging.INFO, logger="default_person_test"):
        r = run_person(Person("female", "animated", "Parent"), tmp_path, never, passes, None, None)
    assert r.picture == "animated_female_parent.png" and not r.videos and not r.error
    assert [rec.getMessage() for rec in caplog.records] == ["Default person done"]


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
