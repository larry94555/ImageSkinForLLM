"""R127: where the mouth runs ahead of the voice. An experiment, not part of the app.

    python experiments/mouth_sync/mouth_lead.py [--voice af_heart] [--lang a]
        [--clone WAV [--pocket]] [-o mouth-lead] [--media FOLDER]

For each clip the app makes (three reply sentences, "Goodbye.", "Welcome back." and the sample
video's script) it speaks the text with the app's own voice engine, writes the WAV and timings
JSON as the app does (`write_speech`), and works out the mouth's weights per frame as the
photoreal engine does (`mouth_weights` on the JSON's shapes). Then, at the start of the clip and
at each word that starts after a pause:

- the voice is heard at the first 5 ms window no more than HEARD_DB below the clip's loud level
  (the silence level `expression.loudness` uses);
- the mouth opens on the first frame after the pause whose openness (`expression.openness`, 0
  closed to 1 the widest shape) reaches OPEN_AT, at the time that frame starts to show;
- the lead (voice heard minus mouth opens) is split into the part from the sound timings (voice
  heard minus the first sound's start in the JSON) and the part from turning them into frames
  (the first sound's start minus the mouth opening: `frame_weights`' blend and lead, and the
  frame it lands in).

Each clip is then written as an MP4 with `write_mp4`, whole (the sample and the fixed lines) and
progressive (reply clips, R22d), and its audio decoded back and lined up against the WAV, which
gives how much later the sound is in the file than in the WAV. For Kokoro, the forced aligner the
cloned voice uses (R25) is run on Kokoro's audio, and its word starts compared with Kokoro's own.

--media writes the browser test's MP4s (a white frame and a beep at the same moments, whole and
progressive) to FOLDER, for browser_sync.js. The tables go to <out>/mouth-lead-<voice>.md and
.json.
"""

import argparse
import json
import logging
import math
import subprocess
import tempfile
import time
import wave
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from imageskin.expression import openness
from imageskin.mouth_sync import mouth_weights
from imageskin.photoreal import read_shapes
from imageskin.sample import SAMPLE_SCRIPT
from imageskin.video import FPS, find_ffmpeg, write_mp4
from imageskin.visemes import SoundTiming
from imageskin.voice import Speech, WordTiming, write_speech

logger = logging.getLogger("mouth_lead")

WINDOW_S = 0.005  # loudness is measured in windows this long
HEARD_DB = -35.0  # quieter than this below the clip's loud level is silence
PAUSE_S = 0.15  # silence at least this long before a word means the mouth may close in it
OPEN_AT = 0.1  # openness at which the mouth counts as open (a tenth of the widest shape)
LIMIT_MS = 80  # the most the mouth may lead (R128's default)
SEARCH_MS = 200  # how far either way the MP4's audio is looked for against the WAV

CLIPS: tuple[tuple[str, str], ...] = (
    ("reply 1", "Hello! I'm glad you asked."),
    ("reply 2", "Mount Everest is the tallest mountain in the world, at about 8,849 meters."),
    ("reply 3", "Once upon a time, a cat named Milo was afraid of water."),
    ("goodbye", "Goodbye."),
    ("welcome back", "Welcome back."),
    ("sample", SAMPLE_SCRIPT),
)

Samples = NDArray[np.float64]


@dataclass(frozen=True)
class Onset:
    """The voice starting after a pause, and the mouth opening for it; times in seconds."""

    word: str
    heard: float  # the voice is first heard
    sound: float | None  # the first sound's start in the timings
    opens: float | None  # the frame where the mouth opens starts to show; None if it never
    # closed in the pause before, or never opens

    @property
    def lead_ms(self) -> float | None:
        return None if self.opens is None else round((self.heard - self.opens) * 1000)

    @property
    def timings_ms(self) -> float | None:
        """Of the lead, how much the sound timings put the sound before it is heard."""
        return None if self.sound is None else round((self.heard - self.sound) * 1000)

    @property
    def frames_ms(self) -> float | None:
        """Of the lead, how much the frames open the mouth before the sound's start."""
        if self.sound is None or self.opens is None:
            return None
        return round((self.sound - self.opens) * 1000)


@dataclass
class ClipResult:
    name: str
    text: str
    seconds: float
    onsets: list[Onset]
    whole_mp4_ms: float | None = None  # the sound's delay in the MP4 against the WAV
    progressive_mp4_ms: float | None = None
    aligner_ms: list[tuple[str, float]] = field(default_factory=list)  # aligner minus Kokoro

    @property
    def start(self) -> Onset | None:
        return self.onsets[0] if self.onsets else None


def to_float(pcm: bytes) -> Samples:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32768.0


def level_db(samples: Samples, rate: int) -> NDArray[np.float64]:
    """Loudness of each WINDOW_S window in dB below the clip's loud level (its 98th percentile,
    so a few peaks don't set it)."""
    n = int(rate * WINDOW_S)
    windows = len(samples) // n
    if windows == 0:
        return np.zeros(0)
    power = np.mean(samples[: windows * n].reshape(windows, n) ** 2, axis=1)
    db = 10 * np.log10(power + 1e-12)
    return db - float(np.percentile(db, 98))


def voice_onsets(
    samples: Samples, rate: int, pause_s: float = PAUSE_S
) -> list[tuple[float, float]]:
    """Each time the voice starts after a silence of at least `pause_s`, or at the clip's
    start: (when the silence before it began, when the voice is heard)."""
    heard = level_db(samples, rate) > HEARD_DB
    out: list[tuple[float, float]] = []
    quiet_from = 0.0
    was_heard = False
    for i, h in enumerate(heard):
        t = i * WINDOW_S
        if h and not was_heard and (not out or t - quiet_from >= pause_s):
            out.append((round(quiet_from, 3), round(t, 3)))
        if not h and was_heard:
            quiet_from = t
        was_heard = bool(h)
    return out


def openness_track(weights: Sequence[dict[str, float]]) -> list[float]:
    return [openness(w) for w in weights]


def mouth_opens(
    track: Sequence[float], fps: float, quiet_from: float, heard: float
) -> float | None:
    """When the mouth opens for a voice heard at `heard` after silence from `quiet_from`: the
    start of the first frame at or over OPEN_AT after one under it, looking from the silence's
    start. None if the mouth stays open from the silence until well after the voice."""
    first = max(0, math.floor(quiet_from * fps))
    last = min(len(track), math.ceil((heard + 0.5) * fps))
    closed = False
    for f in range(first, last):
        if track[f] < OPEN_AT:
            closed = True
        elif closed:
            return round(f / fps, 3)
    return None


def first_sound(
    sounds: Sequence[SoundTiming], quiet_from: float, heard: float
) -> SoundTiming | None:
    """The sound in the timings for a voice heard at `heard` after silence from `quiet_from`:
    of the sounds that aren't a pause and start after the silence began, the one starting
    nearest the voice."""
    after = [s for s in sounds if s.shape != "rest" and s.start >= quiet_from]
    return min(after, key=lambda s: abs(s.start - heard)) if after else None


def word_near(words: Sequence[WordTiming], t: float) -> str:
    if not words:
        return ""
    return min(words, key=lambda w: abs(w.start - t)).word


def measure_onsets(speech: Speech, weights: Sequence[dict[str, float]]) -> list[Onset]:
    samples = to_float(speech.pcm)
    track = openness_track(weights)
    out = []
    for quiet_from, heard in voice_onsets(samples, speech.sample_rate):
        sound = first_sound(speech.sounds, quiet_from, heard)
        out.append(
            Onset(
                word_near(speech.words, heard),
                heard,
                None if sound is None else sound.start,
                mouth_opens(track, FPS, quiet_from, heard),
            )
        )
    return out


def audio_delay_ms(reference: Samples, decoded: Samples, rate: int) -> float:
    """How much later `decoded` is than `reference`, in ms, from their cross-correlation within
    SEARCH_MS either way."""
    span = int(rate * SEARCH_MS / 1000)
    n = min(len(reference), len(decoded))
    a, b = reference[:n], decoded[:n]
    size = 1 << (2 * n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(b, size) * np.conj(np.fft.rfft(a, size)), size)
    lags = np.concatenate([np.arange(0, span + 1), np.arange(-span, 0)])
    values = np.concatenate([corr[: span + 1], corr[-span:]])
    return round(float(lags[int(np.argmax(values))]) / rate * 1000, 1)


def decode_audio(mp4: Path, rate: int) -> Samples:
    pcm = subprocess.run(
        [
            find_ffmpeg(),
            "-v",
            "error",
            "-i",
            str(mp4),
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            str(rate),
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=120,
    ).stdout
    return to_float(pcm)


def blank_frames(n: int, size: tuple[int, int] = (64, 64)) -> list[bytes]:
    return [bytes(size[0] * size[1] * 3)] * n


def frame_times(mp4: Path) -> list[float]:
    """Each video frame's presentation time in the MP4, in seconds."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v",
            "-show_entries",
            "frame=pts_time",
            "-of",
            "csv=p=0",
            str(mp4),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    ).stdout
    return [float(line.strip(",")) for line in out.split() if line.strip(",")]


def video_shift_ms(times: Sequence[float], fps: float = FPS) -> float:
    """How much later the frames are in the MP4 than at frame / fps, in ms (the median, from the
    second frame: a progressive MP4's first frame stays at 0 while the rest move)."""
    shifts = [t - k / fps for k, t in enumerate(times)][1:] or [0.0]
    return round(float(np.median(shifts)) * 1000, 1)


def mp4_delays(wav: Path, speech: Speech, folder: Path) -> tuple[float, float]:
    """How much later the sound is than the picture in a whole and in a progressive MP4 written
    by `write_mp4`, in ms: the sound's delay against the WAV less the frames' own."""
    n = max(1, round(len(speech.pcm) / 2 / speech.sample_rate * FPS))
    reference = to_float(speech.pcm)
    out = []
    for progressive in (False, True):
        mp4 = folder / f"{wav.stem}-{int(progressive)}.mp4"
        write_mp4(blank_frames(n), (64, 64), wav, mp4, 120, progressive=progressive)
        sound = audio_delay_ms(reference, decode_audio(mp4, speech.sample_rate), speech.sample_rate)
        out.append(round(sound - video_shift_ms(frame_times(mp4)), 1))
    return out[0], out[1]


def _plain(word: str) -> str:
    return "".join(ch for ch in word.lower() if ch.isalnum())


def aligner_offsets(
    speech: Speech, text: str, align: Callable[[Samples, int, str], list[WordTiming]]
) -> list[tuple[str, float]]:
    """Each word's start found by the aligner minus Kokoro's own, in ms. Words are paired in
    order by their letters, as the two can split a text into words differently ("8,849")."""
    aligned = align(to_float(speech.pcm).astype(np.float32), speech.sample_rate, text)
    out = []
    j = 0
    for k in speech.words:
        for i in range(j, min(j + 4, len(aligned))):
            if _plain(aligned[i].word) == _plain(k.word):
                out.append((k.word, round((aligned[i].start - k.start) * 1000)))
                j = i + 1
                break
    return out


def measure_clip(
    name: str,
    text: str,
    speak: Callable[[str], Speech],
    folder: Path,
    align: Callable[[Samples, int, str], list[WordTiming]] | None = None,
    mp4: bool = True,
) -> ClipResult:
    start = time.perf_counter()
    speech = speak(text)
    wav = folder / f"{name.replace(' ', '-')}.wav"
    seconds = write_speech(speech, wav, wav.with_suffix(".json"))
    n_frames = max(1, round(seconds * FPS))
    # As the photoreal engine draws them (R128 moved each word after a pause to its voice).
    shapes = read_shapes(wav.with_suffix(".json"))
    weights = mouth_weights(shapes, to_float(speech.pcm), speech.sample_rate, n_frames, FPS)
    result = ClipResult(name, text, round(seconds, 2), measure_onsets(speech, weights))
    if mp4:
        result.whole_mp4_ms, result.progressive_mp4_ms = mp4_delays(wav, speech, folder)
    if align is not None:
        result.aligner_ms = aligner_offsets(speech, text, align)
    logger.info(
        "Measured clip",
        extra={
            "clip": name,
            "start_lead_ms": result.start.lead_ms if result.start else None,
            "onsets": len(result.onsets),
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return result


def total_ms(onset: Onset, mp4_ms: float | None) -> float | None:
    """The lead the viewer gets from the file: the frames' lead plus the sound's delay in it."""
    if onset.lead_ms is None:
        return None
    return onset.lead_ms + (mp4_ms or 0.0)


def file_delay(r: ClipResult) -> float | None:
    """The sound's delay in the MP4 the app writes for this clip: progressive for replies."""
    return r.progressive_mp4_ms if r.name.startswith("reply") else r.whole_mp4_ms


def _cell(v: float | None) -> str:
    return "–" if v is None else f"{v:g}"


def markdown(voice: str, results: Sequence[ClipResult]) -> str:
    lines = [
        f"# Mouth against voice: {voice}",
        "",
        "Lead is how long the mouth opens before the voice is heard (negative: after). "
        "Timings is the part from the sound timings, Frames the part from turning them into "
        "frames, and the MP4 columns how much later the sound is than the picture in the file.",
        "",
        "## At the start of each clip",
        "",
        "| Clip | Heard | Opens | Lead in the WAV | Timings | Frames "
        "| Sound later in whole MP4 | in progressive MP4 | Lead in the file |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        o = r.start
        if o is None:
            lines.append(f"| {r.name} | no voice | | | | | | | |")
            continue
        file_ms = file_delay(r)
        lines.append(
            f"| {r.name} | {o.heard:.3f} s | {_cell(o.opens)} s | {_cell(o.lead_ms)} ms "
            f"| {_cell(o.timings_ms)} ms | {_cell(o.frames_ms)} ms | {_cell(r.whole_mp4_ms)} ms "
            f"| {_cell(r.progressive_mp4_ms)} ms | {_cell(total_ms(o, file_ms))} ms |"
        )
    lines += [
        "",
        "Lead in the file uses the progressive MP4 for reply clips and the whole one for the rest, "
        "as the app writes them.",
        "",
        "## At each word after a pause",
        "",
        "| Clip | Word | Heard | Opens | Lead | Timings | Frames |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        for o in r.onsets[1:]:
            lines.append(
                f"| {r.name} | {o.word} | {o.heard:.3f} s | {_cell(o.opens)} s "
                f"| {_cell(o.lead_ms)} ms | {_cell(o.timings_ms)} ms | {_cell(o.frames_ms)} ms |"
            )
    aligned = [(r.name, w, d) for r in results for w, d in r.aligner_ms]
    if aligned:
        diffs = [d for _, _, d in aligned]
        lines += [
            "",
            "## The aligner's word starts against Kokoro's own",
            "",
            f"{len(diffs)} words: the aligner's start is {np.mean(diffs):+.0f} ms from Kokoro's on "
            f"average (median {np.median(diffs):+.0f} ms, from {min(diffs):+.0f} to "
            f"{max(diffs):+.0f} ms). Negative is earlier.",
            "",
            "| Clip | Word | Aligner minus Kokoro |",
            "|---|---|---|",
        ]
        lines += [f"| {c} | {w} | {d:+g} ms |" for c, w, d in aligned]
    over = [
        (r.name, o)
        for r in results
        for o in r.onsets
        if (t := total_ms(o, file_delay(r))) is not None and t > LIMIT_MS
    ]
    lines += [
        "",
        f"Leads over {LIMIT_MS} ms in the file: {len(over)} of "
        f"{sum(len(r.onsets) for r in results)}.",
        "",
    ]
    return "\n".join(lines)


def write_results(out: Path, voice: str, results: Sequence[ClipResult]) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    slug = Path(voice).stem if voice.endswith(".wav") else voice
    md = out / f"mouth-lead-{slug}.md"
    md.write_text(markdown(voice, results), encoding="utf-8")
    data: list[dict[str, Any]] = []
    for r in results:
        d = asdict(r)
        d["onsets"] = [
            {
                **asdict(o),
                "lead_ms": o.lead_ms,
                "timings_ms": o.timings_ms,
                "frames_ms": o.frames_ms,
            }
            for o in r.onsets
        ]
        data.append(d)
    md.with_suffix(".json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return md


# The browser test's media: a white frame and a 1 kHz beep at the same moments.
MARKS_S = (0.6, 1.6, 2.6)  # on whole frames at 25 fps
MEDIA_SECONDS = 3.0
MEDIA_RATE = 24000


def sync_media(folder: Path) -> list[Path]:
    """Write the browser test's MP4s, whole and progressive, as the app writes its clips; and
    a muted idle video, as the chat shows between replies."""
    folder.mkdir(parents=True, exist_ok=True)
    n = round(MEDIA_SECONDS * FPS)
    size = (64, 64)
    marks = {round(m * FPS) for m in MARKS_S}
    frames = [bytes([255 if f in marks else 0]) * (size[0] * size[1] * 3) for f in range(n)]
    t = np.arange(int(MEDIA_SECONDS * MEDIA_RATE)) / MEDIA_RATE
    audio = np.zeros_like(t)
    for m in MARKS_S:
        on = (t >= m) & (t < m + 0.04)
        audio[on] = 0.5 * np.sin(2 * np.pi * 1000 * (t[on] - m))
    wav = folder / "marks.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(MEDIA_RATE)
        w.writeframes((audio * 32767).astype("<i2").tobytes())
    out = []
    whites: dict[str, list[float]] = {}
    for progressive in (False, True):
        mp4 = folder / f"marks-{'progressive' if progressive else 'whole'}.mp4"
        write_mp4(frames, size, wav, mp4, 120, progressive=progressive)
        times = frame_times(mp4)
        whites[mp4.name] = [times[round(m * FPS)] for m in MARKS_S]
        out.append(mp4)
    idle = folder / "idle.mp4"
    write_mp4(blank_frames(n), size, None, idle, 120)
    # When each white frame shows in the file, for browser_sync.js.
    (folder / "marks.json").write_text(json.dumps(whites, indent=2) + "\n", encoding="utf-8")
    return out + [idle]


def kokoro_speaker(voice: str, lang: str) -> Callable[[str], Speech]:
    from imageskin.kokoro_engine import kokoro_for

    engine = kokoro_for(lang)
    return lambda text: engine.speak(voice, text)


def clone_speaker(sample: Path, pocket: bool = False) -> Callable[[str], Speech]:
    from imageskin.chatterbox_engine import ChatterboxEngine
    from imageskin.pocket_engine import pocket_engine

    engine = pocket_engine() if pocket else ChatterboxEngine()
    return lambda text: engine.speak(str(sample), text)


def aligner() -> Callable[[Samples, int, str], list[WordTiming]]:
    from imageskin.alignment import Aligner

    a = Aligner()
    return lambda samples, rate, text: a.align(np.asarray(samples, np.float32), rate, text)[0]


def main(argv: Sequence[str] | None = None) -> int:
    from imageskin.logging_setup import setup_logging

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--voice", default="af_heart", help="a Kokoro voice (default af_heart)")
    p.add_argument("--lang", default="a", help="Kokoro's language code: a American, b British")
    p.add_argument("--clone", type=Path, help="a voice sample WAV: speak in the cloned voice")
    p.add_argument("--pocket", action="store_true", help="clone with Pocket TTS (R22f)")
    p.add_argument("--no-aligner", action="store_true", help="skip the aligner check (Kokoro)")
    p.add_argument("-o", "--out", type=Path, default=Path("mouth-lead"))
    p.add_argument("--media", type=Path, help="write the browser test's MP4s to this folder")
    args = p.parse_args(argv)
    setup_logging()
    if args.media:
        for path in sync_media(args.media):
            print(path)
        return 0
    start = time.perf_counter()
    if args.clone:
        speak, voice, align = clone_speaker(args.clone, args.pocket), str(args.clone), None
    else:
        speak, voice = kokoro_speaker(args.voice, args.lang), args.voice
        align = None if args.no_aligner else aligner()
    logger.info("Mouth lead experiment started", extra={"voice": voice})
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in CLIPS:
            try:
                results.append(measure_clip(name, text, speak, Path(tmp), align))
            except Exception:
                logger.exception("Could not measure a clip", extra={"clip": name, "voice": voice})
    md = write_results(args.out, voice, results)
    logger.info(
        "Mouth lead experiment done",
        extra={
            "voice": voice,
            "clips": len(results),
            "output": str(md),
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    print(md.read_text(encoding="utf-8"))
    return 0 if len(results) == len(CLIPS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
