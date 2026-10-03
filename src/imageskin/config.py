"""Settings loaded from an optional TOML file."""

import logging
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


class ConfigError(Exception):
    """The config file is missing, unreadable or has invalid values."""


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"


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
    if not isinstance(settings.port, int) or not 1 <= settings.port <= 65535:
        raise ConfigError(f"port in {path} must be a number from 1 to 65535")
    if settings.log_level not in LOG_LEVELS:
        raise ConfigError(f"log_level in {path} must be one of {', '.join(LOG_LEVELS)}")
    logger.info("Loaded config", extra={"path": str(path)})
    return settings
