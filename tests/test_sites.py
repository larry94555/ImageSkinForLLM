"""One set of app state per site (R61b): each site's own app, sharing the accounts and the
administrator's files."""

import asyncio
import io
import logging
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from imageskin.app import create_app
from imageskin.config import default_home
from imageskin.pdf_reading import Piece, Progress, Reading
from imageskin.review import Review
from imageskin.sites import (
    DEFAULT_SITE,
    Asgi,
    Scope,
    SiteApps,
    make_service,
    one_site,
    site_home,
)
from imageskin.uploads import PhotoResult
from imageskin.wiki import Progress as WikiProgress
from imageskin.wiki import Wiki, WikiPage

PDF = b"%PDF-1.4\n%fake\n"


class Llm:
    """Answers each prompt with its own last words, so each site's reply says whose it is."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.sent: list[list[dict[str, str]]] = []

    def __call__(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        with self.lock:
            self.sent.append(messages)
        time.sleep(0.05)  # long enough for the two sites' replies to overlap
        return "Answer to " + messages[-1]["content"].rsplit("\n", 1)[-1]


def site(home: Path, service: Any, llm: Llm, read: Any = None) -> FastAPI:
    def lesson(path: Path, progress: Progress) -> Reading:
        return Reading("text", 1, [Piece(1, "paragraph", f"Read from {home.name}.")], [])

    def topics(pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, w: Any) -> Wiki:
        return Wiki(1, [WikiPage(f"{pdf_id}-a", f"Topic of {home.name}", "Text.", [1])])

    return create_app(
        home,
        check_photo=lambda p: PhotoResult([], 80),
        prepare_voice=lambda: None,
        prepare_face=lambda photo, progress: None,
        render_clip=lambda photo, text, output: None,
        ask_llm=llm,
        read_pdf=read or lesson,
        build_wiki=topics,
        service=service,
    )


def two_sites(tmp_path: Path) -> tuple[SiteApps, dict[str, FastAPI], Llm]:
    service = make_service(tmp_path / "service")
    llm = Llm()
    made: dict[str, FastAPI] = {}

    def make(name: str) -> FastAPI:
        made[name] = site(tmp_path / name, service, llm)
        return made[name]

    def by_host(scope: Scope) -> str:
        return dict(scope["headers"])[b"host"].decode().split(".")[0]

    return SiteApps(make, by_host), made, llm


def test_each_site_keeps_its_own_pdfs_and_conversation(tmp_path: Path) -> None:
    sites, made, llm = two_sites(tmp_path)
    a = TestClient(sites, base_url="http://a.localhost")
    b = TestClient(sites, base_url="http://b.localhost")
    for client in (a, b):
        client.post("/api/consent", json={"agreed": True})
    a.post("/api/content", files={"file": ("mars.pdf", io.BytesIO(PDF))})
    made["a"].state.readings.wait()
    made["a"].state.wiki.wait()

    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        # Site a's PDF has nothing on the question, so it's declined, naming site a's topic.
        declined = a.post("/api/chat", json={"prompt": "Hello from a?"}).json()["content"]
        assert b.post("/api/chat", json={"prompt": "Hello from b?"}).status_code == 200

    assert [p["name"] for p in a.get("/api/content").json()] == ["mars.pdf"]
    assert b.get("/api/content").json() == []
    assert [t["content"] for t in a.get("/api/chat").json()["turns"]][0] == "Hello from a?"
    assert [t["content"] for t in b.get("/api/chat").json()["turns"]] == [
        "Hello from b?",
        "Answer to Hello from b?",
    ]
    # Only site a's PDF was looked up for site a's question; site b has none to find.
    assert "Topic of a" in declined
    # Site b has no PDF, so its question went to the LLM with none of site a's passages.
    assert [m[-1]["content"] for m in llm.sent] == ["Hello from b?"]
    assert (tmp_path / "a" / "conversation.json").exists()
    assert not (tmp_path / "service" / "conversation.json").exists()
    assert sites.sites() == ["a", "b"]


def test_two_sites_answering_at_once_keep_their_own_conversations(tmp_path: Path) -> None:
    sites, made, llm = two_sites(tmp_path)
    clients = {name: TestClient(sites, base_url=f"http://{name}.localhost") for name in "ab"}
    for client in clients.values():
        client.post("/api/consent", json={"agreed": True})

    def ask(name: str, n: int) -> None:
        clients[name].post("/api/chat", json={"prompt": f"{name} question {n}"})

    with patch("imageskin.app.load_review", return_value=Review(accepted=True)):
        threads = [threading.Thread(target=ask, args=(name, n)) for n in range(3) for name in "ab"]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    for name, other in (("a", "b"), ("b", "a")):
        turns = [t["content"] for t in clients[name].get("/api/chat").json()["turns"]]
        assert len(turns) == 6
        assert all(t.split()[-3] == name or t.startswith(name) for t in turns), turns
        assert not any(f"{other} question" in t for t in turns)


def test_a_pdf_read_on_one_site_while_the_other_reads_stays_with_its_site(tmp_path: Path) -> None:
    service = make_service(tmp_path / "service")
    llm = Llm()
    started = threading.Barrier(2, timeout=5)

    def slow(name: str) -> Any:
        def read(path: Path, progress: Progress) -> Reading:
            started.wait()  # both sites are reading at the same time
            return Reading("text", 1, [Piece(1, "paragraph", f"Only {name}.")], [])

        return read

    apps = {name: site(tmp_path / name, service, llm, slow(name)) for name in "ab"}
    for name, app in apps.items():
        client = TestClient(app)
        client.post("/api/consent", json={"agreed": True})
        client.post("/api/content", files={"file": (f"{name}.pdf", io.BytesIO(PDF))})
    for name, app in apps.items():
        app.state.readings.wait()
        client = TestClient(app)
        pdfs = client.get("/api/content").json()
        assert [p["name"] for p in pdfs] == [f"{name}.pdf"]
        pieces = client.get(f"/api/content/{pdfs[0]['id']}/reading").json()["pieces"]
        assert [p["text"] for p in pieces] == [f"Only {name}."]


@pytest.mark.real_hosts
def test_the_host_accounts_and_admin_settings_are_every_sites(tmp_path: Path) -> None:
    sites, made, llm = two_sites(tmp_path)
    a = TestClient(sites, base_url="http://a.localhost")
    b = TestClient(sites, base_url="http://b.localhost")
    signed_up = a.post(
        "/api/host/sign-up", json={"email": "ann@example.com", "password": "0123456789"}
    )
    assert signed_up.status_code == 200
    b.post("/api/host/sign-in", json={"email": "ann@example.com", "password": "0123456789"})
    assert b.get("/api/host/me").json()["email"] == "ann@example.com"
    assert made["a"].state.service is made["b"].state.service
    assert made["a"].state.admin_settings is made["b"].state.admin_settings
    assert (tmp_path / "service" / "hosts.json").exists()
    assert not (tmp_path / "a" / "hosts.json").exists()


def test_a_site_is_made_once_however_many_ask_at_the_same_time(
    caplog: pytest.LogCaptureFixture,
) -> None:
    made: list[str] = []

    def make(name: str) -> Asgi:
        time.sleep(0.05)
        made.append(name)
        return FastAPI()

    sites = SiteApps(make)
    with caplog.at_level(logging.INFO, logger="imageskin.sites"):
        threads = [threading.Thread(target=sites.app, args=(DEFAULT_SITE,)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert made == [DEFAULT_SITE]
    assert sites.app(DEFAULT_SITE) is sites.app(DEFAULT_SITE)
    logged = [r for r in caplog.records if r.message == "Site state made"]
    assert len(logged) == 1 and logged[0].__dict__["site"] == DEFAULT_SITE
    assert logged[0].__dict__["duration_ms"] >= 50


def test_a_site_that_cant_be_made_is_logged_and_tried_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tries: list[int] = []

    def make(name: str) -> Asgi:
        tries.append(1)
        if len(tries) == 1:
            raise OSError("disk gone")
        return FastAPI()

    sites = SiteApps(make)
    with caplog.at_level(logging.ERROR), pytest.raises(OSError):
        sites.app("a")
    assert "Site state not made" in caplog.text and sites.sites() == []
    assert sites.app("a") is not None and sites.sites() == ["a"]


def test_every_request_is_the_one_sites_until_sites_are_matched() -> None:
    assert one_site({"type": "http", "headers": [(b"host", b"a.localhost")]}) == DEFAULT_SITE
    assert site_home(DEFAULT_SITE) == default_home()
    with pytest.raises(ValueError):
        site_home("a")


def test_the_server_starts_and_stops_with_no_site_made() -> None:
    sites = SiteApps(lambda name: pytest.fail("no site is made for the lifespan"))
    sent: list[dict[str, str]] = []
    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])

    async def receive() -> dict[str, str]:
        return next(messages)

    async def send(message: Any) -> None:
        sent.append(message)

    asyncio.run(sites({"type": "lifespan"}, receive, send))
    assert sent == [{"type": "lifespan.startup.complete"}, {"type": "lifespan.shutdown.complete"}]
