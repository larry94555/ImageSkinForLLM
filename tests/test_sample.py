import json
import wave
from pathlib import Path

from imageskin.sample import SAMPLE_SCRIPT, make_sample
from imageskin.video import Face
from imageskin.voice import Speech, WordTiming

FACE = Face(Path("me.jpg"), 64, 64, 32, 40, 20, 16)


class FakeVoice:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def speak(self, voice: str, text: str) -> Speech:
        self.calls.append((voice, text))
        return Speech(pcm=b"\x00\x00" * 48000, sample_rate=24000, words=[WordTiming("This", 0, 1)])


class FakeVideo:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def prepare(self, photo: Path) -> Face:
        self.calls.append(f"prepare {photo}")
        return FACE

    def render(self, face: Face, wav: Path, output: Path) -> float:
        with wave.open(str(wav), "rb") as w:
            assert w.getnframes() == 48000
        assert json.loads(wav.with_suffix(".json").read_text())["words"][0]["word"] == "This"
        self.calls.append(f"render {face.photo} {output}")
        return 2.0


def test_make_sample_prepares_speaks_and_renders(tmp_path: Path) -> None:
    voice, video = FakeVoice(), FakeVideo()
    result = make_sample(Path("me.jpg"), tmp_path / "out.mp4", voice, video, "af_heart")
    assert voice.calls == [("af_heart", SAMPLE_SCRIPT)]
    assert video.calls == ["prepare me.jpg", f"render me.jpg {tmp_path / 'out.mp4'}"]
    assert result.seconds == 2.0
    assert min(result.speak_ms, result.prepare_ms, result.render_ms) >= 0


def test_sample_script_is_the_item_6_text() -> None:
    assert SAMPLE_SCRIPT.startswith("This is a test. How do I sound?")
    assert SAMPLE_SCRIPT.endswith("tell me now so we can fix it.")
    assert "  " not in SAMPLE_SCRIPT
