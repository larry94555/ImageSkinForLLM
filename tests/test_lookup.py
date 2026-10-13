import io
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from imageskin import cli
from imageskin.content import ContentStore
from imageskin.lookup import (
    ContentLookup,
    Passage,
    look_up,
    one_typo_apart,
    pages_label,
    pdf_passages,
    rank,
    shorten,
    spelled_as_in,
    wiki_passages,
    words,
)
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.reading_job import ReadingJob
from imageskin.wiki import Progress as WikiProgress
from imageskin.wiki import Wiki, WikiPage
from imageskin.wiki_job import WikiJob

PDF = b"%PDF-1.7\n" + b"x" * 100 + b"\n%%EOF\n"

PIECES = [
    Piece(1, "paragraph", "Photosynthesis turns sunlight, water and carbon dioxide into sugar."),
    Piece(2, "paragraph", "Plants take in water through their roots."),
    Piece(3, "table", "Planet | Moons\nMars | 2\nJupiter | 95", [["Planet", "Moons"]]),
    Piece(4, "paragraph", "   "),
]


def lesson(path: Path, progress: Progress) -> Reading:
    return Reading("text", 4, PIECES, [])


def topics(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: Any) -> Wiki:
    return Wiki(
        1,
        [
            WikiPage(f"{pdf_id}-photo", "Photosynthesis", "How plants make sugar from light.", [1]),
            WikiPage(f"{pdf_id}-moons", "Moons of planets", "Mars has two moons.", [3]),
        ],
    )


def content(tmp_path: Path) -> tuple[ContentStore, ReadingJob, WikiJob]:
    store = ContentStore(tmp_path)
    readings = ReadingJob(store, lesson)
    wiki = WikiJob(store, readings, topics)
    readings.on_read = wiki.queue
    pdf = store.add("science.pdf", io.BytesIO(PDF))
    readings.queue(pdf)
    readings.wait()
    wiki.wait()
    return store, readings, wiki


def test_words_are_lower_case_without_common_words_or_endings() -> None:
    assert words("How do the Plants' roots take in WATER?") == ["plant", "root", "take", "water"]
    assert words("glass gas is") == ["glass", "gas"]  # "ss" and short words are kept
    assert words("recordings recording recorded record") == ["record"] * 4
    assert words("thing bed lighting") == ["thing", "bed", "light"]  # short words are kept


def test_greek_letters_and_word_endings_match_their_other_forms() -> None:
    assert words("ζ(s) and Zeta") == ["zeta", "s", "zeta"]
    assert words("Σ π") == ["sigma", "pi"]
    assert words("used uses use") == ["use"] * 3
    assert words("phase phases phased") == ["phas"] * 3


def test_a_misspelled_word_matches_the_content_word_one_typo_away() -> None:
    assert one_typo_apart("reimann", "riemann")  # letters swapped
    assert one_typo_apart("prims", "primes") and one_typo_apart("primes", "prims")
    assert one_typo_apart("zetas", "zetes")  # one letter changed
    assert not one_typo_apart("riemann", "riemann") and not one_typo_apart("zeta", "beta function")
    assert not one_typo_apart("abcde", "badce")
    content = Counter({"riemann": 3, "reimanns": 1})
    assert spelled_as_in("reimann", content) == "riemann"  # the most common one
    assert spelled_as_in("cat", Counter({"cut": 1})) == "cat"  # short words aren't changed


def test_larrys_riemann_question_is_found() -> None:
    # Larry's test (2026-10-13): the paper writes ζ, says "use", and spells Riemann right, so
    # "How is the zeta function used by Reimann?" found nothing and was declined.
    def pdf(text: str) -> Passage:
        return Passage("pdf", "p", "a.pdf", "", text, [1])

    paper = [
        pdf("Riemann uses the function ζ(s) to count the primes."),
        *(pdf(f"The function {n} is continuous.") for n in range(5)),
        pdf("Riemann thanks the Academy."),
        pdf("Primes below a given quantity."),
    ]
    found = rank("How is the zeta function used by Reimann?", paper)
    assert found[0].passage.text.startswith("Riemann uses the function ζ(s)")
    assert rank("What lighting is best for the photo?", paper) == []


def test_a_typo_correction_alone_does_not_find_an_off_topic_prompt() -> None:
    # Review on PR #74: "polar" is one letter from "solar", but nothing else matches.
    solar = [Passage("pdf", "p", "a.pdf", "", "Solar energy comes from the sun.", [1])]
    assert rank("What is polar?", solar) == []
    assert len(rank("What is solar energy?", solar)) == 1
    assert len(rank("Where does sloar energy come from?", solar)) == 1  # beside "energy"

    # Review on PR #74: "energy" is in the content but too common to find a passage alone, so
    # only the correction "polar" to "solar" would have found the passage on solar flares.
    flares = Passage("pdf", "p", "a.pdf", "", "Solar flares erupt.", [2])
    common = [Passage("pdf", "p", "a.pdf", "", f"Energy note {n}.", [3]) for n in range(10)]
    assert rank("What is polar energy?", [flares, *common]) == []


def test_contractions_and_possessives_add_no_stray_words() -> None:
    assert words("What's photosynthesis?") == words("photosynthesis")
    assert words("Can't plants? Don’t they?") == ["plant"]
    assert words("The student's notes, the students’ notes") == ["student", "note"] * 2
    assert words("You're, we've, I'll, I'd, I'm, others") == []
    # Review on PR #72: "'s" scored as a word no passage has, so this exact match was dropped.
    passages = [Passage("pdf", "p", "a.pdf", "", "Photosynthesis makes sugar.", [1])]
    assert len(rank("What's photosynthesis?", passages)) == 1


def test_rank_puts_the_passage_with_more_and_rarer_words_first() -> None:
    def pdf(text: str) -> Passage:
        return Passage("pdf", "p", "a.pdf", "", text, [1])

    passages = [pdf("Water is wet."), pdf("Roots take water in."), pdf("Nothing here.")]
    passages.append(pdf("Roots grow down."))
    found = rank("Roots and water?", passages)
    assert found[0].passage.text == "Roots take water in."  # both words
    assert {f.passage.text for f in found[1:]} == {"Water is wet.", "Roots grow down."}
    assert found[0].score > found[1].score > 0
    assert rank("the of and", passages) == []  # only common words
    assert rank("water", []) == []


def test_a_passage_sharing_only_a_common_word_is_not_found() -> None:
    # Larry's test (2026-10-13): with only a paper on primes, "best" matched its thanks.
    def pdf(text: str) -> Passage:
        return Passage("pdf", "p", "a.pdf", "", text, [1])

    primes = [pdf("I can best convey my thanks."), pdf("Primes are counted."), pdf("Zeta.")]
    assert rank("What lighting is best for the photo?", primes) == []
    assert [f.passage.text for f in rank("How are primes counted?", primes)] == [
        "Primes are counted."
    ]
    # Most of the question's weight is in the one rare word a passage has: it is found.
    guide = [pdf("A kitchen echoes."), *(pdf(f"Record voice {n}.") for n in range(6))]
    assert rank("Can I record in a kitchen?", guide)[0].passage.text == "A kitchen echoes."


def test_a_wiki_title_counts_twice() -> None:
    title = Passage("wiki", "p", "a.pdf", "Moons", "About them.", [1], "p-moons")
    text = Passage("wiki", "p", "a.pdf", "Planets", "Moons.", [1], "p-planets")
    assert [f.passage.id for f in rank("moons", [text, title])] == ["p-moons", "p-planets"]


def test_look_up_keeps_the_best_of_each_kind_and_times_it() -> None:
    passages = [Passage("pdf", "p", "a.pdf", "", f"moon {n}", [n]) for n in range(1, 8)]
    passages.append(Passage("wiki", "p", "a.pdf", "Moon", "", [1], "p-moon"))
    result = look_up("moon", passages, wiki_limit=1, pdf_limit=2)
    assert [f.passage.id for f in result.wiki] == ["p-moon"]
    assert len(result.pdf) == 2 and result.duration_ms >= 0


def test_wiki_passages_include_every_level_and_pdf_passages_skip_empty_pieces() -> None:
    contents = [
        {
            "pdf_id": "p",
            "pdf_name": "a.pdf",
            "entries": [
                {
                    "id": "p-s",
                    "title": "Section",
                    "summary": "S.",
                    "pages": [1],
                    "entries": [{"id": "p-t", "title": "Topic", "summary": "T.", "pages": [2]}],
                }
            ],
        }
    ]
    assert [p.id for p in wiki_passages(contents)] == ["p-s", "p-t"]
    reading = {"id": "p", "name": "a.pdf", "pieces": [{"page": 1, "kind": "slide", "text": " "}]}
    assert pdf_passages(reading) == []


def test_content_lookup_finds_wiki_entries_with_edits_and_pdf_passages(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store, readings, wiki = content(tmp_path)
    pdf_id = store.list()[0].id
    wiki.edit(f"{pdf_id}-moons", "Moons of Mars", "Phobos and Deimos circle Mars.")
    lookup = ContentLookup(wiki, readings)
    with caplog.at_level(logging.INFO):
        result = lookup.find("Which moons circle Mars?")

    assert result.wiki[0].passage.id == f"{pdf_id}-moons"
    assert result.wiki[0].passage.text == "Phobos and Deimos circle Mars."  # the edit is used
    assert result.pdf[0].passage.kind == "table" and result.pdf[0].passage.pages == [3]
    assert len(lookup.passages()) == 5  # 2 wiki entries, 3 pieces with text
    record = [r for r in caplog.records if r.message == "Looked up a question"][0]
    assert record.__dict__["wiki_found"][0] == f"{pdf_id}-moons"
    assert record.__dict__["duration_ms"] >= 0


def test_lookup_command_prints_what_was_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    content(tmp_path)
    monkeypatch.setattr(cli, "default_home", lambda: tmp_path)
    assert (
        cli.main(["lookup", "What does photosynthesis turn into sugar?", "zebra", "--pdf", "1"])
        == 0
    )
    out = capsys.readouterr().out
    assert "Question: What does photosynthesis turn into sugar?" in out and "Looked up in" in out
    assert "Photosynthesis (science.pdf, page 1): How plants make sugar from light." in out
    assert "(science.pdf, page 1, paragraph): Photosynthesis turns sunlight" in out
    assert "Wiki: nothing found" in out and "PDF: nothing found" in out  # for "zebra"


def test_lookup_command_says_when_there_is_nothing_to_look_up_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "default_home", lambda: tmp_path)
    assert cli.main(["lookup", "Anything?"]) == 1
    assert "Nothing to look up in" in capsys.readouterr().err


def test_shorten_cuts_long_passages_at_a_word() -> None:
    assert shorten("a  b\nc", 10) == "a b c"
    assert shorten("one two three", 9) == "one two …"
    assert pages_label([1, 2]) == "pages 1, 2" and pages_label([3]) == "page 3"


def test_the_time_taken_includes_gathering_the_passages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, readings, wiki = content(tmp_path)
    lookup = ContentLookup(wiki, readings)
    gather = lookup.passages

    def slow() -> list[Passage]:
        time.sleep(0.05)
        return gather()

    monkeypatch.setattr(lookup, "passages", slow)
    result = lookup.find("photosynthesis")
    assert result.duration_ms >= 50 and result.passages == 5


@pytest.mark.parametrize("value", ["-1", "two"])
def test_lookup_limits_must_be_zero_or_more(value: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["lookup", "Anything?", "--wiki", value])
    assert "must be a whole number, 0 or more" in capsys.readouterr().err
    assert cli.build_parser().parse_args(["lookup", "q", "--pdf", "0"]).pdf == 0
