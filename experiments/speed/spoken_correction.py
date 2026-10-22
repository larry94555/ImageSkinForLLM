"""The spoken question's check before and after R101, timed against llama-server (R96).

Run from the repository with llama-server on http://127.0.0.1:8080 and the old spoken.py:
    git show main:src/imageskin/spoken.py > /tmp/spoken_old.py
    python experiments/speed/spoken_correction.py /tmp/spoken_old.py
"""

import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType

from imageskin import spoken
from imageskin.chat import FOUND_END, FOUND_START, LlmClient, LlmSettings

QUESTIONS = [
    "What did Oiler multiply over?",
    "Tell me about the boiler product",
    "How long does prepare take?",
    "Who are you?",
]


def load(path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location("spoken_old", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(old_path: str) -> None:
    client = LlmClient(LlmSettings(url="http://127.0.0.1:8080/v1"))

    def write(instruction: str, material: list[str]) -> str:
        """As Conversation.write asks: the material quoted before the instruction."""
        if material:
            quoted = "".join(f"- {m}\n" for m in material)
            instruction = f"{FOUND_START}\n<<<\n{quoted}>>>\n{FOUND_END}\n{instruction}"
        return client.ask([{"role": "user", "content": instruction}])

    # 100 content words: two names, then the roadmap's headings as a stand-in for a wiki.
    roadmap = Path("docs/requirements/roadmap.md").read_text(encoding="utf-8").splitlines()
    titles = [{"title": line[4:], "summary": ""} for line in roadmap if line.startswith("### ")]
    terms = ["Euler", "Riemann", *spoken.vocabulary([{"entries": titles}])[:98]]
    for name, module in (("before", load(old_path)), ("after", spoken)):
        for question in QUESTIONS:
            start = time.perf_counter()
            meant = module.corrected(question, terms, write)
            ms = round((time.perf_counter() - start) * 1000)
            print(json.dumps({"when": name, "heard": question, "meant": meant, "ms": ms}))


if __name__ == "__main__":
    main(sys.argv[1])
