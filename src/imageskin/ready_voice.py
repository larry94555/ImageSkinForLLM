"""The ready-made voice the user's own photo speaks in while there are no recordings (item 59).

Until recordings pass the checks, or once they are all rejected or removed, the person speaks in
one of the ready-made Kokoro voices the default people use (item 58), instead of setup waiting
for recordings. The one used is the last ready-made avatar's voice, or the one chosen in setup,
saved as ready-voice.json in the app's home folder.
"""

import json
import logging
from pathlib import Path

from imageskin.default_people import VOICES

logger = logging.getLogger(__name__)

FILENAME = "ready-voice.json"
# Kokoro's voices by name, with their language codes.
LANGS = {voice: lang for lang, voice in VOICES.values()}
DEFAULT = "af_heart"  # the first in the list, until an avatar or setup picks one


def load_ready_voice(home: Path) -> str:
    """The ready-made voice chosen, or the default when none is saved or it can't be read."""
    path = home / FILENAME
    try:
        voice = json.loads(path.read_text(encoding="utf-8")).get("voice")
    except FileNotFoundError:
        return DEFAULT
    except (OSError, ValueError, AttributeError) as e:
        logger.error("Could not read the ready-made voice", extra={"error": str(e)})
        return DEFAULT
    return voice if voice in LANGS else DEFAULT


def save_ready_voice(home: Path, voice: str) -> str:
    """Save the ready-made voice to use without recordings. ValueError for an unknown one."""
    if voice not in LANGS:
        raise ValueError(f"{voice!r} is not one of {', '.join(LANGS)}.")
    home.mkdir(parents=True, exist_ok=True)
    (home / FILENAME).write_text(json.dumps({"voice": voice}), encoding="utf-8")
    logger.info("Ready-made voice chosen", extra={"voice": voice})
    return voice


def preset(voice: str) -> tuple[str, str]:
    """Kokoro's language code and voice."""
    return LANGS[voice], voice
