"""Settings loaded from an optional TOML file."""

import logging
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
# Moved to the Settings page in roadmap R42 (Larry, 2026-10-19).
MOVED_TO_SETTINGS = ("llm_provider", "llm_api_key")


def default_home() -> Path:
    """Where models, libraries and app data are kept: IMAGESKIN_HOME, or ~/.imageskin."""
    return Path(os.environ.get("IMAGESKIN_HOME") or Path.home() / ".imageskin")


class ConfigError(Exception):
    """The config file is missing, unreadable or has invalid values."""


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    # The local LLM: llama-server's OpenAI-compatible API (roadmap R15). Claude, OpenAI, Grok or
    # OpenRouter is picked instead on the Settings page (R42); the context window is for all.
    llm_url: str = "http://127.0.0.1:8080/v1"
    llm_model: str = "local"
    llm_context_tokens: int = 4096
    # Whether the chat answers prompts the PDFs have nothing on, or politely declines them
    # (roadmap R41, item 28). Declining is the default.
    general_prompts: bool = False


def load_settings(path: Path | None) -> Settings:
    """Return defaults when path is None, otherwise the values in the TOML file."""
    if path is None:
        return Settings()
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"Config file not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Config file {path} is not valid TOML: {e}") from e

    moved = [k for k in MOVED_TO_SETTINGS if k in data]
    if moved:
        raise ConfigError(
            f"{' and '.join(moved)} in {path} {'are' if len(moved) > 1 else 'is'} no longer"
            " used: remove it and pick the LLM, with its API key, on the Settings page"
        )
    known = {f.name for f in fields(Settings)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(f"Unknown keys in {path}: {', '.join(unknown)}")

    settings = Settings(**data)
    if not isinstance(settings.host, str):
        raise ConfigError(f"host in {path} must be a string")
    # type() rather than isinstance(): bool is a subclass of int, so `port = true` must fail here.
    if type(settings.port) is not int or not 1 <= settings.port <= 65535:
        raise ConfigError(f"port in {path} must be a number from 1 to 65535")
    if not isinstance(settings.llm_url, str) or not settings.llm_url.startswith(
        ("http://", "https://")
    ):
        raise ConfigError(f"llm_url in {path} must start with http:// or https://")
    if not isinstance(settings.llm_model, str):
        raise ConfigError(f"llm_model in {path} must be a string")
    if type(settings.llm_context_tokens) is not int or settings.llm_context_tokens < 1024:
        raise ConfigError(f"llm_context_tokens in {path} must be a number of at least 1024")
    if not isinstance(settings.general_prompts, bool):
        raise ConfigError(f"general_prompts in {path} must be true or false")
    if settings.log_level not in LOG_LEVELS:
        raise ConfigError(f"log_level in {path} must be one of {', '.join(LOG_LEVELS)}")
    logger.info("Loaded config", extra={"path": str(path)})
    return settings
