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


def test_voice_sample_writes_wav(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "sample.wav"
    with patch("imageskin.cli.make_voice_sample", return_value=42.0) as make:
        assert main(["voice-sample", "a.m4a", "b.mp3", "-o", str(out), "--timeout", "5"]) == 0
    make.assert_called_once_with([Path("a.m4a"), Path("b.mp3")], out, 5.0)
    assert capsys.readouterr().out.strip() == f"Wrote {out} (42.0 seconds from 2 recordings)"


def test_voice_sample_error_logs_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["voice-sample", str(tmp_path / "missing.m4a")]) == 1
    entry = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert entry["level"] == "ERROR"
    assert "file not found" in entry["error"]
