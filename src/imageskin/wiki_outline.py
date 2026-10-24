"""The wiki as an outline (roadmap R37a, item 26): each PDF's table of contents.

The topics R37 finds (`wiki.build_wiki`) are grouped by the LLM into the sections of a table of
contents, each with a short summary. Each topic is shown with the LLM's few sentences on it. When
what the PDF itself says on the topic's pages is simple enough, that is all; when it says more,
the topic gets a detail page: the LLM groups the PDF's paragraphs about the topic into parts and
summarizes them, and each part is again either simple enough to show in the PDF's own words or a
detail page of its own, down to MAX_DEPTH levels. The LLM writes only titles and summaries, not
the PDF's text again, which keeps the build fast (most of an LLM request's time is spent writing
its answer). If the LLM can't group or split something, it stays as it is.

Once built, each paragraph of the PDF that is in no entry (the LLM left it out of a topic's parts,
or no topic names its page) is put back, at its place in the PDF's order (R98b).
"""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any, TypeVar

from imageskin.chat import TOKENS_PER_MESSAGE, Count, EmptyReply, LlmError, Message
from imageskin.wiki import (
    JSON_ONLY,
    WaitForLlm,
    WikiPage,
    clean_title,
    cut,
    down,
    load_json,
    slug,
    unique,
)

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
    " the numbers of its topics. Put every topic in exactly one section."
    f' {JSON_ONLY} {{"sections": [{{"title": "…", "summary": "…", "topics": [1, 2]}}]}}'
)
SUMMARY_PROMPT = (
    "Below are summaries of consecutive parts of a text from a document, in order; the topic is"
    " in the first line. Write one summary of the whole text in 1 or 2 sentences, using only"
    f' what they say. {JSON_ONLY} {{"summary": "…"}}'
)
# The detail of a topic or part. Both start the same, up to what is asked for besides the parts,
# so llama-server reuses that start whichever was asked before (R98).
DETAIL_START = (
    "Below are numbered paragraphs from a document, in its order; the topic is in the first"
    " line. Using only what they say about that topic, group the paragraphs about it into 2 to 6"
    " parts that each cover one point, in order, each with a short title of a few words and the"
    " numbers of its paragraphs. Leave out paragraphs that are not about the topic."
)
DETAIL_PROMPT = (
    f"{DETAIL_START} Also write a summary of the topic in 1 or 2 sentences. {JSON_ONLY}"
    ' {"summary": "…", "parts": [{"title": "…", "paragraphs": [1, 2]}]}'
)
# A topic keeps the summary it was found with, so only its parts are asked for (R98).
PARTS_PROMPT = f'{DETAIL_START} {JSON_ONLY} {{"parts": [{{"title": "…", "paragraphs": [1, 2]}}]}}'

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
SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
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
PARTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"parts": DETAIL_SCHEMA["properties"]["parts"]},
    "required": ["parts"],
}

# Each request's step in the log, by its schema.
STEPS = {
    id(SECTIONS_SCHEMA): "sections",
    id(DETAIL_SCHEMA): "detail",
    id(PARTS_SCHEMA): "parts",
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
    # The PDF's paragraphs (its units) in its order, those in an entry so far, and where in that
    # order each entry starts (R98b).
    order: dict[Unit, int] = field(default_factory=dict)
    kept: set[Unit] = field(default_factory=set)
    starts: dict[str, int] = field(default_factory=dict)

    def outline(
        self, topics: list[WikiPage], pieces: list[dict[str, Any]] | None = None
    ) -> list[Entry]:
        """The table of contents: sections of topics, or the topics alone when there are few.
        `pieces` is what was read in the PDF, each with its page: a topic's detail comes from
        the pieces on its pages."""
        start = time.perf_counter()
        logger.info("Building wiki outline", extra={"id": self.pdf_id, "topics": len(topics)})
        self.used.update(t.id for t in topics)  # a topic's entry keeps its page's id
        for p in pieces or []:
            for u in units(p["page"], p["text"]):
                self.order.setdefault(u, len(self.order))
        sources = [self.source(t, pieces or []) for t in topics]
        for t, source in zip(topics, sources, strict=True):
            if opens(source, 2):
                batches = self.batches(numbered(source), PARTS_PROMPT, t.title)
                self.planned += requests_for(batches, summarized=False)
        if len(topics) > FEW_TOPICS:
            self.planned += len(self.batches(self.contents_lines(topics), SECTIONS_PROMPT))
        entries = [
            self.entry(t.title, t.text, source, t.pages, 2, t.id, planned=True)
            for t, source in zip(topics, sources, strict=True)
        ]
        contents = self.sections(topics, entries) if len(topics) > FEW_TOPICS else entries
        contents = self.put_back(topics, entries, contents)
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
        here = [self.order[u] for u in source if u in self.order]
        if here:
            self.starts[entry_id] = min(here)
        if not opens(source, depth):
            self.kept.update(source)  # shown as it is, or simple enough for the topic's own text
            return entry
        found = self.split(title, source, planned, summarize=summary is None)
        if found is None:
            if summary is None:
                self.kept.update(source)  # a part that can't be split shows its own words
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
        """The entries grouped into sections, in batches that fit the context window, in the
        document's order whatever order the LLM answers in. A topic the LLM leaves out stays in
        the table of contents on its own, where it was; so does a section's topics when they
        aren't next to each other."""
        lines = self.contents_lines(topics)
        contents: list[tuple[int, Entry]] = []  # by the number of its first topic
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
                members = sorted(n for n in members if n not in placed)
                if not members or members[-1] - members[0] + 1 != len(members):
                    continue  # none left, or not next to each other
                placed.update(members)
                children = [entries[n - 1] for n in members]
                pages = sorted({p for c in children for p in c.pages})
                section_id = unique(f"{self.pdf_id}-{slug(title)}", self.used)
                contents.append((members[0], Entry(section_id, title, summary, pages, children)))
            for n in sorted(numbers - placed):
                contents.append((n, entries[n - 1]))
                placed.add(n)
        return [entry for _, entry in sorted(contents, key=lambda c: c[0])]

    def put_back(
        self, topics: list[WikiPage], entries: list[Entry], contents: list[Entry]
    ) -> list[Entry]:
        """The contents with each paragraph of the PDF that is in no entry put back, in the PDF's
        own words, at its place in the PDF's order: in the first topic that has its page, or in
        an entry of its own titled from its page when no topic has it. Paragraphs next to each
        other on the same page go back together."""
        groups: list[tuple[int, list[Unit]]] = []  # by where the first is in the PDF's order
        for u, n in self.order.items():
            if u in self.kept:
                continue
            last = groups[-1] if groups else None
            if last and last[0] + len(last[1]) == n and last[1][-1][0] == u[0]:
                last[1].append(u)
            else:
                groups.append((n, [u]))
        for start, group in groups:
            page = group[0][0]
            owner = next((e for t, e in zip(topics, entries, strict=True) if page in t.pages), None)
            title = f"More from page {page}" if owner else f"Page {page}"
            entry_id = unique(f"{self.pdf_id}-{slug(title)}", self.used)
            self.starts[entry_id] = start
            entry = Entry(entry_id, title, " ".join(t for _, t in group), [page])
            if owner:
                owner.detail = True
                self.insert(owner.entries, entry)
            else:
                self.insert(contents, entry)
        logger.info(
            "Wiki paragraphs put back",
            extra={
                "id": self.pdf_id,
                "paragraphs": sum(len(g) for _, g in groups),
                "pages": sorted({g[0][0] for _, g in groups}),
            },
        )
        return contents

    def insert(self, entries: list[Entry], entry: Entry) -> None:
        """Puts an entry among others before the first that starts later in the PDF."""
        start = self.start(entry)
        at = next((i for i, e in enumerate(entries) if self.start(e) > start), len(entries))
        entries.insert(at, entry)

    def start(self, entry: Entry) -> float:
        """Where an entry starts in the PDF's order: its own, or its first part's (a section's)."""
        if entry.id in self.starts:
            return self.starts[entry.id]
        return min((self.start(e) for e in entry.entries), default=float("inf"))

    def contents_lines(self, topics: list[WikiPage]) -> list[str]:
        return [f"{n}. {t.title}: {first_sentence(t.text)}" for n, t in enumerate(topics, 1)]

    def split(
        self, title: str, source: list[Unit], planned: bool = False, summarize: bool = True
    ) -> tuple[str, list[tuple[str, list[int]]]] | None:
        """A long source's summary and its parts, each with the numbers of its units (from 1);
        None if the LLM couldn't split it. A unit goes to the first part that names it; a batch
        with no usable answer (it may say nothing about the topic) adds no parts. When several
        batches were summarized, their summaries are summarized as one. Without `summarize`
        (the entry has its summary already) only the parts are asked for, and the summary is ""."""
        prompt, schema = DETAIL_PROMPT, DETAIL_SCHEMA
        if not summarize:
            prompt, schema = PARTS_PROMPT, PARTS_SCHEMA
        summaries: list[str] = []
        parts: list[tuple[str, list[int]]] = []
        placed: set[int] = set()
        batches = self.batches(numbered(source), prompt, title)
        if not planned:
            self.planned += requests_for(batches, summarize)
        for batch in batches:
            numbers = {int(m.group(1)) for line in batch if (m := NUMBERED.match(line))}
            read = partial(read_detail, numbers=numbers, summarized=summarize)
            found = self.request(prompt, f"{title}\n\n" + "\n\n".join(batch), schema, read)
            for part_title, members in found[1] if found else []:
                members = [n for n in members if n not in placed]
                if members:
                    placed.update(members)
                    parts.append((part_title, sorted(members)))
            if found:
                summaries.append(found[0])
        if summarize and len(batches) > 1:  # planned for, whatever the batches gave
            summaries = [self.summarize(title, summaries)] if summaries else []
        parts.sort(key=lambda part: part[1][0])
        return (summaries[0], parts) if summaries and len(parts) > 1 else None

    def summarize(self, title: str, summaries: list[str]) -> str:
        """One summary of several batches' summaries; them joined, if the LLM can't. When they
        don't fit in one request, each batch of them is summarized first, and so on."""
        joined = " ".join(summaries)
        if len(summaries) < 2:
            self.planned -= 1  # the request planned for isn't needed
            return joined
        batches = self.batches(summaries, SUMMARY_PROMPT, title)
        if len(batches) == 1:
            return self.summary_of(title, summaries)
        if len(batches) == len(summaries):  # one a batch: summarizing them would never end
            logger.warning(
                "The wiki outline's summaries are too long to summarize as one",
                extra={"id": self.pdf_id, "summaries": len(summaries)},
            )
            self.planned -= 1
            return joined
        self.planned += len(batches)  # a level more; the last request is planned for already
        return self.summarize(title, [self.summary_of(title, batch) for batch in batches])

    def summary_of(self, title: str, summaries: list[str]) -> str:
        text = f"{title}\n\n" + "\n\n".join(summaries)
        return self.request(SUMMARY_PROMPT, text, SUMMARY_SCHEMA, read_summary) or " ".join(
            summaries
        )

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
                "step": STEPS.get(id(schema), "summary"),
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


def read_detail(
    answer: str, numbers: set[int], summarized: bool = True
) -> tuple[str, list[tuple[str, list[int]]]] | None:
    """The summary and parts in the LLM's answer, each part with only the paragraphs asked
    about; None if it has no summary or parts. Not `summarized`, only parts were asked for, and
    the summary is ""."""
    data = load_json(answer)
    if not isinstance(data, dict):
        return None
    summary, parts = data.get("summary") if summarized else "-", data.get("parts")
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
    return (summary.strip() if summarized else ""), found


def requests_for(batches: list[list[str]], summarized: bool = True) -> int:
    """The requests a split takes: one a batch, and one to summarize them when there are several
    and they were summarized."""
    return len(batches) + (summarized and len(batches) > 1)


def read_summary(answer: str) -> str | None:
    data = load_json(answer)
    summary = data.get("summary") if isinstance(data, dict) else None
    return summary.strip() if isinstance(summary, str) and summary.strip() else None


def opens(source: list[Unit], depth: int) -> bool:
    """Whether an entry on this level gets a detail page of its source's parts."""
    return depth < MAX_DEPTH and len(source) > 1 and not simple(" ".join(t for _, t in source))


def numbered(source: list[Unit]) -> list[str]:
    return [f"{n}. {text}" for n, (_, text) in enumerate(source, 1)]


def units(page: int, text: str) -> list[Unit]:
    """A paragraph of the PDF, in pieces short enough to show as they are; a sentence too long
    for one (a table or list with no full stops, say) is cut at spaces."""
    pieces = [
        piece
        for sentence in SENTENCE_END.split(text.strip())
        if sentence
        for piece in cut(sentence, SIMPLE_CHARS, len)
    ]
    found: list[Unit] = []
    group: list[str] = []
    for piece in pieces:
        if group and not simple(" ".join([*group, piece])):
            found.append((page, " ".join(group)))
            group = []
        group.append(piece)
    if group:
        found.append((page, " ".join(group)))
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


def ancestors(entries: list[Entry], entry_id: str) -> list[Entry] | None:
    """The entries above an entry, from the top of the outline down; None if it isn't there."""
    for entry in entries:
        if entry.id == entry_id:
            return []
        found = ancestors(entry.entries, entry_id)
        if found is not None:
            return [entry, *found]
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
