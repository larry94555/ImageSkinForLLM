"""Building the wiki from what was read in a PDF (roadmap R37, item 26).

The reading (R36) is cut into parts that fit the LLM's context window, each piece marked with its
page. For each part the LLM lists the topics it covers, each with a title, the pages it comes from
and a short page of text in its own words. A topic that goes on over several parts is merged into
one page (the LLM is told the titles found so far, so it reuses them), so the wiki has one page per
topic of the PDF, each linking back to the PDF's pages.

Each PDF has its own pages, so adding, replacing or removing a PDF rebuilds or removes only its
pages. The same topic in two PDFs is two pages, one per PDF.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from imageskin.chat import Count, LlmError, Message, unreachable

logger = logging.getLogger(__name__)

# The longest answer asked for per part: up to 6 topics of 3 to 8 sentences each.
WIKI_REPLY_TOKENS = 1200
# Room for the instructions and the titles found so far, besides the part itself.
PROMPT_TOKENS = 600
# The latest titles found so far that are passed on to the next part.
KNOWN_TITLES = 40
MAX_TITLE_CHARS = 80
# A piece too long for one part is cut into parts of at most this many characters.
MIN_CUT_CHARS = 200

WIKI_PROMPT = (
    "You are building a wiki from a document. Below is one part of it; each piece starts with its"
    " page number in square brackets. List the main topics this part covers, at most 6. For each"
    " topic give a short title of a few words, the page numbers it comes from, and a text of 3 to"
    " 8 sentences that explains what the document says about it, in plain words, using only what"
    " the document says. Answer with JSON only, in this form:"
    ' {"topics": [{"title": "…", "pages": [1, 2], "text": "…"}]}'
)
KNOWN_PROMPT = "Topics found in earlier parts (reuse a title exactly when this part continues it):"

# Asks the LLM about one part (the messages) and returns its answer, or raises LlmError.
AskForTopics = Callable[[list[Message]], str]
Progress = Callable[[int, int], None]  # parts done, parts in all

# What the LLM's answer must look like; servers that support it (llama-server, OpenAI) are held
# to it, and every answer is checked anyway.
TOPICS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "pages": {"type": "array", "items": {"type": "integer"}},
                    "text": {"type": "string"},
                },
                "required": ["title", "pages", "text"],
            },
        }
    },
    "required": ["topics"],
}


@dataclass
class WikiPage:
    id: str  # unique in the wiki: the PDF's id and the title's slug
    title: str
    text: str
    pages: list[int]  # the PDF's pages it comes from, from 1


@dataclass(frozen=True)
class Part:
    text: str
    pages: list[int]


@dataclass
class Wiki:
    parts: int
    pages: list[WikiPage] = field(default_factory=list)
    # Parts the LLM gave no usable answer for, even asked twice (from 1); their pages may be
    # missing from the wiki.
    skipped_parts: list[int] = field(default_factory=list)


class WikiError(Exception):
    """The wiki could not be built; the message says why, for the administrator."""


def build_wiki(
    pdf_id: str,
    pieces: list[dict[str, Any]],
    ask: AskForTopics,
    count: Count,
    context_tokens: int,
    progress: Progress | None = None,
) -> Wiki:
    """Turn a reading's pieces into wiki pages. LlmError when the LLM can't be reached."""
    budget = context_tokens - WIKI_REPLY_TOKENS - PROMPT_TOKENS
    if budget < 200:
        raise WikiError(
            f"The LLM's context window ({context_tokens} tokens) is too small to build the wiki."
        )
    parts = split(pieces, budget, count)
    wiki = Wiki(len(parts))
    topics: dict[str, WikiPage] = {}  # by normalized title, in the order found
    for number, part in enumerate(parts, start=1):
        start = time.perf_counter()
        found = ask_part(part, list(t.title for t in topics.values())[-KNOWN_TITLES:], ask)
        if found is None:
            wiki.skipped_parts.append(number)
        for title, pages, text in found or []:
            key = normalize(title)
            if key in topics:
                page = topics[key]
                page.text += "\n\n" + text
                page.pages = sorted({*page.pages, *pages})
            else:
                topics[key] = WikiPage("", title, text, pages)
        logger.info(
            "Wiki part done",
            extra={
                "id": pdf_id,
                "part": number,
                "parts": len(parts),
                "topics": len(found or []),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        if progress:
            progress(number, len(parts))
    if parts and len(wiki.skipped_parts) == len(parts):
        raise WikiError("The LLM gave no usable answer for this PDF; the log has what it said.")
    used: set[str] = set()
    for page in topics.values():
        page.id = unique(f"{pdf_id}-{slug(page.title)}", used)
        wiki.pages.append(page)
    return wiki


def split(pieces: list[dict[str, Any]], budget: int, count: Count) -> list[Part]:
    """The pieces, each marked with its page, in parts of at most `budget` tokens."""
    parts: list[Part] = []
    lines: list[str] = []
    pages: list[int] = []
    used = 0

    def close() -> None:
        nonlocal lines, pages, used
        if lines:
            parts.append(Part("\n\n".join(lines), sorted(set(pages))))
        lines, pages, used = [], [], 0

    for piece in pieces:
        for text in cut(f"[page {piece['page']}] {piece['text']}", budget, count):
            n = count(text) + 2  # the blank line between pieces
            if used + n > budget:
                close()
            lines.append(text)
            pages.append(piece["page"])
            used += n
    close()
    return parts


def cut(text: str, budget: int, count: Count) -> list[str]:
    """A text too long for one part, cut at spaces into pieces that fit."""
    n = count(text)
    if n <= budget:
        return [text]
    size = max(MIN_CUT_CHARS, len(text) * budget // n * 9 // 10)
    found: list[str] = []
    while text:
        if len(text) <= size:
            found.append(text)
            break
        at = text.rfind(" ", 0, size)
        at = at if at > 0 else size
        found.append(text[:at])
        text = text[at:].lstrip()
    return found


def ask_part(
    part: Part, known: list[str], ask: AskForTopics
) -> list[tuple[str, list[int], str]] | None:
    """The topics the LLM finds in one part, asked twice if the first answer can't be used; None
    if neither can. LlmError when the LLM can't be reached at all."""
    prompt = WIKI_PROMPT if not known else f"{WIKI_PROMPT}\n\n{KNOWN_PROMPT} {'; '.join(known)}"
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": part.text}]
    for attempt in (1, 2):
        try:
            answer = ask(messages)
        except LlmError as e:
            if e.__cause__ is not None and unreachable(e.__cause__):
                raise
            answer = str(e)  # refused or empty: no better asked again
        topics = parse(answer, part.pages)
        if topics:
            return topics
        logger.warning(
            "The LLM's wiki answer could not be used",
            extra={"attempt": attempt, "pages": part.pages, "answer": answer[:300]},
        )
    return None


def parse(answer: str, pages: list[int]) -> list[tuple[str, list[int], str]]:
    """The usable topics in the LLM's answer: each with a title and text, and only the part's
    pages (all of them when it gave none of the part's pages)."""
    try:
        data = json.loads(answer)
    except ValueError:
        start, end = answer.find("{"), answer.rfind("}")  # JSON inside other words, or ```json
        try:
            data = json.loads(answer[start : end + 1]) if 0 <= start < end else None
        except ValueError:
            data = None
    topics = data.get("topics") if isinstance(data, dict) else None
    found = []
    for topic in topics if isinstance(topics, list) else []:
        if not isinstance(topic, dict):
            continue
        title, text = topic.get("title"), topic.get("text")
        if not isinstance(title, str) or not isinstance(text, str):
            continue
        title, text = " ".join(title.split())[:MAX_TITLE_CHARS], text.strip()
        if not title or not text:
            continue
        given = topic.get("pages")
        cited = sorted(
            {p for p in given if type(p) is int and p in pages} if isinstance(given, list) else []
        )
        found.append((title, cited or pages, text))
    return found


def normalize(title: str) -> str:
    """'The Water Cycle.' and 'the water cycle' are the same topic."""
    return " ".join(re.sub(r"[^\w\s]", " ", title.casefold()).split())


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:60].strip("-") or "topic"


def unique(name: str, used: set[str]) -> str:
    candidate, n = name, 1
    while candidate in used:
        n += 1
        candidate = f"{name}-{n}"
    used.add(candidate)
    return candidate
