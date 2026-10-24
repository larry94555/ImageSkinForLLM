"""`imageskin time-pdf`: where the time goes in the wiki and the answers from it (roadmap R96a),
measured against the running app over its API, as the Manage Content page and the chat do it
but without a browser. The PDF is uploaded, read and built into a wiki (Larry's timing 4), with
each wiki part's and outline step's time and llama-server's own timings, which the wiki saves
with its pages; a question is asked while the wiki is built, which waits for the wiki's request;
then questions about the PDF are answered from the wiki (timing 5), and the longer requests
built on it ("What can you talk about?", Teach me, Quiz me and the assessment) are timed to
their first word heard, as `imageskin time-reply` times a reply."""

import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from imageskin import time_reply
from imageskin.time_reply import TimingError, ask, table

logger = logging.getLogger(__name__)

# Five questions about the sample PDF, experiments/speed/sample.pdf.
DEFAULT_QUESTIONS = (
    "What is a prime number?",
    "What did Euler find about the primes and the zeta function?",
    "How many primes are there below one million?",
    "What does the Riemann hypothesis say?",
    "How is the zeta function used in physics?",
)
POLL_S = 0.1  # how often the reading and the wiki are asked how far they have got
BUILD_LIMIT_S = 4 * 60 * 60  # a PDF that takes longer than this to read and build is given up
UPLOAD_TIMEOUT_S = 120
LESSONS_LIMIT_S = 30 * 60  # how long the first lesson parts written ahead are waited for


def upload(base: str, path: Path, pdf_id: str | None = None) -> dict[str, Any]:
    """Add the PDF (or, with `pdf_id`, replace that one) as the Manage Content page does."""
    boundary = uuid.uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{path.name}"\r\nContent-Type: application/pdf\r\n\r\n'
        ).encode()
        + path.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    url = base + "/api/content" + (f"/{pdf_id}" if pdf_id else "")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="PUT" if pdf_id else "POST",
    )
    with urllib.request.urlopen(request, timeout=UPLOAD_TIMEOUT_S) as response:
        added: dict[str, Any] = json.loads(response.read())
        return added


def remove(base: str, pdf_id: str) -> None:
    request = urllib.request.Request(base + f"/api/content/{pdf_id}", method="DELETE")
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
    except OSError as e:
        logger.error("Could not remove the timed PDF", extra={"id": pdf_id, "error": str(e)})


def wait_for(base: str, path: str, pdf_id: str, until: set[str]) -> tuple[dict[str, Any], float]:
    """Ask `path` (the readings' or the wiki builds' statuses) until this PDF's state is one of
    `until`; its last status, and when that was seen."""
    limit = time.perf_counter() + BUILD_LIMIT_S
    while time.perf_counter() < limit:
        status = ask(base + path).get(pdf_id)
        if status is not None and status["state"] in until:
            return status, time.perf_counter()
        time.sleep(POLL_S)
    raise TimingError(f"The PDF wasn't done in {BUILD_LIMIT_S // 3600} hours.")


def process(
    base: str, path: Path, during: str | None, added: list[str], pdf_id: str | None = None
) -> dict[str, Any]:
    """Upload the PDF (or replace `pdf_id` with it), noting its id in `added`, wait for it to
    be read and its wiki built, and ask `during` while the wiki is being built. Times in
    milliseconds from the upload."""
    start = time.perf_counter()
    pdf = upload(base, path, pdf_id)
    uploaded = time.perf_counter()
    if pdf["id"] not in added:
        added.append(pdf["id"])
    logger.info("Timing a PDF", extra={"id": pdf["id"], "replaced": pdf_id is not None})
    read, read_at = wait_for(base, "/api/content/readings", pdf["id"], {"done", "failed"})
    if read["state"] == "failed":
        raise TimingError(f"The PDF couldn't be read: {read.get('error')}")
    asked = None
    if during:
        # Asked once the wiki is under way, so it waits for the wiki's current LLM request.
        wait_for(base, "/api/wiki/builds", pdf["id"], {"building", "waiting", "done", "failed"})
        asked = time_reply.summarize(time_reply.measure(base, during))
    built, built_at = wait_for(base, "/api/wiki/builds", pdf["id"], {"done", "failed"})
    if built["state"] == "failed":
        raise TimingError(f"The wiki couldn't be built: {built.get('error')}")
    wiki = ask(base + f"/api/content/{pdf['id']}/wiki")
    return {
        "pdf_id": pdf["id"],
        "name": pdf["name"],
        "bytes": pdf["size"],
        "upload_ms": time_reply.ms(uploaded, start),
        "read_ms": time_reply.ms(read_at, uploaded),
        "pages": read["pages"],
        "kind": read["kind"],
        "counts": read["counts"],
        "wiki_ms": time_reply.ms(built_at, read_at),
        "total_ms": time_reply.ms(built_at, start),
        "wiki_built_s": wiki.get("duration_s"),  # the build alone, by the server's clock
        "parts": wiki["parts"],
        "wiki_pages": len(wiki["pages"]),
        "topic": wiki["pages"][0]["title"] if wiki["pages"] else None,
        "steps": wiki.get("timings") or [],
        "asked_during_build": asked,
    }


def wait_for_lessons(base: str) -> float | None:
    """Wait for the first lesson parts written ahead once the wiki is built (R98a), so Teach me
    is timed as a participant who picks a topic later finds it. Milliseconds waited, or None
    when the app writes none (Teach me off, or an app from before R98a)."""
    start = time.perf_counter()
    while time.perf_counter() < start + LESSONS_LIMIT_S:
        try:
            status = ask(base + "/api/lessons")
        except urllib.error.HTTPError:
            return None
        if not status.get("wanted"):
            return None
        if status.get("ready"):  # every topic's part saved for the wiki as it is now
            waited = time_reply.ms(time.perf_counter(), start)
            logger.info(
                "Lessons written ahead", extra={"saved": len(status["saved"]), "wait_ms": waited}
            )
            return waited
        time.sleep(POLL_S)
    logger.warning("Lessons not written ahead in time", extra={"limit_s": LESSONS_LIMIT_S})
    return time_reply.ms(time.perf_counter(), start)


def step_rows(steps: list[dict[str, Any]]) -> list[list[object]]:
    """One row a wiki part or outline step, with llama-server's timings summed over its
    requests (a part whose answer couldn't be used is asked twice)."""
    rows: list[list[object]] = []
    for s in steps:
        requests = s["requests"]

        def total(key: str, rs: list[dict[str, Any]] = requests) -> float:
            return float(sum(r.get(key, 0) for r in rs))

        read_ms, written_ms = total("prompt_ms"), total("predicted_ms")
        rows.append(
            [
                "Topics" if s["stage"] == "topics" else "Outline",
                s["step"],
                round(s["duration_ms"]),
                round(s["ended_ms"]),
                len(requests),
                int(total("prompt_n")),
                int(total("cache_n")),
                round(total("prompt_n") * 1000 / read_ms, 1) if read_ms else None,
                int(total("predicted_n")),
                round(total("predicted_n") * 1000 / written_ms, 1) if written_ms else None,
            ]
        )
    return rows


def stage_totals(steps: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Each stage's steps, time and tokens, for the summary."""
    totals: dict[str, dict[str, float]] = {}
    for s in steps:
        t = totals.setdefault(
            s["stage"], {"steps": 0, "ms": 0, "prompt_n": 0, "cache_n": 0, "predicted_n": 0}
        )
        t["steps"] += 1
        t["ms"] += s["duration_ms"]
        for r in s["requests"]:
            for key in ("prompt_n", "cache_n", "predicted_n"):
                t[key] += r.get(key, 0)
    return totals


def pdf_markdown(p: dict[str, Any], title: str) -> list[str]:
    counts = ", ".join(f"{n} {kind}s" for kind, n in (p["counts"] or {}).items() if n)
    out = [
        f"## {title}: {p['name']}",
        "",
        f"{p['pages']} pages read as {p['kind']} ({counts}); {p['parts']} wiki parts, "
        f"{p['wiki_pages']} wiki topics. All times in milliseconds from the upload.",
        "",
        table(
            ["Upload", "Reading", "Wiki", "Total", "Wiki build (server)"],
            [
                [
                    p["upload_ms"],
                    p["read_ms"],
                    p["wiki_ms"],
                    p["total_ms"],
                    None if p["wiki_built_s"] is None else round(p["wiki_built_s"] * 1000),
                ]
            ],
        ),
        "",
    ]
    totals = stage_totals(p["steps"])
    if totals:
        out += [
            table(
                ["Stage", "Steps", "Took", "Prompt tokens read", "Reused", "Tokens written"],
                [
                    [
                        stage.capitalize(),
                        int(t["steps"]),
                        round(t["ms"]),
                        int(t["prompt_n"]),
                        int(t["cache_n"]),
                        int(t["predicted_n"]),
                    ]
                    for stage, t in totals.items()
                ],
            ),
            "",
            table(
                [
                    "Stage",
                    "Step",
                    "Took",
                    "Ended",
                    "Requests",
                    "Prompt tokens read",
                    "Reused from cache",
                    "Read tokens/s",
                    "Tokens written",
                    "Written tokens/s",
                ],
                step_rows(p["steps"]),
            ),
            "",
        ]
    return out


def markdown(results: dict[str, Any], llm_name: str) -> str:
    out = [f"# Where the time goes: the wiki and answers from it ({llm_name})", ""]
    out += pdf_markdown(results["pdf"], "The PDF")
    during = results["pdf"]["asked_during_build"]
    if during is not None:
        out += ["## Asked while the wiki was built", ""]
        out += time_reply.replies_markdown([during], "###")
        out.append("")
    out += ["## Answers from the wiki", "", "All times in milliseconds from the prompt being sent."]
    if results.get("lessons_ms") is not None:
        out += [
            "",
            f"The longer requests were asked once the lessons written ahead were saved,"
            f" {round(results['lessons_ms'])} ms after the last question was answered.",
        ]
    out += [""] + time_reply.replies_markdown(results["answers"], "###")
    if results.get("replaced"):
        out += [""] + pdf_markdown(results["replaced"], "The PDF replaced by itself")
    return "\n".join(out) + "\n"


def longer_requests(topic: str | None) -> list[str]:
    """The requests built on the wiki, each on its first topic where it takes one."""
    asks = ["What can you talk about?"]
    if topic:
        asks += [f"Teach me about {topic}", f"Quiz me on {topic}"]
    return asks + ["Assess me"]


def run(
    base: str,
    path: Path,
    questions: list[str],
    out: Path,
    spoken: int | None = None,
    replace: bool = False,
    keep: bool = False,
) -> int:
    """Time the PDF and the questions (the `spoken` one, from 1, as if said with Hold to talk),
    then the longer requests; with `replace`, the PDF replaced by itself and rebuilt. Writes
    the results as JSON and Markdown in `out` and prints the Markdown. The PDF is removed again
    unless `keep`."""
    base = base.rstrip("/")
    start = time.perf_counter()
    try:
        ask(base + "/health", timeout=10)
    except OSError as e:
        logger.error("Could not reach the app", extra={"url": base, "error": str(e)})
        return 1
    name = time_reply.llm_name(base)
    results: dict[str, Any] = {"llm": name, "pdf": None, "answers": [], "replaced": None}
    added: list[str] = []
    try:
        results["pdf"] = process(base, path, questions[0] if questions else None, added)
        prompts = [(q, i == spoken) for i, q in enumerate(questions, 1)]
        longer = [(q, False) for q in longer_requests(results["pdf"]["topic"])]
        for n, (prompt, said) in enumerate(prompts + longer):
            if n == len(prompts):  # Teach me after its first parts are written (R98a)
                results["lessons_ms"] = wait_for_lessons(base)
            results["answers"].append(time_reply.summarize(time_reply.measure(base, prompt, said)))
        if replace:
            results["replaced"] = process(base, path, None, added, results["pdf"]["pdf_id"])
    except (TimingError, OSError, KeyError, ValueError) as e:
        logger.error("Could not time the PDF", extra={"error": str(e)})
        if results["pdf"] is None:
            return 1
        results["error"] = str(e)
    finally:
        for pdf_id in [] if keep else added:
            remove(base, pdf_id)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report = markdown(results, name)
    (out / f"pdf-{stamp}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out / f"pdf-{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {(out / f'pdf-{stamp}.md').resolve()} and the .json beside it")
    during = results["pdf"]["asked_during_build"]
    failed = sum(1 for r in results["answers"] if r["error"]) + bool(results.get("error"))
    failed += bool(during and during["error"])
    logger.info(
        "PDF timed",
        extra={
            "answers": len(results["answers"]),
            "failed": failed,
            "llm": name,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return 1 if failed else 0
