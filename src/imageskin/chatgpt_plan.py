"""Answers through the user's ChatGPT plan (roadmap R43a, feature item 29).

Once signed in with ChatGPT (R43) and allowed to use the plan, the app asks OpenAI's Responses
API with the account's access token in place of an API key. OpenAI takes a plan's requests only
streamed and unstored (`stream` true, `store` false), with the system prompt as `instructions`
rather than a system message, and without a token limit or a temperature. The token is renewed
when it is about to end, and once more when OpenAI refuses it. The models are those the plan's
own list shows (`visibility` "list"), in its order.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

from imageskin.chat import (
    DECLINED,
    REPLY_TOKENS,
    EmptyReply,
    LlmError,
    LlmSettings,
    Message,
    estimate,
    ms_since,
    strict,
)

logger = logging.getLogger(__name__)

# The API a plan's requests go to: the sign-in's `resource` (chatgpt_signin.RESOURCE).
RESOURCE = "https://api.openai.com/v1"
URL = RESOURCE + "/responses"
# Said in the chat when OpenAI refuses a plan's request, by HTTP status.
ERRORS = {
    403: "Your ChatGPT plan isn't allowed to use this model. Pick another on the Settings page.",
    404: "ChatGPT doesn't know the model. Pick another on the Settings page.",
    429: "Your ChatGPT plan has reached its limit for now, or ChatGPT is busy. Try again later.",
}
UNREACHABLE = "Could not reach ChatGPT. Is the internet connection working?"
SIGN_IN_AGAIN = "ChatGPT refused the sign-in. Sign in with ChatGPT again on the Settings page."

# Gets the access token: renewed first when True, since OpenAI refused the one sent. LlmError,
# in plain words, when there is no sign-in to use (`ChatGptSignIn.plan_token`).
Token = Callable[[bool], str]
Opener = Callable[..., Any]


def plan_models(data: Any) -> list[str]:
    """The models in the plan's list that are meant to be shown, in the list's order: each an
    object with a `slug` (or an `id`) and, when it says, `visibility` "list"."""
    items = data.get("models", data.get("data")) if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("no list of models")
    found: list[str] = []
    for item in items:
        if not isinstance(item, dict) or item.get("visibility", "list") != "list":
            continue
        slug = item.get("slug") or item.get("id")
        if isinstance(slug, str) and slug and slug not in found:
            found.append(slug)
    return found


def request_body(
    model: str, messages: list[Message], schema: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The Responses API request for a plan: the system messages as `instructions`, the rest of
    the conversation as `input`."""
    instructions = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    body: dict[str, Any] = {
        "model": model,
        "input": [
            {"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"
        ],
        "stream": True,
        "store": False,
    }
    if instructions:
        body["instructions"] = instructions
    if schema is not None:
        body["text"] = {
            "format": {
                "type": "json_schema",
                "name": "answer",
                "strict": True,
                "schema": strict(schema),
            }
        }
    return body


class ChatGptPlanClient:
    """Asks the Responses API through the signed-in ChatGPT plan; the same calls as
    `chat.LlmClient`."""

    def __init__(
        self, settings: LlmSettings, token: Token, opener: Opener = urllib.request.urlopen
    ) -> None:
        self.settings = settings
        self._token = token
        self._open = opener

    def count(self, text: str) -> int:
        return estimate(text)  # OpenAI doesn't count for free; the safe estimate never falls short

    def context_tokens(self) -> int:
        return self.settings.context_tokens

    def warm_up(self) -> None:
        logger.info("The ChatGPT plan needs no warm-up", extra={"model": self.settings.model})

    def _response(self, body: dict[str, Any]) -> Any:
        """The open stream of OpenAI's answer, with the token renewed once if it was refused."""
        for renew in (False, True):
            request = urllib.request.Request(
                URL,
                data=json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                    "Authorization": f"Bearer {self._token(renew)}",
                },
                method="POST",
            )
            try:
                return self._open(request, timeout=self.settings.timeout_s)
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:300]
                logger.error(
                    "ChatGPT refused the request",
                    extra={"status": e.code, "model": body["model"], "detail": detail},
                )
                if e.code == 401 and not renew:
                    continue
                if e.code == 401:
                    raise LlmError(SIGN_IN_AGAIN) from e
                said = ERRORS.get(e.code, f"ChatGPT refused the prompt ({e.code}).")
                raise LlmError(said) from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                logger.error("Could not reach ChatGPT", extra={"error": str(e)})
                raise LlmError(UNREACHABLE) from e
        raise AssertionError("unreachable")  # pragma: no cover

    def _pieces(self, body: dict[str, Any]) -> Iterator[str]:
        """The reply's text as OpenAI streams it, read from the server-sent events."""
        start = time.perf_counter()
        finished = False
        with self._response(body) as response:
            try:
                for raw in response:
                    line = raw.decode(errors="replace").strip()
                    if not line.startswith("data:"):
                        continue  # event names, comments and the blank lines between events
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    kind = event.get("type")
                    if kind == "response.output_text.delta" and isinstance(event.get("delta"), str):
                        yield event["delta"]
                    elif kind == "response.refusal.delta":
                        logger.warning("ChatGPT declined to answer")
                        raise LlmError(DECLINED)
                    elif kind == "response.completed":
                        finished = True
                    elif kind == "response.incomplete":
                        # Only response.completed is a whole answer (OpenAI's plan docs): the
                        # part sent so far is not kept as the reply (a review on PR #118).
                        details = (event.get("response") or {}).get("incomplete_details") or {}
                        reason = details.get("reason") or "unknown"
                        logger.error("ChatGPT left its reply unfinished", extra={"reason": reason})
                        raise LlmError(f"ChatGPT didn't finish its reply ({reason}). Try again.")
                    elif kind in ("response.failed", "error"):
                        error = (event.get("response") or {}).get("error") or event
                        logger.error("ChatGPT failed", extra={"error": str(error)[:300]})
                        raise LlmError("ChatGPT couldn't answer that. Try again.")
            except (TimeoutError, OSError) as e:
                raise LlmError(f"ChatGPT stopped answering ({e}). Try again.") from e
            except (ValueError, AttributeError, TypeError) as e:
                raise LlmError("ChatGPT sent a reply that could not be read.") from e
        if not finished:
            raise LlmError("ChatGPT stopped before finishing its reply. Try again.")
        logger.info(
            "ChatGPT answered", extra={"model": body["model"], "duration_ms": ms_since(start)}
        )

    def ask(
        self,
        messages: list[Message],
        max_tokens: int = REPLY_TOKENS,
        schema: dict[str, Any] | None = None,
    ) -> str:
        # A plan's requests are always streamed, and take no token limit: the prompts ask for
        # short replies, which keeps them short.
        text = "".join(self._pieces(request_body(self.settings.model, messages, schema))).strip()
        if not text:
            raise EmptyReply("The LLM sent an empty reply. Try asking again.")
        return text

    def stream(self, messages: list[Message]) -> Iterator[str]:
        return self._pieces(request_body(self.settings.model, messages))
