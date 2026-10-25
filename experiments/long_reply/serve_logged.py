"""R129: `imageskin serve`, noting each reply clip's words and speech. An experiment, not part of
the app.

    python experiments/long_reply/serve_logged.py CLIPS_JSONL [--config FILE]

The app runs exactly as `imageskin [--config FILE] serve` runs it, except that each reply clip's
voice step is wrapped: once the clip is spoken, a line is added to CLIPS_JSONL with its folder,
the clip's number, the text the LLM gave for it and the text spoken, its words, how long the
speech is and how much silence it starts and ends with (measured as R127 measures when the voice
is heard). The API doesn't give a clip's text, and the speech is removed once its video is made,
so long_reply.py reads them from here.
"""

import json
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

WINDOW_S = 0.005  # loudness is measured in windows this long (as in R127)
HEARD_DB = -35.0  # quieter than this below the clip's loud level is silence (as in R127)


def silences(path: Path) -> tuple[float, float, float]:
    """The WAV's length, and the silence before the voice is first heard and after it is last
    heard, in seconds."""
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64)
    seconds = len(samples) / rate
    size = max(1, int(rate * WINDOW_S))
    n = len(samples) // size
    if n == 0:
        return seconds, seconds, 0.0
    rms = np.sqrt(np.mean(samples[: n * size].reshape(n, size) ** 2, axis=1))
    loud = float(np.percentile(rms, 95))
    if loud <= 0:
        return seconds, seconds, 0.0
    heard = np.flatnonzero(20 * np.log10(np.maximum(rms, 1e-9) / loud) > HEARD_DB)
    if len(heard) == 0:
        return seconds, seconds, 0.0
    lead = float(heard[0] * WINDOW_S)
    trail = max(0.0, seconds - float((heard[-1] + 1) * WINDOW_S))
    return seconds, lead, trail


def clip_row(folder: str, n: int, sentence: str, text: str, wav: Path) -> dict[str, Any]:
    seconds, lead, trail = silences(wav)
    return {
        "reply": folder.removeprefix("clips-"),
        "n": n,
        "sentence": sentence,
        "text": text,
        "words": len(text.split()),
        "wav_s": round(seconds, 3),
        "lead_silence_s": round(lead, 3),
        "trail_silence_s": round(trail, 3),
        "noted_at": time.time(),
    }


def note_clips(out: Path) -> None:
    """Wrap SentenceClips._speak so every clip spoken adds its line to `out`."""
    from imageskin import reply_video
    from imageskin.speech_text import spoken_text

    speak = reply_video.SentenceClips._speak
    lock = threading.Lock()

    def noted(
        self: reply_video.SentenceClips, n: int, sentence: str, sentence_at: float
    ) -> reply_video.Spoken | None:
        spoken = speak(self, n, sentence, sentence_at)
        if spoken is not None:
            row = clip_row(self.folder.name, n, sentence, spoken_text(sentence), spoken.wav)
            with lock, out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        return spoken

    reply_video.SentenceClips._speak = noted  # type: ignore[method-assign]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    note_clips(out)
    from imageskin import cli

    return cli.main([*sys.argv[2:], "serve"])


if __name__ == "__main__":
    sys.exit(main())
