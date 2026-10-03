from pathlib import Path

import pytest

from imageskin.config import ConfigError, Settings, load_settings


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_defaults_without_a_file() -> None:
    assert load_settings(None) == Settings()


def test_values_from_file(tmp_path: Path) -> None:
    path = write(tmp_path, 'host = "0.0.0.0"\nport = 9000\nlog_level = "DEBUG"\n')
    assert load_settings(path) == Settings(host="0.0.0.0", port=9000, log_level="DEBUG")


def test_example_config_loads() -> None:
    example = Path(__file__).parent.parent / "config.example.toml"
    assert load_settings(example) == Settings()


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("port = [", "not valid TOML"),
        ("colour = 1", "Unknown keys"),
        ("host = 1", "host"),
        ('port = "80"', "port"),
        ("port = 70000", "port"),
        ('log_level = "LOUD"', "log_level"),
    ],
)
def test_invalid_files_are_rejected(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_settings(write(tmp_path, text))


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "missing.toml")
