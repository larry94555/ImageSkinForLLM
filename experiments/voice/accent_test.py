"""R26a accent test: the person's own voice with another accent (American, British, or a donor's).

    python experiments/voice/accent_test.py --sample voice-sample.wav \
        [--donor Slavic=donor.wav ...] [-o accent-test]

Voice conversion keeps the person's timbre and takes the accent from whatever voice speaks first:
- American and British: one of Kokoro's ready-made voices speaks the line. The voice is picked to
  suit the person: every Kokoro voice of that accent says a probe line, each is converted to their
  voice, and the closest after conversion wins.
- A donor accent (for example Russian-English): Chatterbox Turbo speaks the line in a voice cloned
  from a recording of someone with that accent, then it is converted to the person's voice.
The person's own clone (their own accent, as the app speaks today) is made too, for comparison.
Writes each clip, the time it took, how much it sounds like the person, and index.html. A changed
accent's time is the base voice's plus the conversion's, since every reply pays both.
"""

import argparse
import logging
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
from page import Clip, Line, build_page
from run_test import CHAT_REPLIES, write_wav
from voice_tools import reference_clip

from imageskin.accent import KOKORO_VOICES, PROBE, convert_fitted

logger = logging.getLogger("accent_test")

# Kokoro's English voices by accent (lang code, voices), the app's lists (R26).
KOKORO_ACCENTS: dict[str, tuple[str, list[str]]] = {
    "American": KOKORO_VOICES["american"],
    "British": KOKORO_VOICES["british"],
}
CLONE = "Your accent"
# The accent classifier and the exact weights the R26a results were heard with.
ACCENT_MODEL = "Jzuluaga/accent-id-commonaccent_ecapa"
ACCENT_MODEL_REVISION = "14bebf44b7e7a34204d0acc2c897935945fb5c51"

Audio = Callable[[str], np.ndarray]  # text in, 24 kHz float samples out
Convert = Callable[[np.ndarray], np.ndarray]
Similarity = Callable[[Path], float]


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def pick_base(
    voices: Sequence[str],
    speak: Callable[[str, str], np.ndarray],
    convert: Convert,
    similarity: Similarity,
    out: Path,
) -> tuple[str, list[dict[str, object]]]:
    """The base voice that sounds most like the person once converted, with every score. Every
    voice is converted: conversion changes which voice is closest, so a ranking before it would
    not do."""
    start = time.perf_counter()
    out.mkdir(parents=True, exist_ok=True)
    scores: list[dict[str, object]] = []
    probes: dict[str, np.ndarray] = {}
    for voice in voices:
        probes[voice] = speak(voice, PROBE)
        wav = out / f"{voice}.wav"
        write_wav(probes[voice], wav)
        converted = out / f"{voice}_converted.wav"
        write_wav(convert_fitted(probes[voice], convert), converted)
        scores.append(
            {
                "voice": voice,
                "base": round(similarity(wav), 3),
                "converted": round(similarity(converted), 3),
            }
        )
    scores.sort(key=lambda s: -float(s["converted"]))  # type: ignore[arg-type]
    best = scores[0]
    logger.info(
        "Picked base voice",
        extra={"voice": best["voice"], "scores": scores[:3], "duration_ms": _ms(start)},
    )
    return str(best["voice"]), scores


def run(
    lines: Sequence[str],
    out: Path,
    clone: Audio,
    bases: dict[str, Audio],
    convert: Convert,
    similarity: Similarity | None = None,
    heard_as: Callable[[Path], str] | None = None,
) -> list[Line]:
    """Each line in the person's own accent, then each accent's base voice and its conversion."""
    results = []
    for i, text in enumerate(lines, 1):
        line = Line(text)
        start = time.perf_counter()
        line.clips[CLONE] = _clip(clone(text), out / f"line{i}_clone.wav", _ms(start))
        for accent, speak in bases.items():
            slug = accent.lower().replace(" ", "-")
            start = time.perf_counter()
            base = speak(text)
            line.clips[f"{accent} base"] = _clip(base, out / f"line{i}_{slug}_base.wav", _ms(start))
            start = time.perf_counter()
            voiced = convert_fitted(base, convert)
            # Every reply pays for both the base voice and the conversion.
            ms = round(line.clips[f"{accent} base"].added_ms + _ms(start), 1)
            line.clips[accent] = _clip(voiced, out / f"line{i}_{slug}.wav", ms)
        for name, clip in line.clips.items():
            if similarity is not None:
                clip.similarity = round(similarity(out / clip.wav), 3)
            if heard_as is not None:
                clip.heard_as = heard_as(out / clip.wav)
            logger.info(
                "Made line",
                extra={
                    "line": i,
                    "voice": name,
                    "speech_s": clip.speech_s,
                    "duration_ms": clip.added_ms,
                    "similarity": clip.similarity,
                    "heard_as": clip.heard_as,
                },
            )
        results.append(line)
    return results


def _clip(samples: np.ndarray, wav: Path, ms: float) -> Clip:
    return Clip(wav.name, round(write_wav(samples, wav), 2), ms)


def voice_descriptions(bases: dict[str, str]) -> dict[str, str]:
    """Column headings: the person's clone, then each accent's base voice and conversion."""
    columns = {CLONE: "your clone (Chatterbox Turbo), as the app speaks today"}
    for accent, base in bases.items():
        columns[f"{accent} base"] = f"{base}: where the accent comes from"
        columns[accent] = f"{base} converted to your voice (time: speaking and converting)"
    return columns


def accent_classifier() -> Callable[[Path], str]:  # pragma: no cover - needs the model
    """The English accent a classifier hears (CommonAccent ECAPA, MIT) and its score."""
    import librosa
    import torch
    from huggingface_hub import snapshot_download
    from speechbrain.inference.classifiers import EncoderClassifier

    # Downloaded at the pinned revision first: SpeechBrain's loader takes no revision.
    folder = snapshot_download(ACCENT_MODEL, revision=ACCENT_MODEL_REVISION)
    model = EncoderClassifier.from_hparams(source=folder)

    def heard(path: Path) -> str:
        samples, _ = librosa.load(str(path), sr=16000)
        out, _, index, labels = model.classify_batch(torch.tensor(samples)[None])
        return f"{labels[0]} {float(out[0, int(index[0])]):.2f}"  # a score per accent, not a share

    return heard


def parse_donors(values: Sequence[str]) -> dict[str, Path]:
    """--donor NAME=recording.wav, repeatable."""
    donors = {}
    for value in values:
        name, sep, path = value.partition("=")
        if not sep or not name or not path:
            raise ValueError(f"--donor wants NAME=recording.wav, not {value!r}")
        donors[name] = Path(path)
    return donors


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - runs the real models
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from run_test import ecapa_similarity
    from voice_tools import ChatterboxCloner, ChatterboxConverter, pcm16_to_float

    from imageskin.chatterbox_engine import read_voice_sample
    from imageskin.kokoro_engine import REPO_ID, KokoroEngine
    from imageskin.logging_setup import setup_logging

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=Path, required=True, help="voice-sample.wav (24 kHz)")
    parser.add_argument("--donor", action="append", default=[], help="NAME=accent-recording.wav")
    parser.add_argument("-o", "--output", type=Path, default=Path("accent-test"))
    args = parser.parse_args(argv)
    setup_logging()
    args.output.mkdir(parents=True, exist_ok=True)
    donors = parse_donors(args.donor)

    reference = reference_clip(read_voice_sample(args.sample))
    recording = args.output / "your_recording.wav"
    write_wav(reference, recording)
    similarity = ecapa_similarity(recording)

    start = time.perf_counter()
    cloner = ChatterboxCloner()
    converter = ChatterboxConverter(cloner.tts.s3gen)
    converter.set_voice(reference)
    logger.info("Loaded voice tools", extra={"duration_ms": _ms(start)})

    current: list[object] = [None]

    def clone_as(voice: np.ndarray) -> Audio:
        def speak(text: str) -> np.ndarray:
            if current[0] is not voice:  # the cloner holds one voice at a time
                cloner.set_voice(voice)
                current[0] = voice
            return cloner(text)

        return speak

    bases: dict[str, Audio] = {}
    names: dict[str, str] = {}
    for accent, (lang, voices) in KOKORO_ACCENTS.items():
        from kokoro import KPipeline

        pipeline = KPipeline(lang_code=lang, repo_id=REPO_ID, device="cpu")
        kokoro = KokoroEngine(lambda p=pipeline: p)

        def say(voice: str, text: str, k: KokoroEngine = kokoro) -> np.ndarray:
            return pcm16_to_float(k.speak(voice, text).pcm)

        best, _ = pick_base(voices, say, converter, similarity, args.output / "probes" / accent)
        bases[accent] = lambda text, v=best, s=say: s(v, text)
        names[accent] = f"Kokoro {best}"
    for accent, path in donors.items():
        bases[accent] = clone_as(reference_clip(read_voice_sample(path)))
        names[accent] = f"{accent} speaker ({path.name}), cloned"

    heard = accent_classifier()
    logger.info("Your recording", extra={"heard_as": heard(recording)})
    lines = run(CHAT_REPLIES, args.output, clone_as(reference), bases, converter, similarity, heard)
    page = args.output / "index.html"
    page.write_text(
        build_page(recording.name, voice_descriptions(names), lines, "Accent test"),
        encoding="utf-8",
    )
    print(f"Wrote {page.resolve()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
