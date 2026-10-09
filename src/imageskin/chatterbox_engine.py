"""Voice engine adapter for Chatterbox Turbo, which speaks text in a voice cloned from a sample.

Picked in R25a: Larry found the clone sounds like him. It learns the voice from 10 seconds of the
voice sample (`imageskin voice-sample`) with no training, keeps the person's own accent and runs
on the CPU, at about 1.5 to 2 seconds of work per second of speech on 4 cores. It reports no word
or sound timings, so they are found in its audio by forced alignment (alignment.py).

Chatterbox (MIT, Resemble AI) adds Resemble AI's inaudible Perth watermark to what it makes. Its
models (about 2.8 GB) are downloaded from Hugging Face on first use and cached. It pins old
versions of torch and numpy, so it is installed without its pins; see the README.
"""

import importlib.resources
import importlib.util
import logging
import sys
import time
import types
import warnings
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import numpy as np

from imageskin.alignment import Aligner
from imageskin.kokoro_engine import to_pcm16
from imageskin.logging_setup import quiet_library_warnings
from imageskin.voice import Speech, VoiceError

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000  # Chatterbox's output rate, and the voice sample's
REFERENCE_S = 10.0  # Chatterbox learns from about this much of the voice sample
TURBO_REVISION = "749d1c1a46eb10492095d68fbcf55691ccf137cd"  # the weights tested in R25a
INSTALL_HINT = "see 'Your own voice' in the README"


class Cloner(Protocol):
    def set_voice(self, reference: np.ndarray) -> None:
        """Learn the voice from a stretch of the person's speech (24 kHz float samples)."""
        ...

    def __call__(self, text: str) -> np.ndarray:
        """Speak the text in the learned voice; return 24 kHz float samples."""
        ...


def start_of_speech(samples: np.ndarray, threshold: float = 0.02) -> int:
    """Index of the first sample louder than the threshold (0 if none), to skip leading silence."""
    loud = np.flatnonzero(np.abs(samples) > threshold)
    return int(loud[0]) if len(loud) else 0


def reference_clip(samples: np.ndarray, rate: int = SAMPLE_RATE) -> np.ndarray:
    """The stretch of the voice sample the clone learns from: REFERENCE_S seconds of speech."""
    start = start_of_speech(samples)
    return samples[start : start + int(REFERENCE_S * rate)]


def read_voice_sample(path: Path) -> np.ndarray:
    """The voice sample's samples as floats; it must be the 24 kHz mono WAV voice-sample makes."""
    try:
        with wave.open(str(path), "rb") as w:
            params = w.getparams()
            frames = w.readframes(params.nframes)
    except (OSError, EOFError, wave.Error) as e:
        raise VoiceError(f"could not read the voice sample {path}: {e}") from e
    if (params.framerate, params.nchannels, params.sampwidth) != (SAMPLE_RATE, 1, 2):
        raise VoiceError(
            f"{path} is not a 24 kHz mono 16-bit WAV; make it with: imageskin voice-sample"
        )
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768
    if not np.any(np.abs(samples) > 0.02):
        raise VoiceError(f"the voice sample {path} is silent")
    return samples


def provide_pkg_resources() -> None:
    """Let Chatterbox's watermarker import pkg_resources, which setuptools 81 removed.

    It only calls resource_filename to find its bundled model folder, so when setuptools no longer
    provides the module, a stand-in answers that one call. Nothing is installed or downgraded.
    """
    try:
        with warnings.catch_warnings():  # setuptools 80 warns that pkg_resources is deprecated
            warnings.simplefilter("ignore")
            import pkg_resources  # noqa: F401
    except ImportError:
        shim = types.ModuleType("pkg_resources")
        shim.resource_filename = lambda package, name: str(  # type: ignore[attr-defined]
            importlib.resources.files(package) / name
        )
        sys.modules["pkg_resources"] = shim


REQUIRED = ("chatterbox", "transformers", "kokoro")  # the clone, the aligner, pronunciation


def check_installed() -> None:
    """Fail at once, before any download, when a package the clone needs is missing."""
    missing = [name for name in REQUIRED if importlib.util.find_spec(name) is None]
    if missing:
        raise VoiceError(f"{', '.join(missing)} not installed; {INSTALL_HINT}")


class ChatterboxEngine:
    """Speaks text in the voice of a voice sample; `voice` is the sample's path."""

    def __init__(
        self,
        load: Callable[[], Cloner] | None = None,
        aligner: Aligner | None = None,
        check: Callable[[], None] | None = None,
    ) -> None:
        self._load = load or _load_cloner
        self._aligner = aligner or Aligner()
        self._check = check or check_installed
        self._cloner: Cloner | None = None
        self._voice: str | None = None  # the voice the cloner has learned
        self._reference: tuple[str, np.ndarray] | None = None  # a checked voice sample

    def check_voice_sample(self, voice: str) -> None:
        """Check the install and read the voice sample, so a mistake in either shows at once,
        before the models download or a photo is prepared. speak() reuses what was read."""
        self._check()
        if voice != self._voice and (self._reference is None or self._reference[0] != voice):
            self._reference = (voice, reference_clip(read_voice_sample(Path(voice))))

    def learn_voice(self, voice: str) -> None:
        """Load the models and learn the voice afresh, even one learned before from the same
        path: the voice sample is joined again whenever the recordings change (roadmap R25b)."""
        self._voice = None
        self._reference = None
        self.check_voice_sample(voice)
        self._learn_voice(self._loaded(), voice)

    def reference(self, voice: str) -> np.ndarray:
        """The stretch of the voice sample the voice is learned from."""
        self.check_voice_sample(voice)
        assert self._reference is not None
        return self._reference[1]

    def cloner(self) -> Cloner:
        """The loaded clone model, which the accent converter shares (roadmap R26)."""
        return self._get_cloner()

    def speak(self, voice: str, text: str) -> Speech:
        if not text.strip():
            raise VoiceError("no text to speak")
        self.check_voice_sample(voice)
        cloner = self._loaded()
        if voice != self._voice:
            self._learn_voice(cloner, voice)
        start = time.perf_counter()
        try:
            samples = np.asarray(cloner(text), dtype=np.float32)
        except Exception as e:  # the model's own errors
            raise VoiceError(f"Chatterbox could not speak the text: {e}") from e
        clone_s = time.perf_counter() - start
        start = time.perf_counter()
        words, sounds = self._aligner.align(samples, SAMPLE_RATE, text)
        align_s = time.perf_counter() - start
        audio_s = len(samples) / SAMPLE_RATE
        logger.info(
            "Spoke text in cloned voice",
            extra={
                "chars": len(text),
                "words": len(words),
                "sounds": len(sounds),
                "audio_s": round(audio_s, 2),
                "clone_ms": round(clone_s * 1000, 1),
                "align_ms": round(align_s * 1000, 1),
                # Seconds of work per second of speech; below 1.0 is faster than real time.
                "real_time_factor": round((clone_s + align_s) / audio_s, 2) if audio_s else None,
            },
        )
        return Speech(to_pcm16(samples.tolist()), SAMPLE_RATE, words, sounds)

    def _learn_voice(self, cloner: Cloner, voice: str) -> None:
        assert self._reference is not None and self._reference[0] == voice
        reference = self._reference[1]
        start = time.perf_counter()
        try:
            cloner.set_voice(reference)
        except Exception as e:  # the model's own errors
            raise VoiceError(f"Chatterbox could not learn the voice in {voice}: {e}") from e
        self._voice = voice
        logger.info(
            "Learned voice",
            extra={
                "voice_sample": voice,
                "reference_s": round(len(reference) / SAMPLE_RATE, 2),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )

    def _loaded(self) -> Cloner:
        cloner = self._get_cloner()
        # The aligner too, so a download or install problem shows before the slow clone.
        self._aligner.load()
        return cloner

    def _get_cloner(self) -> Cloner:
        if self._cloner is None:
            start = time.perf_counter()
            try:
                self._cloner = self._load()
            except ImportError as e:
                logger.exception("Could not import Chatterbox")
                raise VoiceError(f"Chatterbox is installed but could not be loaded: {e}") from e
            except Exception as e:  # download or model load failure
                raise VoiceError(f"could not load Chatterbox Turbo: {e}") from e
            logger.info(
                "Loaded Chatterbox Turbo",
                extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)},
            )
        return self._cloner


class TurboCloner:  # pragma: no cover - needs the models; see the functional run in the PR
    def __init__(self) -> None:
        provide_pkg_resources()
        from chatterbox.tts_turbo import REPO_ID, ChatterboxTurboTTS
        from huggingface_hub import snapshot_download

        # The repository also holds the ten-step decoder (1 GB) that Turbo never loads.
        folder = snapshot_download(
            REPO_ID, revision=TURBO_REVISION, ignore_patterns=["s3gen.safetensors"]
        )
        self.tts = ChatterboxTurboTTS.from_local(folder, "cpu")

    def set_voice(self, reference: np.ndarray) -> None:
        import tempfile

        import soundfile

        # Chatterbox's own loudness step turns the audio into float64 under NumPy 2, which its
        # model then rejects, so the reference is levelled here and kept float32.
        levelled = self.tts.norm_loudness(reference, SAMPLE_RATE).astype(np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "reference.wav"
            soundfile.write(wav, levelled, SAMPLE_RATE, subtype="FLOAT")
            self.tts.prepare_conditionals(str(wav), exaggeration=0.0, norm_loudness=False)

    def __call__(self, text: str) -> np.ndarray:
        with quiet_library_warnings():
            out: np.ndarray = self.tts.generate(text).squeeze(0).cpu().numpy()
        return out


class TurboConverter:  # pragma: no cover - needs the models; see the functional run in the PR
    """Changes speech in another voice into the person's, keeping its words, timing and accent.

    Chatterbox's voice converter, run with Turbo's own one-step decoder (already loaded for the
    clone), which is about five times faster on the CPU than the converter's ten-step one.
    """

    def __init__(self, cloner: Cloner) -> None:
        from chatterbox.vc import ChatterboxVC

        self._vc = ChatterboxVC(cloner.tts.s3gen, "cpu")  # type: ignore[attr-defined]

    def set_voice(self, reference: np.ndarray) -> None:
        self._vc.ref_dict = self._vc.s3gen.embed_ref(reference, SAMPLE_RATE, device="cpu")

    def __call__(self, samples: np.ndarray) -> np.ndarray:
        import librosa
        import torch
        from chatterbox.models.s3tokenizer import S3_SR

        with torch.inference_mode(), quiet_library_warnings():
            audio_16 = librosa.resample(samples, orig_sr=SAMPLE_RATE, target_sr=S3_SR)
            tokens, _ = self._vc.s3gen.tokenizer(torch.from_numpy(audio_16).float()[None,])
            wav, _ = self._vc.s3gen.inference(speech_tokens=tokens, ref_dict=self._vc.ref_dict)
            out = wav.squeeze(0).cpu().numpy()
        marked: np.ndarray = self._vc.watermarker.apply_watermark(out, sample_rate=SAMPLE_RATE)
        return marked


def _load_cloner() -> Cloner:  # pragma: no cover - needs the models
    with quiet_library_warnings():
        return TurboCloner()
