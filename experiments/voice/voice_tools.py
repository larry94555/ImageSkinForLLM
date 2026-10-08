"""Candidate tools that speak in the person's voice, for the R25a voice cloning test.

- conversion: Kokoro speaks the text, then Chatterbox's voice converter (MIT) changes the timbre
  to the person's, learned from their voice sample. The timing does not change, so Kokoro's word
  and sound timings still drive the mouth. The accent is Kokoro's (American).
- clone: Chatterbox Turbo (MIT) speaks the text directly in a voice cloned from the sample,
  which keeps the person's own accent. It reports no word or sound timings.

Both run on the CPU. Chatterbox marks its output with Resemble AI's inaudible Perth watermark.
The models (about 2 GB) are downloaded from Hugging Face on first use and cached.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import numpy as np

from imageskin.voice import Speech

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000  # Kokoro's and Chatterbox's output rate
REFERENCE_S = 10.0  # Chatterbox uses about this much of the voice sample


def pcm16_to_float(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768


def float_to_pcm16(samples: np.ndarray) -> bytes:
    return (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def fit_length(samples: np.ndarray, n: int) -> np.ndarray:
    """Trim or pad with silence to exactly n samples, so the converted audio matches the timings."""
    if len(samples) >= n:
        return samples[:n]
    return np.concatenate([samples, np.zeros(n - len(samples), dtype=samples.dtype)])


def start_of_speech(samples: np.ndarray, threshold: float = 0.02) -> int:
    """Index of the first sample louder than the threshold (0 if none), to skip leading silence."""
    loud = np.flatnonzero(np.abs(samples) > threshold)
    return int(loud[0]) if len(loud) else 0


def reference_clip(samples: np.ndarray, rate: int = SAMPLE_RATE) -> np.ndarray:
    """The stretch of the voice sample the tools learn from: REFERENCE_S seconds of speech."""
    start = start_of_speech(samples)
    return samples[start : start + int(REFERENCE_S * rate)]


def converted(speech: Speech, convert: Callable[[np.ndarray], np.ndarray]) -> Speech:
    """The same speech in another voice: new audio, the same word and sound timings."""
    samples = pcm16_to_float(speech.pcm)
    out = fit_length(convert(samples).astype(np.float32), len(samples))
    return replace(speech, pcm=float_to_pcm16(out))


def _timed(what: str, start: float) -> None:
    logger.info(what, extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)})


class ChatterboxConverter:  # pragma: no cover - needs the models; see the functional run
    """Kokoro's audio in, the same words in the person's voice out (24 kHz float samples).

    Uses the one-step (mean flow) decoder that ships with Chatterbox Turbo, about five times faster
    on the CPU than the converter's default ten-step decoder, with the same speaker similarity.
    """

    def __init__(self, s3gen: Any = None) -> None:
        start = time.perf_counter()
        from chatterbox.vc import ChatterboxVC

        if s3gen is None:
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            s3gen = ChatterboxTurboTTS.from_pretrained("cpu").s3gen
        self._vc = ChatterboxVC(s3gen, "cpu")
        _timed("Loaded Chatterbox converter", start)

    def set_voice(self, reference: np.ndarray) -> None:
        start = time.perf_counter()
        self._vc.ref_dict = self._vc.s3gen.embed_ref(reference, SAMPLE_RATE, device="cpu")
        _timed("Learned voice for conversion", start)

    def __call__(self, samples: np.ndarray) -> np.ndarray:
        import librosa
        import torch
        from chatterbox.models.s3tokenizer import S3_SR

        with torch.inference_mode():
            audio_16 = librosa.resample(samples, orig_sr=SAMPLE_RATE, target_sr=S3_SR)
            tokens, _ = self._vc.s3gen.tokenizer(torch.from_numpy(audio_16).float()[None,])
            wav, _ = self._vc.s3gen.inference(speech_tokens=tokens, ref_dict=self._vc.ref_dict)
            out = wav.squeeze(0).cpu().numpy()
        marked: np.ndarray = self._vc.watermarker.apply_watermark(out, sample_rate=SAMPLE_RATE)
        return marked


class ChatterboxCloner:  # pragma: no cover - needs the models; see the functional run
    """Text in, speech in a voice cloned from the sample out (24 kHz float samples)."""

    def __init__(self) -> None:
        start = time.perf_counter()
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        self.tts = ChatterboxTurboTTS.from_pretrained("cpu")
        _timed("Loaded Chatterbox Turbo", start)

    def set_voice(self, reference_wav: str) -> None:
        start = time.perf_counter()
        self.tts.prepare_conditionals(reference_wav, exaggeration=0.0)
        _timed("Learned voice for cloning", start)

    def __call__(self, text: str) -> np.ndarray:
        wav = self.tts.generate(text)
        out: np.ndarray = wav.squeeze(0).cpu().numpy()
        return out
