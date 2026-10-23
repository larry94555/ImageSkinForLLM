"""R99: a reply asked while the wiki is built, with and without replies going first.

Runs the app's own wiki builder on the sample PDF against a running llama-server, and asks a
reply, as the chat streams it, `--delay` seconds into the wiki's first part. With `--first` the
reply goes through `RepliesFirst`, as the app now does; without it, the two share llama-server
as before. Also asks the same reply with the LLM idle first, as the usual time. Prints a JSON
line per run with the reply's first token, first sentence and last token (ms from being sent),
llama-server's timings, and when the wiki's first part was done.

    python experiments/speed/reply_during_wiki.py --url http://127.0.0.1:8080/v1 [--first]
"""

import argparse
import json
import logging
import re
import threading
import time
from contextlib import nullcontext
from dataclasses import asdict
from pathlib import Path
from typing import Any

from imageskin import reply_times
from imageskin.app import wiki_builder
from imageskin.chat import LlmCancelled, LlmClient, LlmError, LlmSettings, ask_stop, system_message
from imageskin.pdf_reading import read_pdf
from imageskin.replies_first import RepliesFirst
from imageskin.reply_times import ReplyTimes

PROMPT = "What is a prime number?"
SENTENCE_END = re.compile(r"[.!?](\s|$)")


def reply(client: LlmClient, replies: RepliesFirst | None) -> dict[str, Any]:
    times = ReplyTimes(received_at=time.perf_counter())
    token = reply_times.current.set(times)
    start = time.perf_counter()
    first_token = first_sentence = None
    text = ""
    try:
        with replies.reply() if replies is not None else nullcontext():
            messages = [system_message(None), {"role": "user", "content": PROMPT}]
            for piece in client.stream(messages):
                now = round((time.perf_counter() - start) * 1000)
                first_token = first_token or now
                text += piece
                if first_sentence is None and SENTENCE_END.search(text):
                    first_sentence = now
    finally:
        reply_times.current.reset(token)
    return {
        "first_token_ms": first_token,
        "first_sentence_ms": first_sentence,
        "last_token_ms": round((time.perf_counter() - start) * 1000),
        "llm": times.llm,
        "reply": text,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--pdf", type=Path, default=Path(__file__).with_name("sample.pdf"))
    parser.add_argument("--delay", type=float, default=20.0)
    parser.add_argument("--first", action="store_true", help="replies go first (R99)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(relativeCreated)8.0f ms %(message)s")

    settings = LlmSettings(url=args.url)
    client = LlmClient(settings)
    replies = RepliesFirst() if args.first else None
    pieces = [asdict(p) for p in read_pdf(args.pdf).pieces]
    idle = reply(client, replies)
    print(json.dumps({"run": "idle", **idle}), flush=True)

    build = wiki_builder(settings, client, None, replies)
    stop = threading.Event()
    started = time.perf_counter()
    parts: list[float] = []

    def progress(part: int, total: int) -> None:
        if part:
            parts.append(round(time.perf_counter() - started, 1))
            if part == 1:
                stop.set()  # the first part is enough; the rest is cut off

    def wait(error: LlmError, part: int, total: int) -> None:
        raise error

    def run() -> None:
        token = ask_stop.set(stop)
        try:
            build("sample", pieces, progress, wait)
        except LlmCancelled:
            pass
        finally:
            ask_stop.reset(token)

    wiki = threading.Thread(target=run)
    wiki.start()
    time.sleep(args.delay)
    during = reply(client, replies)
    print(json.dumps({"run": "during wiki", "first": args.first, **during}), flush=True)
    wiki.join()
    print(json.dumps({"run": "wiki", "first_part_done_s": parts[:1]}), flush=True)


if __name__ == "__main__":
    main()
