from pathlib import Path

import pytest

from imageskin.config import ConfigError, Settings, default_home, load_settings


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_defaults_without_a_file() -> None:
    assert load_settings(None) == Settings()


def test_values_from_file(tmp_path: Path) -> None:
    path = write(tmp_path, 'host = "0.0.0.0"\nport = 9000\nlog_level = "DEBUG"\n')
    assert load_settings(path) == Settings(host="0.0.0.0", port=9000, log_level="DEBUG")


def test_general_prompts_are_declined_unless_allowed(tmp_path: Path) -> None:
    assert Settings().general_prompts is False
    assert load_settings(write(tmp_path, "general_prompts = true\n")).general_prompts is True


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (
            'llm_provider = "claude"\nllm_api_key = "sk-ant-1"\n',
            "llm_provider and llm_api_key .* are",
        ),
        ('llm_provider = "local"\n', "llm_provider .* is no longer used"),
    ],
)
def test_the_llm_and_its_key_moved_to_the_settings_page(
    tmp_path: Path, text: str, said: str
) -> None:
    # R42: picked on the Settings page, so a config file that still names them says so.
    with pytest.raises(ConfigError, match=said) as refused:
        load_settings(write(tmp_path, text))
    assert "Settings page" in str(refused.value) and "sk-ant-1" not in str(refused.value)


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
        ("port = true", "port"),
        ("port = false", "port"),
        ('log_level = "LOUD"', "log_level"),
        ('llm_url = "127.0.0.1:8080"', "llm_url"),
        ("llm_model = 3", "llm_model"),
        ("llm_context_tokens = 512", "llm_context_tokens"),
        ('llm_context_tokens = "4096"', "llm_context_tokens"),
        ('general_prompts = "yes"', "general_prompts"),
        ("trusted_proxies = 1", "trusted_proxies"),
        ('trusted_proxies = " "', "trusted_proxies"),
    ],
)
def test_invalid_files_are_rejected(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_settings(write(tmp_path, text))


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "missing.toml")


def test_default_home_follows_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGESKIN_HOME", "/data/skin")
    assert default_home() == Path("/data/skin")
    monkeypatch.delenv("IMAGESKIN_HOME")
    assert default_home() == Path.home() / ".imageskin"
