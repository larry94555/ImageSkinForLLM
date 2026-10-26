"""R129: `imageskin serve`, noting each reply clip's words and speech. An experiment, not part of
the app.

    python experiments/long_reply/serve_logged.py CLIPS_JSONL [--config FILE]

The app runs exactly as `imageskin [--config FILE] serve` runs it, except that each reply clip's
voice step is wrapped: once the clip is spoken, a line is added to CLIPS_JSONL with its folder,
the clip's number, the text the LLM gave for it and the text spoken, its words, how long the
speech is and how much silence it starts and ends with (where the voice is heard measured by
the app's `mouth_sync.heard`, as R127 measured it). The API doesn't give a clip's text, and the
speech is removed once its video is made, so long_reply.py reads them from here.
"""

import json
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

from imageskin.mouth_sync import WINDOW_S, heard


def silences(path: Path) -> tuple[float, float, float]:
    """The WAV's length, and the silence before the voice is first heard and after it is last
    heard, in seconds, with the app's own measure of where the voice is heard (R127, R128's
    `mouth_sync.heard`)."""
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2") / 32768.0
    seconds = len(samples) / rate
    windows = np.flatnonzero(heard(samples, rate))
    if len(windows) == 0:
        return seconds, seconds, 0.0
    lead = float(windows[0] * WINDOW_S)
    trail = max(0.0, seconds - float((windows[-1] + 1) * WINDOW_S))
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
