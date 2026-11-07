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


# The mail service from the environment (R215), so the hosted site sets it in deploy/.env.
MAIL = {
    "IMAGESKIN_SMTP_HOST": "smtp.email.us-ashburn-1.oci.oraclecloud.com",
    "IMAGESKIN_SMTP_PORT": "587",
    "IMAGESKIN_SMTP_USER": "ocid1.user.oc1..aaaa@ocid1.tenancy.oc1..bbbb.xy.com",
    "IMAGESKIN_MAIL_FROM": "me0.ai <noreply@me0.ai>",
}


def test_the_mail_service_comes_from_the_environment_over_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    for name, value in MAIL.items():
        monkeypatch.setenv(name, value)
    path = write(tmp_path, 'smtp_host = "smtp.example.com"\nsmtp_port = 465\n')
    with caplog.at_level("INFO"):
        settings = load_settings(path)
    assert settings.smtp_host == MAIL["IMAGESKIN_SMTP_HOST"]
    assert settings.smtp_port == 587
    assert settings.smtp_user == MAIL["IMAGESKIN_SMTP_USER"]
    assert settings.mail_from == MAIL["IMAGESKIN_MAIL_FROM"]
    told = [r for r in caplog.records if r.message == "Mail service set in the environment"]
    assert told[0].__dict__["keys"] == ["mail_from", "smtp_host", "smtp_port", "smtp_user"]


def test_the_mail_service_from_the_environment_needs_no_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in MAIL.items():
        monkeypatch.setenv(name, value)
    assert load_settings(None) == Settings(
        smtp_host=MAIL["IMAGESKIN_SMTP_HOST"],
        smtp_user=MAIL["IMAGESKIN_SMTP_USER"],
        mail_from=MAIL["IMAGESKIN_MAIL_FROM"],
    )


def test_empty_mail_variables_leave_the_file_as_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in MAIL:
        monkeypatch.setenv(name, "")
    path = write(tmp_path, 'smtp_host = "smtp.example.com"\nmail_from = "a@b.c"\n')
    assert load_settings(path).smtp_host == "smtp.example.com"
    assert load_settings(None) == Settings()


@pytest.mark.parametrize(
    ("variable", "value", "said"),
    [
        ("IMAGESKIN_SMTP_PORT", "five", "IMAGESKIN_SMTP_PORT must be a number"),
        ("IMAGESKIN_SMTP_PORT", "70000", "smtp_port in the environment"),
        ("IMAGESKIN_SMTP_HOST", "smtp.example.com", "mail_from in the environment"),
    ],
)
def test_wrong_mail_variables_are_refused(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str, said: str
) -> None:
    monkeypatch.setenv(variable, value)
    with pytest.raises(ConfigError, match=said):
        load_settings(None)
