"""Candidate tools that speak in the person's voice, for the R25a voice cloning test.

- conversion: Kokoro speaks the text, then Chatterbox's voice converter (MIT) changes the timbre
  to the person's, learned from their voice sample. The timing does not change, so Kokoro's word
  and sound timings still drive the mouth. The accent is Kokoro's (American).
- clone: Chatterbox Turbo (MIT) speaks the text directly in a voice cloned from the sample,
  which keeps the person's own accent. It reports no word or sound timings. Larry picked it, so
  R25 moved it into the app (imageskin.chatterbox_engine), and this test now uses that copy.

Both run on the CPU. Chatterbox marks its output with Resemble AI's inaudible Perth watermark.
The models (about 2 GB) are downloaded from Hugging Face on first use and cached.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import numpy as np

from imageskin.chatterbox_engine import (  # the app's clone (R25); this test reuses it
    SAMPLE_RATE,
    TurboCloner,
    provide_pkg_resources,
    reference_clip,
)
from imageskin.kokoro_engine import to_pcm16
from imageskin.voice import Speech

logger = logging.getLogger(__name__)


def pcm16_to_float(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768


def fit_length(samples: np.ndarray, n: int) -> np.ndarray:
    """Trim or pad with silence to exactly n samples, so the converted audio matches the timings."""
    if len(samples) >= n:
        return samples[:n]
    return np.concatenate([samples, np.zeros(n - len(samples), dtype=samples.dtype)])


def converted(speech: Speech, convert: Callable[[np.ndarray], np.ndarray]) -> Speech:
    """The same speech in another voice: new audio, the same word and sound timings."""
    samples = pcm16_to_float(speech.pcm)
    out = fit_length(convert(samples).astype(np.float32), len(samples))
    return replace(speech, pcm=to_pcm16(out.tolist()))


def _timed(what: str, start: float) -> None:
    logger.info(what, extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)})


class ChatterboxConverter:  # pragma: no cover - needs the models; see the functional run
    """Kokoro's audio in, the same words in the person's voice out (24 kHz float samples).

    Uses the one-step (mean flow) decoder that ships with Chatterbox Turbo, about five times faster
    on the CPU than the converter's default ten-step decoder, with the same speaker similarity.
    """

    def __init__(self, s3gen: Any = None) -> None:
        start = time.perf_counter()
        provide_pkg_resources()
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


# Chatterbox Turbo cloning, as the app does it (`.tts` is the loaded model the converter shares).
ChatterboxCloner = TurboCloner
__all__ = [
    "SAMPLE_RATE",
    "ChatterboxCloner",
    "ChatterboxConverter",
    "converted",
    "fit_length",
    "pcm16_to_float",
    "reference_clip",
]
