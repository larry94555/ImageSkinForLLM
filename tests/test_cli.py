import json
from pathlib import Path
from unittest.mock import patch

import pytest

from imageskin import __version__
from imageskin.cli import main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"imageskin {__version__}"


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: imageskin" in capsys.readouterr().out


def test_bad_config_logs_error_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--config", str(tmp_path / "missing.toml"), "serve"]) == 2
    entry = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert entry["level"] == "ERROR"
    assert "not found" in entry["error"]


def test_serve_runs_uvicorn_with_config(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("port = 9123\n")
    with patch("uvicorn.run") as run:
        assert main(["--config", str(config), "serve"]) == 0
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 9123
