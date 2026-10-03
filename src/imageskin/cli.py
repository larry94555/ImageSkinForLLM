"""The `imageskin` command."""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from imageskin import __version__
from imageskin.audio import DEFAULT_TIMEOUT_S, AudioError, make_voice_sample
from imageskin.config import ConfigError, load_settings
from imageskin.logging_setup import setup_logging

logger = logging.getLogger(__name__)


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
    return parser


def serve(host: str, port: int) -> None:
    import uvicorn

    from imageskin.app import create_app

    logger.info("Starting server", extra={"host": host, "port": port, "version": __version__})
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
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
