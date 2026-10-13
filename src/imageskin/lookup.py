"""Looking up a question in the wiki and the PDFs (roadmap R39, item 27).

Keyword search, as the roadmap's open decision suggested: the simplest method, with no model to
download, and embeddings can be added later if answers miss. Every wiki entry (its title and
summary, with the user's edits) and every piece read from a PDF (a paragraph, slide or table) is
a passage, ranked by BM25: a passage scores higher the more of the question's words it has, the
rarer those words are across all the passages, and the shorter it is. Words are matched in lower
case, without common words like "the", and with a plural "s" left off. A wiki entry's title
counts twice, since it names what the entry is about.

The passages are gathered again for each question, so a new edit or rebuild is found at once; the
content is small (a few PDFs), and the time each lookup takes is logged.
"""

import logging
import math
import re
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from imageskin.reading_job import ReadingJob
from imageskin.wiki_job import WikiJob

logger = logging.getLogger(__name__)

Source = Literal["wiki", "pdf"]

# How many of each kind are found for a question.
WIKI_LIMIT = 3
PDF_LIMIT = 5
# The most of a passage the LLM is given to answer from (R40).
PASSAGE_CHARS = 400
# BM25's usual settings: how fast more of the same word stops adding to the score, and how much
# a long passage is held back.
K1 = 1.5
B = 0.75
# The share of the question's words, weighted by rarity, that a passage must have to be found.
MIN_SHARE = 0.4
WORD = re.compile(r"[^\W_]+")
# A contraction like "can't" or "don't" is a common word, so it goes whole; the ending of
# "what's", "you're" or "student's" is left off. Straight and curly apostrophes alike.
NOT_CONTRACTION = re.compile(r"[^\W_]+n['’]t\b")
CONTRACTION_ENDING = re.compile(r"['’](?:s|re|ve|ll|d|m)\b")
STOP_WORDS = frozenset(
    """a about above after again all also am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers him his how i if in into is it its just me more most my
    no nor not now of off on once only or other our out over own same she should so some such
    than that the their them then there these they this those through to too under until up very
    was we were what when where which while who whom why will with would you your""".split()
)


@dataclass(frozen=True)
class Passage:
    source: Source  # a wiki entry, or a piece read from a PDF
    pdf_id: str
    pdf_name: str
    title: str  # a wiki entry's title; empty for a PDF piece
    text: str  # a wiki entry's summary, or the piece's text
    pages: list[int]  # the PDF's pages it comes from
    id: str | None = None  # a wiki entry's id (its page), so answers can link to it
    kind: str | None = None  # a PDF piece's kind: paragraph, slide or table


@dataclass(frozen=True)
class Found:
    passage: Passage
    score: float


@dataclass(frozen=True)
class Lookup:
    question: str
    wiki: list[Found] = field(default_factory=list)
    pdf: list[Found] = field(default_factory=list)
    duration_ms: float = 0.0
    passages: int = 0  # how many were searched


def words(text: str) -> list[str]:
    """The words that count for matching: lower case, no common words, and a plural "s" or an
    "ing" or "ed" ending left off, so "recordings", "recording" and "recorded" all match
    "record"."""
    text = CONTRACTION_ENDING.sub("", NOT_CONTRACTION.sub(" ", text.lower()))
    found = []
    for word in WORD.findall(text):
        if word in STOP_WORDS:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        if len(word) > 5 and word.endswith("ing"):
            word = word[:-3]
        elif len(word) > 4 and word.endswith("ed"):
            word = word[:-2]
        if word not in STOP_WORDS:  # "others" is "other" once its "s" is off
            found.append(word)
    return found


def passage_words(passage: Passage) -> list[str]:
    return words(passage.title) * 2 + words(passage.text)


def wiki_passages(contents: list[dict[str, Any]]) -> list[Passage]:
    """Every entry of every table of contents (as `WikiJob.contents` gives them), parts too."""

    def walk(entries: list[dict[str, Any]], pdf: dict[str, Any]) -> Iterator[Passage]:
        for e in entries:
            yield Passage(
                "wiki",
                pdf["pdf_id"],
                pdf["pdf_name"],
                e["title"],
                e["summary"],
                e["pages"],
                e["id"],
            )
            yield from walk(e.get("entries", []), pdf)

    return [p for pdf in contents for p in walk(pdf["entries"], pdf)]


def pdf_passages(reading: dict[str, Any]) -> list[Passage]:
    """Every piece read from a PDF (as `ReadingJob.reading` gives it)."""
    return [
        Passage("pdf", reading["id"], reading["name"], "", p["text"], [p["page"]], kind=p["kind"])
        for p in reading["pieces"]
        if p["text"].strip()
    ]


def rank(question: str, passages: list[Passage]) -> list[Found]:
    """The passages that match enough of the question, best first, scored with BM25.

    A passage must have at least MIN_SHARE of the question's words, each weighted by how rare it
    is in the content; a word the content doesn't have at all weighs the most. So a passage that
    shares only a common word ("best" in "What lighting is best for the photo?") is left out,
    and a question about something the content doesn't cover finds nothing."""
    asked = set(words(question))
    if not asked or not passages:
        return []
    counted = [Counter(passage_words(p)) for p in passages]
    lengths = [sum(c.values()) for c in counted]
    average = sum(lengths) / len(lengths) or 1.0
    total = len(passages)
    idf = {}
    for w in asked:
        having = sum(1 for c in counted if w in c)
        idf[w] = math.log(1 + (total - having + 0.5) / (having + 0.5))
    weight = sum(idf.values())
    found = []
    for passage, counts, length in zip(passages, counted, lengths, strict=True):
        matched = [w for w in asked if w in counts]
        if sum(idf[w] for w in matched) < MIN_SHARE * weight:
            continue
        score = 0.0
        for w in matched:
            n = counts[w]
            score += idf[w] * n * (K1 + 1) / (n + K1 * (1 - B + B * length / average))
        found.append(Found(passage, round(score, 3)))
    return sorted(found, key=lambda f: -f.score)


def look_up(
    question: str,
    passages: list[Passage],
    wiki_limit: int = WIKI_LIMIT,
    pdf_limit: int = PDF_LIMIT,
) -> Lookup:
    """The best wiki entries and PDF passages for a question, ranked together so a word's
    rarity is judged across all the content."""
    start = time.perf_counter()
    ranked = rank(question, passages)
    wiki = [f for f in ranked if f.passage.source == "wiki"][:wiki_limit]
    pdf = [f for f in ranked if f.passage.source == "pdf"][:pdf_limit]
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    return Lookup(question, wiki, pdf, duration_ms, len(passages))


def pages_label(pages: list[int]) -> str:
    return ("page " if len(pages) == 1 else "pages ") + ", ".join(map(str, pages))


def shorten(text: str, chars: int) -> str:
    """The text on one line, cut at a word to at most `chars` characters with " …" after it."""
    text = " ".join(text.split())
    return text if len(text) <= chars else text[:chars].rsplit(" ", 1)[0] + " …"


def as_passages(result: Lookup, chars: int = PASSAGE_CHARS) -> list[str]:
    """What was found, best first, each with where it came from, for the LLM to answer from
    (roadmap R40). A long passage (a big table, say) is cut at a word to `chars` characters."""
    found = sorted([*result.wiki, *result.pdf], key=lambda f: -f.score)
    passages = []
    for f in found:
        p = f.passage
        where = f"{p.pdf_name}, {pages_label(p.pages)}"
        text = shorten(p.text, chars)
        passages.append(f"{p.title} ({where}): {text}" if p.title else f"({where}): {text}")
    return passages


class ContentLookup:
    """Looks questions up in the current wiki (with the user's edits) and what was read from the
    PDFs."""

    def __init__(self, wiki: WikiJob, readings: ReadingJob) -> None:
        self.wiki = wiki
        self.readings = readings

    def passages(self) -> list[Passage]:
        found = wiki_passages(self.wiki.contents())
        for pdf in self.wiki.store.list():
            reading = self.readings.reading(pdf.id)
            if reading is not None:
                found += pdf_passages(reading)
        return found

    def find(
        self, question: str, wiki_limit: int = WIKI_LIMIT, pdf_limit: int = PDF_LIMIT
    ) -> Lookup:
        start = time.perf_counter()
        passages = self.passages()  # unreadable saved files are logged and left out there
        result = look_up(question, passages, wiki_limit, pdf_limit)
        # The whole lookup, gathering the passages too, not only ranking them.
        result = replace(result, duration_ms=round((time.perf_counter() - start) * 1000, 1))
        logger.info(
            "Looked up a question",
            extra={
                "question_chars": len(question),
                "passages": len(passages),
                "wiki_found": [f.passage.id for f in result.wiki],
                "pdf_found": len(result.pdf),
                "duration_ms": result.duration_ms,
            },
        )
        return result
