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
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from imageskin.reading_job import ReadingJob
from imageskin.topics import main_entries
from imageskin.wiki_job import WikiJob

logger = logging.getLogger(__name__)

Source = Literal["wiki", "pdf"]

# How many of each kind are found for a question.
WIKI_LIMIT = 3
PDF_LIMIT = 5
# How many example questions the chat is given for under the prompt box (R41g), which it shows
# three at a time, the next three with "other topics..." (R182), and how they are asked: each in
# turn, all opening with words ASKING_ABOUT takes off, so only the subject is looked up.
EXAMPLES = 24
EXAMPLE_ASKS = ("What can you tell me about {}?", "Can you explain {}?", "Tell me about {}.")
# The most of a passage the LLM is given to answer from (R40).
PASSAGE_CHARS = 400
# How much comes before the question's first word when a passage is cut to show it.
LEAD_CHARS = 120
# BM25's usual settings: how fast more of the same word stops adding to the score, and how much
# a long passage is held back.
K1 = 1.5
B = 0.75
# The share of the question's words, weighted by rarity, that a passage must have to be found.
MIN_SHARE = 0.4
# A question word at least this long that the content doesn't have is matched to a content word
# one typo away, so a misspelled name (Larry's "Reimann", 2026-10-13) is still found in a passage
# that also has another of the question's words as typed (review on PR #74).
MIN_TYPO_CHARS = 5
WORD = re.compile(r"[^\W_]+")
# A contraction like "can't" or "don't" is a common word, so it goes whole; the ending of
# "what's", "you're" or "participant's" is left off. Straight and curly apostrophes alike.
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
# How a question can start by asking about something, taken off before it is looked up (R41f):
# "What can you tell me about the zeta function integral?" is looked up as "the zeta function
# integral", so a content without "tell" doesn't count it as the question's rarest word and find
# nothing. Only these opening words go; the same words later on, or in the content ("Learning"),
# still count (review on PR #85).
ASKING_ABOUT = re.compile(
    r"^[\W_]*(?:(?:so|ok|okay|and|hi|hello|hey|well|please)\b[\W_]*)*"
    r"(?:(?:what|how much) (?:else )?(?:can|could|do|would|will) you (?:tell|teach|explain|say)"
    r"(?: to)?(?: me| us)?(?: more)? about"
    r"|(?:can|could|would|will) you (?:please )?(?:tell|teach|explain|describe)(?: to)?(?: me| us)?"
    r"(?: more)?(?: about)?"
    r"|(?:please )?(?:tell|teach) (?:me|us)(?: more)?(?: about)?"
    r"|(?:please )?(?:explain|describe)"
    r"|(?:i['’]?d|i would|i) (?:like|want|love) to (?:know|learn|hear)(?: more)?(?: about)?"
    r"|what do you know about)\b",
    re.IGNORECASE,
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


def greek_name(letter: str) -> str:
    """A Greek letter's name ("ζ" is "zeta"), so a PDF that writes the symbol matches a
    question that spells it out; any other word as it is."""
    if len(letter) == 1 and "\u0370" <= letter <= "\u03ff":
        name = unicodedata.name(letter, "")
        if name.startswith("GREEK SMALL LETTER ") or name.startswith("GREEK CAPITAL LETTER "):
            return name.split()[-1].lower()
    return letter


def words(text: str) -> list[str]:
    """The words that count for matching: lower case, no common words, Greek letters by name,
    and a plural "s" or an "ing" or "ed" ending left off, so "recordings", "recording" and
    "recorded" all match "record". A final "e" is left off too, so "used", "uses" and "use"
    match, and "phased" matches "phase"."""
    text = CONTRACTION_ENDING.sub("", NOT_CONTRACTION.sub(" ", text.lower()))
    found = []
    for word in WORD.findall(text):
        word = greek_name(word)
        if word in STOP_WORDS:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        if len(word) > 5 and word.endswith("ing"):
            word = word[:-3]
        elif len(word) > 3 and word.endswith("ed"):
            word = word[:-1]  # "used" is "use", and "recorded" is "recorde" until its "e" is off
        if len(word) > 4 and word.endswith("e"):
            word = word[:-1]
        if word not in STOP_WORDS:  # "others" is "other" once its "s" is off
            found.append(word)
    return found


def one_typo_apart(a: str, b: str) -> bool:
    """Whether b is a with one letter changed, added, left out, or swapped with the next."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        i, j = diff[0], diff[-1]
        return len(diff) == 2 and j == i + 1 and a[i] == b[j] and a[j] == b[i]
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return any(long[:i] + long[i + 1 :] == short for i in range(len(long)))


def spelled_as_in(word: str, content: Counter[str]) -> str:
    """A question word the content doesn't have, as the content spells it when one typo apart
    ("Reimann" for "Riemann"), the most common such word; otherwise the word as it is. Short
    words are left alone: one letter off turns too many of them into other words."""
    if word in content or len(word) < MIN_TYPO_CHARS:
        return word
    near = [w for w in content if len(w) >= MIN_TYPO_CHARS and one_typo_apart(word, w)]
    return max(near, key=lambda w: content[w]) if near else word


def asked_about(question: str) -> str:
    """The question without the words it opens with to ask about something (ASKING_ABOUT), or
    the whole question when nothing would be left."""
    rest = ASKING_ABOUT.sub("", question, count=1)
    return rest if words(rest) else question


# Words that ask about a subject rather than name it: "What did Euler notice?" is about Euler,
# and a paper on Euler that never says "notice" still answers it (Larry, 2026-10-15). "What is
# the weather in Paris?" names the weather, so a paper that says Paris once doesn't (review on
# PR #91).
REQUEST_WORDS = frozenset(
    words(
        "notice explain say think mean find discover show prove observe believe idea realize"
        " conclude learn describe talk relation relate contribution famous example"
    )
)


def passage_words(passage: Passage) -> list[str]:
    return words(passage.title) * 2 + words(passage.text)


@dataclass(frozen=True)
class Corpus:
    """The passages with their words counted, so several questions can be looked up in the same
    content without counting them again (review on PR #217: the example questions)."""

    passages: list[Passage]
    counted: list[Counter[str]]
    having: Counter[str]  # how many passages have each word
    lengths: list[int]
    average: float

    @classmethod
    def of(cls, passages: list[Passage]) -> "Corpus":
        counted = [Counter(passage_words(p)) for p in passages]
        having: Counter[str] = Counter()
        for c in counted:
            having.update(c.keys())
        lengths = [sum(c.values()) for c in counted]
        average = (sum(lengths) / len(lengths) if lengths else 0.0) or 1.0
        return cls(passages, counted, having, lengths, average)


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


def rank(question: str, passages: list[Passage] | Corpus) -> list[Found]:
    """The passages that match enough of the question, best first, scored with BM25.

    A passage must have at least MIN_SHARE of the question's words, each weighted by how rare it
    is in the content; a word the content doesn't have at all weighs the most (after a word one
    typo from a content word is taken as that word, in a passage with a word as typed). So a
    passage that shares only a common word ("best" in "What lighting is best for the photo?")
    is left out, and a question about something the content doesn't cover finds nothing. Words
    that ask about a subject rather than name it ("notice", "explain") don't count against a
    passage that lacks them (REQUEST_WORDS), so "What did Euler notice?" finds Euler."""
    corpus = passages if isinstance(passages, Corpus) else Corpus.of(passages)
    if not words(question) or not corpus.passages:
        return []
    content = corpus.having
    typed = set(words(question))
    asked = {spelled_as_in(w, content) for w in typed} if typed & content.keys() else typed
    average = corpus.average
    total = len(corpus.passages)
    idf = {}
    for w in asked:
        having = content[w]
        idf[w] = math.log(1 + (total - having + 0.5) / (having + 0.5))
    # The question's words that name what it is about; all of them if it has only asking
    # words. Only these count for or against a passage (review on PR #91).
    subject = {w for w in asked if w not in REQUEST_WORDS} or asked
    weight = sum(idf[w] for w in subject)
    found = []
    for passage, counts, length in zip(
        corpus.passages, corpus.counted, corpus.lengths, strict=True
    ):
        matched = [w for w in asked if w in counts]
        # A typo corrected helps only a passage that has a question word as typed, so a
        # correction is never the only reason a passage, or an off-topic prompt, is found
        # ("polar energy" isn't found by a passage on solar flares; review on PR #74).
        named = [w for w in matched if w in subject]
        if not typed.intersection(named) or sum(idf[w] for w in named) < MIN_SHARE * weight:
            continue
        score = 0.0
        for w in matched:
            n = counts[w]
            score += idf[w] * n * (K1 + 1) / (n + K1 * (1 - B + B * length / average))
        found.append(Found(passage, round(score, 3)))
    return sorted(found, key=lambda f: -f.score)


def look_up(
    question: str,
    passages: list[Passage] | Corpus,
    wiki_limit: int = WIKI_LIMIT,
    pdf_limit: int = PDF_LIMIT,
) -> Lookup:
    """The best wiki entries and PDF passages for a question, ranked together so a word's
    rarity is judged across all the content."""
    start = time.perf_counter()
    ranked = rank(asked_about(question), passages)
    wiki = [f for f in ranked if f.passage.source == "wiki"][:wiki_limit]
    pdf = [f for f in ranked if f.passage.source == "pdf"][:pdf_limit]
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    searched = passages.passages if isinstance(passages, Corpus) else passages
    return Lookup(question, wiki, pdf, duration_ms, len(searched))


def pages_label(pages: list[int]) -> str:
    return ("page " if len(pages) == 1 else "pages ") + ", ".join(map(str, pages))


def shorten(text: str, chars: int) -> str:
    """The text on one line, cut at a word to at most `chars` characters with " …" after it."""
    text = " ".join(text.split())
    return text if len(text) <= chars else text[:chars].rsplit(" ", 1)[0] + " …"


def excerpt(text: str, chars: int, question: str) -> str:
    """The text on one line, cut to at most about `chars` characters where it has the most of the
    question's words: the start, unless they come later. The paragraph where the Riemann paper
    names Euler opens with 500 characters of thanks, so the cut start left Euler out and
    "What did Euler notice?" got a vague answer (Larry, 2026-10-15)."""
    text = " ".join(text.split())
    if len(text) <= chars:
        return text
    asked = set(words(question))
    hits = [(m.span(), w) for m in WORD.finditer(text) for w in words(m.group()) if w in asked]

    def has(start: int) -> int:
        return len({w for (at, end), w in hits if start <= at and end <= start + chars})

    starts = [0, *(text.rfind(" ", 0, max(0, at - LEAD_CHARS)) + 1 for (at, _), _ in hits)]
    best = max(starts, key=lambda start: (has(start), -start))
    return shorten(text, chars) if best == 0 else "… " + shorten(text[best:], chars)


def as_passages(result: Lookup, chars: int = PASSAGE_CHARS) -> list[str]:
    """What was found, best first, each with where it came from, for the LLM to answer from
    (roadmap R40). A long passage (a big table, say) is cut at a word to `chars` characters."""
    found = sorted([*result.wiki, *result.pdf], key=lambda f: -f.score)
    passages = []
    for f in found:
        p = f.passage
        where = f"{p.pdf_name}, {pages_label(p.pages)}"
        text = excerpt(p.text, chars, result.question)
        passages.append(f"{p.title} ({where}): {text}" if p.title else f"({where}): {text}")
    return passages


def named_topic(question: str, contents: list[dict[str, Any]]) -> str | None:
    """The topic (a main wiki entry, R41f) the question names: its title's words, together and
    in order, as in "What's so special about the Zeta Function Integral?", or None. The one with
    the most words when it names several. Its words scattered through the question don't name
    it: "Is water safe to drink during my cycle?" isn't about the Water Cycle (review on #85)."""
    asked = words(asked_about(question))

    def named(title: list[str]) -> bool:
        n = len(title)
        return n > 0 and any(asked[i : i + n] == title for i in range(len(asked) - n + 1))

    found = [t for t in main_entries(contents) if named(words(t))]
    return max(found, key=lambda t: len(words(t)), default=None)


def look_up_named(
    question: str,
    contents: list[dict[str, Any]],
    passages: list[Passage] | Corpus,
    wiki_limit: int = WIKI_LIMIT,
    pdf_limit: int = PDF_LIMIT,
) -> Lookup:
    """look_up, and when it finds nothing, the topic the question names (R41f) instead, so a
    topic is always answered, however it is asked about."""
    result = look_up(question, passages, wiki_limit, pdf_limit)
    if not result.wiki and not result.pdf:
        topic = named_topic(question, contents)
        if topic is not None:
            logger.info("Question names a topic; looking the topic up", extra={"topic": topic})
            result = replace(look_up(topic, passages, wiki_limit, pdf_limit), question=question)
    return result


def example_subjects(contents: list[dict[str, Any]]) -> list[str]:
    """What the example questions can ask about (R41g), best first: each topic's first part (more
    particular than the topic), or the topic when it has no parts; then the topics that had
    parts. Each title once, without the punctuation it ends with."""
    first, then = [], []
    for pdf in contents:
        for topic in pdf["entries"]:
            parts = topic.get("entries") or []
            first.append(parts[0]["title"] if parts else topic["title"])
            if parts:
                then.append(topic["title"])
    seen: set[str] = set()
    subjects = []
    for title in first + then:
        subject = " ".join(str(title).split()).rstrip(".:;,!?")
        if subject and subject.casefold() not in seen:
            seen.add(subject.casefold())
            subjects.append(subject)
    return subjects


class ContentLookup:
    """Looks questions up in the current wiki (with the user's edits) and what was read from the
    PDFs."""

    def __init__(self, wiki: WikiJob, readings: ReadingJob) -> None:
        self.wiki = wiki
        self.readings = readings

    def passages(self, contents: list[dict[str, Any]] | None = None) -> list[Passage]:
        found = wiki_passages(self.wiki.contents() if contents is None else contents)
        for pdf in self.wiki.store.list():
            reading = self.readings.reading(pdf.id)
            if reading is not None:
                found += pdf_passages(reading)
        return found

    def find(
        self, question: str, wiki_limit: int = WIKI_LIMIT, pdf_limit: int = PDF_LIMIT
    ) -> Lookup:
        start = time.perf_counter()
        contents = self.wiki.contents()
        passages = self.passages(contents)  # unreadable saved files are logged and left out there
        result = look_up_named(question, contents, passages, wiki_limit, pdf_limit)
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

    def examples(self, limit: int = EXAMPLES) -> list[str]:
        """A few questions to show under the prompt box (R41g), drawn from the wiki, each one
        that finds something, so clicking it is never declined (R41)."""
        contents = self.wiki.contents()
        corpus = Corpus.of(self.passages(contents))  # counted once for all the candidates
        found: list[str] = []
        for subject in example_subjects(contents):
            question = EXAMPLE_ASKS[len(found) % len(EXAMPLE_ASKS)].format(subject)
            result = look_up_named(question, contents, corpus)
            if result.wiki or result.pdf:
                found.append(question)
                if len(found) == limit:
                    break
        return found
