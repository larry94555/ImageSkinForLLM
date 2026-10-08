"""R25a voice cloning test: make the sample script and a few chat replies in the person's voice.

    python experiments/voice/run_test.py --sample voice-sample.wav [--photo me.jpg] [-o voice-test]

Writes, for each line, Kokoro's ready-made voice and each candidate tool's version, the time each
tool takes, how similar each clip sounds to the person's recording, and index.html to listen to
them side by side. With --photo, the Kokoro and conversion clips are also rendered on the
photoreal video (the photo is prepared first if needed, about 17 minutes on a 4-core CPU).
"""

import argparse
import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

import numpy as np
from page import Clip, Line, build_page
from voice_tools import (
    SAMPLE_RATE,
    converted,
    float_to_pcm16,
    reference_clip,
)

from imageskin.sample import SAMPLE_SCRIPT
from imageskin.video import read_pcm16
from imageskin.voice import Speech, write_speech

logger = logging.getLogger("voice_test")

CHAT_REPLIES = [
    "Good morning! It's nice to see you again.",
    "That's a great question. The short answer is yes, but it depends on the weather.",
    "I'm not sure I follow. Could you tell me a little more about what you mean?",
]
LINES = [SAMPLE_SCRIPT, *CHAT_REPLIES]
KOKORO, CONVERSION, CLONE = "Kokoro", "Conversion", "Clone"
VOICES = {
    KOKORO: "ready-made voice, today's app",
    CONVERSION: "Kokoro converted to your voice (Chatterbox VC); American accent",
    CLONE: "your voice cloned from the sample (Chatterbox Turbo); keeps your accent",
}

Speak = Callable[[str], Speech]
Convert = Callable[[np.ndarray], np.ndarray]
Clone = Callable[[str], np.ndarray]
Similarity = Callable[[Path], float]
Render = Callable[[Path, Path], None]


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def write_wav(samples: np.ndarray, path: Path) -> float:
    """Write float samples as a WAV with no timings; return the length in seconds."""
    write_speech(Speech(float_to_pcm16(samples), SAMPLE_RATE, []), path, path.with_suffix(".json"))
    return len(samples) / SAMPLE_RATE


def run(
    lines: Sequence[str],
    out: Path,
    speak: Speak,
    convert: Convert | None = None,
    clone: Clone | None = None,
    similarity: Similarity | None = None,
    render: Render | None = None,
) -> list[Line]:
    """Make every line in every voice under out; return what was made, with timings."""
    results = []
    for i, text in enumerate(lines, 1):
        line = Line(text)
        start = time.perf_counter()
        speech = speak(text)
        kokoro_ms = _ms(start)
        wav = out / f"line{i}_kokoro.wav"
        seconds = write_speech(speech, wav, wav.with_suffix(".json"))
        line.clips[KOKORO] = Clip(wav.name, round(seconds, 2), kokoro_ms)

        if convert is not None:
            start = time.perf_counter()
            voiced = converted(speech, convert)
            ms = _ms(start)  # on top of Kokoro's time, every reply pays it
            wav = out / f"line{i}_conversion.wav"
            seconds = write_speech(voiced, wav, wav.with_suffix(".json"))
            line.clips[CONVERSION] = Clip(wav.name, round(seconds, 2), ms)

        if clone is not None:
            start = time.perf_counter()
            samples = clone(text)
            ms = _ms(start)
            wav = out / f"line{i}_clone.wav"
            line.clips[CLONE] = Clip(wav.name, round(write_wav(samples, wav), 2), ms)

        for name, clip in line.clips.items():
            path = out / clip.wav
            if similarity is not None:
                clip.similarity = round(similarity(path), 3)
            if render is not None and name != CLONE:  # the clone has no sound timings for the mouth
                video = path.with_suffix(".mp4")
                render(path, video)
                clip.video = video.name
            logger.info(
                "Made line",
                extra={
                    "line": i,
                    "voice": name,
                    "speech_s": clip.speech_s,
                    "duration_ms": clip.added_ms,
                    "seconds_per_speech_second": round(clip.added_ms / 1000 / clip.speech_s, 2)
                    if clip.speech_s
                    else None,
                    "similarity": clip.similarity,
                },
            )
        results.append(line)
    return results


def write_results(out: Path, recording: str, lines: list[Line]) -> Path:
    voices = {name: d for name, d in VOICES.items() if any(name in ln.clips for ln in lines)}
    (out / "results.json").write_text(
        json.dumps([asdict(line) for line in lines], indent=2) + "\n", encoding="utf-8"
    )
    page = out / "index.html"
    page.write_text(build_page(recording, voices, lines), encoding="utf-8")
    return page


def ecapa_similarity(recording: Path) -> Similarity:  # pragma: no cover - needs the model
    """Cosine similarity of speaker embeddings (SpeechBrain ECAPA, Apache 2.0) to the recording."""
    import librosa
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

    model = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb")

    def embed(path: Path) -> torch.Tensor:
        samples, _ = librosa.load(str(path), sr=16000)
        return model.encode_batch(torch.tensor(samples)[None]).squeeze()

    ref = embed(recording)
    return lambda path: float(torch.nn.functional.cosine_similarity(ref, embed(path), dim=0))


def photoreal_render(photo: Path) -> Render:  # pragma: no cover - needs the models
    from imageskin.photoreal import PhotorealEngine

    engine = PhotorealEngine()
    lib = engine.prepare(photo)
    return lambda wav, video: engine.render(lib, wav, video) and None


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - runs the real models
    from voice_tools import ChatterboxCloner, ChatterboxConverter

    from imageskin.kokoro_engine import KokoroEngine
    from imageskin.logging_setup import setup_logging

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=Path, required=True, help="voice-sample.wav (24 kHz)")
    parser.add_argument("--photo", type=Path, help="also render the clips on this photo")
    parser.add_argument("--kokoro-voice", default="am_michael", help="voice to convert from")
    parser.add_argument("-o", "--output", type=Path, default=Path("voice-test"))
    args = parser.parse_args(argv)
    setup_logging()
    args.output.mkdir(parents=True, exist_ok=True)

    samples, rate = read_pcm16(args.sample)
    if rate != SAMPLE_RATE:
        logger.error("Voice sample must be 24 kHz; make it with imageskin voice-sample")
        return 1
    reference = reference_clip(np.array(samples, dtype=np.float32) / 32768)
    recording = args.output / "your_recording.wav"
    write_wav(reference, recording)

    start = time.perf_counter()
    cloner = ChatterboxCloner()
    cloner.set_voice(reference)
    converter = ChatterboxConverter(cloner.tts.s3gen)
    converter.set_voice(reference)
    kokoro = KokoroEngine()
    render = photoreal_render(args.photo) if args.photo else None
    logger.info("Loaded voice tools", extra={"duration_ms": _ms(start)})

    lines = run(
        LINES,
        args.output,
        lambda text: kokoro.speak(args.kokoro_voice, text),
        converter,
        cloner,
        ecapa_similarity(recording),
        render,
    )
    page = write_results(args.output, recording.name, lines)
    print(f"Wrote {page.resolve()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
