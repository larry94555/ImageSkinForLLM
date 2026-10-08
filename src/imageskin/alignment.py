"""Word and sound timings for speech whose text is known, found in the audio (forced alignment).

The cloned voice (Chatterbox) reports no timings, but the mouth and the word highlighting need
them. The words are known, so a speech recognizer only has to say when each letter is heard:
wav2vec2 (facebook/wav2vec2-base-960h, Apache 2.0, about 360 MB, on the CPU) scores every
letter in each 20 ms of audio, and the most likely path through the text's letters (CTC
alignment) gives each word's start and end. Each word's sounds come from Kokoro's own
pronunciation step (misaki), so they are the phonemes the mouth shapes were tuned on; they share
out the word's time equally.
"""

import json
import logging
import os
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from imageskin.config import default_home
from imageskin.download import download
from imageskin.kokoro_engine import INSTALL_HINT as KOKORO_HINT
from imageskin.logging_setup import quiet_library_warnings
from imageskin.visemes import HOLDS, SoundTiming, sound_timings
from imageskin.voice import VoiceError, WordTiming

logger = logging.getLogger(__name__)

CLONE_HINT = "see 'Your own voice' in the README"
ALIGNER_REPO = "facebook/wav2vec2-base-960h"
ALIGNER_REVISION = "22aad52d435eb6dbaf354bdad9b0da84ce7d6156"  # the tested weights
ALIGNER_RATE = 16000
# The recognizer's files at that revision, as (name, bytes, sha256). They are fetched with the
# app's own downloader, which logs progress and resumes after a dropped connection.
ALIGNER_FILES = [
    ("config.json", 1596, "d3ec255c063d9f95057b553b19c20135b259875834a4fe9deb218a6be25b4cf3"),
    ("vocab.json", 291, "19727f8944fe6459fc3f240ae2c198395b740f6a029bd23e06656266b83bcf64"),
    (
        "model.safetensors",
        377607901,
        "8aa76ab2243c81747a1f832954586bc566090c83a0ac167df6f31f0fa917d74a",
    ),
]
WORD_GAP = "|"  # the recognizer's token between words
# The recognizer stops hearing a word's last letter before its sound has died away, so each word
# runs on into the next one, or for at most this long into a pause. On three test texts that
# matched the mouth shapes from Kokoro's own sound timings best (the same shape 62% to 65% of
# the time, against 24% to 28% without it); moving word starts earlier only made it worse.
END_PAD_S = 0.2
WILDCARD_PENALTY = 0.1  # log-probability below the best token, for speech with no letters


@dataclass(frozen=True)
class Word:
    text: str
    phonemes: str
    joined: bool = False  # no space before the next word, as in "I" + "'m"


Emissions = Callable[[np.ndarray], np.ndarray]  # 16 kHz samples in, log-probabilities [T, V] out
G2P = Callable[[str], list[Word]]


def ctc_frames(log_probs: np.ndarray, targets: Sequence[int], blank: int = 0) -> list[range]:
    """The frames each target token is heard in, on the most likely CTC path (Viterbi).

    `log_probs` has one row per frame and one column per token. Every target gets at least one
    frame. Raises ValueError when the audio has too few frames for the text.
    """
    n_frames = len(log_probs)
    ext = np.full(2 * len(targets) + 1, blank)
    ext[1::2] = targets
    n_states = len(ext)
    # A token may follow the one two states back (skipping a blank) unless it repeats it.
    can_skip = np.zeros(n_states, dtype=bool)
    can_skip[2:] = (ext[2:] != blank) & (ext[2:] != ext[:-2])
    score = np.full(n_states, -np.inf)
    score[0] = log_probs[0, ext[0]]
    if n_states > 1:
        score[1] = log_probs[0, ext[1]]
    back = np.zeros((n_frames, n_states), dtype=np.int8)
    for t in range(1, n_frames):
        step = np.concatenate(([-np.inf], score[:-1]))
        skip = np.where(can_skip, np.concatenate(([-np.inf, -np.inf], score[:-2])), -np.inf)
        options = np.stack([score, step, skip])
        back[t] = np.argmax(options, axis=0)
        score = options[back[t], np.arange(n_states)] + log_probs[t, ext]
    state = n_states - 1
    if n_states > 1 and score[n_states - 2] > score[state]:
        state = n_states - 2
    if not np.isfinite(score[state]):
        raise ValueError(f"{n_frames} frames of audio is too short for {len(targets)} letters")
    states = np.empty(n_frames, dtype=int)
    for t in range(n_frames - 1, -1, -1):
        states[t] = state
        state -= int(back[t, state])
    out = []
    for i in range(len(targets)):
        frames = np.flatnonzero(states == 2 * i + 1)
        out.append(range(int(frames[0]), int(frames[-1]) + 1))
    return out


def letter_tokens(text: str, vocab: dict[str, int]) -> list[int]:
    """The recognizer's tokens for a word's letters; characters it has no token for are left out.

    A word with digits gets none, since "3pm" is said as "three p m" but spelled with two letters;
    word_timings matches it with a wildcard instead.
    """
    if any(ch.isdigit() for ch in text):
        return []
    return [vocab[ch] for ch in text.upper() if ch in vocab and ch != WORD_GAP]


def word_timings(
    words: Sequence[Word], log_probs: np.ndarray, vocab: dict[str, int], seconds: float
) -> list[WordTiming]:
    """When each word is said.

    A run of words with no letters to align (such as "45 67" or "2026") is matched by a wildcard
    token that stands for any sounds, so the run gets its own stretch of the audio instead of
    the words around it absorbing it; its words then share that stretch by how many sounds each
    has.
    """
    wildcard = log_probs.shape[1]
    targets: list[int] = []
    spans: list[tuple[int, int]] = []  # each word's first and last target (a run shares one)
    anchored = [bool(letter_tokens(w.text, vocab)) for w in words]
    for i, word in enumerate(words):
        if not anchored[i] and i > 0 and not anchored[i - 1]:
            spans.append(spans[-1])
            continue
        if targets and not words[i - 1].joined:
            targets.append(vocab[WORD_GAP])
        tokens = letter_tokens(word.text, vocab) or [wildcard]
        spans.append((len(targets), len(targets) + len(tokens) - 1))
        targets += tokens
    # The wildcard scores, in each frame, a little below the most likely token there, so silence
    # still goes to the blank and the text's own letters still win where they are heard.
    best = log_probs.max(axis=1, keepdims=True) - WILDCARD_PENALTY
    scores = np.concatenate([log_probs, best], axis=1)
    frames = ctc_frames(scores, targets, blank=vocab.get("<pad>", 0))
    frame_s = seconds / len(log_probs)
    out: list[WordTiming] = []
    i = 0
    while i < len(words):
        j = i + 1
        while j < len(words) and spans[j] == spans[i]:
            j += 1
        start = frames[spans[i][0]].start * frame_s
        length = frames[spans[i][1]].stop * frame_s - start
        weights = [max(1, sound_count(w.phonemes)) for w in words[i:j]]
        for word, weight in zip(words[i:j], weights, strict=True):
            step = length * weight / sum(weights)
            out.append(WordTiming(word.text, round(start, 3), round(start + step, 3)))
            start += step
        i = j
    return widened(out, seconds)


def sound_count(phonemes: str) -> int:
    return sum(ch not in HOLDS for ch in phonemes)


def widened(timings: Sequence[WordTiming], seconds: float) -> list[WordTiming]:
    """Each word ends END_PAD_S later, but no later than the next word's start or the clip."""
    out: list[WordTiming] = []
    for i, w in enumerate(timings):
        limit = timings[i + 1].start if i + 1 < len(timings) else seconds
        out.append(WordTiming(w.word, w.start, round(max(w.end, min(w.end + END_PAD_S, limit)), 3)))
    return out


def word_sounds(phonemes: str, start: float, end: float) -> list[SoundTiming]:
    """A word's sounds share out its time equally (weighting vowels longer matched worse)."""
    phonemes = phonemes.lstrip("".join(HOLDS))
    if not phonemes:
        return [SoundTiming("ə", start, end)] if end > start else []
    weights = [0.0 if ch in HOLDS else 1.0 for ch in phonemes]
    total = sum(weights)
    return sound_timings(phonemes, [(end - start) * w / total for w in weights], start)


def sound_timings_for(
    words: Sequence[Word], timings: Sequence[WordTiming], seconds: float
) -> list[SoundTiming]:
    """Every sound in the clip, with the mouth at rest (".") between words and at both ends."""
    out: list[SoundTiming] = []
    t = 0.0
    for word, timing in zip(words, timings, strict=True):
        if timing.start > t:
            out.append(SoundTiming(".", round(t, 3), timing.start))
        out += word_sounds(word.phonemes, max(t, timing.start), timing.end)
        t = max(t, timing.end)
    if seconds > t:
        out.append(SoundTiming(".", round(t, 3), round(seconds, 3)))
    return out


def to_rate(samples: np.ndarray, rate: int, target: int) -> np.ndarray:
    """Resample by linear interpolation; plenty for a recognizer that works in 20 ms frames."""
    if rate == target:
        return samples
    n = round(len(samples) * target / rate)
    out: np.ndarray = np.interp(np.arange(n) * rate / target, np.arange(len(samples)), samples)
    return out.astype(np.float32)


class Aligner:
    """Finds the word and sound timings of speech whose text is known."""

    def __init__(
        self,
        load: Callable[[], tuple[Emissions, dict[str, int]]] | None = None,
        g2p: Callable[[], G2P] | None = None,
    ) -> None:
        self._load = load or _load_recognizer
        self._load_g2p = g2p or _load_g2p
        self._model: tuple[Emissions, dict[str, int]] | None = None
        self._g2p: G2P | None = None

    def load(self) -> None:
        """Load the pronunciation step, then (the first time, downloading it) the recognizer."""
        self._get_g2p()
        self._get_model()

    def align(
        self, samples: np.ndarray, rate: int, text: str
    ) -> tuple[list[WordTiming], list[SoundTiming]]:
        emissions, vocab = self._get_model()
        g2p = self._get_g2p()
        start = time.perf_counter()
        seconds = len(samples) / rate
        words = g2p(text)
        if not words:
            raise VoiceError(f"no words to align in {text!r}")
        try:
            log_probs = emissions(to_rate(samples, rate, ALIGNER_RATE))
            timings = word_timings(words, log_probs, vocab, seconds)
        except ValueError as e:
            raise VoiceError(f"could not find the words in the audio: {e}") from e
        sounds = sound_timings_for(words, timings, seconds)
        logger.info(
            "Aligned words",
            extra={
                "words": len(timings),
                "sounds": len(sounds),
                "audio_s": round(seconds, 2),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return timings, sounds

    def _get_model(self) -> tuple[Emissions, dict[str, int]]:
        if self._model is None:
            start = time.perf_counter()
            try:
                self._model = self._load()
            except ImportError as e:
                raise VoiceError(f"the aligner could not be loaded: {e}; {CLONE_HINT}") from e
            except Exception as e:  # download or model load failure
                raise VoiceError(f"could not load the aligner {ALIGNER_REPO}: {e}") from e
            logger.info(
                "Loaded aligner",
                extra={
                    "repo_id": ALIGNER_REPO,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
        return self._model

    def _get_g2p(self) -> G2P:
        if self._g2p is None:
            try:
                self._g2p = self._load_g2p()
            except ImportError as e:
                raise VoiceError(f"{KOKORO_HINT} ({e})") from e
        return self._g2p


def hf_cache() -> Path:
    """Hugging Face's download cache folder."""
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    return Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"


def ensure_aligner(home: Path, fetch: Callable[[str, Path, int, str], None] = download) -> Path:
    """Download the recognizer into <home>/models once; files already there are checked."""
    folder = home / "models" / "wav2vec2-base-960h"
    cached = hf_cache() / "models--facebook--wav2vec2-base-960h" / "snapshots" / ALIGNER_REVISION
    for name, size, sha256 in ALIGNER_FILES:
        dest = folder / name
        if not dest.exists() and (cached / name).is_file():
            # An earlier version fetched it into Hugging Face's cache; copy it rather than download
            # it again. The downloader still checks its size and checksum.
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cached / name, dest)
        url = f"https://huggingface.co/{ALIGNER_REPO}/resolve/{ALIGNER_REVISION}/{name}"
        fetch(url, dest, size, sha256)
    return folder


def _load_recognizer() -> tuple[Emissions, dict[str, int]]:  # pragma: no cover - needs the model
    with quiet_library_warnings():  # imported first, so a missing install fails before download
        import torch
        from transformers import Wav2Vec2ForCTC
        from transformers.utils import logging as transformers_logging
    folder = ensure_aligner(default_home())
    with quiet_library_warnings():
        # Its load report reads like an error.
        transformers_logging.set_verbosity_error()  # type: ignore[no-untyped-call,unused-ignore]
        model = Wav2Vec2ForCTC.from_pretrained(folder)
    vocab: dict[str, int] = json.loads((folder / "vocab.json").read_text(encoding="utf-8"))
    model.eval()  # type: ignore[no-untyped-call,unused-ignore]

    def emissions(samples: np.ndarray) -> np.ndarray:
        # The model expects each clip scaled to zero mean and unit variance.
        x = (samples - samples.mean()) / (samples.std() + 1e-7)
        with torch.inference_mode():
            logits = model(torch.from_numpy(x.astype(np.float32))[None]).logits[0]
            out: np.ndarray = torch.log_softmax(logits, dim=-1).numpy()
        return out

    return emissions, vocab


def words_from_tokens(tokens: Sequence[Any]) -> list[Word]:
    """Misaki's tokens (text, phonemes, whitespace after) as words, punctuation left out."""
    out: list[Word] = []
    for t, after in zip(tokens, [*tokens[1:], None], strict=True):
        if not any(ch.isalnum() for ch in t.text):
            continue
        joined = after is not None and not t.whitespace and any(ch.isalnum() for ch in after.text)
        out.append(Word(t.text, t.phonemes or "", joined))
    return out


def _load_g2p() -> G2P:  # pragma: no cover - needs Kokoro
    with quiet_library_warnings():
        from kokoro import KPipeline

    from imageskin.kokoro_engine import LANG_CODE, REPO_ID

    with quiet_library_warnings():
        pipeline = KPipeline(lang_code=LANG_CODE, repo_id=REPO_ID, model=False)

    def g2p(text: str) -> list[Word]:
        _, tokens = pipeline.g2p(text)
        return words_from_tokens(tokens)

    return g2p
