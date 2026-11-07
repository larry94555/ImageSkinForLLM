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
# The mail service can be set in the environment too, over config.toml, so the hosted site sets
# it in deploy/.env and its config.toml stays as `git pull` leaves it (Larry, on PR 313).
MAIL_VARIABLES = {
    "smtp_host": "IMAGESKIN_SMTP_HOST",
    "smtp_port": "IMAGESKIN_SMTP_PORT",
    "smtp_user": "IMAGESKIN_SMTP_USER",
    "mail_from": "IMAGESKIN_MAIL_FROM",
}


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
    # The administrator's password file (roadmap R149, item 122); empty for admin.toml in the
    # app's home folder.
    admin_file: str = ""
    # The allowed laptops file (roadmap R163, item 133); empty for admin-laptops.toml beside the
    # password file.
    admin_laptops_file: str = ""
    # The proxies whose X-Forwarded-For names the browser (uvicorn's forwarded_allow_ips): a
    # comma-separated list of addresses or networks, or "*" when only a proxy can reach the app,
    # as on the hosted site. Others' requests are taken to come from where they connect from.
    trusted_proxies: str = "127.0.0.1"
    # How many sites keep the voice clone (about 3 GB each) loaded at once (roadmap R61d): the
    # one used least recently is unloaded, and learns its voice again when next needed.
    clones_loaded: int = 2
    # The hosted service's domain (R61): each site is at name.<main_domain>, as name.localhost is
    # locally; the domain itself, www and app are the main address's site.
    main_domain: str = "me0.ai"
    # The mail service email is sent through (roadmap R215), with its password in the
    # IMAGESKIN_SMTP_PASSWORD environment variable. With no smtp_host, each email is written to
    # the outbox folder in the app's home folder instead.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    mail_from: str = ""


def mail_from_environment() -> dict[str, object]:
    """The mail service's settings set in the environment (MAIL_VARIABLES), each over the file's."""
    found: dict[str, object] = {}
    for key, variable in MAIL_VARIABLES.items():
        value = os.environ.get(variable, "").strip()
        if not value:
            continue
        if key == "smtp_port":
            if not value.isdigit():
                raise ConfigError(f"{variable} must be a number from 1 to 65535")
            found[key] = int(value)
        else:
            found[key] = value
    if found:
        logger.info("Mail service set in the environment", extra={"keys": sorted(found)})
    return found


def load_settings(path: Path | None) -> Settings:
    """The defaults when path is None, otherwise the values in the TOML file; either way with
    the mail service's settings from the environment over them."""
    if path is None:
        mail = mail_from_environment()
        if not mail:
            return Settings()
        return checked_settings(Settings(**mail), "the environment")  # type: ignore[arg-type]
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
    if "stripe_price_id" in data:
        # Only in a file that isn't checked in, so the server's config.toml never differs from
        # what `git pull` brings (Larry, 2026-11-03).
        raise ConfigError(
            f"stripe_price_id in {path} is no longer used: put it in deploy/.env as"
            " IMAGESKIN_STRIPE_PRICE_ID (deploy/README.md, step 9), then remove it here"
        )
    known = {f.name for f in fields(Settings)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(f"Unknown keys in {path}: {', '.join(unknown)}")

    settings = checked_settings(Settings(**{**data, **mail_from_environment()}), path)
    logger.info("Loaded config", extra={"path": str(path)})
    return settings


def checked_settings(settings: Settings, path: object) -> Settings:
    """The settings, or ConfigError naming the first wrong one and where it was set."""
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
    if not isinstance(settings.admin_file, str):
        raise ConfigError(f"admin_file in {path} must be a string")
    if not isinstance(settings.admin_laptops_file, str):
        raise ConfigError(f"admin_laptops_file in {path} must be a string")
    if not isinstance(settings.trusted_proxies, str) or not settings.trusted_proxies.strip():
        raise ConfigError(f'trusted_proxies in {path} must be a list of addresses, or "*"')
    if type(settings.clones_loaded) is not int or settings.clones_loaded < 1:
        raise ConfigError(f"clones_loaded in {path} must be a number of at least 1")
    if not isinstance(settings.main_domain, str) or "." not in settings.main_domain.strip("."):
        raise ConfigError(f"main_domain in {path} must be a domain, such as me0.ai")
    for key in ("smtp_host", "smtp_user", "mail_from"):
        if not isinstance(getattr(settings, key), str):
            raise ConfigError(f"{key} in {path} must be a string")
    if type(settings.smtp_port) is not int or not 1 <= settings.smtp_port <= 65535:
        raise ConfigError(f"smtp_port in {path} must be a number from 1 to 65535")
    if settings.smtp_host and "@" not in settings.mail_from:
        raise ConfigError(
            f"mail_from in {path} must be the address email is sent from, such as"
            ' "me0.ai <noreply@me0.ai>", when smtp_host is set'
        )
    if settings.log_level not in LOG_LEVELS:
        raise ConfigError(f"log_level in {path} must be one of {', '.join(LOG_LEVELS)}")
    return settings
