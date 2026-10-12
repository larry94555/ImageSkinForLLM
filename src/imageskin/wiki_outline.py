"""The wiki as an outline (roadmap R37a, item 26): each PDF's table of contents.

The topics R37 finds (`wiki.build_wiki`) are grouped by the LLM into the sections of a table of
contents, each with a short summary. Each topic is shown with the LLM's few sentences on it. When
what the PDF itself says on the topic's pages is simple enough, that is all; when it says more,
the topic gets a detail page: the LLM groups the PDF's paragraphs about the topic into parts and
summarizes them, and each part is again either simple enough to show in the PDF's own words or a
detail page of its own, down to MAX_DEPTH levels. The LLM writes only titles and summaries, not
the PDF's text again, which keeps the build fast (most of an LLM request's time is spent writing
its answer). If the LLM can't group or split something, it stays as it is.
"""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any, TypeVar

from imageskin.chat import TOKENS_PER_MESSAGE, Count, EmptyReply, LlmError, Message
from imageskin.wiki import WaitForLlm, WikiPage, clean_title, cut, down, load_json, slug, unique

logger = logging.getLogger(__name__)

T = TypeVar("T")

# A text of at most this many sentences, and characters, is shown as it is (Larry, 2026-10-12).
SIMPLE_SENTENCES = 5
SIMPLE_CHARS = 600
# Levels in all, the table of contents' sections being the first, so a long PDF can't make the
# build run on. An entry on the last level is shown as it is.
MAX_DEPTH = 4
# Tables of contents this short need no sections.
FEW_TOPICS = 3
# The longest answer asked for: a few sections, or a summary and the parts of a text, each
# with its title and paragraph numbers.
OUTLINE_REPLY_TOKENS = 600
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
NUMBERED = re.compile(r"(\d+)\. ")

SECTIONS_PROMPT = (
    "Below are the topics of a document, numbered, in the document's order, each with how it"
    " starts. Group them into the sections of a table of contents, keeping the document's order:"
    " 2 to 8 sections, each with a short title of a few words, a summary of 1 or 2 sentences, and"
    " the numbers of its topics. Put every topic in exactly one section. Answer with JSON only,"
    ' in this form: {"sections": [{"title": "…", "summary": "…", "topics": [1, 2]}]}'
)
DETAIL_PROMPT = (
    "Below are numbered paragraphs from a document, in its order; the topic is in the first"
    " line. Using only what they say about that topic, write a summary of it in 2 or 3"
    " sentences, then group the paragraphs about the topic into 2 to 6 parts that each cover one"
    " point, in order, each with a short title of a few words and the numbers of its paragraphs."
    " Leave out paragraphs that are not about the topic. Answer with JSON only, in this form:"
    ' {"summary": "…", "parts": [{"title": "…", "paragraphs": [1, 2]}]}'
)

SECTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "topics": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["title", "summary", "topics"],
            },
        }
    },
    "required": ["sections"],
}
DETAIL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "paragraphs": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["title", "paragraphs"],
            },
        },
    },
    "required": ["summary", "parts"],
}

# Asks the LLM for JSON held to a schema, and returns its answer; LlmError when that fails.
AskForJson = Callable[[list[Message], dict[str, Any]], str]
# The LLM requests made so far, and those planned in all so far: the topics' and the sections'
# at first, more as parts are found long enough to open up too.
OutlineProgress = Callable[[int, int], None]
# A paragraph of the PDF (or a few sentences of a long one), with its page.
Unit = tuple[int, str]


@dataclass
class Entry:
    id: str  # unique in the wiki
    title: str
    summary: str
    pages: list[int]  # the PDF's pages it comes from
    entries: list["Entry"] = field(default_factory=list)  # its parts, once opened
    detail: bool = False  # whether its parts are on a page of its own


@dataclass
class Outliner:
    pdf_id: str
    ask: AskForJson
    count: Count
    context_tokens: int
    progress: OutlineProgress | None = None
    wait_for_llm: WaitForLlm | None = None
    requests: int = 0
    planned: int = 0
    used: set[str] = field(default_factory=set)

    def outline(
        self, topics: list[WikiPage], pieces: list[dict[str, Any]] | None = None
    ) -> list[Entry]:
        """The table of contents: sections of topics, or the topics alone when there are few.
        `pieces` is what was read in the PDF, each with its page: a topic's detail comes from
        the pieces on its pages."""
        start = time.perf_counter()
        logger.info("Building wiki outline", extra={"id": self.pdf_id, "topics": len(topics)})
        self.used.update(t.id for t in topics)  # a topic's entry keeps its page's id
        sources = [self.source(t, pieces or []) for t in topics]
        for t, source in zip(topics, sources, strict=True):
            if opens(source, 2):
                self.planned += len(self.batches(numbered(source), DETAIL_PROMPT, t.title))
        if len(topics) > FEW_TOPICS:
            self.planned += len(self.batches(self.contents_lines(topics), SECTIONS_PROMPT))
        entries = [
            self.entry(t.title, t.text, source, t.pages, 2, t.id, planned=True)
            for t, source in zip(topics, sources, strict=True)
        ]
        contents = self.sections(topics, entries) if len(topics) > FEW_TOPICS else entries
        logger.info(
            "Wiki outline built",
            extra={
                "id": self.pdf_id,
                "entries": len(contents),
                "detail_pages": sum(count_detail(e) for e in contents),
                "requests": self.requests,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return contents

    def source(self, page: WikiPage, pieces: list[dict[str, Any]]) -> list[Unit]:
        """A topic's detail: what the PDF says on its pages (or the LLM's few sentences on it,
        when nothing was read there)."""
        source = [u for p in pieces if p["page"] in page.pages for u in units(p["page"], p["text"])]
        return source or units(page.pages[0] if page.pages else 1, page.text)

    def entry(
        self,
        title: str,
        summary: str | None,
        source: list[Unit],
        pages: list[int],
        depth: int,
        entry_id: str = "",
        planned: bool = False,  # whether its requests are counted in self.planned already
    ) -> Entry:
        """An entry with its summary (for a part, None: its own text, or the LLM's summary of
        it once opened), and a detail page of its source's parts unless the source is simple
        enough (or the entry is on the last level)."""
        entry_id = entry_id or unique(f"{self.pdf_id}-{slug(title)}", self.used)
        text = " ".join(t for _, t in source)
        entry = Entry(entry_id, title, text if summary is None else summary, pages)
        if not opens(source, depth):
            return entry
        found = self.split(title, source, planned)
        if found is None:
            return entry
        if summary is None:
            entry.summary = found[0]
        for part_title, numbers in found[1]:
            part = [source[n - 1] for n in numbers]
            part_pages = sorted({p for p, _ in part})
            entry.entries.append(self.entry(part_title, None, part, part_pages, depth + 1))
        entry.detail = True
        return entry

    def sections(self, topics: list[WikiPage], entries: list[Entry]) -> list[Entry]:
        """The entries grouped into sections, in batches that fit the context window. A topic
        the LLM leaves out stays in the table of contents on its own."""
        lines = self.contents_lines(topics)
        contents: list[Entry] = []
        placed: set[int] = set()
        for batch in self.batches(lines, SECTIONS_PROMPT):
            numbers = {int(line.split(".", 1)[0]) for line in batch}
            found = self.request(
                SECTIONS_PROMPT,
                "\n".join(batch),
                SECTIONS_SCHEMA,
                partial(read_sections, numbers=numbers),
            )
            for title, summary, members in found or []:
                members = [n for n in members if n not in placed]
                if not members:
                    continue
                placed.update(members)
                children = [entries[n - 1] for n in members]
                pages = sorted({p for c in children for p in c.pages})
                section_id = unique(f"{self.pdf_id}-{slug(title)}", self.used)
                contents.append(Entry(section_id, title, summary, pages, children))
            for n in sorted(numbers - placed):
                contents.append(entries[n - 1])
                placed.add(n)
        return contents

    def contents_lines(self, topics: list[WikiPage]) -> list[str]:
        return [f"{n}. {t.title}: {first_sentence(t.text)}" for n, t in enumerate(topics, 1)]

    def split(
        self, title: str, source: list[Unit], planned: bool = False
    ) -> tuple[str, list[tuple[str, list[int]]]] | None:
        """A long source's summary and its parts, each with the numbers of its units (from 1);
        None if the LLM couldn't split it. A unit goes to the first part that names it; a batch
        with no usable answer (it may say nothing about the topic) adds no parts."""
        summary: str | None = None
        parts: list[tuple[str, list[int]]] = []
        placed: set[int] = set()
        batches = self.batches(numbered(source), DETAIL_PROMPT, title)
        if not planned:
            self.planned += len(batches)
        for batch in batches:
            numbers = {int(m.group(1)) for line in batch if (m := NUMBERED.match(line))}
            read = partial(read_detail, numbers=numbers)
            found = self.request(
                DETAIL_PROMPT, f"{title}\n\n" + "\n\n".join(batch), DETAIL_SCHEMA, read
            )
            for part_title, members in found[1] if found else []:
                members = [n for n in members if n not in placed]
                if members:
                    placed.update(members)
                    parts.append((part_title, sorted(members)))
            summary = summary or (found[0] if found else None)
        parts.sort(key=lambda part: part[1][0])
        return (summary, parts) if summary and len(parts) > 1 else None

    def batches(self, lines: list[str], prompt: str, heading: str = "") -> list[list[str]]:
        """The lines in groups that fit, with the prompt and reply, in the context window."""
        budget = (
            self.context_tokens
            - OUTLINE_REPLY_TOKENS
            - self.count(prompt)
            - self.count(heading)
            - 2 * TOKENS_PER_MESSAGE
        )
        if budget < 100:
            budget = 100  # a tiny window: asked anyway, and the LLM says if it's refused
        found: list[list[str]] = [[]]
        used = 0
        for line in lines:
            for piece in cut(line, budget, self.count):
                n = self.count(piece) + 2
                if found[-1] and used + n > budget:
                    found.append([])
                    used = 0
                found[-1].append(piece)
                used += n
        return [batch for batch in found if batch]

    def request(
        self, prompt: str, text: str, schema: dict[str, Any], read: Callable[[str], T | None]
    ) -> T | None:
        """The LLM's answer, read; asked twice if the first can't be used, None if neither can.
        While the LLM can't be reached, waits and asks again."""
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": text}]
        self.requests += 1
        start = time.perf_counter()
        found: T | None = None
        for attempt in (1, 2):
            answer = self.answer(messages, schema)
            found = read(answer)
            if found is not None:
                break
            logger.warning(
                "The LLM's wiki outline answer could not be used",
                extra={"id": self.pdf_id, "attempt": attempt, "answer": answer[:300]},
            )
        logger.info(
            "Wiki outline step done",
            extra={
                "id": self.pdf_id,
                "step": "sections" if schema is SECTIONS_SCHEMA else "detail",
                "request": self.requests,
                "used": found is not None,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        if self.progress:
            self.progress(self.requests, max(self.planned, self.requests))
        return found

    def answer(self, messages: list[Message], schema: dict[str, Any]) -> str:
        while True:
            try:
                return self.ask(messages, schema)
            except EmptyReply:
                return ""
            except LlmError as e:
                if self.wait_for_llm is None or not down(e):
                    raise
                self.wait_for_llm(e, self.requests, 0)


def read_sections(answer: str, numbers: set[int]) -> list[tuple[str, str, list[int]]] | None:
    """The sections in the LLM's answer, with only the topics asked about; None if none."""
    data = load_json(answer)
    sections = data.get("sections") if isinstance(data, dict) else None
    found = []
    for section in sections if isinstance(sections, list) else []:
        if not isinstance(section, dict):
            continue
        title, summary = clean_title(section.get("title")), section.get("summary")
        given = section.get("topics")
        members = (
            [n for n in given if type(n) is int and n in numbers] if isinstance(given, list) else []
        )
        if title and isinstance(summary, str) and summary.strip() and members:
            found.append((title, summary.strip(), list(dict.fromkeys(members))))
    return found or None


def read_detail(answer: str, numbers: set[int]) -> tuple[str, list[tuple[str, list[int]]]] | None:
    """The summary and parts in the LLM's answer, each part with only the paragraphs asked
    about; None if it has no summary or parts."""
    data = load_json(answer)
    if not isinstance(data, dict):
        return None
    summary, parts = data.get("summary"), data.get("parts")
    found = []
    for part in parts if isinstance(parts, list) else []:
        if not isinstance(part, dict):
            continue
        title, given = clean_title(part.get("title")), part.get("paragraphs")
        members = (
            [n for n in given if type(n) is int and n in numbers] if isinstance(given, list) else []
        )
        if title and members:
            found.append((title, list(dict.fromkeys(members))))
    if not isinstance(summary, str) or not summary.strip() or not found:
        return None
    return summary.strip(), found


def opens(source: list[Unit], depth: int) -> bool:
    """Whether an entry on this level gets a detail page of its source's parts."""
    return depth < MAX_DEPTH and len(source) > 1 and not simple(" ".join(t for _, t in source))


def numbered(source: list[Unit]) -> list[str]:
    return [f"{n}. {text}" for n, (_, text) in enumerate(source, 1)]


def units(page: int, text: str) -> list[Unit]:
    """A paragraph of the PDF, in pieces short enough to show as they are."""
    found: list[Unit] = []
    sentences_in: list[str] = []
    for sentence in SENTENCE_END.split(text.strip()):
        if sentences_in and not simple(" ".join([*sentences_in, sentence])):
            found.append((page, " ".join(sentences_in)))
            sentences_in = []
        if sentence:
            sentences_in.append(sentence)
    if sentences_in:
        found.append((page, " ".join(sentences_in)))
    return found


def sentences(text: str) -> int:
    return len([s for s in SENTENCE_END.split(text.strip()) if s])


def simple(text: str) -> bool:
    return sentences(text) <= SIMPLE_SENTENCES and len(text) <= SIMPLE_CHARS


def first_sentence(text: str) -> str:
    return SENTENCE_END.split(text.strip(), maxsplit=1)[0]


def count_detail(entry: Entry) -> int:
    return entry.detail + sum(count_detail(e) for e in entry.entries)


def plain_outline(topics: list[WikiPage]) -> list[Entry]:
    """The topics as the table of contents, as they are, without asking the LLM."""
    return [Entry(t.id, t.title, t.text, t.pages) for t in topics]


def find(entries: list[Entry], entry_id: str) -> Entry | None:
    for entry in entries:
        if entry.id == entry_id:
            return entry
        found = find(entry.entries, entry_id)
        if found is not None:
            return found
    return None


def shown(entry: Entry) -> dict[str, Any]:
    """An entry as its page shows it: its parts, and theirs down to the next detail pages, whose
    own parts are on those pages."""
    return {
        "id": entry.id,
        "title": entry.title,
        "summary": entry.summary,
        "pages": entry.pages,
        "detail": entry.detail,
        "entries": [part(e) for e in entry.entries],
    }


def part(entry: Entry) -> dict[str, Any]:
    if entry.detail:
        return {**shown(entry), "entries": []}
    return shown(entry)


def from_saved(data: list[dict[str, Any]]) -> list[Entry]:
    return [
        Entry(d["id"], d["title"], d["summary"], d["pages"], from_saved(d["entries"]), d["detail"])
        for d in data
    ]
