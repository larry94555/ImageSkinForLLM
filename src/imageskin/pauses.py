"""The pause at each join between a reply's clips, the length the text calls for (roadmap R130).

R129 (experiments/long_reply/) found Kokoro starting every clip with about 315 ms of silence and
ending it with about 470 ms, so about 0.8 s was heard at every join, even mid-sentence. Each
clip's speech is cut down to LEAD_S before the voice, so the mouth's rest frame still comes
first (R127), and to a pause after it set by how its text ends: longest at a full stop, list
item or heading, short at a comma, none mid-clause. The timings JSON beside the WAV is moved
with it, so the mouth (R128) follows the speech.
"""

import json
import logging
import re
import wave
from pathlib import Path

import numpy as np

from imageskin.mouth_sync import WINDOW_S, heard

logger = logging.getLogger(__name__)

LEAD_S = 0.05  # silence kept before the voice at a clip's start
# Silence after the voice at a clip's end, by how its text ends. With the next clip's LEAD_S and
# the browser's switch between clips (about 90 ms, R127), the pause heard is about 0.45 s at a
# full stop and 0.25 s at a comma.
PAUSE_S = {"sentence": 0.3, "clause": 0.12, "none": 0.0}

_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]*_]*$")
_CLAUSE_END = re.compile(r"(?:[,;:]|\s[-—–]|[—–])[\"'”’)\]*_]*$")


def end_kind(text: str) -> str:
    """How the clip's text ends: `sentence` (a full stop, or a line of its own, as a list item
    or heading), `clause` (a comma, semicolon, colon or dash) or `none` (mid-clause)."""
    text = text.rstrip()
    if _SENTENCE_END.search(text) or re.match(r"[ \t]*(?:\d+[.)]|[-*+]|#{1,6})[ \t]", text):
        return "sentence"
    return "clause" if _CLAUSE_END.search(text) else "none"


def _shifted(items: list[dict[str, object]], by: float, end: float) -> list[dict[str, object]]:
    out = []
    for item in items:
        start = min(end, max(0.0, float(item["start"]) - by))  # type: ignore[arg-type]
        stop = min(end, max(0.0, float(item["end"]) - by))  # type: ignore[arg-type]
        if stop > start:
            out.append({**item, "start": round(start, 3), "end": round(stop, 3)})
    return out


def fit_pause(wav: Path, text: str) -> tuple[float, float] | None:
    """Cut the speech in `wav` (and its timings JSON beside it) to LEAD_S of silence before the
    voice and the pause `text`'s end calls for after it, padding with silence if there is
    less. Returns the seconds removed at the start and at the end (negative: added), or None
    when there is nothing to fit: no timings beside it, or no voice heard."""
    timings = wav.with_suffix(".json")
    if not timings.is_file():
        return None
    with wave.open(str(wav), "rb") as w:
        params = w.getparams()
        pcm = w.readframes(w.getnframes())
    if params.sampwidth != 2 or params.nchannels != 1:
        return None
    rate = params.framerate
    samples = np.frombuffer(pcm, dtype="<i2")
    loud = heard(samples.astype(np.float64), rate)
    if not loud.any():
        return None
    voice = np.flatnonzero(loud)
    first = max(0, round((voice[0] * WINDOW_S - LEAD_S) * rate))
    voice_end = round((voice[-1] + 1) * WINDOW_S * rate)
    last = voice_end + round(PAUSE_S[end_kind(text)] * rate)
    kept = samples[first : min(last, len(samples))]
    if last > len(samples):  # less silence than the pause: pad it
        kept = np.concatenate([kept, np.zeros(last - len(samples), dtype="<i2")])
    with wave.open(str(wav), "wb") as w:
        w.setparams(params)
        w.writeframes(kept.tobytes())

    cut = first / rate
    seconds = len(kept) / rate
    data = json.loads(timings.read_text(encoding="utf-8"))
    data["seconds"] = round(seconds, 3)
    for key in ("words", "sounds", "shapes"):
        data[key] = _shifted(data.get(key, []), cut, seconds)
    timings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return round(cut, 3), round((len(samples) - last) / rate, 3)
