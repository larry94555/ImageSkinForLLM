"""How soon the first word of "What can you talk about?" is spoken, whole or cut into clips (R100).

The answer is made without the LLM, so nothing else uses the cores: Kokoro speaks on all of them,
as the app lets it once no LLM request is under way. Each clip is spoken in turn, as the reply's
clips are, and played on paper once spoken and the one before has ended; the video step, which
follows each clip's voice in the app, is left out, so the times are the voice's alone.

    python experiments/speed/made_reply_clips.py [threads]
"""

import sys
import time

import torch

from imageskin.kokoro_engine import kokoro_for
from imageskin.sentences import clips
from imageskin.topics import topics_reply

# Topics like the sample PDF's (prime numbers and the zeta function); R96a kept no reply text.
TOPICS = [
    "Prime Number Definition",
    "The Fundamental Theorem of Arithmetic",
    "The Sieve of Eratosthenes",
    "The Infinitude of Primes",
    "The Prime Number Theorem",
    "The Riemann Zeta Function",
    "Euler's Product Formula",
    "The Riemann Hypothesis",
    "Twin Primes and Open Problems",
]


def timeline(engine: object, pieces: list[str]) -> list[tuple[str, float, float, float]]:
    """Each piece with when it was spoken, how long it plays, and the gap heard before it."""
    rows = []
    start = time.perf_counter()
    plays_until = 0.0
    for piece in pieces:
        speech = engine.speak("af_heart", piece)  # type: ignore[attr-defined]
        spoken = time.perf_counter() - start
        seconds = len(speech.pcm) / 2 / speech.sample_rate
        plays = max(spoken, plays_until)
        gap = plays - plays_until if rows else 0.0
        plays_until = plays + seconds
        rows.append((piece, spoken, seconds, gap))
    return rows


def main() -> None:
    threads = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    torch.set_num_threads(threads)
    engine = kokoro_for("a")
    engine.speak("af_heart", "Hello.")  # load and warm up
    sentences = topics_reply(TOPICS, content_only=False, choose=lambda t: t[2])
    print(f"Kokoro on {threads} threads, the voice alone\n")
    runs = (("Before: whole sentences", sentences), ("After: clips", clips(sentences)))
    for name, pieces in runs:
        rows = timeline(engine, pieces)
        print(f"## {name}\n")
        print("| Clip | Text | Spoken at | Plays for | Gap before |")
        print("|---|---|---|---|---|")
        for i, (piece, spoken, seconds, gap) in enumerate(rows, 1):
            print(f"| {i} | {piece} | {spoken:.1f} s | {seconds:.1f} s | {gap:.1f} s |")
        gaps = sum(r[3] for r in rows)
        print(f"\nFirst word heard after {rows[0][1]:.1f} s; gaps {gaps:.1f} s\n")


if __name__ == "__main__":
    main()
