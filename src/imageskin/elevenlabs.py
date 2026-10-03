"""Voice engine adapter for the ElevenLabs API (instant voice cloning and text to speech)."""

import base64
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

from imageskin.voice import Speech, VoiceError, words_from_characters

logger = logging.getLogger(__name__)

API_URL = "https://api.elevenlabs.io"
API_KEY_ENV = "ELEVENLABS_API_KEY"
DEFAULT_MODEL = "eleven_multilingual_v2"
SAMPLE_RATE = 24000  # matches the voice sample from `imageskin voice-sample`
DEFAULT_TIMEOUT_S = 120.0


class ElevenLabsEngine:
    name = "elevenlabs"

    def __init__(
        self,
        api_key: str,
        model_id: str = DEFAULT_MODEL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model_id = model_id
        self._client = httpx.Client(
            base_url=API_URL,
            headers={"xi-api-key": api_key},
            timeout=timeout_s,
            transport=transport,
        )

    @classmethod
    def from_env(cls) -> "ElevenLabsEngine":
        api_key = os.environ.get(API_KEY_ENV, "").strip()
        if not api_key:
            raise VoiceError(f"set the {API_KEY_ENV} environment variable to your ElevenLabs key")
        return cls(api_key)

    def clone(self, sample: Path) -> str:
        start = time.perf_counter()
        try:
            audio = sample.read_bytes()
        except OSError as e:
            raise VoiceError(f"could not read voice sample {sample}: {e}") from e
        data = self._post(
            "/v1/voices/add",
            "clone voice",
            data={"name": f"ImageSkinForLLM {sample.stem}"},
            files={"files": (sample.name, audio, "audio/wav")},
        )
        voice_id = data.get("voice_id")
        if not isinstance(voice_id, str):
            raise VoiceError("ElevenLabs did not return a voice id")
        logger.info(
            "Cloned voice",
            extra={
                "voice_id": voice_id,
                "sample": str(sample),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return voice_id

    def speak(self, voice_id: str, text: str) -> Speech:
        if not text.strip():
            raise VoiceError("no text to speak")
        start = time.perf_counter()
        data = self._post(
            f"/v1/text-to-speech/{voice_id}/with-timestamps",
            "speak",
            params={"output_format": f"pcm_{SAMPLE_RATE}"},
            json={"text": text, "model_id": self.model_id},
        )
        try:
            pcm = base64.b64decode(data["audio_base64"])
            align = data["alignment"]
            words = words_from_characters(
                align["characters"],
                align["character_start_times_seconds"],
                align["character_end_times_seconds"],
            )
        except (KeyError, TypeError, ValueError) as e:
            raise VoiceError(f"ElevenLabs returned an unexpected response: {e!r}") from e
        logger.info(
            "Spoke text",
            extra={
                "voice_id": voice_id,
                "chars": len(text),
                "words": len(words),
                "audio_s": round(len(pcm) / 2 / SAMPLE_RATE, 2),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return Speech(pcm=pcm, sample_rate=SAMPLE_RATE, words=words)

    def _post(self, path: str, action: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.post(path, **kwargs)
        except httpx.HTTPError as e:
            raise VoiceError(f"could not reach ElevenLabs to {action}: {e}") from e
        if response.status_code != 200:
            raise VoiceError(
                f"ElevenLabs could not {action} (HTTP {response.status_code}: "
                f"{_error_detail(response)})"
            )
        try:
            body = response.json()
        except ValueError as e:
            raise VoiceError(f"ElevenLabs returned invalid JSON when asked to {action}") from e
        if not isinstance(body, dict):
            raise VoiceError(f"ElevenLabs returned an unexpected response to {action}")
        return body


def _error_detail(response: httpx.Response) -> str:
    """The API's own error message when it sends one, otherwise the start of the body."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return str(detail["message"])
    if isinstance(detail, str):
        return detail
    return response.text[:200] or "no details"
