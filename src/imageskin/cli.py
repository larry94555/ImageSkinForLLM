"""The `imageskin` command."""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from imageskin import __version__
from imageskin.config import ConfigError, load_settings
from imageskin.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="imageskin", description="ImageSkinForLLM")
    parser.add_argument("--version", action="version", version=f"imageskin {__version__}")
    parser.add_argument("--config", type=Path, help="path to a TOML config file")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="run the web server")
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
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
