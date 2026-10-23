"""`imageskin time-startup`: where the time goes when the app starts (roadmap R96c), measured
against the running app over its API. Run it right after starting or restarting the app: it
waits for the ready line, with llama-server's model loaded beside it (Larry's timing 10), and
reads when each part of the start began and ended from the app itself (timing 7). Then it
times the first prompt and the next, so the first can be compared with the usual speed; the
browser's first load (the page, its scripts, styles and fonts, and the face pictures); the
requests the chat makes when it is opened again after a restart, with Welcome back's video;
and saving the local LLM again in Settings, to its next answer."""

import gzip
import json
import logging
import posixpath
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from imageskin import time_reply
from imageskin.time_reply import ask, ms, table

logger = logging.getLogger(__name__)

PROMPT = "Hello! Who are you?"
NEXT_PROMPT = "What is the tallest mountain in the world?"
READY_LIMIT_S = 1800  # llama-server took 164 s to load its model on the hosted machine
POLL_S = 0.25
FETCH_TIMEOUT_S = 60
BROWSER_CONNECTIONS = 6  # as many as a browser opens to one address over HTTP/1.1
# What the chat asks for when it is opened (web/src/api.ts), in the order it asks.
CHAT_OPENING = (
    "/api/consent",
    "/api/settings",
    "/api/review",
    "/api/start-now",
    "/api/chat",
    "/api/chat/hints",
    "/api/chat/photo",
    "/api/chat/idle",
)
LINKED = re.compile(r'(?:src|href)="(/[^"]+)"')
CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)")


def fetch(url: str) -> dict[str, Any]:
    """GET `url` as a browser does, compressed; its status, bytes on the wire, time to its
    first byte and to its end, and its text when it is a page, script or style."""
    request = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    start = time.perf_counter()
    row: dict[str, Any] = {"url": url, "status": None, "bytes": 0, "error": None}
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_S) as response:
            row["status"] = response.status
            first = response.read1(64 * 1024)
            row["first_byte_ms"] = ms(time.perf_counter(), start)
            body = first + response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                row["bytes"] = len(body)
                body = gzip.decompress(body)
            else:
                row["bytes"] = len(body)
            kind = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        row["status"] = e.code
        row["error"] = f"refused ({e.code})"
        return {**row, "ms": ms(time.perf_counter(), start)}
    except OSError as e:
        row["error"] = str(e)
        logger.error("Could not fetch", extra={"url": url, "error": str(e)})
        return {**row, "ms": ms(time.perf_counter(), start)}
    row["ms"] = ms(time.perf_counter(), start)
    if kind.startswith(("text/", "application/javascript")):
        row["text"] = body.decode(errors="replace")
    return row


def fetch_all(base: str, paths: list[str]) -> dict[str, Any]:
    """Fetch the paths at once over as many connections as a browser opens: how long all of
    them took, their bytes, and each one's row."""
    start = time.perf_counter()
    with ThreadPoolExecutor(BROWSER_CONNECTIONS) as pool:
        rows = list(pool.map(lambda p: fetch(base + p), paths))
    return {
        "files": len(rows),
        "bytes": sum(r["bytes"] for r in rows),
        "ms": ms(time.perf_counter(), start),
        "failed": [r["url"] for r in rows if r["error"]],
        "rows": rows,
    }


def wait_until_ready(base: str, limit_s: float | None = None) -> dict[str, Any]:
    """Ask for the start's parts until the app says it is ready; the app may still be
    starting, or not listening yet."""
    limit_s = READY_LIMIT_S if limit_s is None else limit_s
    start = time.perf_counter()
    while time.perf_counter() - start < limit_s:
        try:
            startup = ask(base + "/api/startup", timeout=10)
        except (OSError, ValueError):  # not listening yet, or an app from before R96c
            startup = None
        if startup and any(p["name"] == "ready" for p in startup["parts"]):
            return startup
        time.sleep(POLL_S)
    raise time_reply.TimingError(f"The app wasn't ready within {limit_s} s.")


def llm_health_url(llm_url: str) -> str:
    """llama-server's /health, beside its OpenAI-style /v1."""
    root = llm_url.rstrip("/")
    return (root[: -len("/v1")] if root.endswith("/v1") else root) + "/health"


def watch_llm(url: str, seen: dict[str, Any], stop: threading.Event) -> None:
    """Note in `seen` when llama-server first answers /health with 200 (it answers 503 while
    it loads its model), and whether it already did the first time it was asked. Any failure
    to ask is kept in `seen` and asked again: the hosted run of PR #150 lost the watch, with
    no time for llama-server, when one wasn't an OSError."""
    first = True
    while not stop.is_set():
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.status == 200:
                    seen["wall"] = time.time()
                    seen["already"] = first
                    return
                seen["error"] = f"answered {response.status}"
        except Exception as e:  # 503 while loading, refused while starting, or anything else
            seen["error"] = f"{type(e).__name__}: {e}"
        first = False
        stop.wait(POLL_S)


def first_load(base: str) -> dict[str, Any]:
    """The browser's first load: the page, what it links (scripts and styles), the fonts the
    styles name, the face pictures of the avatar page, each as one group."""
    page = fetch(base + "/")
    linked = sorted(set(LINKED.findall(page.get("text", ""))))
    files = fetch_all(base, linked)
    fonts: set[str] = set()
    for row in files["rows"]:
        if row["url"].endswith(".css"):
            folder = row["url"][len(base) :].rsplit("/", 1)[0]
            for name in CSS_URL.findall(row.get("text", "")):
                if not name.startswith(("data:", "http")):
                    fonts.add(posixpath.normpath(posixpath.join(folder, name)))
    font_files = fetch_all(base, sorted(fonts))
    try:
        listed: Any = ask(base + "/api/start-now/faces")  # a list, not an object
        faces = [f"/faces/{f['name']}.jpg" for f in listed]
    except (OSError, ValueError) as e:
        logger.error("Could not list the faces", extra={"error": str(e)})
        faces = []
    face_files = fetch_all(base, faces)
    groups = {
        "page": {
            "files": 1,
            "bytes": page["bytes"],
            "ms": page["ms"],
            "failed": [page["url"]] if page["error"] else [],
            "rows": [page],
        },
        "scripts and styles": files,
        "fonts": font_files,
        "face pictures": face_files,
    }
    for group in groups.values():
        for row in group["rows"]:
            row.pop("text", None)
    return groups


def welcome_back_path(base: str) -> str | None:
    """Where Welcome back's video is, as the chat finds it (lineUrl in web/src/api.ts)."""
    try:
        if ask(base + "/api/start-now").get("chosen"):
            return "/api/start-now/lines/welcome-back"
        if ask(base + "/api/prepare").get("state") == "done":
            return "/api/prepare/clips/welcome-back"
    except (OSError, ValueError) as e:
        logger.error("Could not find Welcome back", extra={"error": str(e)})
    return None


def chat_opening(base: str) -> dict[str, Any]:
    """The chat opened again after a restart: its requests, then Welcome back's video, which
    plays when the chat is opened with Start again after Exit."""
    opening = fetch_all(base, list(CHAT_OPENING))
    line = welcome_back_path(base)
    welcome = fetch(base + line) if line else None
    return {"opening": opening, "welcome_back": welcome}


def change_llm(base: str) -> dict[str, Any]:
    """Save the local LLM again, as Settings does, and time the next prompt, which has the
    LLM's warm-up started by the save beside it. Only for the local LLM: the speed tests use
    llama.cpp alone for now (Larry, 2026-10-22)."""
    try:
        choice = ask(base + "/api/llm")
    except (OSError, ValueError) as e:
        return {"error": f"Could not read the LLM setting ({e})."}
    if choice.get("provider") != "local":
        named = choice.get("provider")
        return {"error": f"Not timed: the app answers with {named}, not llama.cpp."}
    request = urllib.request.Request(
        base + "/api/llm",
        json.dumps({"provider": "local"}).encode(),
        {"Content-Type": "application/json"},
        method="PUT",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except OSError as e:
        return {"error": f"The LLM setting wasn't saved ({e})."}
    saved_ms = ms(time.perf_counter(), start)
    reply = time_reply.summarize(time_reply.measure(base, NEXT_PROMPT))
    return {"error": reply["error"], "saved_ms": saved_ms, "reply": reply}


def at_ms(wall: float | None, started_wall: float) -> float | None:
    """A moment on this machine's clock, in ms from the app's process starting."""
    return None if wall is None else round((wall - started_wall) * 1000)


def measure_all(base: str, llm_url: str, began_wall: float) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    stop = threading.Event()
    watcher = threading.Thread(
        target=watch_llm, args=(llm_health_url(llm_url), seen, stop), daemon=True
    )
    watcher.start()
    start = time.perf_counter()
    try:
        startup = wait_until_ready(base)
        # The prompts are timed once the LLM is loaded too, which can come after the ready line.
        watcher.join(max(0.0, READY_LIMIT_S - (time.perf_counter() - start)))
    finally:
        stop.set()
    started = startup["started_wall"]
    llm = {
        "loaded_ms": at_ms(seen.get("wall"), started),
        "already_loaded": seen.get("already", False),
        "error": None if "wall" in seen else seen.get("error"),
        "began_ms": at_ms(began_wall, started),
    }
    logger.info("App ready; timing the first prompts", extra={"llm_loaded_ms": llm["loaded_ms"]})
    prompts = [time_reply.summarize(time_reply.measure(base, p)) for p in (PROMPT, NEXT_PROMPT)]
    return {
        "startup": startup,
        "llm": llm,
        "prompts": prompts,
        "first_load": first_load(base),
        "chat_opening": chat_opening(base),
        "llm_change": change_llm(base),
    }


def markdown(results: dict[str, Any]) -> str:
    startup, llm = results["startup"], results["llm"]
    out = ["# Where the time goes: start-up and the first load", ""]
    out += [
        "## Start-up (Larry's timings 7 and 10)",
        "",
        "Milliseconds from the app's process starting.",
        "",
    ]
    rows: list[list[object]] = [
        [p["name"], p["start_ms"], p["end_ms"], ms_between(p), p.get("error")]
        for p in startup["parts"]
    ]
    loaded = llm["loaded_ms"]
    if loaded is not None:
        when = f"before {loaded}" if llm["already_loaded"] else loaded
        rows.append(["llama-server answering /health", "-", when, "-", None])
    else:
        rows.append(["llama-server answering /health", "-", "not seen", "-", llm.get("error")])
    rows.append(["time-startup began", llm["began_ms"], llm["began_ms"], 0, None])
    rows.sort(key=lambda r: r[1] if isinstance(r[1], (int, float)) else -1)
    out += [table(["Part", "Began", "Ended", "Took", "Error"], rows), ""]
    warm_up = next((p for p in startup["parts"] if p["name"] == "LLM warm-up"), None)
    ended = None if warm_up is None else warm_up["end_ms"]
    if ended is not None and loaded is not None and not llm["already_loaded"]:
        if ended < loaded:
            out += [
                "The LLM's warm-up ended before llama-server had loaded its model, so llama-server "
                "refused it (503, logged as `Could not warm up the LLM`) and the first prompt read "
                "the system prompt again.",
                "",
            ]
    out += [
        "## The first prompt and the next",
        "",
        "Milliseconds from each prompt being sent. The first after the start against the next "
        "shows whether the warm-up left the LLM at its usual speed.",
        "",
        *time_reply.replies_markdown(results["prompts"], "###"),
        "",
    ]
    out += [
        "## The browser's first load",
        "",
        f"Each group fetched at once over {BROWSER_CONNECTIONS} connections, compressed, as a "
        "browser does; one group after the other.",
        "",
    ]
    groups = results["first_load"]
    out += [
        table(
            ["What", "Files", "Bytes", "Took (ms)", "Failed"],
            [
                [name, g["files"], g["bytes"], g["ms"], ", ".join(g["failed"]) or None]
                for name, g in groups.items()
            ]
            + [
                [
                    "all",
                    sum(g["files"] for g in groups.values()),
                    sum(g["bytes"] for g in groups.values()),
                    sum(g["ms"] or 0 for g in groups.values()),
                    None,
                ]
            ],
        ),
        "",
    ]
    opening = results["chat_opening"]
    out += ["## Opening the chat after a restart", ""]
    out += [
        table(
            ["Request", "Status", "First byte", "Took (ms)"],
            [
                [r["url"].split("/", 3)[-1], r["status"], r.get("first_byte_ms"), r["ms"]]
                for r in opening["opening"]["rows"]
            ],
        ),
        "",
        f"All at once: {opening['opening']['ms']} ms.",
        "",
    ]
    welcome = opening["welcome_back"]
    if welcome is None:
        out += ["Welcome back: there is no video of it yet.", ""]
    else:
        out += [
            f"Welcome back's video: first byte in {welcome.get('first_byte_ms')} ms, "
            f"{welcome['bytes']} bytes in {welcome['ms']} ms (status {welcome['status']}).",
            "",
        ]
    change = results["llm_change"]
    out += ["## Changing the LLM in Settings", ""]
    if "saved_ms" in change:
        out += [
            f"Saved in {change['saved_ms']} ms; the next prompt, in ms from being sent:",
            "",
            *time_reply.replies_markdown([change["reply"]], "###"),
        ]
    else:
        out += [change["error"]]
    return "\n".join(out) + "\n"


def ms_between(part: dict[str, Any]) -> float | None:
    if part["end_ms"] is None:
        return None
    return round(float(part["end_ms"]) - float(part["start_ms"]), 1)


def failures(results: dict[str, Any]) -> int:
    failed = sum(1 for r in results["prompts"] if r["error"])
    failed += sum(len(g["failed"]) for g in results["first_load"].values())
    failed += sum(1 for p in results["startup"]["parts"] if p.get("error"))
    return failed + (1 if results["llm_change"].get("error") else 0)


def run(base: str, llm_url: str, out: Path) -> int:
    """Time the start of the running app; write the results as JSON and Markdown in `out` and
    print the Markdown."""
    base = base.rstrip("/")
    began_wall = time.time()
    start = time.perf_counter()
    logger.info("Timing the start", extra={"url": base, "llm_url": llm_url})
    try:
        results = measure_all(base, llm_url, began_wall)
    except time_reply.TimingError as e:
        logger.error("Could not time the start", extra={"url": base, "error": str(e)})
        return 1
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report = markdown(results)
    written = out / f"startup-{stamp}.md"
    (out / f"startup-{stamp}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    written.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {written.resolve()} and the .json beside it")
    failed = failures(results)
    logger.info(
        "Start timed",
        extra={"failed": failed, "duration_ms": round((time.perf_counter() - start) * 1000, 1)},
    )
    return 1 if failed else 0
