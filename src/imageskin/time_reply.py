"""`imageskin time-reply`: where the time goes in a reply (roadmap R96), measured against the
running app over its chat API, as the browser does it but without one. Each prompt is sent,
its clips are followed and downloaded the moment they are listed, and the reply is played
back on paper: clip 1 plays once its first bytes arrive, and each next clip once it has
arrived and the one before has ended. The tables say how long the LLM took (Larry's timing 1),
how long from its first sentence to the first word heard (timing 2), and the gap heard
between sentences (timing 3), with the waits found in the code beside them."""

import json
import logging
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:8000"
DEFAULT_PROMPTS = (
    "Hello! Who are you?",
    "What is the tallest mountain in the world, and how high is it?",
    "Tell me a short story about a cat who learns to swim.",
)
CLIPS_WAIT_S = 10  # as the browser asks: the server answers at once when there is news
NOT_YET_S = 0.05  # how often to ask for the clips before the prompt has listed them
REPLY_LIMIT_S = 600  # a reply that takes longer than this is given up on
PROBE_TIMEOUT_S = 30


class TimingError(Exception):
    """The app couldn't be reached, or refused the prompt."""


@dataclass
class ClipSeen:
    """One clip as the client saw it: client clock seconds, and the server's own times."""

    n: int
    server: dict[str, Any]  # its entry in the clip list
    seen_at: float  # when the list first had it
    first_byte_at: float | None = None
    downloaded_at: float | None = None
    seconds: float | None = None  # how long it plays
    error: str | None = None


@dataclass
class Measured:
    """One prompt's raw times, on the client's clock unless named server."""

    prompt: str
    spoken: bool
    sent_at: float = 0.0
    answered_at: float | None = None
    status: int | None = None
    reply: dict[str, Any] | None = None
    clips: list[ClipSeen] = field(default_factory=list)
    offset: float | None = None  # server clock minus client clock, from the clip lists
    stopped_at: float | None = None  # when Stop was pressed, with --stop
    stop_answered_at: float | None = None
    error: str | None = None


def ask(url: str, body: dict[str, Any] | None = None, timeout: float = 30) -> dict[str, Any]:
    """GET (or POST `body` to) the app's API; a refusal raises HTTPError, as urllib does."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        answer: dict[str, Any] = json.loads(response.read())
        return answer


def clip_seconds(path: Path) -> float | None:
    """How long the clip plays, by ffprobe, or None when it can't tell."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    try:
        done = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
            check=True,
        )
        return float(done.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        logger.warning("Could not tell how long a clip plays", extra={"clip": str(path)})
        return None


def download(base: str, clip: ClipSeen, folder: Path) -> None:
    """Fetch the clip as the browser does, as it is written, noting its first byte and end."""
    path = folder / f"{clip.n}.mp4"
    try:
        with urllib.request.urlopen(base + clip.server["url"], timeout=REPLY_LIMIT_S) as response:
            with path.open("wb") as f:
                while chunk := response.read(64 * 1024):
                    if clip.first_byte_at is None:
                        clip.first_byte_at = time.perf_counter()
                    f.write(chunk)
        clip.downloaded_at = time.perf_counter()
    except urllib.error.HTTPError as e:
        clip.error = str(e)
        if e.code == 404:  # removed by Stop or a newer prompt, as the browser would find too
            logger.info("Clip gone before it was downloaded", extra={"clip": clip.n})
        else:
            logger.error("Could not download a clip", extra={"clip": clip.n, "error": str(e)})
        return
    except (OSError, urllib.error.URLError) as e:
        clip.error = str(e)
        logger.error("Could not download a clip", extra={"clip": clip.n, "error": str(e)})
        return
    clip.seconds = clip_seconds(path)
    if clip.seconds is None:
        # A clip that wasn't written front to back (not a progressive MP4) reads well only
        # whole: fetched again now that it is, for its length alone.
        try:
            with urllib.request.urlopen(base + clip.server["url"], timeout=60) as response:
                path.write_bytes(response.read())
        except (OSError, urllib.error.URLError):
            return
        clip.seconds = clip_seconds(path)


def measure(base: str, prompt: str, spoken: bool = False, stop: bool = False) -> Measured:
    """Send the prompt and follow its clips until the reply is done. With `stop`, Stop is
    pressed as soon as the first clip is listed."""
    reply_id = uuid.uuid4().hex
    measured = Measured(prompt, spoken)
    body = {"prompt": prompt, "reply_id": reply_id, "spoken": spoken}

    def send() -> None:
        try:
            measured.reply = ask(base + "/api/chat", body, timeout=REPLY_LIMIT_S)
            measured.status = 200
        except urllib.error.HTTPError as e:
            measured.status = e.code
            measured.error = e.read().decode(errors="replace")[:300]
        except OSError as e:
            measured.error = str(e)
        measured.answered_at = time.perf_counter()

    start = time.perf_counter()
    logger.info("Timing a reply", extra={"prompt_chars": len(prompt), "spoken": spoken})
    measured.sent_at = start
    sender = threading.Thread(target=send, name="time-reply-send", daemon=True)
    sender.start()
    downloads: list[threading.Thread] = []
    with tempfile.TemporaryDirectory(prefix="time-reply-") as folder:
        follow(base, reply_id, measured, sender, downloads, Path(folder), stop)
        sender.join(REPLY_LIMIT_S)
        for d in downloads:
            d.join(REPLY_LIMIT_S)
    if stop and measured.status == 409:  # stopped, as it was meant to be
        measured.error = None
    if measured.status is None and measured.error is None:
        measured.error = "The app didn't answer in time."
    logger.info(
        "Reply timed",
        extra={
            "status": measured.status,
            "clips": len(measured.clips),
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return measured


def follow(
    base: str,
    reply_id: str,
    measured: Measured,
    sender: threading.Thread,
    downloads: list[threading.Thread],
    folder: Path,
    stop: bool,
) -> None:
    """Ask for the reply's clips as the browser does, starting each one's download the moment
    it is listed, until the reply is done, or the prompt is answered with no clips."""
    url = f"{base}/api/chat/clips/{reply_id}"
    limit = time.perf_counter() + REPLY_LIMIT_S
    while time.perf_counter() < limit:
        try:
            listed = ask(f"{url}?known={len(measured.clips)}&wait={CLIPS_WAIT_S}", timeout=60)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                measured.error = f"The clips were refused ({e.code})."
                return
            if not sender.is_alive():  # answered without clips, or they were taken back
                return
            time.sleep(NOT_YET_S)  # not listed yet: the prompt may wait for one before it
            continue
        except OSError as e:
            measured.error = f"Could not reach the app for the clips ({e})."
            return
        now = time.perf_counter()
        # The server's `now` is from before the answer reached here, so the largest difference
        # seen is the closest to the true one.
        offset = listed["now"] - now
        measured.offset = offset if measured.offset is None else max(measured.offset, offset)
        for entry in listed["clips"][len(measured.clips) :]:
            clip = ClipSeen(len(measured.clips) + 1, entry, now)
            measured.clips.append(clip)
            d = threading.Thread(target=download, args=(base, clip, folder), daemon=True)
            d.start()
            downloads.append(d)
        if stop and measured.clips and measured.stopped_at is None:
            press_stop(base, reply_id, measured)
            return
        if listed["done"] or listed["error"]:
            for clip in measured.clips:  # the server's last word on each clip's times
                if clip.n <= len(listed["clips"]):
                    clip.server = listed["clips"][clip.n - 1]
            return
    measured.error = "The reply's clips didn't finish in time."


def press_stop(base: str, reply_id: str, measured: Measured) -> None:
    measured.stopped_at = time.perf_counter()
    try:
        ask(f"{base}/api/chat/clips/{reply_id}/stop", {})
    except OSError as e:
        measured.error = f"Stop failed ({e})."
        return
    measured.stop_answered_at = time.perf_counter()


def ms(later: float | None, earlier: float | None) -> float | None:
    if later is None or earlier is None:
        return None
    return round((later - earlier) * 1000)


def summarize(m: Measured) -> dict[str, Any]:
    """The prompt's times in milliseconds, from the prompt being sent, with each clip's row
    and the reply played back on paper."""
    times = (m.reply or {}).get("timings") or {}
    offset = m.offset
    if offset is None and times.get("received_at") is not None:
        offset = times["received_at"] - m.sent_at  # no clips: as if the request took no time
    zero = m.sent_at + (offset or 0.0)  # the send, on the server's clock

    def at(name: str) -> float | None:
        return ms(times.get(name), zero)

    rows = []
    previous_end = None
    first_play = None
    for clip in m.clips:
        s = clip.server
        first_byte = None if clip.first_byte_at is None else clip.first_byte_at + (offset or 0)
        play = (
            first_byte
            if previous_end is None or first_byte is None
            else max(first_byte, previous_end)
        )
        end = None if play is None or clip.seconds is None else play + clip.seconds
        rows.append(
            {
                "clip": clip.n,
                "sentence_ms": ms(s.get("sentence_at"), zero),
                "waited_ms": ms(s.get("started_at"), s.get("sentence_at")),
                "voice_ms": ms(s.get("ready_at"), s.get("started_at")),
                "video_ms": ms(s.get("whole_at"), s.get("ready_at")),
                "listed_ms": ms(s.get("ready_at"), zero),
                "seen_ms": ms(clip.seen_at, m.sent_at),
                "first_byte_ms": ms(first_byte, zero),
                "downloaded_ms": ms(clip.downloaded_at, m.sent_at),
                "seconds": None if clip.seconds is None else round(clip.seconds, 2),
                "plays_ms": ms(play, zero),
                # The gap heard after the clip before, and whether this clip was late for it.
                "gap_ms": ms(play, previous_end),
                "late": previous_end is not None
                and first_byte is not None
                and first_byte > previous_end,
                "error": clip.error,
            }
        )
        if first_play is None:
            first_play = play
        previous_end = end
    llm = times.get("llm") or {}
    return {
        "prompt": m.prompt,
        "spoken": m.spoken,
        "status": m.status,
        "error": m.error,
        "streamed": (m.reply or {}).get("streamed"),
        # The waits before the prompt reaches the LLM.
        "reached_server_ms": at("received_at"),
        "waited_warm_up_ms": times.get("waited_warm_up_ms"),
        "waited_turn_ms": times.get("waited_turn_ms"),
        "history_tokens": times.get("history_tokens"),
        # Larry's timing 1: the LLM.
        "prompt_sent_ms": at("prompt_sent_at"),
        "first_token_ms": at("first_token_at"),
        "first_sentence_ms": at("first_sentence_at"),
        "last_token_ms": at("last_token_at"),
        "answered_ms": ms(m.answered_at, m.sent_at),
        "llm": llm,
        # Larry's timing 2: from the first sentence to the first word heard.
        "first_word_heard_ms": ms(first_play, zero),
        "first_sentence_to_heard_ms": ms(first_play, times.get("first_sentence_at")),
        "stop_answered_ms": ms(m.stop_answered_at, m.stopped_at),
        "next_prompt_taken_after_stop_ms": ms(m.answered_at, m.stopped_at),
        # Larry's timing 3: the clips, with each one's gap.
        "clips": rows,
    }


def cell(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else ""
    return str(value)


def table(header: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def markdown(results: list[dict[str, Any]], llm_name: str) -> str:
    """The results as tables, all in milliseconds from the prompt being sent."""
    out = [f"# Where the time goes: a reply ({llm_name})", ""]
    out.append("All times in milliseconds from the prompt being sent.")
    out.append("")
    reply_rows = []
    for i, r in enumerate(results, 1):
        llm = r["llm"]
        reply_rows.append(
            [
                i,
                "spoken" if r["spoken"] else "typed",
                r["waited_warm_up_ms"],
                r["waited_turn_ms"],
                r["history_tokens"],
                r["prompt_sent_ms"],
                llm.get("prompt_n"),
                llm.get("cache_n"),
                llm.get("prompt_per_second") and round(llm["prompt_per_second"], 1),
                r["first_token_ms"],
                r["first_sentence_ms"],
                r["last_token_ms"],
                llm.get("predicted_n"),
                llm.get("predicted_per_second") and round(llm["predicted_per_second"], 1),
                r["first_sentence_to_heard_ms"],
                r["first_word_heard_ms"],
            ]
        )
    out.append(
        table(
            [
                "Reply",
                "Prompt",
                "Warm-up wait",
                "Turn wait",
                "History tokens",
                "Reached LLM",
                "Prompt tokens read",
                "Reused from cache",
                "Read tokens/s",
                "First token",
                "First sentence",
                "Last token",
                "Tokens written",
                "Written tokens/s",
                "First sentence to heard",
                "First word heard",
            ],
            reply_rows,
        )
    )
    for i, r in enumerate(results, 1):
        out += ["", f"## Reply {i}: {r['prompt']}", ""]
        if r["error"]:
            out += [f"Error: {r['error']}", ""]
        if r["stop_answered_ms"] is not None:
            out += [
                f"Stop answered in {r['stop_answered_ms']} ms; the next prompt could be taken "
                f"{r['next_prompt_taken_after_stop_ms']} ms after Stop.",
                "",
            ]
        out.append(
            table(
                [
                    "Clip",
                    "Sentence",
                    "Waited",
                    "Voice",
                    "Video",
                    "Listed",
                    "Seen",
                    "First byte",
                    "Downloaded",
                    "Seconds",
                    "Plays",
                    "Gap",
                    "Late",
                ],
                [
                    [
                        c["clip"],
                        c["sentence_ms"],
                        c["waited_ms"],
                        c["voice_ms"],
                        c["video_ms"],
                        c["listed_ms"],
                        c["seen_ms"],
                        c["first_byte_ms"],
                        c["downloaded_ms"],
                        c["seconds"],
                        c["plays_ms"],
                        c["gap_ms"],
                        c["late"],
                    ]
                    for c in r["clips"]
                ],
            )
        )
    return "\n".join(out) + "\n"


def llm_name(base: str) -> str:
    """The LLM the app answers with, as its Settings page names it."""
    try:
        choice = ask(base + "/api/llm")
    except (OSError, ValueError):
        return "unknown LLM"
    for p in choice.get("providers", []):
        if p.get("id") == choice.get("provider"):
            model = p.get("model") or p.get("default_model")
            return f"{p.get('label')}, {model}" if model else str(p.get("label"))
    return str(choice.get("provider") or "unknown LLM")


def run(
    base: str,
    prompts: list[str],
    out: Path,
    spoken: int | None = None,
    stop: bool = False,
) -> int:
    """Time each prompt in turn, the `spoken` one (from 1) as if said with Hold to talk, then
    with --stop one more, stopped at its first clip; write the results as JSON and Markdown in
    `out` and print the Markdown."""
    base = base.rstrip("/")
    start = time.perf_counter()
    try:
        ask(base + "/health", timeout=10)
    except OSError as e:
        logger.error("Could not reach the app", extra={"url": base, "error": str(e)})
        return 1
    name = llm_name(base)
    results = []
    plan = [(p, i == spoken, False) for i, p in enumerate(prompts, 1)]
    if stop:
        plan.append((prompts[-1], False, True))
    for prompt, said, stopped in plan:
        results.append(summarize(measure(base, prompt, said, stopped)))
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report = markdown(results, name)
    (out / f"reply-{stamp}.json").write_text(
        json.dumps({"llm": name, "results": results}, indent=2), encoding="utf-8"
    )
    (out / f"reply-{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {(out / f'reply-{stamp}.md').resolve()} and the .json beside it")
    failed = sum(1 for r in results if r["error"])
    logger.info(
        "Replies timed",
        extra={
            "replies": len(results),
            "failed": failed,
            "llm": name,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return 1 if failed and failed == len(results) else 0
