"""R24e: a page to hear every default person's voice, with each voice's measured pitch.

    python tools/default_people/hear_voices.py [-o default-people/voices]

It says LINE in each voice the people use (`VOICE_CHOICES` in `imageskin.default_people`), once
for each, as a small MP3, measures the voice's median pitch, and writes voices.json and
index.html: every one of the 68 faces, in the avatar page's order for each look, beside its
American and British voice. Kokoro (about 330 MB) is downloaded on first use; ffmpeg makes the
MP3s. The faces are the app's thumbnails, copied next to the page.
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from html import escape
from pathlib import Path

import numpy as np

from imageskin.default_people import (
    ACCENT_LANGS,
    REALISMS,
    VOICE_CHOICES,
    age,
    page_order,
    people,
    voice_label,
    voice_of,
)

logger = logging.getLogger("hear_voices")

LINE = "Hello, it's good to meet you. Ask me anything you like about the course."
FACES = Path(__file__).resolve().parents[2] / "web" / "public" / "faces"
# A frame counts as voiced when its loudness and its self-likeness at the pitch's period are
# at least these; the lowest and highest pitches looked for, in Hz.
MIN_LOUDNESS = 0.02
MIN_LIKENESS = 0.5
LOWEST, HIGHEST = 60.0, 400.0

Speak = Callable[[str, str], tuple[np.ndarray, int]]  # language code, voice: samples, rate


def median_pitch(samples: np.ndarray, rate: int, frame_s: float = 0.04) -> float:
    """The median pitch of the voiced frames, in Hz, by autocorrelation; 0 when none is voiced."""
    n, hop = int(frame_s * rate), int(frame_s * rate / 4)
    shortest, longest = int(rate / HIGHEST), int(rate / LOWEST)
    found = []
    for start in range(0, len(samples) - n, hop):
        frame = samples[start : start + n] - samples[start : start + n].mean()
        if np.sqrt(np.mean(frame * frame)) < MIN_LOUDNESS:
            continue
        likeness = np.correlate(frame, frame, "full")[n - 1 :]
        period = shortest + int(np.argmax(likeness[shortest:longest]))
        if likeness[period] / likeness[0] >= MIN_LIKENESS:
            found.append(rate / period)
    return round(float(np.median(found)), 1) if found else 0.0


def every_voice() -> list[tuple[str, str]]:
    """Each voice the people use, with its language code."""
    return [(ACCENT_LANGS[a], v) for (_, a, _), vs in VOICE_CHOICES.items() for v in vs]


def file_name(voice: str) -> str:
    return voice.replace(",", "+") + ".mp3"


def to_mp3(samples: np.ndarray, rate: int, output: Path) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1"]
        + ["-i", "-", "-b:a", "48k", str(output)],
        input=pcm,
        check=True,
    )


def say_each(speak: Speak, out: Path, write: Callable[..., None] = to_mp3) -> dict[str, float]:
    """Say LINE in every voice, written as <voice>.mp3; each voice's median pitch."""
    pitches: dict[str, float] = {}
    for lang, voice in every_voice():
        start = time.perf_counter()
        try:
            samples, rate = speak(lang, voice)
            write(samples, rate, out / file_name(voice))
        except Exception as e:
            logger.error("Could not say the line", extra={"voice": voice, "error": str(e)})
            raise
        pitches[voice] = median_pitch(samples, rate)
        logger.info(
            "Voice said",
            extra={
                "voice": voice,
                "pitch_hz": pitches[voice],
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
    return pitches


def build_page(pitches: dict[str, float]) -> str:
    """The listening page: each look's faces in the avatar page's order, with both voices."""
    sections = []
    for realism in REALISMS:
        rows = []
        for p in page_order([p for p in people() if p.realism == realism]):
            cells = []
            for accent in ACCENT_LANGS:
                voice = voice_of(p.name, accent)[1]
                cells.append(
                    f'<td><audio controls preload="none" src="{escape(file_name(voice))}"></audio>'
                    f"<br><b>{escape(voice_label(voice))}</b> · <code>{escape(voice)}</code>"
                    f" · {pitches.get(voice, 0):.0f} Hz</td>"
                )
            rows.append(
                f'<tr><td><img src="faces/{p.name}.jpg" width="96" height="96" alt=""></td>'
                f"<td><code>{p.name}</code><br>{escape(age(p))}</td>{''.join(cells)}</tr>"
            )
        sections.append(
            f"<h2>{realism.title()}</h2><table><tr><th></th><th>Person</th>"
            f"<th>American</th><th>British</th></tr>{''.join(rows)}</table>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Default people's voices</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font: 15px/1.4 system-ui, sans-serif; margin: 16px; }}
table {{ border-collapse: collapse; }}
td, th {{ padding: 6px 10px; border-bottom: 1px solid #8884; text-align: left;
  vertical-align: middle; }}
img {{ border-radius: 8px; }}
audio {{ height: 32px; }}
</style></head><body>
<h1>Default people's voices (R24e)</h1>
<p>Each face in the order the avatar page shows it, with the line "{escape(LINE)}" in its
American and British voice, and the voice's median pitch. Teenagers have the accent's younger
voices and the people in their sixties and seventies its older ones.</p>
{"".join(sections)}
</body></html>
"""


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - runs the real model
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # see experiments/voice/run_test.py
    from kokoro import KPipeline

    from imageskin.logging_setup import setup_logging

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", type=Path, default=Path("default-people/voices"))
    args = parser.parse_args(argv)
    setup_logging()
    out: Path = args.output
    out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    pipelines = {lang: KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M") for lang in "ab"}

    def speak(lang: str, voice: str) -> tuple[np.ndarray, int]:
        parts = [r.audio.numpy() for r in pipelines[lang](LINE, voice=voice) if r.audio is not None]
        return np.concatenate(parts), 24000

    pitches = say_each(speak, out)
    shutil.copytree(FACES, out / "faces", dirs_exist_ok=True)
    (out / "voices.json").write_text(json.dumps(pitches, indent=2), encoding="utf-8")
    (out / "index.html").write_text(build_page(pitches), encoding="utf-8")
    logger.info(
        "Listening page written",
        extra={
            "page": str(out / "index.html"),
            "voices": len(pitches),
            "duration_s": round(time.perf_counter() - start, 1),
        },
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
