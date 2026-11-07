"""The me0.ai icon in the browser tab for the plain pages the server writes itself.

The app's own page links the icon files in `static/` (see `web/index.html`). The plain pages,
such as Site not found, are also served at addresses with no app behind them, so they carry the
icon in the page itself, as a data URL of the 32 by 32 PNG.
"""

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ICON_FILE = Path(__file__).parent / "static" / "favicon-32x32.png"


def favicon_link(path: Path = ICON_FILE) -> str:
    """The `<link rel=icon>` tag with the icon inlined, or "" (logged) when the file is missing,
    so a page is never refused for want of its icon."""
    try:
        data = path.read_bytes()
    except OSError as e:
        logger.error("Tab icon not loaded", extra={"path": str(path), "error": str(e)})
        return ""
    logger.debug("Tab icon loaded", extra={"path": str(path), "bytes": len(data)})
    encoded = base64.b64encode(data).decode("ascii")
    return f'<link rel=icon type=image/png href="data:image/png;base64,{encoded}">'


FAVICON_LINK = favicon_link()
