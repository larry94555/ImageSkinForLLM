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

from imageskin.chat import (
    TOKENS_PER_MESSAGE,
    Count,
    EmptyReply,
    LlmError,
    LlmStarting,
    Message,
    unreachable,
)

logger = logging.getLogger(__name__)

# The longest answer asked for per part: up to 6 topics of 2 or 3 sentences each. The detail
# comes from the PDF itself (wiki_outline), so the LLM writes only a summary of each topic,
# which keeps the build fast: most of an LLM request's time is spent writing its answer.
WIKI_REPLY_TOKENS = 800
# The most the titles found so far may take in the prompt; the latest that fit are passed on.
TITLES_TOKENS = 300
MAX_TITLE_CHARS = 80
# A piece too long for one part is cut into parts of at most this many characters.
MIN_CUT_CHARS = 200

WIKI_PROMPT = (
    "You are building a wiki from a document. Below is one part of it; each piece starts with its"
    " page number in square brackets. List the main topics this part covers, at most 6. For each"
    " topic give a short title of a few words, the page numbers it comes from, and a summary of 2"
    " or 3 sentences of what the document says about it, in plain words, using only what the"
    " document says. Answer with JSON only, in this form:"
    ' {"topics": [{"title": "…", "pages": [1, 2], "text": "…"}]}'
)
KNOWN_PROMPT = "Topics found in earlier parts (reuse a title exactly when this part continues it):"

# Asks the LLM about one part (the messages) and returns its answer, or raises LlmError.
AskForTopics = Callable[[list[Message]], str]
Progress = Callable[[int, int], None]  # parts done, parts in all
# Called when the LLM can't be reached while a part is asked (with the error, the part and the
# parts in all); it waits, then the same part is asked again, so the parts already done are kept.
# It may raise to stop the build.
WaitForLlm = Callable[[LlmError, int, int], None]

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
    wait_for_llm: WaitForLlm | None = None,
) -> Wiki:
    """Turn a reading's pieces into wiki pages. LlmError when the LLM can't be reached and
    there is no `wait_for_llm`."""
    budget = context_tokens - WIKI_REPLY_TOKENS - prompt_tokens(count)
    if budget < 200:
        logger.error("The LLM's context window is too small", extra={"tokens": context_tokens})
        raise WikiError(
            "The AI can't take in enough of the PDF at once to build its wiki. Whoever set up"
            " the app can give it more room."
        )
    parts = split(pieces, budget, count)
    wiki = Wiki(len(parts))
    if progress:
        progress(0, len(parts))  # how many parts there are, before the first is asked for
    topics: dict[str, WikiPage] = {}  # by normalized title, in the order found
    for number, part in enumerate(parts, start=1):
        start = time.perf_counter()
        known = latest_titles([t.title for t in topics.values()], count)
        while True:
            try:
                found = ask_part(part, known, ask)
                break
            except LlmError as e:
                if wait_for_llm is None or not down(e):
                    raise
                wait_for_llm(e, number, len(parts))
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
        raise WikiError(
            "The AI's answers for this PDF couldn't be used. Rebuild the wiki to try again."
        )
    used: set[str] = set()
    for page in topics.values():
        page.id = unique(f"{pdf_id}-{slug(page.title)}", used)
        wiki.pages.append(page)
    return wiki


def prompt_tokens(count: Count) -> int:
    """The most a part's prompt can take besides the part: the instructions, the titles found so
    far, and the two messages' framing."""
    return count(f"{WIKI_PROMPT}\n\n{KNOWN_PROMPT} ") + TITLES_TOKENS + 2 * TOKENS_PER_MESSAGE


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
        # Every cut of a long piece is marked with its page, so none is put down to the next.
        marker = f"[page {piece['page']}] "
        for cut_text in cut(piece["text"], budget - count(marker), count):
            text = marker + cut_text
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


def latest_titles(titles: list[str], count: Count) -> list[str]:
    """The latest titles that fit in TITLES_TOKENS, oldest first."""
    kept: list[str] = []
    room = TITLES_TOKENS
    for title in reversed(titles):
        room -= count(title) + 1  # and the "; " between titles
        if room < 0:
            break
        kept.append(title)
    return list(reversed(kept))


def down(e: LlmError) -> bool:
    """Whether the LLM couldn't be reached at all, or is still loading its model, as opposed to
    answering badly or refusing."""
    return isinstance(e, LlmStarting) or e.__cause__ is not None and unreachable(e.__cause__)


def ask_part(
    part: Part, known: list[str], ask: AskForTopics
) -> list[tuple[str, list[int], str]] | None:
    """The topics the LLM finds in one part, asked twice if the first answer can't be used; None
    if neither can. LlmError when the request itself fails: the LLM can't be reached, or it
    refused the request, which asking again would not change."""
    prompt = WIKI_PROMPT if not known else f"{WIKI_PROMPT}\n\n{KNOWN_PROMPT} {'; '.join(known)}"
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": part.text}]
    for attempt in (1, 2):
        try:
            answer = ask(messages)
        except EmptyReply:
            answer = ""  # the LLM's output, like an answer that can't be parsed
        # Any other LlmError (unreachable, refused, unreadable) is passed on.
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
    data = load_json(answer)
    topics = data.get("topics") if isinstance(data, dict) else None
    found = []
    for topic in topics if isinstance(topics, list) else []:
        if not isinstance(topic, dict):
            continue
        title, text = topic.get("title"), topic.get("text")
        if not isinstance(title, str) or not isinstance(text, str):
            continue
        title, text = clean_title(title), text.strip()
        if not title or not text:
            continue
        given = topic.get("pages")
        cited = sorted(
            {p for p in given if type(p) is int and p in pages} if isinstance(given, list) else []
        )
        found.append((title, cited or pages, text))
    return found


def load_json(answer: str) -> Any:
    """The JSON object in the LLM's answer, even inside other words or ```json; None if none."""
    try:
        return json.loads(answer)
    except ValueError:
        start, end = answer.find("{"), answer.rfind("}")
        try:
            return json.loads(answer[start : end + 1]) if 0 <= start < end else None
        except ValueError:
            return None


def clean_title(title: object) -> str:
    """A title on one line and not too long, or "" if it isn't text."""
    return " ".join(title.split())[:MAX_TITLE_CHARS] if isinstance(title, str) else ""


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
