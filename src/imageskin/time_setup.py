"""`imageskin time-setup`: where the time goes in setup (roadmap R96b), measured against the
running app over its API, as the browser does it but without one. A photo and recordings are
uploaded (Larry's timings 8 and 9, each step from the upload's Server-Timing header), the video
and voice are prepared, then prepared again after a change of photo and of accent (timing 6),
then Start now picks a default person, then another, each timed to the chat opening and its
first reply's first word, and last the avatar is prepared in the user's own voice (R24d).

It changes the app's setup, so it runs only on an app with nothing set up yet, unless told to
go on anyway: start the app with an empty data folder for it."""

import json
import logging
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from imageskin import server_timing, time_reply
from imageskin.time_reply import ask, ms, table

logger = logging.getLogger(__name__)

# Inside the package, so they are there when it is installed, as in the Docker image.
SAMPLES = Path(__file__).with_name("setup_samples")
DEFAULT_PHOTOS = (
    SAMPLES / "photoreal_male_professor.jpg",
    SAMPLES / "photoreal_male_professor_2.jpg",  # the change of photo
)
# One man's recording three times: three recordings of one person, as setup asks for. It is
# the American donor's 20 s twice over (experiments/voice/donors), so it has the 15 s of speech
# a recording needs, as an M4A, as a phone records it.
DEFAULT_RECORDINGS = (SAMPLES / "recording.m4a",) * 3
# Start now's two people, then the switch to the second.
PEOPLE = (
    {"gender": "male", "accent": "American", "realism": "photoreal", "role": "Professor"},
    {"gender": "female", "accent": "British", "realism": "animated", "role": "Boss"},
)
PROMPT = "Hello! Who are you?"
# How often the browser asks, so what it shows can lag by up to this much.
PREPARE_POLL_MS = 1000  # web/src/pages.tsx
START_NOW_POLL_MS = 500  # web/src/start-now.tsx
POLL_S = 0.25  # how often this asks: often enough for each state, not so often it floods the log
PREPARE_LIMIT_S = 3600
START_NOW_LIMIT_S = 1800
UPLOAD_TIMEOUT_S = 600


class SetupError(Exception):
    """A step was refused or didn't finish; what came before is still reported."""


@dataclass
class Changes:
    """Each state seen while waiting, with when it was first seen, in ms from the start."""

    states: list[tuple[str, float]]
    last: dict[str, Any]


def put(url: str, body: dict[str, Any]) -> None:
    """PUT `body` as JSON; a refusal raises HTTPError."""
    request = urllib.request.Request(
        url, json.dumps(body).encode(), {"Content-Type": "application/json"}, method="PUT"
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def upload(base: str, kind: str, path: Path) -> dict[str, Any]:
    """Upload one file as the setup page does; the time until it shows as checked, with the
    server's steps from its Server-Timing header."""
    boundary = uuid.uuid4().hex
    kind_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {kind_type}\r\n\r\n"
        ).encode()
        + path.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(
        f"{base}/api/uploads/{kind}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    start = time.perf_counter()
    row: dict[str, Any] = {"file": path.name, "bytes": len(body)}
    try:
        with urllib.request.urlopen(request, timeout=UPLOAD_TIMEOUT_S) as response:
            answer = json.loads(response.read())
            steps = server_timing.parse(response.headers.get("Server-Timing"))
    except urllib.error.HTTPError as e:
        row.update(error=f"{e.code}: {e.read().decode(errors='replace')[:300]}")
        logger.error(
            "Upload refused", extra={"kind": kind, "file": path.name, "error": row["error"]}
        )
        return row
    except OSError as e:
        row.update(error=str(e))
        logger.error("Could not upload", extra={"kind": kind, "file": path.name, "error": str(e)})
        return row
    row.update(
        id=answer.get("id"),
        total_ms=ms(time.perf_counter(), start),
        steps={k: round(v) for k, v in steps.items()},
        problems=answer.get("problems"),
        error=None,
    )
    return row


def wait_for(
    url: str, state: Callable[[dict[str, Any]], str], done: set[str], limit_s: float
) -> Changes:
    """Ask for `url` until `state` of its answer is one of `done`, noting each state's start."""
    start = time.perf_counter()
    states: list[tuple[str, float]] = []
    last: dict[str, Any] = {}
    while time.perf_counter() - start < limit_s:
        last = ask(url)
        now = state(last)
        if not states or states[-1][0] != now:
            states.append((now, ms(time.perf_counter(), start) or 0))
        if now in done:
            return Changes(states, last)
        time.sleep(POLL_S)
    seen = states[-1][0] if states else "none"
    raise SetupError(f"{url} didn't finish in {limit_s} s; last state {seen}.")


def first_byte_ms(url: str) -> float | None:
    """From asking for the clip to its first bytes: when the sample can start playing."""
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            response.read1(1024)
    except OSError as e:
        logger.error("Could not fetch the sample video", extra={"error": str(e)})
        return None
    return ms(time.perf_counter(), start)


def prepare(base: str, label: str, begin: Callable[[], object] | None = None) -> dict[str, Any]:
    """Prepare the video and voice, by Prepare or by `begin` (a change that prepares again on
    its own), until the sample can be watched, with each of Prepare's steps."""
    logger.info("Timing Prepare", extra={"label": label})
    start = time.perf_counter()
    try:
        (begin or (lambda: ask(base + "/api/prepare", {})))()
        changes = wait_for(
            base + "/api/prepare", lambda s: str(s["state"]), {"done", "failed"}, PREPARE_LIMIT_S
        )
    except (OSError, SetupError) as e:
        return {"what": label, "error": describe(e)}
    finished = ms(time.perf_counter(), start)
    status = changes.last
    if status["state"] == "failed":
        return {"what": label, "error": status.get("error") or "Prepare failed.", "ms": finished}
    sample = first_byte_ms(base + "/api/prepare/clips/sample")
    return {
        "what": label,
        "ms": finished,
        "sample_plays_ms": None if sample is None or finished is None else finished + sample,
        "steps": {s["key"]: s.get("seconds") for s in status.get("steps") or []},
        "states": changes.states,
        "error": None,
    }


def start_now(base: str, person: dict[str, str], label: str) -> dict[str, Any]:
    """Start now with `person`, timed through each of its states to the chat opening, then
    the first prompt after it (which waits for the replies' warm-up) to its first word heard."""
    logger.info("Timing Start now", extra={"label": label, **person})
    start = time.perf_counter()
    try:
        ask(base + "/api/start-now", person)
        changes = wait_for(
            base + "/api/start-now",
            lambda s: "chat open" if s.get("chat_ready") else str(s["state"]),
            {"chat open", "failed"},
            START_NOW_LIMIT_S,
        )
    except (OSError, SetupError) as e:
        return {"what": label, "error": describe(e)}
    if changes.last["state"] == "failed":
        return {"what": label, "error": changes.last.get("error"), "states": changes.states}
    opened = ms(time.perf_counter(), start)
    reply = time_reply.summarize(time_reply.measure(base, PROMPT))
    return {
        "what": label,
        "person": changes.last.get("person"),
        "ms": opened,
        "states": changes.states,
        "reply_warm_up_wait_ms": reply["waited_warm_up_ms"],
        "first_word_heard_ms": reply["first_word_heard_ms"],
        "error": reply["error"],
    }


def describe(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return f"{e.code}: {e.read().decode(errors='replace')[:300]}"
    return str(e)


def nothing_set_up(base: str) -> bool:
    """Whether the app has no photos, recordings or default person yet, so changing its setup
    loses nothing."""
    chosen = ask(base + "/api/start-now").get("chosen")
    if chosen is not None:
        return False
    if not ask(base + "/api/consent").get("agreed"):
        return True  # without consent nothing can have been uploaded
    return not ask(base + "/api/uploads/photos") and not ask(base + "/api/uploads/sounds")


def measure_all(base: str, photos: list[Path], recordings: list[Path]) -> dict[str, Any]:
    """Every step of setup in turn, as a new user would go through it."""
    ask(base + "/api/consent", {"agreed": True})
    photo_rows = [upload(base, "photos", photos[0])]
    sound_rows = [upload(base, "sounds", p) for p in recordings]
    prepares = [prepare(base, "Prepare")]
    if len(photos) > 1:
        second = upload(base, "photos", photos[1])
        photo_rows.append(second)

        def choose() -> None:
            put(base + "/api/uploads/photos/chosen", {"id": second.get("id")})
            ask(base + "/api/prepare", {})

        prepares.append(prepare(base, "Prepare again, another photo", choose))
    if ask(base + "/api/accent").get("available"):
        prepares.append(
            prepare(
                base,
                "Prepare again, another accent",
                lambda: put(base + "/api/accent", {"accent": "british"}),
            )
        )
    else:
        logger.info("Accent change not timed: the voice engine has no accents")
    people = [start_now(base, PEOPLE[0], "Start now"), start_now(base, PEOPLE[1], "Switch person")]
    if not people[-1]["error"]:

        def own_voice() -> None:  # the avatar to speak in the user's voice (R24d)
            put(base + "/api/start-now/own-voice", {"agreed": True})
            ask(base + "/api/prepare", {})

        prepares.append(prepare(base, "Prepare, avatar in your own voice", own_voice))
    return {"photos": photo_rows, "recordings": sound_rows, "prepare": prepares, "people": people}


def upload_table(rows: list[dict[str, Any]], steps: list[str]) -> str:
    return table(
        ["File", "Until checked", *steps, "Problems", "Error"],
        [
            [
                r["file"],
                r.get("total_ms"),
                *[(r.get("steps") or {}).get(s) for s in steps],
                None if r.get("problems") is None else len(r["problems"]),
                r.get("error") or "",
            ]
            for r in rows
        ],
    )


def markdown(results: dict[str, Any]) -> str:
    out = ["# Where the time goes: setup", ""]
    out += [
        "## Photos (Larry's timing 8)",
        "",
        "Milliseconds, from the upload's Server-Timing: `receive` the file arriving, `convert`"
        " HEIC to JPG, `wait` for another photo's checks, `read` the photo, `faces` and"
        " `covered` the face checks (R8), `quality` the light and sharpness (R9), `total` the"
        " server's whole request.",
        "",
        upload_table(
            results["photos"],
            ["receive", "convert", "wait", "read", "faces", "covered", "quality", "total"],
        ),
        "",
        "## Recordings (Larry's timing 9)",
        "",
        "`convert` to WAV (R2), `sound` the sound checks (R10), `speakers` the one-speaker check"
        " (R11), `voice-sample` joining the recordings that passed.",
        "",
        upload_table(
            results["recordings"],
            ["receive", "convert", "sound", "speakers", "voice-sample", "total"],
        ),
        "",
        "## Prepare (Larry's timing 6)",
        "",
        f"Milliseconds from Prepare (or the change) to done, then to the sample's first bytes;"
        f" Prepare's own steps in seconds. The page asks every {PREPARE_POLL_MS} ms, so it can"
        f" show each step up to that much later.",
        "",
    ]
    keys = [k for p in results["prepare"] for k in (p.get("steps") or {})]
    steps = list(dict.fromkeys(keys))
    out.append(
        table(
            ["What", "Done", "Sample plays", *[f"{s} (s)" for s in steps], "Error"],
            [
                [
                    p["what"],
                    p.get("ms"),
                    p.get("sample_plays_ms"),
                    *[(p.get("steps") or {}).get(s) for s in steps],
                    p.get("error") or "",
                ]
                for p in results["prepare"]
            ],
        )
    )
    out += [
        "",
        "## Start now",
        "",
        f"Milliseconds from Start now to each state first seen (asked every {round(POLL_S * 1000)}"
        f" ms; the page asks every {START_NOW_POLL_MS} ms), then the first prompt after it.",
        "",
        table(
            ["What", "Person", "States", "Chat open", "Warm-up wait", "First word heard", "Error"],
            [
                [
                    p["what"],
                    p.get("person"),
                    ", ".join(f"{s} {t}" for s, t in p.get("states") or []),
                    p.get("ms"),
                    p.get("reply_warm_up_wait_ms"),
                    p.get("first_word_heard_ms"),
                    p.get("error") or "",
                ]
                for p in results["people"]
            ],
        ),
    ]
    return "\n".join(out) + "\n"


def failures(results: dict[str, Any]) -> int:
    rows = [r for part in results.values() for r in part]
    return sum(1 for r in rows if r.get("error"))


def run(
    base: str,
    photos: list[Path],
    recordings: list[Path],
    out: Path,
    anyway: bool = False,
) -> int:
    """Time setup on the running app; write the results as JSON and Markdown in `out` and
    print the Markdown."""
    base = base.rstrip("/")
    start = time.perf_counter()
    try:
        ask(base + "/health", timeout=10)
        fresh = nothing_set_up(base)
    except OSError as e:
        logger.error("Could not reach the app", extra={"url": base, "error": str(e)})
        return 1
    if not fresh and not anyway:
        logger.error(
            "The app is already set up; time-setup would change it. Start the app with an empty"
            " data folder, or pass --anyway"
        )
        return 1
    results = measure_all(base, photos, recordings)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report = markdown(results)
    (out / f"setup-{stamp}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out / f"setup-{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {(out / f'setup-{stamp}.md').resolve()} and the .json beside it")
    failed = failures(results)
    logger.info(
        "Setup timed",
        extra={"failed": failed, "duration_ms": round((time.perf_counter() - start) * 1000, 1)},
    )
    return 1 if failed else 0
