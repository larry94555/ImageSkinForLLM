"""Pocket TTS (Kyutai), a small voice model that clones a voice from a sample, for replies within
1 to 2 seconds on a 4-core CPU (roadmap R22f).

Measured on 4 cores with 2 threads: a 4-word clause took 0.56 s with Pocket TTS (int8) against
7 s with Chatterbox Turbo, and a 6-word one 0.77 s against 8.8 s, so it runs at about a third of
real time where Chatterbox runs at about four times. It learns the voice from the same 10 seconds
of the voice sample as Chatterbox, keeps the accent of what it learns from (the person's own, or
another learned from converted speech; see accent.py) and speaks at 24 kHz. Like
Chatterbox it reports no timings, so ChatterboxEngine runs it with the same forced alignment.

The code is MIT and the weights are CC-BY-4.0 (credit: Kyutai). The weights that clone a voice
are gated on Hugging Face: accept the terms on the model's page once, then sign in with
`hf auth login`. Without that, the library loads a model with only its own voices, which this
engine refuses. The models (about 530 MB) are downloaded on first use and cached.
"""

import importlib.util
import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import numpy as np

from imageskin.chatterbox_engine import SAMPLE_RATE, ChatterboxEngine, Cloner
from imageskin.logging_setup import quiet_library_warnings
from imageskin.voice import VoiceError

logger = logging.getLogger(__name__)

NAME = "Pocket TTS"
TERMS_URL = "https://huggingface.co/kyutai/pocket-tts"
GATED = (
    f"its weights that clone a voice need the terms accepted at {TERMS_URL}, then: hf auth login"
    " (or uninstall pocket-tts and restart imageskin serve to speak with Chatterbox)"
)
# Pocket runs the voice, the aligner (transformers) and the pronunciation step (Kokoro).
REQUIRED = ("pocket_tts", "transformers", "kokoro")


def installed() -> bool:
    """Whether Pocket TTS is installed; when it is, it speaks every accent (see accent.py)."""
    return importlib.util.find_spec("pocket_tts") is not None


def check_installed() -> None:
    missing = [name for name in REQUIRED if importlib.util.find_spec(name) is None]
    if missing:
        raise VoiceError(f"{', '.join(missing)} not installed; see 'Your own voice' in the README")


@contextmanager
def worker_threads(torch: Any) -> Iterator[None]:
    """Split the engines' threads between Pocket's two worker threads while it speaks.

    Pocket generates and decodes on two threads of its own, which start with PyTorch's thread
    count, so with that count each they would use twice the engines' share of the cores. Beside
    the LLM on 4 cores, a 4-word clause took 0.6 s with one thread each and 1.7 to 2.5 s with two
    each. The count is put back afterwards for the other steps.
    """
    threads = torch.get_num_threads()
    torch.set_num_threads(max(1, threads // 2))
    try:
        yield
    finally:
        torch.set_num_threads(threads)


def gated_reason(download: Callable[[str], object], weights_path: str | None) -> str:
    """Why the weights that clone a voice could not be downloaded. Pocket falls back to its model
    without cloning and drops the error, which says which step is missing (not signed in, terms
    not accepted, a token without access to gated models), so the download is tried again for it.
    """
    if weights_path is None:
        return "this model has no weights that clone a voice"
    try:
        download(weights_path)
    except Exception as e:  # what Hugging Face refused, or a network error
        detail = " ".join(re.sub(r"\(Request ID: [^)]*\)", "", str(e)).split())[:500]
        return f"{type(e).__name__}: {detail}" if detail else type(e).__name__
    return "the download works now; try again"


class PocketCloner:  # pragma: no cover - needs the models; see the functional run in the PR
    def __init__(self) -> None:
        from pocket_tts import TTSModel

        # int8: about 40% faster on the CPU, with no measurable change in quality (Kyutai).
        self.model = TTSModel.load_model(quantize=True)
        if not self.model.has_voice_cloning:
            from pocket_tts.utils.utils import download_if_necessary

            reason = gated_reason(download_if_necessary, self.model.config.weights_path)
            raise VoiceError(f"{GATED}; Hugging Face said: {reason}")
        if self.model.sample_rate != SAMPLE_RATE:
            raise VoiceError(f"Pocket TTS speaks at {self.model.sample_rate} Hz, not {SAMPLE_RATE}")
        self._state: object | None = None

    def set_voice(self, reference: np.ndarray) -> None:
        import torch

        self._state = self.model.get_state_for_audio_prompt(torch.from_numpy(reference)[None])

    def __call__(self, text: str) -> np.ndarray:
        import torch

        if self._state is None:
            raise VoiceError("Pocket TTS has not learned a voice")
        with worker_threads(torch):
            out: np.ndarray = self.model.generate_audio(self._state, text).squeeze(0).numpy()
        return out


def _load_cloner() -> Cloner:  # pragma: no cover - needs the models
    with quiet_library_warnings():
        return PocketCloner()


def pocket_engine() -> ChatterboxEngine:
    """The clone engine, speaking with Pocket TTS."""
    return ChatterboxEngine(load=_load_cloner, check=check_installed, name=NAME)
