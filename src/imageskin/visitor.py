"""The question and answer screen for visitors who aren't signed in (roadmap R45, item 31).

A visitor, anyone neither signed in as a host nor on a laptop in the admin laptops list, gets
only the question box and the person's spoken answers: the topic hints and "What can you talk
about?" (R41f, R41g) but not Teach me, Quiz me or the assessment (R41h to R41j), whatever the
host turned on. The wiki and the PDFs are the host's pages to them too (see `app.py`); R46 gives
a signed-in participant the participant view back.
"""

import logging
from dataclasses import replace

from imageskin.ui_settings import UiSettings

logger = logging.getLogger(__name__)

# The settings a visitor always has off: the chat's Teach me, Quiz me and Assessment buttons.
OFF_FOR_VISITORS = ("teach_me", "quiz_me", "assessment")


def for_visitor(settings: UiSettings) -> UiSettings:
    """The settings as a visitor has them: Teach me, Quiz me and the assessment off."""
    turned_off = [name for name in OFF_FOR_VISITORS if getattr(settings, name)]
    if turned_off:
        logger.info("Turned off for a visitor", extra={"settings": turned_off})
    return replace(settings, teach_me=False, quiz_me=False, assessment=False)
