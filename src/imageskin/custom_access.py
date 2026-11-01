"""Refusing a host's own photo and voice where the administrator turned them off (roadmap R240).

Admin settings' Disable custom image and Disable custom voice (R239) say what a host may use;
here the server holds to it, so neither an old page nor the API can get round it: the photo and
sound uploads, Prepare with the host's own photo or voice, accepting its sample, and the
avatar's own voice are refused with 403 and a plain message. The files already stored are kept.
"""

import logging

from fastapi import HTTPException

from imageskin.admin_settings import CustomUse

logger = logging.getLogger(__name__)

IMAGE_REFUSED = (
    "Using your own photo is turned off for this site. Choose a default person on Start now."
)
VOICE_REFUSED = (
    "Using your own voice is turned off for this site. A default person speaks in a ready-made"
    " voice."
)


def refuse_unless_allowed(
    use: CustomUse, image: bool, voice: bool, host: str | None, route: str
) -> None:
    """Raise 403 when the request needs the host's own photo (`image`) or voice (`voice`) and
    they may not use it; the photo is checked first."""
    if image and not use.image:
        logger.warning("Custom image refused", extra={"host": host, "route": route})
        raise HTTPException(status_code=403, detail=IMAGE_REFUSED)
    if voice and not use.voice:
        logger.warning("Custom voice refused", extra={"host": host, "route": route})
        raise HTTPException(status_code=403, detail=VOICE_REFUSED)


def own_person_blocked(use: CustomUse, needs_image: bool, needs_voice: bool) -> bool:
    """Whether the person the chat would show, the host's own, uses something now turned off."""
    return (needs_image and not use.image) or (needs_voice and not use.voice)
