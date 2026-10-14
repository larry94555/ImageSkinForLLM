"""The `imageskin` command."""

import argparse
import logging
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from imageskin import __version__
from imageskin.audio import DEFAULT_TIMEOUT_S, AudioError, make_voice_sample
from imageskin.config import ConfigError, Settings, default_home, load_settings
from imageskin.kokoro_engine import DEFAULT_VOICE, KokoroEngine
from imageskin.logging_setup import setup_logging
from imageskin.lookup import PDF_LIMIT, WIKI_LIMIT, pages_label, shorten
from imageskin.sample import SAMPLE_SCRIPT, SampleResult, make_sample
from imageskin.speech_text import spoken_text
from imageskin.video import INSTALL_HINT, VideoEngine, VideoError, find_ffmpeg
from imageskin.voice import VoiceEngine, VoiceError, write_speech

logger = logging.getLogger(__name__)

ENGINES = ("opencv", "photoreal")
PRINTED_CHARS = 160  # of each passage the lookup command prints
VOICE_SAMPLE_HELP = (
    "speak in the voice of this voice sample (from imageskin voice-sample) instead of a Kokoro "
    "voice, cloned with Pocket TTS when it is installed, else Chatterbox Turbo; see 'Your own "
    "voice' in the README"
)


def voice_engine(voice: str, voice_sample: Path | None) -> tuple[VoiceEngine, str]:
    """The engine and voice to speak with: a clone of the voice sample, or a Kokoro voice."""
    if voice_sample is None:
        return KokoroEngine(), voice
    from imageskin import pocket_engine
    from imageskin.chatterbox_engine import ChatterboxEngine

    # As in the app: Pocket TTS when installed (roadmap R22f), else Chatterbox.
    engine = pocket_engine.pocket_engine() if pocket_engine.installed() else ChatterboxEngine()
    engine.check_voice_sample(str(voice_sample))  # before the photo is prepared or models load
    return engine, str(voice_sample)


def count(value: str) -> int:
    """A whole number of 0 or more, for an option such as --wiki."""
    try:
        number = int(value)
    except ValueError:
        number = -1
    if number < 0:
        raise argparse.ArgumentTypeError(f"must be a whole number, 0 or more, not {value!r}")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="imageskin", description="ImageSkinForLLM")
    parser.add_argument("--version", action="version", version=f"imageskin {__version__}")
    parser.add_argument("--config", type=Path, help="path to a TOML config file")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="run the web server")
    voice = commands.add_parser(
        "voice-sample", help="join M4A, MP3 or WAV recordings into one WAV voice sample"
    )
    voice.add_argument("recordings", nargs="+", type=Path, help="recordings, in order")
    voice.add_argument(
        "-o", "--output", type=Path, default=Path("voice-sample.wav"), help="WAV file to write"
    )
    voice.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help="seconds allowed to convert each recording",
    )
    say = commands.add_parser(
        "say", help="speak text with a Kokoro voice, or in the person's own voice, on the CPU"
    )
    say.add_argument("text", help="what to say")
    say.add_argument(
        "--voice",
        default=DEFAULT_VOICE,
        help=f"Kokoro voice name, such as af_heart or am_michael (default {DEFAULT_VOICE})",
    )
    say.add_argument("--voice-sample", type=Path, help=VOICE_SAMPLE_HELP)
    say.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("speech.wav"),
        help="WAV file to write; word and sound timings go next to it as .json",
    )
    spoken = commands.add_parser(
        "spoken-text",
        help="print what the voice will say for a reply: Markdown, code, URLs and emoji left out",
    )
    # Several words are joined, so the reply works however the shell splits it: Windows cmd
    # doesn't treat single quotes as quoting.
    spoken.add_argument("text", nargs="*", help="the reply, as shown in the chat")
    spoken.add_argument("--file", type=Path, help="read the reply from this UTF-8 text file")
    prepare = commands.add_parser(
        "prepare",
        help="one-time photoreal setup for a photo: render its frames (minutes on a CPU) and "
        "write a silent preview of the idle face",
    )
    prepare.add_argument("--photo", type=Path, required=True, help="front-facing JPEG or PNG")
    prepare.add_argument(
        "-o", "--output", type=Path, default=Path("idle.mp4"), help="preview MP4 to write"
    )
    sample = commands.add_parser(
        "sample", help="render the sample video: the person in the photo speaks a test script"
    )
    sample.add_argument("--photo", type=Path, required=True, help="front-facing JPEG or PNG")
    sample.add_argument(
        "--voice",
        default=DEFAULT_VOICE,
        help=f"Kokoro voice name (default {DEFAULT_VOICE})",
    )
    sample.add_argument("--voice-sample", type=Path, help=VOICE_SAMPLE_HELP)
    sample.add_argument(
        "-o", "--output", type=Path, default=Path("sample.mp4"), help="MP4 file to write"
    )
    sample.add_argument(
        "--text", default=SAMPLE_SCRIPT, help="what to say (default: the sample test script)"
    )
    sample.add_argument(
        "--engine",
        choices=ENGINES,
        default="opencv",
        help="opencv: quick mouth animation (default); photoreal: LivePortrait, with a "
        "one-time setup per photo",
    )
    lookup = commands.add_parser(
        "lookup",
        help="print the wiki entries and PDF passages found for questions, with the time taken",
    )
    lookup.add_argument("questions", nargs="+", help="questions to look up, each in quotes")
    lookup.add_argument(
        "--wiki",
        type=count,
        default=WIKI_LIMIT,
        help=f"wiki entries to show (default {WIKI_LIMIT})",
    )
    lookup.add_argument(
        "--pdf", type=count, default=PDF_LIMIT, help=f"PDF passages to show (default {PDF_LIMIT})"
    )
    return parser


def load_video_engine(engine: str = "opencv") -> VideoEngine[Any]:
    try:
        if engine == "photoreal":
            from imageskin.photoreal import PhotorealEngine

            return PhotorealEngine()
        from imageskin.mouth_warp import MouthWarpEngine
    except ImportError as e:
        if e.name in ("cv2", "numpy"):
            extra = "photoreal" if engine == "photoreal" else "video"
            raise VideoError(INSTALL_HINT.replace(".[video]", f".[{extra}]")) from e
        raise
    return MouthWarpEngine()


def sample(
    photo: Path,
    voice: str,
    output: Path,
    engine: str = "opencv",
    text: str = SAMPLE_SCRIPT,
    voice_sample: Path | None = None,
) -> SampleResult:
    speaker, voice = voice_engine(voice, voice_sample)
    return make_sample(photo, output, speaker, load_video_engine(engine), voice, text)


def prepare(photo: Path, output: Path) -> tuple[Path, float]:
    """Build the photo's photoreal library; return its folder and the preview's length."""
    try:
        from imageskin.photoreal_library import (
            prepare_library,
            write_idle_preview,
        )
    except ImportError as e:
        if e.name in ("cv2", "numpy"):
            raise VideoError(INSTALL_HINT.replace(".[video]", ".[photoreal]")) from e
        raise
    find_ffmpeg()  # fail now, not after a long setup
    lib = prepare_library(photo, default_home())
    return lib.folder, write_idle_preview(lib, output)


def say(text: str, voice: str, output: Path, voice_sample: Path | None = None) -> float:
    speaker, voice = voice_engine(voice, voice_sample)
    speech = speaker.speak(voice, text)
    try:
        return write_speech(speech, output, output.with_suffix(".json"))
    except OSError as e:
        raise VoiceError(f"could not write {output}: {e}") from e


def print_spoken_text(text: str | None, file: Path | None) -> int:
    if (text is None) == (file is None):
        logger.error("Give the reply as text or with --file, not both")
        return 2
    if file is not None:
        try:
            text = file.read_text(encoding="utf-8-sig")  # Notepad may add a byte-order mark
        except (OSError, UnicodeDecodeError) as e:
            logger.error("Could not read reply", extra={"path": str(file), "error": str(e)})
            return 1
    assert text is not None
    started = time.perf_counter()
    spoken = spoken_text(text)
    logger.info(
        "Cleaned reply for speech",
        extra={
            "shown_chars": len(text),
            "spoken_chars": len(spoken),
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )
    print(spoken)
    return 0


def print_lookups(questions: list[str], wiki_limit: int, pdf_limit: int) -> int:
    """Look questions up in the wiki and PDFs kept in the app's data folder (R39)."""
    from imageskin.content import ContentStore
    from imageskin.lookup import ContentLookup
    from imageskin.reading_job import ReadingJob
    from imageskin.wiki_job import WikiJob

    def no_builds(*_: object) -> Any:
        raise AssertionError("the lookup command builds no wiki")

    store = ContentStore(default_home())
    readings = ReadingJob(store)
    lookup = ContentLookup(WikiJob(store, readings, no_builds), readings)
    for question in questions:
        result = lookup.find(question, wiki_limit, pdf_limit)
        if not result.passages:
            logger.error("Nothing to look up in: add PDFs on Manage Content and let them be read")
            return 1
        print(f"\nQuestion: {question}")
        print(f"Looked up in {result.duration_ms} ms")
        print("Wiki:" if result.wiki else "Wiki: nothing found")
        for n, f in enumerate(result.wiki, start=1):
            p = f.passage
            where = f"{p.pdf_name}, {pages_label(p.pages)}"
            print(f"  {n}. [{f.score}] {p.title} ({where}): {shorten(p.text, PRINTED_CHARS)}")
        print("PDF:" if result.pdf else "PDF: nothing found")
        for n, f in enumerate(result.pdf, start=1):
            p = f.passage
            where = f"{p.pdf_name}, {pages_label(p.pages)}, {p.kind}"
            print(f"  {n}. [{f.score}] ({where}): {shorten(p.text, PRINTED_CHARS)}")
    return 0


def serve(settings: Settings) -> None:
    import uvicorn

    from imageskin.app import create_app
    from imageskin.chat import LlmSettings

    host, port = settings.host, settings.port

    logger.info("Starting server", extra={"host": host, "port": port, "version": __version__})
    # Consent and uploads are kept here; set IMAGESKIN_HOME to use another folder.
    logger.info("App data folder", extra={"path": str(default_home().resolve())})
    # access_log=False: the app's own middleware logs each request with its duration.
    llm = LlmSettings(settings.llm_url, settings.llm_model, settings.llm_context_tokens)
    app = create_app(llm=llm, general_prompts=settings.general_prompts)
    uvicorn.run(app, host=host, port=port, log_config=None, access_log=False)


def main(argv: Sequence[str] | None = None) -> int:
    # Hugging Face's Xet transfer crawled on Larry's Windows laptop (GitHub PR #8) while plain
    # HTTP downloads were steady; this must be set before any model library loads. Windows
    # without Developer Mode can't make the cache's symlinks, which works but warns every run.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging()
    try:
        settings = load_settings(args.config)
    except ConfigError as e:
        logger.error("Could not load config", extra={"error": str(e)})
        return 2
    setup_logging(settings.log_level)

    if args.command == "serve":
        serve(settings)
        return 0
    if args.command == "voice-sample":
        try:
            seconds = make_voice_sample(args.recordings, args.output, args.timeout)
        except AudioError as e:
            logger.error("Could not make voice sample", extra={"error": str(e)})
            return 1
        print(f"Wrote {args.output} ({seconds:.1f} seconds from {len(args.recordings)} recordings)")
        return 0
    if args.command == "say":
        try:
            seconds = say(args.text, args.voice, args.output, args.voice_sample)
        except VoiceError as e:
            logger.error("Could not speak text", extra={"error": str(e)})
            return 1
        # Full paths, so it is clear where the files went (relative to the current folder).
        wav = args.output.resolve()
        timings = wav.with_suffix(".json")
        print(f"Wrote {wav} ({seconds:.1f} seconds) and word and sound timings to {timings}")
        return 0
    if args.command == "spoken-text":
        return print_spoken_text(" ".join(args.text) if args.text else None, args.file)
    if args.command == "lookup":
        return print_lookups(args.questions, args.wiki, args.pdf)
    if args.command == "prepare":
        try:
            folder, seconds = prepare(args.photo, args.output)
        except VideoError as e:
            logger.error("Could not prepare photo", extra={"error": str(e)})
            return 1
        print(
            f"Photo prepared; its frames are in {folder}. "
            f"Wrote {args.output.resolve()} ({seconds:.1f} seconds, no sound)."
        )
        return 0
    if args.command == "sample":
        try:
            result = sample(
                args.photo, args.voice, args.output, args.engine, args.text, args.voice_sample
            )
        except (VoiceError, VideoError) as e:
            logger.error("Could not make sample video", extra={"error": str(e)})
            return 1
        mp4 = args.output.resolve()
        print(
            f"Wrote {mp4} ({result.seconds:.1f} seconds). Took {result.prepare_ms / 1000:.1f} s "
            f"to prepare the photo, {result.speak_ms / 1000:.1f} s to speak and "
            f"{result.render_ms / 1000:.1f} s to render."
        )
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
