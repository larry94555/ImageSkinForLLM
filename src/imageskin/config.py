"""Settings loaded from an optional TOML file."""

import logging
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
LLM_PROVIDERS = ("local", "openai", "claude")


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
    # The LLM the chat talks to: llama-server's OpenAI-compatible API (roadmap R15).
    llm_url: str = "http://127.0.0.1:8080/v1"
    llm_model: str = "local"
    llm_context_tokens: int = 4096
    # Who answers (roadmap R33): llama-server ("local"), OpenAI or Claude. OpenAI and Claude need
    # the user's API key, which stays in this file on the server and is never logged.
    llm_provider: str = "local"
    llm_api_key: str = ""
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
    if settings.llm_provider not in LLM_PROVIDERS:
        raise ConfigError(f"llm_provider in {path} must be one of {', '.join(LLM_PROVIDERS)}")
    if not isinstance(settings.llm_api_key, str):
        raise ConfigError(f"llm_api_key in {path} must be a string")
    if settings.llm_provider != "local" and not settings.llm_api_key.strip():
        raise ConfigError(
            f"llm_api_key in {path} is needed for llm_provider {settings.llm_provider}"
        )
    if settings.llm_provider == "openai" and settings.llm_model == "local":
        raise ConfigError(f"llm_model in {path} must name an OpenAI model, such as gpt-4.1-mini")
    if not isinstance(settings.general_prompts, bool):
        raise ConfigError(f"general_prompts in {path} must be true or false")
    if settings.log_level not in LOG_LEVELS:
        raise ConfigError(f"log_level in {path} must be one of {', '.join(LOG_LEVELS)}")
    logger.info("Loaded config", extra={"path": str(path), "llm_provider": settings.llm_provider})
    return settings
