"""Text chat with the LLM (feature items 10, 15 and 16, roadmap R15).

The LLM is reached through the OpenAI-compatible chat API that llama.cpp's llama-server offers,
so OpenAI is later a change of settings. The conversation is kept on the server, in memory, and
sent with each prompt so the LLM keeps context. The history it sends never takes more than half
of the model's context window, which leaves room for the prompt and the reply: when it would,
the older turns are summarized by the LLM, and the summary is sent in their place.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Literal

from imageskin.sentences import SentenceSplitter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are talking with someone face to face, and your replies are spoken aloud. Keep each"
    " reply short and conversational: one to three sentences in plain words, without lists,"
    " headings or code unless you are asked for them."
    # Asking for the checking as steps ("work out your answer, then check it") made the model
    # say the steps aloud, so the prompt states only what the reply must get right.
    " Everything you say must agree with what was said earlier in this conversation: keep"
    " track of who said what, and get every name and fact right. Reply only with the words you"
    " would say out loud, never with notes about your reply."
)
# The longest reply asked for. A short reply needs far less; this is room in the context window.
REPLY_TOKENS = 300
# How much randomness the LLM picks words with. llama-server's default (0.8) made a small model
# now and then mix up facts it was given, such as calling the user's name a good one for a dog.
TEMPERATURE = 0.3
# Tokens are counted by llama-server's own tokenizer (POST /tokenize). With a server that can't,
# each byte of UTF-8 counts as a token, the most a byte-level tokenizer can use, so no text
# (minified code, hashes, Chinese, emoji) can be undercounted. English runs about 4 characters to
# a token, so this fallback leaves the history about a quarter of the room a real count would.
# The chat template's framing around each message (Gemma's is 5 tokens, Qwen's 5).
TOKENS_PER_MESSAGE = 8
# The history (summary and turns) may use at most this share of the context window; the rest is
# for the system prompt, the new prompt and the reply.
HISTORY_SHARE = 0.5
# When summarizing, the latest messages (two prompts and their replies) are kept word for word.
KEEP_RECENT = 4
SUMMARY_PROMPT = (
    "Summarize the conversation below between a user and an assistant in at most 120 words."
    " Keep every name, fact, preference and decision the user mentioned, and what was agreed."
    " Write only the summary."
)
EARLIER = "Earlier in this conversation (summarized):"


@dataclass(frozen=True)
class LlmSettings:
    # llama-server's OpenAI-compatible API (started with --port 8080).
    url: str = "http://127.0.0.1:8080/v1"
    # llama-server answers with the model it loaded, whatever this says; OpenAI needs a name.
    model: str = "local"
    # The model's context window in tokens (llama-server's --ctx-size).
    context_tokens: int = 4096
    timeout_s: float = 120


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    content: str


Message = dict[str, str]
# Sends the messages to the LLM and returns its reply. LlmError when that fails.
AskLlm = Callable[[list[Message]], str]
# The same, handing back the reply's text in pieces as the LLM writes it (roadmap R20).
StreamLlm = Callable[[list[Message]], Iterator[str]]
# Told when a streamed reply starts (None), then given each sentence of it (roadmap R21).
OnSentence = Callable[[str | None], None]
# The number of tokens in a text.
Count = Callable[[str], int]


class LlmError(Exception):
    """The LLM could not be reached or gave no reply; the message says so in plain words."""


def estimate(text: str) -> int:
    """A count that never falls short of a real tokenizer's, for when the server can't count."""
    return len(text.encode())


def tokens(message: Message, count: Count = estimate) -> int:
    return count(message["content"]) + TOKENS_PER_MESSAGE


def as_message(turn: Turn) -> Message:
    return {"role": turn.role, "content": turn.content}


def system_message(summary: str | None) -> Message:
    content = SYSTEM_PROMPT if summary is None else f"{SYSTEM_PROMPT}\n\n{EARLIER}\n{summary}"
    return {"role": "system", "content": content}


def history_tokens(summary: str | None, turns: list[Turn], count: Count = estimate) -> int:
    """What the history costs: the summary (in the system message) and the turns."""
    extra = 0 if summary is None else count(f"\n\n{EARLIER}\n{summary}")
    return extra + sum(tokens(as_message(t), count) for t in turns)


def latest(turns: list[Turn], budget: int, count: Count = estimate) -> list[Turn]:
    """The latest turns that fit the budget, never starting on a reply whose prompt is left out."""
    kept: list[Turn] = []
    for turn in reversed(turns):
        budget -= tokens(as_message(turn), count)
        if budget < 0:
            break
        kept.append(turn)
    if kept and kept[-1].role == "assistant":
        kept.pop()
    return list(reversed(kept))


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def unreachable(e: Exception) -> bool:
    """The server didn't answer at all (not started yet, say), as opposed to answering no."""
    if isinstance(e, urllib.error.HTTPError):
        return False
    return isinstance(e, urllib.error.URLError | TimeoutError | ConnectionError)


class LlmClient:
    """Asks an OpenAI-compatible chat API, such as llama-server's, for a reply."""

    def __init__(self, settings: LlmSettings) -> None:
        self.settings = settings
        self._root = settings.url.rstrip("/").removesuffix("/v1")
        self._counted: dict[str, int] = {}  # each turn is counted again with every prompt
        self._can_count = True
        self._window: int | None = None  # once the server has answered

    def count(self, text: str) -> int:
        """Tokens in the text by llama-server's tokenizer, or estimated if it can't count."""
        if not self._can_count:
            return estimate(text)
        if text in self._counted:
            return self._counted[text]
        request = urllib.request.Request(
            self._root + "/tokenize",
            data=json.dumps({"content": text}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_s) as response:
                n = len(json.loads(response.read())["tokens"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            if unreachable(e):
                return estimate(text)  # the reply will say the server is down
            self._can_count = False
            logger.warning(
                "The LLM server can't count tokens; estimating them instead",
                extra={"error": str(e)},
            )
            return estimate(text)
        if len(self._counted) > 1000:
            self._counted.clear()
        self._counted[text] = n
        return n

    def context_tokens(self) -> int:
        """The context window llama-server was started with, or the configured one.

        Asked again until the server answers, so starting the app before llama-server works.
        """
        if self._window is not None:
            return self._window
        url = self._root + "/props"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                props = json.loads(response.read())
            n_ctx = props.get("default_generation_settings", {}).get("n_ctx") or props["n_ctx"]
            if type(n_ctx) is not int or n_ctx < 1024:
                raise ValueError(f"n_ctx is {n_ctx!r}")
        except (OSError, ValueError, KeyError, AttributeError) as e:
            logger.info(
                "LLM context window from the config",
                extra={"context_tokens": self.settings.context_tokens, "props_error": str(e)},
            )
            if not unreachable(e):
                self._window = self.settings.context_tokens
            return self.settings.context_tokens
        logger.info("LLM context window from the server", extra={"context_tokens": n_ctx})
        self._window = n_ctx
        return n_ctx

    def _post(self, messages: list[Message], stream: bool) -> tuple[str, urllib.request.Request]:
        url = self.settings.url.rstrip("/") + "/chat/completions"
        body: dict[str, object] = {
            "model": self.settings.model,
            "messages": messages,
            "max_tokens": REPLY_TOKENS,
            "temperature": TEMPERATURE,
        }
        if stream:
            body["stream"] = True
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return url, request

    def _open(self, url: str, request: urllib.request.Request) -> Any:
        try:
            return urllib.request.urlopen(request, timeout=self.settings.timeout_s)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise LlmError(f"The LLM at {url} refused the prompt ({e.code}): {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise LlmError(
                f"Could not reach the LLM at {url} ({reason}). Is llama-server running?"
            ) from e

    def ask(self, messages: list[Message]) -> str:
        url, request = self._post(messages, stream=False)
        try:
            with self._open(url, request) as response:
                data = json.loads(response.read())
        except (TimeoutError, OSError) as e:
            raise LlmError(
                f"Could not reach the LLM at {url} ({e}). Is llama-server running?"
            ) from e
        except ValueError as e:
            raise LlmError(f"The LLM at {url} sent an answer that is not JSON.") from e
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LlmError(f"The LLM at {url} sent an answer without a reply.") from e
        if not isinstance(content, str) or not content.strip():
            raise LlmError("The LLM sent an empty reply. Try asking again.")
        return content.strip()

    def stream(self, messages: list[Message]) -> Iterator[str]:
        """The reply in pieces as the LLM writes it, read from the API's server-sent events."""
        url, request = self._post(messages, stream=True)
        finished = False  # a server or proxy may close the stream cleanly partway through
        with self._open(url, request) as response:
            try:
                for raw in response:
                    line = raw.decode(errors="replace").strip()
                    # Only "data:" lines carry the reply; others are comments (": ping") or
                    # event names, and blank lines separate events.
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        return
                    choice = json.loads(data)["choices"][0]
                    finished = finished or choice.get("finish_reason") is not None
                    piece = choice.get("delta", {}).get("content")
                    if isinstance(piece, str) and piece:
                        yield piece
            except (TimeoutError, OSError) as e:
                raise LlmError(f"The LLM at {url} stopped answering ({e}). Try again.") from e
            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
                raise LlmError(f"The LLM at {url} sent a reply that could not be read.") from e
        if not finished:
            raise LlmError(f"The LLM at {url} stopped before finishing its reply. Try again.")


class Conversation:
    """The one conversation with the LLM, kept in memory until the server stops."""

    def __init__(
        self,
        ask: AskLlm,
        context_tokens: Callable[[], int],
        count: Count = estimate,
        stream: StreamLlm | None = None,  # replies are streamed and split into sentences
    ) -> None:
        self._ask = ask
        self._stream = stream
        self._context_tokens = context_tokens
        self._count = count
        self._transcript: list[Turn] = []  # everything said, as shown in the chat
        self._summary: str | None = None  # of the turns no longer sent word for word
        self._turns: list[Turn] = []  # sent word for word after the summary
        # Guards the turns. Held only briefly, so the chat can be read while a reply is made.
        self._lock = threading.Lock()
        # One prompt at a time, so replies stay in order.
        self._busy = threading.Lock()
        self._summarizer: threading.Thread | None = None

    def turns(self) -> list[Turn]:
        with self._lock:
            return list(self._transcript)

    def send(self, prompt: str, on_sentence: OnSentence | None = None) -> tuple[Turn, int]:
        """Send the prompt with the conversation so far; the reply is kept with it. Returns the
        reply and its place in the conversation (from 0), which other requests can't change.
        When the reply is streamed, `on_sentence` is told when the LLM starts writing (None)
        and is then given each sentence as soon as it is complete (roadmap R21)."""
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Type something to send.")
        with self._busy:
            self.wait()  # for a summary still being made after the last reply
            return self._send(prompt, on_sentence or (lambda sentence: None))

    def _send(self, prompt: str, on_sentence: OnSentence) -> tuple[Turn, int]:
        # Only this send (holding _busy, with no summary running) changes the turns or summary,
        # so reading them here is safe; changes are made under _lock for turns().
        window = self._context_tokens()
        budget = int(window * HISTORY_SHARE)
        count = self._count
        room = window - budget - REPLY_TOKENS - tokens(system_message(None), count)
        if tokens({"role": "user", "content": prompt}, count) > room:
            logger.warning("Chat prompt too long", extra={"prompt_chars": len(prompt)})
            raise ValueError("That message is too long for the LLM. Shorten it or split it in two.")
        # Normally the summary made after the last reply keeps this within budget; if it
        # couldn't be made, the oldest turns are left out.
        turns = latest(self._turns, budget - history_tokens(self._summary, [], count), count)
        messages = [
            system_message(self._summary),
            *map(as_message, turns),
            {"role": "user", "content": prompt},
        ]
        logger.info(
            "Chat prompt sent",
            extra={
                "prompt_chars": len(prompt),
                "turns_sent": len(turns),
                "turns_dropped": len(self._turns) - len(turns),
                "summary": self._summary is not None,
                "history_tokens": history_tokens(self._summary, turns, count),
                "context_tokens": window,
            },
        )
        start = time.perf_counter()
        try:
            content = (
                self._ask(messages)
                if self._stream is None
                else self._stream_reply(messages, on_sentence)
            )
            reply = Turn("assistant", content)
        except LlmError as e:
            logger.error(
                "Chat reply failed",
                extra={"error": str(e), "duration_ms": round((time.perf_counter() - start) * 1000)},
            )
            raise
        said = [Turn("user", prompt), reply]
        with self._lock:
            self._turns = [*turns, *said]
            self._transcript += said
            place = len(self._transcript) - 1
        logger.info(
            "Chat reply received",
            extra={
                "reply_chars": len(reply.content),
                "duration_ms": round((time.perf_counter() - start) * 1000),
            },
        )
        if history_tokens(self._summary, self._turns, count) > budget:
            # After the reply rather than before the next prompt, so the reply doesn't wait for
            # it; the next prompt waits for it instead (see send).
            self._summarizer = threading.Thread(
                target=self._summarize, args=(budget,), name="chat-summary", daemon=True
            )
            self._summarizer.start()
        return reply, place

    def _stream_reply(self, messages: list[Message], on_sentence: OnSentence) -> str:
        """Stream the reply, logging each sentence as soon as it is complete (roadmap R20)."""
        assert self._stream is not None
        start = time.perf_counter()
        splitter = SentenceSplitter()
        pieces: list[str] = []
        count = 0  # sentences so far

        def ready(sentences: list[str]) -> None:
            nonlocal count
            for sentence in sentences:
                count += 1
                logger.info(
                    "Reply sentence ready",
                    extra={
                        "sentence": count,
                        "chars": len(sentence),
                        "since_prompt_ms": ms_since(start),
                    },
                )
                on_sentence(sentence)

        for piece in self._stream(messages):
            if not pieces:
                logger.info("Reply started", extra={"since_prompt_ms": ms_since(start)})
                on_sentence(None)
            pieces.append(piece)
            ready(splitter.feed(piece))
        ready(splitter.flush())
        content = "".join(pieces).strip()
        if not content:
            raise LlmError("The LLM sent an empty reply. Try asking again.")
        return content

    def wait(self) -> None:
        """Wait for a summary being made, if any."""
        if self._summarizer is not None:
            self._summarizer.join()

    def _summarize(self, budget: int) -> None:
        """Fold the older turns into the summary, keeping the latest ones word for word.

        Runs after a reply, while send() holds off the next prompt. If the LLM can't summarize,
        the older turns are dropped instead (send() keeps only the latest turns that fit).
        """
        older, recent = self._turns[:-KEEP_RECENT], self._turns[-KEEP_RECENT:]
        if not older:
            return
        lines = [f"{'User' if t.role == 'user' else 'Assistant'}: {t.content}" for t in older]
        if self._summary:
            lines.insert(0, f"Summary of what came before: {self._summary}")
        messages = [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": "\n".join(lines)},
        ]
        start = time.perf_counter()
        try:
            summary = self._ask(messages)
        except LlmError as e:
            logger.warning(
                "Could not summarize the conversation; dropping the oldest turns instead",
                extra={"error": str(e)},
            )
            return
        with self._lock:
            self._summary, self._turns = summary, recent
        logger.info(
            "Conversation summarized",
            extra={
                "turns_summarized": len(older),
                "summary_chars": len(summary),
                "history_tokens": history_tokens(summary, recent, self._count),
                "budget_tokens": budget,
                "duration_ms": round((time.perf_counter() - start) * 1000),
            },
        )
