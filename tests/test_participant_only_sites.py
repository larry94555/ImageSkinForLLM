"""A host's site signs up participants only and names no host (roadmap R270), and a subdomain
with no site goes to the main address."""

import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_site_addresses import served

from imageskin.sites import SiteApps, main_redirect, site_matcher, trial_mover

pytestmark = pytest.mark.real_hosts


def request(host: str, path: str = "/", method: str = "GET", **extra: Any) -> dict[str, Any]:
    headers = [(b"host", host.encode())]
    if "proto" in extra:
        headers.append((b"x-forwarded-proto", extra.pop("proto").encode()))
    return {"type": "http", "method": method, "path": path, "headers": headers, **extra}


def test_a_page_at_a_subdomain_with_no_site_goes_to_the_main_address() -> None:
    to = main_redirect("me0.ai")
    assert to(request("nobody.me0.ai", proto="https")) == "https://www.me0.ai/"
    assert to(request("nobody.me0.ai", "/favicon.ico", scheme="https")) == "https://www.me0.ai/"
    assert to(request("nobody.localhost:8000")) == "http://localhost:8000/"
    assert to(request("nobody.me0.ai", method="HEAD")) == "http://www.me0.ai/"


def test_calls_and_other_addresses_stay_not_found() -> None:
    to = main_redirect("me0.ai")
    assert to(request("nobody.me0.ai", "/api/host/session")) is None
    assert to(request("nobody.me0.ai", method="POST")) is None
    assert to(request("example.org")) is None
    assert to({"type": "websocket", "path": "/", "headers": [(b"host", b"x.me0.ai")]}) is None


def test_the_server_redirects_an_unknown_subdomain(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sites, made, service = served(tmp_path)
    apps = SiteApps(
        lambda site: made.get(site) or sites.app(site),
        site_matcher(service.sites, "me0.ai"),
        trial_mover(service.sites, "me0.ai"),
        main_redirect("me0.ai"),
    )
    browser = TestClient(apps, base_url="http://b.localhost:8000", follow_redirects=False)
    with caplog.at_level(logging.INFO):
        page = browser.get("/")
    assert page.status_code == 302 and page.headers["location"] == "http://localhost:8000/"
    logged = next(
        r for r in caplog.records if r.message == "Unknown subdomain sent to the main address"
    )
    assert logged.__dict__["address"] == "b.localhost"
    # A call there is still not found, and a site that is set up is served as before.
    assert browser.get("/api/host/session").status_code == 404
    assert "b" not in made
    own = TestClient(apps, base_url="http://a.localhost:8000", follow_redirects=False)
    assert own.get("/api/host/session").status_code == 200


def test_only_a_hosts_site_is_participant_only(tmp_path: Path) -> None:
    sites, _, _ = served(tmp_path)
    main = TestClient(sites, base_url="http://localhost").get("/api/host/session").json()
    assert "participant_only" not in main
    site = TestClient(sites, base_url="http://a.localhost").get("/api/host/session").json()
    assert site["participant_only"] is True
