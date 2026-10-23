"""`imageskin time-llm`: how fast llama-server answers with the settings it was started with
(roadmap R97). It asks the server what the app asks it, without the app: the replies' warm-up
and three prompts of a conversation, streamed as the chat streams them, then the first part of
the sample PDF's wiki, as the wiki asks for it. Run once for each setting (threads, batch size,
flash attention, the model and its quantization, the context size), each run adds its row to
one table, so the settings can be compared side by side. `experiments/speed/llama_settings.sh`
starts llama-server with each setting in turn and runs this against it."""

import json
import logging
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from imageskin.chat import (
    REPLY_TOKENS,
    TEMPERATURE,
    LlmClient,
    LlmSettings,
    Message,
    ms_since,
    system_message,
)
from imageskin.pdf_reading import read_pdf
from imageskin.sentences import SentenceSplitter
from imageskin.time_reply import DEFAULT_PROMPTS, cell, table
from imageskin.wiki import TOPICS_SCHEMA, WIKI_PROMPT, WIKI_REPLY_TOKENS, Part, parse, split
from imageskin.wiki import prompt_tokens as wiki_prompt_tokens

logger = logging.getLogger(__name__)

DEFAULT_LLM_URL = "http://127.0.0.1:8080"
SAMPLE_PDF = Path("experiments/speed/sample.pdf")
READY_LIMIT_S = 1800  # the first start downloads the model, about 2.5 GB for 4B
READY_POLL_S = 1.0
ANSWER_LIMIT_S = 1200  # a wiki part on 2 slow threads takes about 4 minutes
# Every setting is asked for the same wiki part, cut as for a 4096-token window, so the times
# compare; a larger window would cut the PDF into fewer, longer parts.
PART_CONTEXT = 4096
# The sample PDF's wiki in the cloud (R96a, pdf-cloud-2026-10-22-run3): the tokens its 36
# requests read, less those reused from llama-server's cache, and wrote. A setting's reading and
# writing speeds turn these into the time that wiki would take.
WIKI_READ_TOKENS = 24936 - 872
WIKI_WRITTEN_TOKENS = 12521
RESULTS = "llm-settings"


class LlmTimingError(Exception):
    """llama-server didn't answer as expected; the message says what happened."""


def root_of(url: str) -> str:
    return url.rstrip("/").removesuffix("/v1")


def get(url: str, timeout: float = 10) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read())


def post(url: str, body: dict[str, Any]) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=ANSWER_LIMIT_S)


def wait_ready(root: str) -> float:
    """Seconds until llama-server answers /health with 200, once its model is loaded."""
    limit_s = READY_LIMIT_S
    start = time.perf_counter()
    while True:
        try:
            get(root + "/health")
            return round(time.perf_counter() - start, 1)
        except (OSError, ValueError) as e:  # refused while starting, 503 while loading
            if time.perf_counter() - start > limit_s:
                raise LlmTimingError(
                    f"llama-server at {root} wasn't ready in {limit_s} s: {e}"
                ) from e
            time.sleep(READY_POLL_S)


def server_props(root: str) -> dict[str, Any]:
    """What llama-server says it was started with: the model, the context window, the slots."""
    props = get(root + "/props")
    settings = props.get("default_generation_settings") or {}
    model = str(props.get("model_path") or "")
    return {
        "model": model.replace("\\", "/").rsplit("/", 1)[-1] or "unknown",
        "n_ctx": settings.get("n_ctx") or props.get("n_ctx"),
        "slots": props.get("total_slots"),
        "build": props.get("build_info"),
    }


def events(response: Any) -> Iterator[dict[str, Any]]:
    """The server-sent events of a streamed answer, as the chat reads them."""
    for raw in response:
        line = raw.decode(errors="replace").strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            return
        yield json.loads(data)


def warm_up(root: str) -> float:
    """The replies' warm-up as the app does it (R22a): the system prompt read, one token
    written, so the first reply can reuse what was read."""
    start = time.perf_counter()
    body = {
        "messages": [system_message(None), {"role": "user", "content": "Hello."}],
        "max_tokens": 1,
        "temperature": TEMPERATURE,
    }
    with post(root + "/v1/chat/completions", body) as response:
        response.read()
    return ms_since(start)


def stream_reply(root: str, messages: list[Message]) -> dict[str, Any]:
    """One streamed reply, as the chat asks for it: when its first token and first sentence
    came, its last token, and llama-server's own timings."""
    body = {
        "messages": messages,
        "max_tokens": REPLY_TOKENS,
        "temperature": TEMPERATURE,
        "stream": True,
    }
    splitter = SentenceSplitter(first_clause=True)
    text = ""
    first_token = first_sentence = None
    timings: dict[str, Any] = {}
    start = time.perf_counter()
    with post(root + "/v1/chat/completions", body) as response:
        for event in events(response):
            timings = event.get("timings") or timings
            choices = event.get("choices") or [{}]
            piece = (choices[0].get("delta") or {}).get("content") or ""
            if not piece:
                continue
            first_token = first_token or ms_since(start)
            text += piece
            if first_sentence is None and splitter.feed(piece):
                first_sentence = ms_since(start)
    last_token = ms_since(start)
    return {
        "first_token_ms": first_token,
        "first_sentence_ms": first_sentence or last_token,
        "last_token_ms": last_token,
        "text": text.strip(),
        "llm": llm_timings(timings),
    }


def llm_timings(timings: dict[str, Any]) -> dict[str, Any]:
    """llama-server's timings for a request: tokens read (and reused) and written, and their
    speeds."""
    return {
        "prompt_n": timings.get("prompt_n"),
        "cache_n": timings.get("cache_n"),
        "prompt_per_second": rounded(timings.get("prompt_per_second")),
        "predicted_n": timings.get("predicted_n"),
        "predicted_per_second": rounded(timings.get("predicted_per_second")),
    }


def rounded(value: object) -> float | None:
    return round(value, 1) if isinstance(value, int | float) else None


def time_replies(root: str, prompts: list[str]) -> list[dict[str, Any]]:
    """The warm-up, then each prompt in one conversation, as the chat sends them."""
    warm_up(root)
    history: list[Message] = [system_message(None)]
    replies = []
    for prompt in prompts:
        history.append({"role": "user", "content": prompt})
        reply = stream_reply(root, history)
        history.append({"role": "assistant", "content": reply["text"]})
        replies.append(reply)
    return replies


def first_part(pdf: Path, root: str) -> Part:
    """The PDF's first wiki part, cut as the wiki cuts it for a PART_CONTEXT-token window, with
    the server's own token counts."""
    count = LlmClient(LlmSettings(url=root + "/v1")).count
    reading = read_pdf(pdf)
    pieces = [{"page": p.page, "text": p.text} for p in reading.pieces]
    budget = PART_CONTEXT - WIKI_REPLY_TOKENS - wiki_prompt_tokens(count)
    parts = split(pieces, budget, count)
    if not parts:
        raise LlmTimingError(f"No text was read in {pdf}")
    return parts[0]


def time_wiki_part(root: str, part: Part) -> dict[str, Any]:
    """The part asked for as the wiki asks for it (R37), and the topics found in the answer."""
    body = {
        "messages": [
            {"role": "system", "content": WIKI_PROMPT},
            {"role": "user", "content": part.text},
        ],
        "max_tokens": WIKI_REPLY_TOKENS,
        "temperature": TEMPERATURE,
        "response_format": {"type": "json_object", "schema": TOPICS_SCHEMA},
    }
    start = time.perf_counter()
    with post(root + "/v1/chat/completions", body) as response:
        data = json.loads(response.read())
    took = ms_since(start)
    try:
        answer = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise LlmTimingError("llama-server sent a wiki answer without a reply") from e
    return {
        "took_ms": took,
        "topics": [title for title, _, _ in parse(answer, part.pages)],
        "llm": llm_timings(data.get("timings") or {}),
    }


def wiki_estimate_s(wiki: dict[str, Any]) -> float | None:
    """The time the sample PDF's whole wiki would take at this part's speeds."""
    read = wiki["llm"]["prompt_per_second"]
    written = wiki["llm"]["predicted_per_second"]
    if not read or not written:
        return None
    return float(round(WIKI_READ_TOKENS / read + WIKI_WRITTEN_TOKENS / written))


def measure(url: str, label: str, pdf: Path, prompts: list[str]) -> dict[str, Any]:
    """One setting's row: llama-server's readiness and props, the replies and the wiki part."""
    root = root_of(url)
    ready_s = wait_ready(root)
    part = first_part(pdf, root)
    replies = time_replies(root, prompts)
    wiki = time_wiki_part(root, part)
    return {
        "label": label,
        "measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ready_s": ready_s,
        "server": server_props(root),
        "replies": replies,
        "wiki": wiki,
        "wiki_estimate_s": wiki_estimate_s(wiki),
    }


def minutes(seconds: float | None) -> str:
    return "-" if seconds is None else f"{seconds / 60:.1f} min"


def markdown(rows: list[dict[str, Any]]) -> str:
    """The settings side by side: the replies' speeds, the wiki part's, and the topics found."""
    out = [
        "# llama-server settings compared",
        "",
        "Replies: the three prompts of a conversation, after the warm-up. Times in milliseconds"
        " from the request; reading and writing in tokens a second, the replies' averaged.",
        "",
    ]
    reply_rows = []
    for r in rows:
        replies = r["replies"]
        reply_rows.append(
            [
                r["label"],
                r["server"]["model"],
                r["server"]["slots"],
                replies[0]["llm"]["cache_n"] if replies else None,
                " / ".join(cell(x["first_token_ms"]) for x in replies),
                " / ".join(cell(x["first_sentence_ms"]) for x in replies),
                average(x["llm"]["prompt_per_second"] for x in replies),
                average(x["llm"]["predicted_per_second"] for x in replies),
            ]
        )
    out.append(
        table(
            [
                "Setting",
                "Model",
                "Slots",
                "Reused after warm-up",
                "First token",
                "First sentence",
                "Read tokens/s",
                "Written tokens/s",
            ],
            reply_rows,
        )
    )
    out += [
        "",
        f"The wiki: the sample PDF's first part (cut for a {PART_CONTEXT}-token window), and the"
        " whole sample PDF's wiki estimated from its speeds and R96a's tokens"
        f" ({WIKI_READ_TOKENS} read, {WIKI_WRITTEN_TOKENS} written).",
        "",
    ]
    wiki_rows = [
        [
            r["label"],
            r["wiki"]["llm"]["prompt_n"],
            r["wiki"]["llm"]["prompt_per_second"],
            r["wiki"]["llm"]["predicted_n"],
            r["wiki"]["llm"]["predicted_per_second"],
            r["wiki"]["took_ms"],
            minutes(r["wiki_estimate_s"]),
            len(r["wiki"]["topics"]),
        ]
        for r in rows
    ]
    out.append(
        table(
            [
                "Setting",
                "Tokens read",
                "Read tokens/s",
                "Tokens written",
                "Written tokens/s",
                "Part took",
                "Sample PDF's wiki",
                "Topics",
            ],
            wiki_rows,
        )
    )
    out += ["", "The topics each setting found in the first part:", ""]
    for r in rows:
        out.append(f"- **{r['label']}:** {'; '.join(r['wiki']['topics']) or 'none'}")
    return "\n".join(out) + "\n"


def average(values: Iterator[object]) -> float | None:
    found = [v for v in values if isinstance(v, int | float)]
    return round(sum(found) / len(found), 1) if found else None


def saved_rows(path: Path) -> list[dict[str, Any]]:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return rows if isinstance(rows, list) else []


def run(url: str, label: str, pdf: Path, out: Path, prompts: list[str] | None = None) -> int:
    """Measure the llama-server at `url` and add its row, under `label`, to the table in `out`
    (a row of the same label is replaced); write the table as JSON and Markdown and print it."""
    start = time.perf_counter()
    logger.info("Timing llama-server", extra={"url": url, "label": label})
    try:
        row = measure(url, label, pdf, list(prompts or DEFAULT_PROMPTS))
    except (OSError, ValueError, LlmTimingError) as e:
        logger.error(
            "Could not time llama-server", extra={"url": url, "label": label, "error": str(e)}
        )
        return 1
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{RESULTS}.json"
    rows = [r for r in saved_rows(path) if r.get("label") != label] + [row]
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    report = markdown(rows)
    (out / f"{RESULTS}.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {(out / f'{RESULTS}.md').resolve()} and the .json beside it")
    logger.info(
        "llama-server timed",
        extra={
            "label": label,
            "model": row["server"]["model"],
            "first_sentence_ms": [r["first_sentence_ms"] for r in row["replies"]],
            "wiki_part_ms": row["wiki"]["took_ms"],
            "wiki_estimate_s": row["wiki_estimate_s"],
            "duration_ms": ms_since(start),
        },
    )
    return 0
