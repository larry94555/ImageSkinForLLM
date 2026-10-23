"""R98: build a PDF's wiki against a running llama-server, as the app does but without it, and
keep every request the wiki makes: its prompt, its answer and llama-server's timings.

    python experiments/speed/wiki_requests.py experiments/speed/sample.pdf out.json \
        [--url http://127.0.0.1:8080/v1] [--label "after R98"]

Run it on two branches against the same llama-server to compare their wikis: the time, the
tokens read, reused and written, and the topics and outline found. It prints a summary and
writes everything to the JSON file.
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from imageskin import reply_times
from imageskin.chat import LlmClient, LlmSettings
from imageskin.pdf_reading import read_pdf
from imageskin.wiki import TOPICS_SCHEMA, WIKI_REPLY_TOKENS, build_wiki
from imageskin.wiki_outline import OUTLINE_REPLY_TOKENS, Entry, Outliner


def titles(entries: list[Entry], depth: int = 0) -> list[str]:
    return [
        line
        for e in entries
        for line in [
            "  " * depth + e.title + (" *" if e.detail else ""),
            *titles(e.entries, depth + 1),
        ]
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    client = LlmClient(LlmSettings(url=args.url, timeout_s=1800))
    pieces = [asdict(p) for p in read_pdf(args.pdf).pieces]
    kept: list[dict[str, Any]] = []
    timings: list[dict[str, Any]] = []
    reply_times.requests.set(timings)

    def record(stage: str, messages: list[dict[str, str]], answer: str) -> None:
        last = timings[-1] if timings else {}
        kept.append({"stage": stage, "messages": messages, "answer": answer, **last})
        with args.out.with_suffix(".jsonl").open("a") as f:  # as it goes, to look at meanwhile
            f.write(json.dumps(kept[-1]) + "\n")
        print(
            f"{stage:8} {len(kept):3}  {last.get('duration_ms', 0) / 1000:6.1f} s"
            f"  read {last.get('prompt_n', '?'):>5}  reused {last.get('cache_n', '?'):>5}"
            f"  written {last.get('predicted_n', '?'):>4}",
            flush=True,
        )

    def ask_topics(messages: list[dict[str, str]]) -> str:
        answer = client.ask(messages, max_tokens=WIKI_REPLY_TOKENS, schema=TOPICS_SCHEMA)
        record("topics", messages, answer)
        return answer

    def ask_outline(messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        answer = client.ask(messages, max_tokens=OUTLINE_REPLY_TOKENS, schema=schema)
        record("outline", messages, answer)
        return answer

    start = time.perf_counter()
    wiki = build_wiki("pdf", pieces, ask_topics, client.count, client.context_tokens())
    topics_s = time.perf_counter() - start
    outline = Outliner("pdf", ask_outline, client.count, client.context_tokens()).outline(
        wiki.pages, pieces
    )
    total_s = time.perf_counter() - start

    def totals(stage: str) -> dict[str, Any]:
        rows = [r for r in kept if r["stage"] == stage]
        return {
            "requests": len(rows),
            "read": sum(r.get("prompt_n", 0) for r in rows),
            "reused": sum(r.get("cache_n", 0) for r in rows),
            "written": sum(r.get("predicted_n", 0) for r in rows),
            "seconds": round(sum(r.get("duration_ms", 0) for r in rows) / 1000, 1),
        }

    result = {
        "label": args.label,
        "pdf": args.pdf.name,
        "parts": wiki.parts,
        "topics_s": round(topics_s, 1),
        "total_s": round(total_s, 1),
        "totals": {"topics": totals("topics"), "outline": totals("outline")},
        "topics": [p.title for p in wiki.pages],
        "outline": titles(outline),
        "requests": kept,
    }
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "requests"}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
