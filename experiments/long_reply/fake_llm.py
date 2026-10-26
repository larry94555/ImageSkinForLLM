"""R129: a stand-in for llama-server that writes a known long reply at a set pace. An experiment,
not part of the app.

    python experiments/long_reply/fake_llm.py [--port 8080] [--tokens-per-second 4.5]
        [--first-token-s 1.5]

The app talks to it as it talks to llama-server (its default `llm_url`,
http://127.0.0.1:8080/v1): the chat's streamed reply is the one in replies.py for the prompt's
last user message (the first reply when none matches), written a piece at a time at
`--tokens-per-second`, after `--first-token-s`. The defaults are Gemma 3 4B's pace on 2 threads
measured in R96: 4.5 tokens a second in a cloud session, and the first token 1.5 s after the
prompt once the system prompt is cached. Everything else the app asks for (the warm-up, token
counts, the context window) is answered at once. So every run speaks the same words at the same
pace, and only the voice, the video and the playback differ.
"""

import argparse
import json
import logging
import re
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from replies import PROMPTS, REPLIES

logger = logging.getLogger("fake_llm")

CHARS_PER_TOKEN = 4  # about right for English with Gemma's tokenizer
CONTEXT_TOKENS = 4096  # as deploy/compose.yaml starts llama-server
_PIECE = re.compile(r"\s*\S+")  # a word with the space before it


def reply_for(messages: list[dict[str, Any]]) -> str:
    """The known reply to the last user message, or the first reply when none matches."""
    asked = next(
        (str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"), ""
    )
    for prompt in PROMPTS:
        if prompt in asked:
            return REPLIES[prompt]
    return REPLIES[PROMPTS[0]]


def tokens_in(text: str) -> int:
    return max(1, round(len(text.strip()) / CHARS_PER_TOKEN))


def pieces(text: str) -> list[tuple[str, int]]:
    """The reply as the LLM would send it: a word at a time (with its space and any line breaks
    before it), each with how many tokens it is."""
    return [(m.group(), tokens_in(m.group())) for m in _PIECE.finditer(text)]


def paced(
    text: str,
    tokens_per_second: float,
    first_token_s: float,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[str]:
    """The reply's pieces, each once the time to write its tokens has passed."""
    sleep(first_token_s)
    for piece, n in pieces(text):
        yield piece
        sleep(n / tokens_per_second)


def chunk(content: str | None, finish: str | None = None) -> bytes:
    delta = {} if content is None else {"content": content}
    event = {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(event)}\n\n".encode()


class Handler(BaseHTTPRequestHandler):
    tokens_per_second = 4.5
    first_token_s = 1.5

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base's name
        logger.debug(format, *args)

    def _json(self, body: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - the base's name
        if self.path.rstrip("/") in ("/health", "/v1/health"):
            self._json({"status": "ok"})
        elif self.path.rstrip("/") == "/props":
            self._json({"default_generation_settings": {"n_ctx": CONTEXT_TOKENS}})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802 - the base's name
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json({"error": "not JSON"}, 400)
            return
        if self.path == "/tokenize":
            self._json({"tokens": [0] * tokens_in(str(body.get("content", "")))})
        elif self.path == "/v1/chat/completions":
            self._complete(body)
        else:
            self._json({"error": "not found"}, 404)

    def _complete(self, body: dict[str, Any]) -> None:
        text = reply_for(body.get("messages") or [])
        if not body.get("stream"):  # the warm-up, or anything asked whole
            short = text if (body.get("max_tokens") or 0) > 1 else "The"
            self._json({"choices": [{"message": {"role": "assistant", "content": short}}]})
            return
        start = time.perf_counter()
        logger.info("Writing a reply", extra={"words": len(text.split())})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            for piece in paced(text, self.tokens_per_second, self.first_token_s):
                self.wfile.write(chunk(piece))
                self.wfile.flush()
            self.wfile.write(chunk(None, "stop") + b"data: [DONE]\n\n")
        except (BrokenPipeError, ConnectionResetError):  # the reply was stopped
            logger.info("Reply stopped by the app")
            return
        logger.info(
            "Reply written",
            extra={"duration_ms": round((time.perf_counter() - start) * 1000, 1)},
        )


def serve(port: int, tokens_per_second: float, first_token_s: float) -> ThreadingHTTPServer:
    """Start the stand-in on a background thread and return its server."""
    handler = type(
        "PacedHandler",
        (Handler,),
        {"tokens_per_second": tokens_per_second, "first_token_s": first_token_s},
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, name="fake-llm", daemon=True).start()
    logger.info(
        "Fake LLM listening",
        extra={"port": port, "tokens_per_second": tokens_per_second, "first_s": first_token_s},
    )
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--tokens-per-second", type=float, default=Handler.tokens_per_second)
    parser.add_argument("--first-token-s", type=float, default=Handler.first_token_s)
    args = parser.parse_args()
    from imageskin.logging_setup import setup_logging

    setup_logging()
    server = serve(args.port, args.tokens_per_second, args.first_token_s)
    print(f"Fake LLM on http://127.0.0.1:{args.port}/v1 (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
