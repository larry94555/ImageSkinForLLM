"""The `imageskin` command."""

import argparse
import logging
import os
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from imageskin import __version__, time_reply
from imageskin.audio import DEFAULT_TIMEOUT_S, AudioError, make_voice_sample
from imageskin.config import ConfigError, Settings, default_home, load_settings
from imageskin.kokoro_engine import DEFAULT_VOICE, KokoroEngine
from imageskin.logging_setup import setup_logging
from imageskin.lookup import PDF_LIMIT, WIKI_LIMIT, pages_label, shorten
from imageskin.sample import SAMPLE_SCRIPT, SampleResult, make_sample
from imageskin.speech_text import spoken_text
from imageskin.video import INSTALL_HINT, VideoEngine, VideoError, find_ffmpeg
from imageskin.voice import VoiceEngine, VoiceError, write_speech

if TYPE_CHECKING:
    from imageskin.chat import LlmSettings

logger = logging.getLogger(__name__)

READY_POLL_S = 0.1  # how often the ready line checks whether the server is listening yet
# The threads of jobs that may carry on from before a restart, named by the ready line.
BACKGROUND_JOBS = {"pdf-reading", "wiki", "prepare"}

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
    # Sign in with ChatGPT on a self-hosted server (deploy/README.md, step 8): OpenAI's guide has
    # the sign-in done on the user's own computer, then moved to the server.
    export = commands.add_parser(
        "chatgpt-export",
        help="move this computer's ChatGPT sign-in into a file, for a self-hosted server",
    )
    export.add_argument("output", type=Path, help="the file to write, such as chatgpt-sign-in.json")
    imported = commands.add_parser(
        "chatgpt-import", help="use a ChatGPT sign-in from imageskin chatgpt-export here"
    )
    imported.add_argument("file", help="the exported file, or - to read it from standard input")
    check_packs = commands.add_parser(
        "check-packs",
        help="download every default person's pack from the hosted site and check it",
    )
    check_packs.add_argument(
        "--url", help="where the packs are, if not the hosted site (such as http://127.0.0.1:9100)"
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
    timed = commands.add_parser(
        "time-reply",
        help="send prompts to the running app and show where the time goes in each reply",
    )
    timed.add_argument(
        "prompts", nargs="*", help="prompts to send, each in quotes (default: three ready ones)"
    )
    timed.add_argument("--url", default=time_reply.DEFAULT_URL, help="the running app's address")
    timed.add_argument(
        "--out",
        type=Path,
        help="folder for the results (default: speed in the data folder)",
    )
    timed.add_argument(
        "--spoken",
        type=count,
        default=None,
        help="send this prompt (from 1) as if said with Hold to talk",
    )
    timed.add_argument(
        "--stop",
        action="store_true",
        help="then send the last prompt again and press Stop at its first clip",
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


def chatgpt_export(output: Path) -> int:
    from imageskin.chatgpt_signin import ChatGptSignIn, SignInError
    from imageskin.llm_choice import write_owner_only

    try:
        ChatGptSignIn(default_home()).export_active(lambda data: write_owner_only(output, data))
    except (SignInError, OSError) as e:
        logger.error("Could not export the ChatGPT sign-in", extra={"error": str(e)})
        return 1
    print(
        f"Wrote {output.resolve()}. It holds your ChatGPT sign-in: copy it to the server, import "
        "it there, then delete it. This computer is signed out of ChatGPT now, as only one copy "
        "of a sign-in can keep renewing; sign in here again to use the plan here too."
    )
    return 0


def chatgpt_import(file: str) -> int:
    import json

    from imageskin.chatgpt_signin import NOT_A_TRANSFER, ChatGptSignIn, SignInError

    try:
        text = sys.stdin.read() if file == "-" else Path(file).read_text(encoding="utf-8")
        status = ChatGptSignIn(default_home()).import_registration(json.loads(text))
    except (OSError, ValueError, SignInError) as e:
        reason = str(e) if isinstance(e, (OSError, SignInError)) else NOT_A_TRANSFER
        logger.error("Could not import the ChatGPT sign-in", extra={"error": reason})
        return 1
    plan = "" if status["plan_usage"] else ', but click "Allow use of my plan" on Settings'
    print(f"Signed in with ChatGPT as {status['label']}{plan}. Delete the exported file now.")
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


def announce_ready(server: Any, app: Any, url: str, start: float) -> None:
    """Log the ready line once the server is listening and everything the app loads before it
    can take input has loaded. Jobs carried on from before the restart (reading PDFs,
    building the wiki, Prepare) don't hold it back, as the wiki waits on the LLM; the line
    names those still running, as they log after it. Nothing is logged if the server stops
    first."""
    from imageskin.app import READY_MESSAGE, wait_until_loaded

    while not server.started:
        if server.should_exit:
            return
        time.sleep(READY_POLL_S)
    wait_until_loaded(app)
    if server.should_exit:  # stopped while the loading finished
        return
    running = sorted({t.name for t in threading.enumerate()} & BACKGROUND_JOBS)
    logger.info(
        READY_MESSAGE,
        extra={
            "url": url,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            "background_jobs": running,
        },
    )


def llm_settings(settings: Settings) -> "LlmSettings":
    """The local LLM from the config. Another is picked on the Settings page (R42)."""
    from imageskin.chat import LlmSettings

    return LlmSettings(settings.llm_url, settings.llm_model, settings.llm_context_tokens)


def serve(settings: Settings) -> None:
    import uvicorn

    from imageskin.app import create_app

    start = time.perf_counter()
    host, port = settings.host, settings.port

    logger.info("Starting server", extra={"host": host, "port": port, "version": __version__})
    # Consent and uploads are kept here; set IMAGESKIN_HOME to use another folder.
    logger.info("App data folder", extra={"path": str(default_home().resolve())})
    # access_log=False: the app's own middleware logs each request with its duration.
    llm = llm_settings(settings)
    app = create_app(llm=llm, general_prompts=settings.general_prompts)
    config = uvicorn.Config(app, host=host, port=port, log_config=None, access_log=False)
    server = uvicorn.Server(config)
    url = f"http://{host}:{port}"
    threading.Thread(
        target=announce_ready, args=(server, app, url, start), name="ready", daemon=True
    ).start()
    try:
        server.run()
    except KeyboardInterrupt:  # Ctrl+C stops the server quietly, as uvicorn.run() does
        pass


def print_pack_checks(url: str | None) -> int:
    """Check every hosted pack (roadmap R32a), printing a line for each; 1 if any is wrong."""
    from imageskin.hosted_packs import check_all, line
    from imageskin.start_now import load_packs, packs_url

    base_url = url or packs_url()
    print(f"Checking the default people at {base_url}")
    checks = check_all(base_url, load_packs(), report=lambda check: print(line(check), flush=True))
    wrong = [c for c in checks if c.problem]
    seconds = sum(c.seconds for c in checks)
    total = sum(c.bytes for c in checks) / (1024 * 1024)
    print(
        f"{len(checks) - len(wrong)} of {len(checks)} packs match ({total:.0f} MB, {seconds:.0f} s)"
    )
    return 1 if wrong else 0


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
    if args.command == "chatgpt-export":
        return chatgpt_export(args.output)
    if args.command == "chatgpt-import":
        return chatgpt_import(args.file)
    if args.command == "check-packs":
        return print_pack_checks(args.url)
    if args.command == "lookup":
        return print_lookups(args.questions, args.wiki, args.pdf)
    if args.command == "time-reply":
        return time_reply.run(
            args.url,
            args.prompts or list(time_reply.DEFAULT_PROMPTS),
            args.out or default_home() / "speed",
            args.spoken,
            args.stop,
        )
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
