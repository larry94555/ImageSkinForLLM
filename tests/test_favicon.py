"""The me0.ai icon shows in the browser tab on every page the app serves: the app's own page,
at the main address and a trial site's path, and the plain pages the server writes itself."""

import base64
import io
import logging
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_site_addresses import quick_hashes, served  # noqa: F401 (the fixture)

from imageskin.app import STATIC_DIR, create_app, signed_in_page
from imageskin.favicon import FAVICON_LINK, ICON_FILE, favicon_link

ICONS = {
    "favicon.ico": {(16, 16), (32, 32), (48, 48)},
    "favicon-16x16.png": {(16, 16)},
    "favicon-32x32.png": {(32, 32)},
    "apple-touch-icon.png": {(180, 180)},
}
WEB_PUBLIC = Path(__file__).parent.parent / "web" / "public"


@pytest.mark.parametrize("name", ICONS)
def test_each_icon_has_its_sizes_and_matches_the_source(name: str) -> None:
    built = STATIC_DIR / name
    assert built.read_bytes() == (WEB_PUBLIC / name).read_bytes()  # npm run build was run
    with Image.open(built) as icon:
        sizes = icon.info.get("sizes") or {icon.size}
    assert set(sizes) == ICONS[name]


def test_the_app_page_links_every_icon_relative_to_itself(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    page = client.get("/").text
    for name in ICONS:
        # Relative, so a trial site's page at /t/<code>/ (R61a) finds them under its own path.
        assert f'href="./{name}"' in page, name
        icon = client.get(f"/{name}")
        assert icon.status_code == 200 and icon.headers["content-type"].startswith("image/"), name


def test_a_trial_sites_path_serves_the_icons(tmp_path: Path) -> None:
    apps, _, service = served(tmp_path)
    service.host_accounts.sign_up("cy@example.com", "pass-word-1", "test")
    code, _ = service.sites.add_trial("cy@example.com")
    browser = TestClient(apps, base_url="http://localhost:8000")
    assert 'href="./favicon.ico"' in browser.get(f"/t/{code}/").text
    for name in ICONS:
        assert browser.get(f"/t/{code}/{name}").status_code == 200, name


def inlined_icon(page: str) -> Image.Image:
    found = re.search(r'<link rel=icon type=image/png href="data:image/png;base64,([^"]+)">', page)
    assert found, page[:200]
    return Image.open(io.BytesIO(base64.b64decode(found.group(1))))


def test_the_site_not_found_page_carries_the_icon_itself(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    response = TestClient(sites, base_url="http://b.localhost").get("/")
    assert response.status_code == 404
    assert inlined_icon(response.text).size == (32, 32)


def test_the_sign_in_failed_page_carries_the_icon() -> None:
    page = bytes(signed_in_page("denied", 400).body).decode()
    assert FAVICON_LINK in page and inlined_icon(page).size == (32, 32)


def test_the_inlined_icon_is_the_32_pixel_file(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="imageskin.favicon"):
        link = favicon_link()
    assert link == FAVICON_LINK
    assert base64.b64encode(ICON_FILE.read_bytes()).decode() in link
    logged = next(r for r in caplog.records if r.getMessage() == "Tab icon loaded")
    assert logged.__dict__["bytes"] == ICON_FILE.stat().st_size


def test_a_missing_icon_is_logged_and_the_page_still_served(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing = tmp_path / "gone.png"
    with caplog.at_level(logging.ERROR, logger="imageskin.favicon"):
        assert favicon_link(missing) == ""
    logged = next(r for r in caplog.records if r.getMessage() == "Tab icon not loaded")
    assert logged.__dict__["path"] == str(missing) and logged.__dict__["error"]
