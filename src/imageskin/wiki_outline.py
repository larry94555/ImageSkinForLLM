"""The wiki as an outline (roadmap R37a, item 26): each PDF's table of contents.

The topics R37 finds (`wiki.build_wiki`) are grouped by the LLM into the sections of a table of
contents, each with a short summary. A topic simple enough to say in a few sentences is an entry
with its text as the summary. A longer one gets a short summary and a detail page of its own:
the LLM summarizes it and splits it into parts, and each part is again either simple enough to
show as it is or a detail page of its own, down to MAX_DEPTH levels. Nothing is dropped: if the
LLM can't group or split something, it stays as it is.
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

# An entry whose text has at most this many sentences is shown as it is (Larry, 2026-10-12).
SIMPLE_SENTENCES = 5
# Levels in all, the table of contents' sections being the first, so a long PDF can't make the
# build run on. An entry on the last level is shown as it is.
MAX_DEPTH = 4
# Tables of contents this short need no sections.
FEW_TOPICS = 3
# The longest answer asked for: a few sections, or a summary and the parts of a text.
OUTLINE_REPLY_TOKENS = 1200
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

SECTIONS_PROMPT = (
    "Below are the topics of a document, numbered, in the document's order, each with how it"
    " starts. Group them into the sections of a table of contents, keeping the document's order:"
    " 2 to 8 sections, each with a short title of a few words, a summary of 1 or 2 sentences, and"
    " the numbers of its topics. Put every topic in exactly one section. Answer with JSON only,"
    ' in this form: {"sections": [{"title": "…", "summary": "…", "topics": [1, 2]}]}'
)
DETAIL_PROMPT = (
    "Below is a text from a document, about the topic in its first line. Write a summary of it"
    " in 2 or 3 sentences, then split the text into 2 to 6 parts that each cover one point, each"
    " with a short title of a few words and its text. Keep everything the text says, in the same"
    " order, without adding anything. Answer with JSON only, in this form:"
    ' {"summary": "…", "parts": [{"title": "…", "text": "…"}]}'
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
                "properties": {"title": {"type": "string"}, "text": {"type": "string"}},
                "required": ["title", "text"],
            },
        },
    },
    "required": ["summary", "parts"],
}

# Asks the LLM for JSON held to a schema, and returns its answer; LlmError when that fails.
AskForJson = Callable[[list[Message], dict[str, Any]], str]
# The LLM requests made so far; the number in all grows as detail pages are found.
OutlineProgress = Callable[[int], None]


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
    used: set[str] = field(default_factory=set)

    def outline(self, topics: list[WikiPage]) -> list[Entry]:
        """The table of contents: sections of topics, or the topics alone when there are few."""
        start = time.perf_counter()
        logger.info("Building wiki outline", extra={"id": self.pdf_id, "topics": len(topics)})
        self.used.update(t.id for t in topics)  # a topic's entry keeps its page's id
        entries = [self.topic(t) for t in topics]
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

    def topic(self, page: WikiPage) -> Entry:
        return self.entry(page.title, page.text, page.pages, 2, page.id)

    def entry(
        self, title: str, text: str, pages: list[int], depth: int, entry_id: str = ""
    ) -> Entry:
        """An entry shown as it is when simple enough (or on the last level), else summarized
        with its parts on a detail page."""
        entry_id = entry_id or unique(f"{self.pdf_id}-{slug(title)}", self.used)
        entry = Entry(entry_id, title, text, pages)
        if depth >= MAX_DEPTH or simple(text):
            return entry
        found = self.split(title, text)
        if found is None:
            return entry  # kept whole: nothing is lost
        entry.summary, parts = found
        entry.entries = [self.entry(t, x, pages, depth + 1) for t, x in parts]
        entry.detail = True
        return entry

    def sections(self, topics: list[WikiPage], entries: list[Entry]) -> list[Entry]:
        """The entries grouped into sections, in batches that fit the context window. A topic
        the LLM leaves out stays in the table of contents on its own."""
        lines = [f"{n}. {t.title}: {first_sentence(t.text)}" for n, t in enumerate(topics, 1)]
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

    def split(self, title: str, text: str) -> tuple[str, list[tuple[str, str]]] | None:
        """A long text's summary and its parts; None if the LLM couldn't split it."""
        summary: str | None = None
        parts: list[tuple[str, str]] = []
        for batch in self.batches(text.split("\n\n"), DETAIL_PROMPT, title):
            text_batch = f"{title}\n\n" + "\n\n".join(batch)
            found = self.request(DETAIL_PROMPT, text_batch, DETAIL_SCHEMA, read_detail)
            if found is None:
                return None
            summary = summary or found[0]
            parts += found[1]
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
            self.progress(self.requests)
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


def read_detail(answer: str) -> tuple[str, list[tuple[str, str]]] | None:
    """The summary and parts in the LLM's answer; None if it has no summary or parts."""
    data = load_json(answer)
    if not isinstance(data, dict):
        return None
    summary, parts = data.get("summary"), data.get("parts")
    found = []
    for part in parts if isinstance(parts, list) else []:
        if isinstance(part, dict):
            title, text = clean_title(part.get("title")), part.get("text")
            if title and isinstance(text, str) and text.strip():
                found.append((title, text.strip()))
    if not isinstance(summary, str) or not summary.strip() or not found:
        return None
    return summary.strip(), found


def sentences(text: str) -> int:
    return len([s for s in SENTENCE_END.split(text.strip()) if s])


def simple(text: str) -> bool:
    return sentences(text) <= SIMPLE_SENTENCES


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
