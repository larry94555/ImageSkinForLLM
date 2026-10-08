"""The `imageskin` command."""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from imageskin import __version__
from imageskin.audio import DEFAULT_TIMEOUT_S, AudioError, make_voice_sample
from imageskin.config import ConfigError, default_home, load_settings
from imageskin.kokoro_engine import DEFAULT_VOICE, KokoroEngine
from imageskin.logging_setup import setup_logging
from imageskin.sample import SAMPLE_SCRIPT, SampleResult, make_sample
from imageskin.video import INSTALL_HINT, VideoEngine, VideoError, find_ffmpeg
from imageskin.voice import VoiceEngine, VoiceError, write_speech

logger = logging.getLogger(__name__)

ENGINES = ("opencv", "photoreal")
VOICE_SAMPLE_HELP = (
    "speak in the voice of this voice sample (from imageskin voice-sample) instead of a Kokoro "
    "voice, cloned with Chatterbox Turbo; see 'Your own voice' in the README"
)


def voice_engine(voice: str, voice_sample: Path | None) -> tuple[VoiceEngine, str]:
    """The engine and voice to speak with: a clone of the voice sample, or a Kokoro voice."""
    if voice_sample is None:
        return KokoroEngine(), voice
    from imageskin.chatterbox_engine import ChatterboxEngine

    return ChatterboxEngine(), str(voice_sample)


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


def serve(host: str, port: int) -> None:
    import uvicorn

    from imageskin.app import create_app

    logger.info("Starting server", extra={"host": host, "port": port, "version": __version__})
    # Consent and uploads are kept here; set IMAGESKIN_HOME to use another folder.
    logger.info("App data folder", extra={"path": str(default_home().resolve())})
    # access_log=False: the app's own middleware logs each request with its duration.
    uvicorn.run(create_app(), host=host, port=port, log_config=None, access_log=False)


def main(argv: Sequence[str] | None = None) -> int:
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
        serve(settings.host, settings.port)
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
