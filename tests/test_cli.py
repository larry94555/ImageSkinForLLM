import json
import logging
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


def test_serve_logs_the_data_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("IMAGESKIN_HOME", str(tmp_path / "data"))
    # setup_logging would replace the handler caplog listens on.
    with (
        patch("uvicorn.run"),
        patch("imageskin.cli.setup_logging"),
        caplog.at_level(logging.INFO, logger="imageskin.cli"),
    ):
        assert main(["serve"]) == 0
    record = next(r for r in caplog.records if r.getMessage() == "App data folder")
    assert vars(record)["path"] == str((tmp_path / "data").resolve())


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


def test_say_writes_speech_and_timings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from imageskin.voice import Speech, WordTiming

    out = tmp_path / "hello.wav"
    speech = Speech(pcm=b"\x00\x00" * 12000, sample_rate=24000, words=[WordTiming("Hello", 0, 0.5)])
    with patch("imageskin.cli.KokoroEngine.speak", return_value=speech) as speak:
        assert main(["say", "--voice", "am_michael", "-o", str(out), "Hello"]) == 0
    speak.assert_called_once_with("am_michael", "Hello")
    assert out.is_file()
    assert json.loads((tmp_path / "hello.json").read_text())["words"][0]["word"] == "Hello"
    assert f"Wrote {out.resolve()} (0.5 seconds)" in capsys.readouterr().out


def test_say_error_is_logged(capsys: pytest.CaptureFixture[str]) -> None:
    from imageskin.voice import VoiceError

    with patch(
        "imageskin.cli.KokoroEngine.speak", side_effect=VoiceError("Kokoro is not installed")
    ):
        assert main(["say", "Hi"]) == 1
    entry = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert entry["error"] == "Kokoro is not installed"


def test_say_unwritable_output_logs_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from imageskin.voice import Speech

    speech = Speech(pcm=b"", sample_rate=24000, words=[])
    with patch("imageskin.cli.KokoroEngine.speak", return_value=speech):
        out = tmp_path / "missing-dir" / "x.wav"
        assert main(["say", "-o", str(out), "Hi"]) == 1
    assert "could not write" in capsys.readouterr().err


def test_sample_renders_video(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from imageskin.sample import SampleResult

    out = tmp_path / "s.mp4"
    result = SampleResult(seconds=31.2, speak_ms=9000, prepare_ms=50, render_ms=6000)
    with patch("imageskin.cli.make_sample", return_value=result) as make:
        args = ["sample", "--photo", "me.jpg", "--voice", "am_michael", "-o", str(out)]
        assert main(args) == 0
    photo, output, _, video_engine, voice, text = make.call_args.args
    assert (photo, output, voice) == (Path("me.jpg"), out, "am_michael")
    assert type(video_engine).__name__ == "MouthWarpEngine"
    assert text.startswith("This is a test.")
    printed = capsys.readouterr().out
    assert f"Wrote {out.resolve()} (31.2 seconds)" in printed
    assert "0.1 s to prepare the photo, 9.0 s to speak and 6.0 s to render" in printed


def test_sample_error_is_logged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sample", "--photo", str(tmp_path / "missing.jpg")]) == 1
    entry = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert entry["message"] == "Could not make sample video"
    assert "file not found" in entry["error"]


def test_sample_without_opencv_explains_install(capsys: pytest.CaptureFixture[str]) -> None:
    import builtins

    real_import = builtins.__import__

    def no_cv2(name: str, *args: object, **kwargs: object) -> object:
        if name == "imageskin.mouth_warp":
            raise ModuleNotFoundError("No module named 'cv2'", name="cv2")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=no_cv2):
        assert main(["sample", "--photo", "me.jpg"]) == 1
    assert 'pip install -e \\".[video]\\"' in capsys.readouterr().err


def test_sample_photoreal_engine_and_text() -> None:
    from imageskin.sample import SampleResult

    result = SampleResult(seconds=2.0, speak_ms=1, prepare_ms=1, render_ms=1)
    with patch("imageskin.cli.make_sample", return_value=result) as make:
        args = ["sample", "--photo", "me.jpg", "--engine", "photoreal", "--text", "Hi there"]
        assert main(args) == 0
    _, _, _, video_engine, _, text = make.call_args.args
    assert type(video_engine).__name__ == "PhotorealEngine"
    assert text == "Hi there"


def test_photoreal_without_opencv_explains_install(capsys: pytest.CaptureFixture[str]) -> None:
    import builtins

    real_import = builtins.__import__

    def no_cv2(name: str, *args: object, **kwargs: object) -> object:
        if name == "imageskin.photoreal":
            raise ModuleNotFoundError("No module named 'cv2'", name="cv2")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=no_cv2):
        assert main(["sample", "--photo", "me.jpg", "--engine", "photoreal"]) == 1
    assert 'pip install -e \\".[photoreal]\\"' in capsys.readouterr().err


def test_prepare_writes_preview(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "idle.mp4"
    lib = type("Lib", (), {"folder": tmp_path / "lib"})()
    with (
        patch("imageskin.photoreal_library.prepare_library", return_value=lib) as prep,
        patch("imageskin.photoreal_library.write_idle_preview", return_value=8.0) as write,
    ):
        assert main(["prepare", "--photo", "me.jpg", "-o", str(out)]) == 0
    assert prep.call_args.args[0] == Path("me.jpg")
    assert write.call_args.args == (lib, out)
    printed = capsys.readouterr().out
    assert f"frames are in {tmp_path / 'lib'}" in printed
    assert f"Wrote {out.resolve()} (8.0 seconds, no sound)" in printed


def test_prepare_error_is_logged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["prepare", "--photo", str(tmp_path / "missing.jpg")]) == 1
    entry = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert entry["message"] == "Could not prepare photo"
    assert "file not found" in entry["error"]


def test_prepare_without_opencv_explains_install(capsys: pytest.CaptureFixture[str]) -> None:
    import builtins

    real_import = builtins.__import__

    def no_cv2(name: str, *args: object, **kwargs: object) -> object:
        if name == "imageskin.photoreal_library":
            raise ModuleNotFoundError("No module named 'cv2'", name="cv2")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=no_cv2):
        assert main(["prepare", "--photo", "me.jpg"]) == 1
    assert 'pip install -e \\".[photoreal]\\"' in capsys.readouterr().err
