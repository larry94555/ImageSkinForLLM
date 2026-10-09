"""Text chat with the LLM (feature items 10, 15 and 16, roadmap R15).

The LLM is reached through the OpenAI-compatible chat API that llama.cpp's llama-server offers,
so OpenAI is later a change of settings. The conversation is kept on the server, in memory, and
sent with each prompt so the LLM keeps context; when it would overflow the model's context
window, the oldest turns are left out.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are talking with someone face to face, and your replies are spoken aloud. Keep each"
    " reply short and conversational: one to three sentences in plain words, without lists,"
    " headings or code unless you are asked for them."
)
# The longest reply asked for. A short reply needs far less; this is room in the context window.
REPLY_TOKENS = 300
# A rough count: English runs about 4 characters to a token, and each message adds a few for
# its framing. Erring high (3 characters) keeps the conversation inside the window.
CHARS_PER_TOKEN = 3
TOKENS_PER_MESSAGE = 4


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


class LlmError(Exception):
    """The LLM could not be reached or gave no reply; the message says so in plain words."""


def tokens(message: Message) -> int:
    return len(message["content"]) // CHARS_PER_TOKEN + TOKENS_PER_MESSAGE


def fit(turns: list[Turn], context_tokens: int) -> list[Message]:
    """The system prompt and as many of the latest turns as fit, leaving room for the reply.

    Turns are dropped from the oldest, a prompt and its reply together, and the newest prompt
    is always sent, even when it alone is too long (the LLM then says so).
    """
    system = {"role": "system", "content": SYSTEM_PROMPT}
    room = context_tokens - REPLY_TOKENS - tokens(system)
    kept: list[Message] = []
    for turn in reversed(turns):
        message = {"role": turn.role, "content": turn.content}
        if kept and tokens(message) > room:
            break
        room -= tokens(message)
        kept.append(message)
    # Never start on a reply whose prompt was dropped.
    if kept and kept[-1]["role"] == "assistant":
        kept.pop()
    return [system, *reversed(kept)]


class LlmClient:
    """Asks an OpenAI-compatible chat API, such as llama-server's, for a reply."""

    def __init__(self, settings: LlmSettings) -> None:
        self.settings = settings

    def ask(self, messages: list[Message]) -> str:
        url = self.settings.url.rstrip("/") + "/chat/completions"
        body = {"model": self.settings.model, "messages": messages, "max_tokens": REPLY_TOKENS}
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_s) as response:
                data = json.loads(response.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise LlmError(f"The LLM at {url} refused the prompt ({e.code}): {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise LlmError(
                f"Could not reach the LLM at {url} ({reason}). Is llama-server running?"
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


class Conversation:
    """The one conversation with the LLM, kept in memory until the server stops."""

    def __init__(self, ask: AskLlm, context_tokens: int) -> None:
        self._ask = ask
        self._context_tokens = context_tokens
        self._turns: list[Turn] = []
        # One prompt at a time, so replies stay in order.
        self._lock = threading.Lock()

    def turns(self) -> list[Turn]:
        with self._lock:
            return list(self._turns)

    def send(self, prompt: str) -> Turn:
        """Send the prompt with the conversation so far; the reply is kept with it."""
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Type something to send.")
        with self._lock:
            turns = [*self._turns, Turn("user", prompt)]
            messages = fit(turns, self._context_tokens)
            sent = len(messages) - 1
            logger.info(
                "Chat prompt sent",
                extra={
                    "prompt_chars": len(prompt),
                    "turns_sent": sent,
                    "turns_dropped": len(turns) - sent,
                },
            )
            start = time.perf_counter()
            try:
                reply = Turn("assistant", self._ask(messages))
            except LlmError as e:
                logger.error(
                    "Chat reply failed",
                    extra={
                        "error": str(e),
                        "duration_ms": round((time.perf_counter() - start) * 1000),
                    },
                )
                raise
            self._turns = [*turns, reply]
        logger.info(
            "Chat reply received",
            extra={
                "reply_chars": len(reply.content),
                "duration_ms": round((time.perf_counter() - start) * 1000),
            },
        )
        return reply
