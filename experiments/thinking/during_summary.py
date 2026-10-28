"""R147: a question asked while the conversation is being summarized.

Fills the app's chat (`Conversation`, wired as the app wires it, with `RepliesFirst` and
`wait_until_idle`) with turns until one more reply passes half the context window, asks that
reply, which starts a summary, and at once asks another question. Prints how long the second
question took to its first token and what llama-server read and reused for it, then how long
the summary took to finish.

    python experiments/thinking/during_summary.py --url http://127.0.0.1:8080/v1
"""

import argparse
import json
import logging
import time
from typing import Any

import thinking

from imageskin import chat
from imageskin.chat import Conversation, LlmClient, LlmSettings, Turn, wait_until_idle
from imageskin.replies_first import RepliesFirst

FILLER = [
    Turn("user", "Tell me about primes and the zeta function. " * 8),
    Turn("assistant", "Primes are numbers divisible only by one and themselves. " * 6),
]
# Then a short exchange, until the history is this close to half the window, so the next reply
# passes it.
SHORT = [Turn("user", "And then?"), Turn("assistant", "Then more primes.")]
MARGIN = 15


def conversation(client: Any, url: str, find: thinking.Find) -> Conversation:
    replies = RepliesFirst(lambda: wait_until_idle(url))
    return Conversation(
        replies.asking(client.ask, lambda: True),
        client.context_tokens,
        client.count,
        replies.streaming(client.stream, lambda: True),
        find=find,
        summarize=replies.wiki(client.ask),
    )


def run(client: Any, talk: Conversation) -> dict[str, Any]:
    budget = int(client.context_tokens() * chat.HISTORY_SHARE)
    for turns in (FILLER, SHORT):
        while chat.history_tokens(None, [*talk._turns, *turns], client.count) < budget - MARGIN:
            talk._turns += turns  # noqa: SLF001 — an experiment, filling the history
    start = time.perf_counter()
    talk.send("What is a prime number?", on_sentence=lambda s: None)
    passing_ms = round((time.perf_counter() - start) * 1000)
    summarizing = talk.summarizing()
    row = thinking.ask(talk, 2, "What is the Basel problem?", ("square", "pi"))
    start = time.perf_counter()
    talk.wait()
    return {
        "reply_passing_the_budget_ms": passing_ms,
        "summary_started": summarizing,
        "question_during_summary": row,
        "summary_finished_after_ms": round((time.perf_counter() - start) * 1000),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--pdf", default=thinking.SAMPLE_PDF)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    client = LlmClient(LlmSettings(url=args.url))
    talk = conversation(client, args.url, thinking.sample_lookup(args.pdf))
    print(json.dumps(run(client, talk), indent=1))


if __name__ == "__main__":
    main()
