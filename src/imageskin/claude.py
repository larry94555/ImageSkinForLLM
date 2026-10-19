"""Claude as the LLM, with the user's API key (feature item 16, roadmap R33).

A small adapter with the same calls as `chat.LlmClient`, so the chat, the wiki and its outline
use Claude in place of llama-server without knowing which one answers. Claude's Messages API
takes the system prompt apart from the conversation, so the system messages are lifted out.
"""

import logging
import time
from collections.abc import Iterator
from typing import Any

import anthropic

from imageskin.chat import REPLY_TOKENS, EmptyReply, LlmError, LlmSettings, Message, estimate

logger = logging.getLogger(__name__)

# Used when the config names no model ("local", the llama-server default).
DEFAULT_MODEL = "claude-opus-5-5"
# Replies must start within 1 to 2 seconds (R22), and these are short spoken replies, so the
# model thinks as little as it can.
EFFORT = "low"
# Claude always thinks a little first, and its thinking counts against max_tokens: this much more
# is asked for, so a short reply is never cut off by its own thinking.
THINKING_ROOM = 4000
# A model that declines a request is asked again by Anthropic with another model in the same
# call. Only these models take the server-side fallback.
FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
DECLINED = "Claude declined to answer that. Try asking another way."


def strict(schema: Any) -> Any:
    """The schema with every object closed to other properties, as Claude's structured
    outputs require; llama-server and OpenAI take it either way."""
    if isinstance(schema, dict):
        closed = {k: strict(v) for k, v in schema.items()}
        if closed.get("type") == "object":
            closed.setdefault("additionalProperties", False)
        return closed
    if isinstance(schema, list):
        return [strict(v) for v in schema]
    return schema


def split_system(messages: list[Message]) -> tuple[str, list[Message]]:
    """The system messages joined, and the rest of the conversation."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    rest = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    return system, rest


def reply_text(message: Any) -> str:
    """The words of Claude's reply; LlmError when it declined, EmptyReply when there are none."""
    if message.stop_reason == "refusal":
        raise LlmError(DECLINED)
    text = "".join(b.text for b in message.content if b.type == "text").strip()
    if not text:
        raise EmptyReply("The LLM sent an empty reply. Try asking again.")
    return text


def plain_error(e: anthropic.AnthropicError) -> LlmError:
    """The SDK's error said in plain words, for the chat and the logs."""
    if isinstance(e, anthropic.AuthenticationError):
        return LlmError("Claude refused the API key. Check llm_api_key in the config file.")
    if isinstance(e, anthropic.PermissionDeniedError):
        return LlmError("Claude's API key isn't allowed to use this model.")
    if isinstance(e, anthropic.NotFoundError):
        return LlmError("Claude doesn't know the model in llm_model. Check the config file.")
    if isinstance(e, anthropic.RateLimitError):
        return LlmError("Claude is getting too many requests right now. Try again shortly.")
    if isinstance(e, anthropic.APIStatusError):
        return LlmError(f"Claude refused the prompt ({e.status_code}): {e.message}")
    if isinstance(e, anthropic.APIConnectionError):
        return LlmError("Could not reach Claude. Is the internet connection working?")
    return LlmError(f"Claude sent a reply that could not be read ({e}).")


class ClaudeClient:
    """Asks Claude for a reply; the same calls as `chat.LlmClient`."""

    def __init__(self, settings: LlmSettings, client: anthropic.Anthropic | None = None) -> None:
        self.settings = settings
        self.model = DEFAULT_MODEL if settings.model == "local" else settings.model
        self._client = client or anthropic.Anthropic(
            api_key=settings.api_key, timeout=settings.timeout_s
        )

    def count(self, text: str) -> int:
        # Asking Claude to count would add a request to every prompt, so the safe estimate is
        # used: it never falls short, it only leaves the history less room.
        return estimate(text)

    def context_tokens(self) -> int:
        return self.settings.context_tokens

    def warm_up(self) -> None:
        logger.info("Claude needs no warm-up", extra={"model": self.model})

    def _params(
        self, messages: list[Message], max_tokens: int, schema: dict[str, Any] | None
    ) -> dict[str, Any]:
        system, rest = split_system(messages)
        output: dict[str, Any] = {"effort": EFFORT}
        if schema is not None:
            output["format"] = {"type": "json_schema", "schema": strict(schema)}
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens + THINKING_ROOM,
            "messages": rest,
            "output_config": output,
        }
        if system:
            params["system"] = system
        if self.model in FALLBACK_MODELS:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def ask(
        self,
        messages: list[Message],
        max_tokens: int = REPLY_TOKENS,
        schema: dict[str, Any] | None = None,
    ) -> str:
        start = time.perf_counter()
        try:
            message = self._client.beta.messages.create(
                **self._params(messages, max_tokens, schema)
            )
        except anthropic.AnthropicError as e:
            error = plain_error(e)
            logger.error("Claude failed", extra={"model": self.model, "error": str(e)})
            raise error from e
        logger.info(
            "Claude answered",
            extra={
                "model": message.model,
                "stop_reason": message.stop_reason,
                "output_tokens": message.usage.output_tokens,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return reply_text(message)

    def stream(self, messages: list[Message]) -> Iterator[str]:
        """The reply, handed over only once Claude has finished it. Claude can decline partway
        through a reply, and the part already written must then be dropped (review on PR #111),
        so nothing is spoken or kept until the stop reason is known: a spoken sentence can't be
        taken back. The cost is that the video starts after the whole reply, not the first
        sentence."""
        start = time.perf_counter()
        first: float | None = None
        try:
            with self._client.beta.messages.stream(
                **self._params(messages, REPLY_TOKENS, None)
            ) as stream:
                for piece in stream.text_stream:
                    if piece and first is None:
                        first = time.perf_counter()
                message = stream.get_final_message()
        except anthropic.AnthropicError as e:
            error = plain_error(e)
            logger.error("Claude failed", extra={"model": self.model, "error": str(e)})
            raise error from e
        logger.info(
            "Claude streamed a reply",
            extra={
                "model": message.model,
                "stop_reason": message.stop_reason,
                "output_tokens": message.usage.output_tokens,
                "first_words_ms": None if first is None else round((first - start) * 1000, 1),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        yield reply_text(message)
