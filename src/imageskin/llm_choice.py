"""Which LLM answers, picked on the Settings page (roadmap R42, feature item 29).

Local llama.cpp (llama-server) is the default. Claude, OpenAI, Grok and OpenRouter answer with
the user's own API key, entered on the Settings page; the ChatGPT plan answers through the
ChatGPT account signed in there (R43a), with no key. The choice and the keys are saved as
llm.json in the app's home folder, on the server only: a key is never logged or sent back to the
browser. Each provider keeps its own key and model, so switching back needs no key again.

`SwitchableLlm` is the one client the chat, the wiki and its outline are given; a change on the
Settings page swaps the client inside it, so the change holds from the next request. A prompt
or a wiki build in progress is pinned to the client it began with, so it finishes there.
"""

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import anthropic

from imageskin.chat import REPLY_TOKENS, ChatLlm, LlmClient, LlmError, LlmSettings, Message
from imageskin.chatgpt_plan import RESOURCE, ChatGptPlanClient, Session, plan_models
from imageskin.claude import DEFAULT_MODEL as CLAUDE_MODEL
from imageskin.claude import ClaudeClient

logger = logging.getLogger(__name__)

FILENAME = "llm.json"
# Longer than any provider's key or model name; a paste of something else is refused.
MAX_KEY_CHARS = 500
MAX_MODEL_CHARS = 200


@dataclass(frozen=True)
class Provider:
    label: str
    # The OpenAI-compatible API it is asked through; Claude's own SDK and llama-server's address
    # (llm_url in the config file) need none here.
    url: str = ""
    # The model asked for unless another is entered on the Settings page.
    model: str = ""
    # Where the user gets a key, shown beside the key's box.
    keys_at: str = ""
    # Where the models the key can use are listed, under `url`: Grok's language-models leaves
    # out its image and video models.
    models_at: str = "/models"
    # Where a key is checked when listing the models doesn't need one (OpenRouter's lists them
    # for anyone).
    key_at: str = ""
    # Answers through the ChatGPT account signed in on the Settings page (R43), with no key.
    signs_in: bool = False

    @property
    def lists_freely(self) -> bool:
        """Whether its models can be listed before a key is entered (OpenRouter's can)."""
        return bool(self.key_at)


PROVIDERS: dict[str, Provider] = {
    "local": Provider("Local (llama.cpp)"),
    "claude": Provider("Claude", model=CLAUDE_MODEL, keys_at="console.anthropic.com"),
    "openai": Provider(
        "OpenAI", "https://api.openai.com/v1", "gpt-4.1-mini", "platform.openai.com"
    ),
    "grok": Provider("Grok", "https://api.x.ai/v1", "grok-4", "console.x.ai", "/language-models"),
    # openrouter/auto picks a model for each prompt from those OpenRouter offers.
    "openrouter": Provider(
        "OpenRouter",
        "https://openrouter.ai/api/v1",
        "openrouter/auto",
        "openrouter.ai",
        key_at="/key",
    ),
    # No model of its own: the first in the plan's list is saved when none is entered.
    "chatgpt": Provider("ChatGPT plan", RESOURCE, signs_in=True),
}

_saving = threading.Lock()  # one change at a time, so two made together both stay


@dataclass(frozen=True)
class LlmChoice:
    provider: str = "local"
    keys: dict[str, str] = field(default_factory=dict, repr=False)  # never in a log line
    models: dict[str, str] = field(default_factory=dict)  # only those entered

    def model(self, provider: str) -> str:
        return self.models.get(provider) or PROVIDERS[provider].model


def load_choice(home: Path) -> LlmChoice:
    """The saved choice, or local llama.cpp when nothing is saved or the file can't be used."""
    path = home / FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        choice = LlmChoice(data["provider"], dict(data["keys"]), dict(data["models"]))
        if choice.provider not in PROVIDERS:
            raise ValueError(f"no provider called {choice.provider!r}")
        if needs_key(choice.provider) and not choice.keys.get(choice.provider):
            raise ValueError(f"no key for {choice.provider}")
    except FileNotFoundError:
        return LlmChoice()
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.error("Could not read the LLM choice", extra={"path": str(path), "error": str(e)})
        return LlmChoice()
    return choice


def needs_key(provider: str) -> bool:
    return provider != "local" and not PROVIDERS[provider].signs_in


def save_choice(
    home: Path, provider: str, api_key: str | None = None, model: str | None = None
) -> LlmChoice:
    """Make `provider` the LLM, with its key and model when given (a blank model means its
    default); ValueError, in plain words, when that can't be done."""
    if provider not in PROVIDERS:
        raise ValueError(f"There is no LLM called {provider}.")
    label = PROVIDERS[provider].label
    key = (api_key or "").strip()
    if len(key) > MAX_KEY_CHARS or any(c.isspace() for c in key):
        raise ValueError(f"That doesn't look like a {label} API key.")
    name = None if model is None else model.strip()
    if name is not None and len(name) > MAX_MODEL_CHARS:
        raise ValueError("The model's name is too long.")
    with _saving:
        saved = load_choice(home)
        keys, models = dict(saved.keys), dict(saved.models)
        if key and needs_key(provider):
            keys[provider] = key
        if needs_key(provider) and not keys.get(provider):
            raise ValueError(f"Enter your {label} API key.")
        if name is not None and provider != "local":
            if name:
                models[provider] = name
            else:
                models.pop(provider, None)
        choice = LlmChoice(provider, keys, models)
        write_owner_only(home / FILENAME, {"provider": provider, "keys": keys, "models": models})
    logger.info(
        "LLM chosen",
        extra={"provider": provider, "model": choice.model(provider), "key_changed": bool(key)},
    )
    return choice


def write_owner_only(path: Path, data: dict[str, Any]) -> None:
    """Written beside it, readable by the owner only where the system allows, then put in its
    place, so a read never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part")
    fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(part, path)


def described(choice: LlmChoice, signed_in: bool = False) -> dict[str, Any]:
    """The choice for the Settings page: which providers have a key, but never the keys. The
    ChatGPT plan "has a key" while a ChatGPT account that allowed plan use is `signed_in`."""
    return {
        "provider": choice.provider,
        "providers": [
            {
                "id": pid,
                "label": p.label,
                "keys_at": p.keys_at,
                "model": choice.models.get(pid, ""),
                "default_model": p.model,
                "has_key": signed_in if p.signs_in else bool(choice.keys.get(pid)),
                "lists_freely": p.lists_freely,
                "signs_in": p.signs_in,
            }
            for pid, p in PROVIDERS.items()
        ],
    }


def settings_for(base: LlmSettings, choice: LlmChoice) -> LlmSettings:
    """The settings to ask the chosen LLM with. `base` is llama-server's, from the config file;
    the context window is the config's for every provider."""
    if choice.provider == "local":
        return replace(base, provider="local", api_key="")
    p = PROVIDERS[choice.provider]
    return replace(
        base,
        url=p.url or base.url,
        model=choice.model(choice.provider),
        provider=choice.provider,
        api_key=choice.keys.get(choice.provider, ""),
    )


@contextmanager
def _no_sign_in(renew: bool) -> Iterator[str]:
    raise LlmError("Sign in with ChatGPT on the Settings page first.")
    yield ""  # pragma: no cover


def llm_client(llm: LlmSettings) -> ChatLlm:
    """The client for the LLM: Claude's own, or the OpenAI-compatible one for llama-server,
    OpenAI, Grok and OpenRouter (R33, R42). The ChatGPT plan's needs the sign-in's token, which
    `SwitchableLlm` gives it."""
    return ClaudeClient(llm) if llm.provider == "claude" else LlmClient(llm)


# The models each provider can use, looked up when a provider is picked (Larry, 2026-10-19: a
# fixed list goes out of date). Kept a while, so picking the same provider again is quick.
MODELS_KEPT_S = 600
# OpenAI lists every model the key can use, embeddings and speech among them: these can't chat.
NOT_CHAT = (
    "embedding",
    "tts",
    "whisper",
    "dall-e",
    "moderation",
    "transcribe",
    "image",
    "audio",
    "realtime",
    "search",
    "babbage",
    "davinci",
    "sora",
)


class ModelListError(Exception):
    """The provider's models couldn't be listed; the message says why in plain words.
    `refused` when it was the key the provider refused."""

    def __init__(self, message: str, refused: bool = False) -> None:
        super().__init__(message)
        self.refused = refused


Fetch = Callable[[str, dict[str, str]], Any]  # URL, headers: the decoded JSON


def _get_json(url: str, headers: dict[str, str]) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json", **headers})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def _ids(data: Any, provider: str) -> list[str]:
    """The chat models in a provider's answer: OpenAI's and OpenRouter's `data`, or Grok's
    `models`, each an object with an `id`, and for Grok its `aliases`, which it accepts too
    (grok-4, the default, can be one: a review on PR #115)."""
    items = data.get("data", data.get("models")) if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("no list of models")
    ids = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        if provider == "openai" and any(word in item["id"] for word in NOT_CHAT):
            continue
        outputs = (item.get("architecture") or {}).get("output_modalities")
        if provider == "openrouter" and isinstance(outputs, list) and "text" not in outputs:
            continue
        ids.append(item["id"])
        aliases = item.get("aliases")
        if isinstance(aliases, list):
            ids += [a for a in aliases if isinstance(a, str)]
    return sorted(set(ids))


class ModelLists:
    """Looks up the models a provider offers to a key, and keeps each list a while."""

    def __init__(
        self,
        fetch: Fetch = _get_json,
        claude: Callable[[str], list[str]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._claude = claude or _claude_models
        self._clock = clock
        # Each list with the names it shows for its models, where they differ from the IDs
        # (the ChatGPT plan's `display_name`s, R43a): kept per key, since each account's plan
        # has its own (a review on PR #118).
        self._kept: dict[tuple[str, str], tuple[float, list[str], dict[str, str]]] = {}
        self._lock = threading.Lock()

    def models(self, provider: str, key: str) -> list[str]:
        return self.named_models(provider, key)[0]

    def named_models(self, provider: str, key: str) -> tuple[list[str], dict[str, str]]:
        """The models a provider offers to this key, and the names shown for those whose name
        isn't their ID."""
        if provider not in PROVIDERS or provider == "local":
            raise ModelListError("Only a provider's models can be listed.")
        if not key and PROVIDERS[provider].signs_in:
            raise ModelListError("Sign in with ChatGPT on the Settings page first.")
        if not key and not PROVIDERS[provider].lists_freely:
            raise ModelListError(f"Enter your {PROVIDERS[provider].label} API key first.")
        # The key is kept only as a hash, so the cache holds no key.
        kept_as = (provider, hashlib.sha256(key.encode()).hexdigest())
        now = self._clock()
        with self._lock:
            kept = self._kept.get(kept_as)
        if kept is not None and now - kept[0] < MODELS_KEPT_S:
            return kept[1], kept[2]
        start = time.perf_counter()
        found, names = self._look_up(provider, key)
        with self._lock:
            self._kept[kept_as] = (now, found, names)
        logger.info(
            "Listed the provider's models",
            extra={
                "provider": provider,
                "models": len(found),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return found, names

    def _look_up(self, provider: str, key: str) -> tuple[list[str], dict[str, str]]:
        p = PROVIDERS[provider]
        names: dict[str, str] = {}
        try:
            if provider == "claude":
                found = self._claude(key)
            else:
                # Without a key, only a list anyone may read is asked for (Larry, 2026-10-19).
                auth = {"Authorization": f"Bearer {key}"} if key else {}
                if p.key_at and key:
                    self._fetch(p.url + p.key_at, auth)  # refused if the key isn't valid
                listed = self._fetch(p.url + p.models_at, auth)
                # The plan's list keeps its own order (R43a); the others are sorted.
                if p.signs_in:
                    pairs = plan_models(listed)
                    names = {slug: name for slug, name in pairs if name != slug}
                    found = [slug for slug, _ in pairs]
                else:
                    found = _ids(listed, provider)
        except (urllib.error.HTTPError, anthropic.APIStatusError) as e:
            code = getattr(e, "code", None) or getattr(e, "status_code", None)
            logger.error(
                "Could not list the provider's models", extra={"provider": provider, "status": code}
            )
            if code in (401, 403) and p.signs_in:
                raise ModelListError(
                    "ChatGPT refused the sign-in. Sign in with ChatGPT again.", refused=True
                ) from e
            if code in (401, 403):
                raise ModelListError(f"{p.label} refused the API key.", refused=True) from e
            raise ModelListError(f"{p.label} couldn't list its models ({code}).") from e
        except (OSError, ValueError, TypeError, AttributeError, anthropic.AnthropicError) as e:
            logger.error(
                "Could not list the provider's models",
                extra={"provider": provider, "error": type(e).__name__},
            )
            raise ModelListError(f"{p.label}'s models couldn't be listed. Try again.") from e
        if not found:
            raise ModelListError(f"{p.label} listed no models{' for this key' if key else ''}.")
        return found, names


def _claude_models(key: str) -> list[str]:
    """Claude's models, through Anthropic's SDK, which reads every page of the list."""
    client = anthropic.Anthropic(api_key=key, timeout=10)
    return sorted({m.id for m in client.models.list(limit=1000)})


class SwitchableLlm:
    """The chosen LLM, which a change on the Settings page swaps (R42): the same calls as
    `chat.LlmClient`, each asking the client chosen when it is made."""

    def __init__(
        self, base: LlmSettings, choice: LlmChoice, plan_session: Session = _no_sign_in
    ) -> None:
        self._base = base
        self._plan_session = plan_session
        self._lock = threading.Lock()
        self.settings = settings_for(base, choice)
        self._client = self._client_for(self.settings)
        # The settings and client a thread is pinned to (see pinned), if it is.
        self._held = threading.local()

    def _client_for(self, settings: LlmSettings) -> ChatLlm:
        if settings.provider == "chatgpt":  # with the signed-in account's token (R43a)
            return ChatGptPlanClient(settings, self._plan_session)
        return llm_client(settings)

    @contextmanager
    def pinned(self) -> Iterator[None]:
        """Every call this thread makes inside goes to the client chosen when it began, so one
        prompt, or one wiki build, is answered by one LLM whole even if the LLM is changed
        meanwhile (a review on PR #115). Inside another, the outer one's client holds."""
        if getattr(self._held, "pin", None) is not None:
            yield
            return
        with self._lock:
            self._held.pin = (self.settings, self._client)
        try:
            yield
        finally:
            self._held.pin = None

    def use(self, choice: LlmChoice) -> None:
        settings = settings_for(self._base, choice)
        client = self._client_for(settings)
        with self._lock:
            self.settings, self._client = settings, client
        logger.info(
            "Chat LLM changed",
            extra={"provider": settings.provider, "url": settings.url, "model": settings.model},
        )

    def _pin(self) -> tuple[LlmSettings, ChatLlm]:
        held: tuple[LlmSettings, ChatLlm] | None = getattr(self._held, "pin", None)
        if held is not None:
            return held
        with self._lock:
            return self.settings, self._client

    @property
    def local(self) -> bool:
        return self._pin()[0].local

    def _current(self) -> ChatLlm:
        return self._pin()[1]

    def count(self, text: str) -> int:
        return self._current().count(text)

    def context_tokens(self) -> int:
        return self._current().context_tokens()

    def warm_up(self) -> None:
        self._current().warm_up()

    def ask(
        self,
        messages: list[Message],
        max_tokens: int = REPLY_TOKENS,
        schema: dict[str, Any] | None = None,
    ) -> str:
        return self._current().ask(messages, max_tokens, schema)

    def stream(self, messages: list[Message]) -> Iterator[str]:
        return self._current().stream(messages)


def pinned(client: ChatLlm | None) -> AbstractContextManager[None]:
    """`SwitchableLlm.pinned` for the LLM picked on the Settings page; nothing for another."""
    return client.pinned() if isinstance(client, SwitchableLlm) else nullcontext()
