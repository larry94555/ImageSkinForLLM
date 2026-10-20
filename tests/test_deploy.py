"""The hosted site's files (roadmap R32) agree with each other and with the app."""

import re
from pathlib import Path

from imageskin.config import load_settings

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_hosted_config_loads_and_listens_where_caddy_and_docker_look() -> None:
    settings = load_settings(DEPLOY / "config.toml")
    assert settings.host == "0.0.0.0"  # reachable from Caddy's container
    assert f"reverse_proxy app:{settings.port}" in text(DEPLOY / "Caddyfile")
    dockerfile = text(ROOT / "Dockerfile")
    assert f"EXPOSE {settings.port}" in dockerfile
    assert f"http://127.0.0.1:{settings.port}/health" in dockerfile
    assert "COPY deploy/config.toml /etc/imageskin/config.toml" in dockerfile


def test_the_password_is_asked_before_anything_is_proxied() -> None:
    caddyfile = text(DEPLOY / "Caddyfile")
    assert caddyfile.index("basic_auth") < caddyfile.index("reverse_proxy")
    assert "{$LOGIN_NAME} {$LOGIN_PASSWORD_HASH}" in caddyfile


def test_the_app_is_published_only_on_the_servers_own_loopback() -> None:
    compose = text(DEPLOY / "compose.yaml")
    app = compose.split("\n  caddy:")[0]
    published = re.findall(r'^\s+- "(.+:\d+)"$', app.split("ports:")[1], re.MULTILINE)
    assert published == ["127.0.0.1:8000:8000"]  # the SSH tunnel for Sign in with ChatGPT


def test_every_variable_compose_needs_is_in_the_example_env() -> None:
    needed = set(re.findall(r"\$\{(\w+):\?", text(DEPLOY / "compose.yaml")))
    example = set(re.findall(r"^(\w+)=", text(DEPLOY / ".env.example"), re.MULTILINE))
    assert needed == {"SITE_ADDRESS", "LOGIN_NAME", "LOGIN_PASSWORD_HASH"}
    assert needed <= example
    assert "deploy/.env" in text(ROOT / ".gitignore").splitlines()  # the hash stays on the server


def test_the_image_installs_the_cloned_voice_as_the_readme_does() -> None:
    dockerfile = text(ROOT / "Dockerfile")
    chatterbox = re.search(r"chatterbox-tts==[\d.]+", dockerfile)
    assert chatterbox is not None
    assert f"pip install --no-deps {chatterbox.group()}" in text(ROOT / "README.md")
    torch = re.search(r"torch==([\d.]+)", dockerfile)
    assert torch is not None
    assert f"Tested with torch {torch.group(1)}" in text(ROOT / "clone-requirements.txt")


def test_both_containers_have_public_name_servers() -> None:
    # Oracle's Ubuntu resolves through 127.0.0.53, which a container can't reach (Larry's test).
    compose = text(DEPLOY / "compose.yaml")
    assert compose.count("dns:\n      - 1.1.1.1\n      - 8.8.8.8") == 2
