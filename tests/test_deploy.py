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


def test_only_caddy_reaches_the_app() -> None:
    # No port of its own, not even on the server's loopback: the SSH tunnel it was for is gone,
    # as OpenAI has the ChatGPT sign-in done on the laptop and moved over (review on PR #120).
    compose = text(DEPLOY / "compose.yaml")
    app = compose.split("\n  app:")[1].split("\n  llama:")[0]
    assert "ports:" not in app
    readme = text(DEPLOY / "README.md")
    assert "imageskin chatgpt-export chatgpt-sign-in.json" in readme
    assert "docker compose exec -T app imageskin chatgpt-import -" in readme
    assert "-L 8000" not in readme


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


def test_torchaudio_comes_from_the_cpu_index_with_torch() -> None:
    # PyPI's Linux torchaudio needs CUDA, which the CPU-only image lacks (Larry's test on Oracle).
    install = re.search(
        r"pip install .*torch==.*--index-url \"\$TORCH_INDEX\"", text(ROOT / "Dockerfile")
    )
    assert install is not None
    version = re.search(
        r"^torchaudio==([\d.]+)$", text(ROOT / "clone-requirements.txt"), re.MULTILINE
    )
    assert version is not None
    assert f"torchaudio=={version.group(1)}" in install.group()


def test_the_app_asks_the_llama_container_with_the_laptops_model() -> None:
    settings = load_settings(DEPLOY / "config.toml")
    assert settings.llm_url == "http://llama:8080/v1"
    compose = text(DEPLOY / "compose.yaml")
    assert "--port 8080" in compose
    # Gemma 3 4B as in the README's llama-server line, in the Q4_0 quantization that is faster
    # on the hosted machine's ARM cores (R97), and no port open outside Docker.
    assert "-hf ggml-org/gemma-3-4b-it-GGUF --no-mmproj" in text(ROOT / "README.md")
    assert "-hf unsloth/gemma-3-4b-it-GGUF:Q4_0 --no-mmproj" in compose
    llama = compose.split("\n  llama:")[1].split("\n  caddy:")[0]
    assert "ports:" not in llama


def test_llama_server_reuses_what_it_has_read_as_on_the_laptop() -> None:
    # Without --swa-full Gemma 3 reads every prompt again from its start, even after the
    # replies' warm-up (R97); the hosted machine runs what the README says to run.
    llama = text(DEPLOY / "compose.yaml").split("\n  llama:")[1].split("\n  caddy:")[0]
    options = "--ctx-size 4096 --threads 2 --threads-batch 4 --swa-full"
    assert options in llama
    assert options in text(ROOT / "README.md")
    # Reading on all 4 threads needs the cores' quota for them.
    assert "cpus: 4" in llama


def test_llama_servers_prompt_cache_fits_in_its_memory_cap() -> None:
    # llama-server keeps up to 8 GB of earlier prompts unless --cache-ram says otherwise; on the
    # hosted machine that outgrew the 6 GB cap during a wiki build and it was killed (2026-10-24).
    llama = text(DEPLOY / "compose.yaml").split("\n  llama:")[1].split("\n  caddy:")[0]
    cache = re.search(r"--cache-ram (\d+)", llama)
    limit = re.search(r"mem_limit: (\d+)g", llama)
    assert cache is not None and limit is not None
    # The model (about 2.5 GB), its context and working memory need the rest.
    assert int(cache.group(1)) <= (int(limit.group(1)) - 4) * 1024
    assert f"--cache-ram {cache.group(1)}" in text(ROOT / "README.md")


def test_the_containers_leave_room_for_the_machine() -> None:
    # Without caps, Prepare and the LLM together froze a 24 GB machine with no swap.
    limits = re.findall(r"mem_limit: (\d+)([gm])", text(DEPLOY / "compose.yaml"))
    gigabytes = sum(int(n) / (1 if unit == "g" else 1024) for n, unit in limits)
    assert len(limits) == 3
    assert gigabytes <= 21


def test_the_default_people_are_served_without_the_password() -> None:
    # Start now on any computer downloads them (roadmap R32a); only the app is behind basic_auth.
    caddyfile = text(DEPLOY / "Caddyfile")
    site = caddyfile.split("\n:8090")[0]
    assert site.index("handle_path /default-people/*") < site.index("basic_auth")
    assert site.count("root * /srv/default-people") == 1
    compose = text(DEPLOY / "compose.yaml")
    assert "./default-people:/srv/default-people:ro" in compose
    assert "deploy/default-people/" in text(ROOT / ".gitignore").splitlines()  # not committed


def test_the_hosted_app_gets_the_packs_from_caddy_inside_docker() -> None:
    compose = text(DEPLOY / "compose.yaml")
    assert "IMAGESKIN_DEFAULT_PEOPLE_URL: http://caddy:8090" in compose
    caddy = compose.split("\n  caddy:")[1]
    assert "8090" not in caddy  # not published outside Docker
    assert "\n:8090 {" in text(DEPLOY / "Caddyfile")


def test_the_image_stops_building_if_kokoros_english_model_cant_load() -> None:
    # preshed 3.0.14 broke loading it, so prepare failed on the site (roadmap R134a).
    dockerfile = text(ROOT / "Dockerfile")
    assert "python -m spacy download en_core_web_sm" in dockerfile
    assert "spacy.load('en_core_web_sm')" in dockerfile
    assert '"preshed<3.0.14"' in text(ROOT / "pyproject.toml")


def test_the_admin_password_folder_is_mounted_where_the_config_looks() -> None:
    # A folder, not the file, so an edit made on the machine is seen with no restart (R149).
    settings = load_settings(DEPLOY / "config.toml")
    assert settings.admin_file == "/etc/imageskin/admin/admin.toml"
    assert "- ./admin:/etc/imageskin/admin:ro" in text(DEPLOY / "compose.yaml")
    assert (DEPLOY / "admin" / "README.md").exists()
