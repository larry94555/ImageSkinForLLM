import base64
import json
from pathlib import Path

import httpx
import pytest

from imageskin.elevenlabs import API_KEY_ENV, ElevenLabsEngine
from imageskin.voice import VoiceError


def engine_with(handler: httpx.MockTransport) -> ElevenLabsEngine:
    return ElevenLabsEngine("test-key", transport=handler)


def tts_body(text: str, pcm: bytes) -> dict[str, object]:
    return {
        "audio_base64": base64.b64encode(pcm).decode(),
        "alignment": {
            "characters": list(text),
            "character_start_times_seconds": [i * 0.1 for i in range(len(text))],
            "character_end_times_seconds": [(i + 1) * 0.1 for i in range(len(text))],
        },
    }


def test_clone_uploads_sample(tmp_path: Path) -> None:
    sample = tmp_path / "me.wav"
    sample.write_bytes(b"RIFF-audio")
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"voice_id": "v1", "requires_verification": False})

    assert engine_with(httpx.MockTransport(handle)).clone(sample) == "v1"
    request = seen[0]
    assert request.url.path == "/v1/voices/add"
    assert request.headers["xi-api-key"] == "test-key"
    body = request.read()
    assert b"RIFF-audio" in body and b"ImageSkinForLLM me" in body


def test_speak_returns_audio_and_word_timings() -> None:
    pcm = b"\x01\x00" * 4800

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/text-to-speech/v1/with-timestamps"
        assert request.url.params["output_format"] == "pcm_24000"
        assert json.loads(request.content)["text"] == "Hi you"
        return httpx.Response(200, json=tts_body("Hi you", pcm))

    speech = engine_with(httpx.MockTransport(handle)).speak("v1", "Hi you")
    assert speech.pcm == pcm
    assert speech.sample_rate == 24000
    assert [w.word for w in speech.words] == ["Hi", "you"]
    you = speech.words[1]
    assert (round(you.start, 6), round(you.end, 6)) == (0.3, 0.6)


def test_speak_rejects_empty_text() -> None:
    engine = engine_with(httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(VoiceError, match="no text"):
        engine.speak("v1", "  ")


def test_api_error_message_is_reported() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": {"status": "x", "message": "Invalid API key"}})

    with pytest.raises(VoiceError, match=r"HTTP 401: Invalid API key"):
        engine_with(httpx.MockTransport(handle)).speak("v1", "Hi")


@pytest.mark.parametrize(
    ("response", "match"),
    [
        (httpx.Response(422, json={"detail": "bad voice"}), "bad voice"),
        (httpx.Response(500, text="oops"), "HTTP 500: oops"),
        (httpx.Response(200, text="not json"), "invalid JSON"),
        (httpx.Response(200, json=[1]), "unexpected response"),
        (httpx.Response(200, json={"audio_base64": "AAAA"}), "unexpected response"),
    ],
)
def test_bad_responses_raise_voice_error(response: httpx.Response, match: str) -> None:
    engine = engine_with(httpx.MockTransport(lambda r: response))
    with pytest.raises(VoiceError, match=match):
        engine.speak("v1", "Hi")


def test_clone_without_voice_id_fails(tmp_path: Path) -> None:
    sample = tmp_path / "me.wav"
    sample.write_bytes(b"x")
    engine = engine_with(httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(VoiceError, match="voice id"):
        engine.clone(sample)


def test_clone_missing_sample(tmp_path: Path) -> None:
    engine = engine_with(httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(VoiceError, match="could not read"):
        engine.clone(tmp_path / "missing.wav")


def test_network_error_is_reported() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(VoiceError, match="could not reach ElevenLabs"):
        engine_with(httpx.MockTransport(handle)).speak("v1", "Hi")


def test_from_env_needs_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    with pytest.raises(VoiceError, match=API_KEY_ENV):
        ElevenLabsEngine.from_env()
    monkeypatch.setenv(API_KEY_ENV, "k")
    assert ElevenLabsEngine.from_env().model_id == "eleven_multilingual_v2"
