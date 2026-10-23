"""Does speaking the next sentence while the clip before renders save time, with the LLM writing?"""

import json
import threading
import time
import urllib.request
from pathlib import Path

import cv2
import torch

from imageskin.kokoro_engine import kokoro_for
from imageskin.prepare_job import photoreal_steps

home = Path("/root/.imageskin")
photo = Path("/home/user/work/photoreal_male_professor.png")
steps = photoreal_steps(home, kokoro_for("a"), "am_michael", max_side=720, progressive=True)
out = Path("/home/user/work/ovl")
out.mkdir(exist_ok=True)
S1 = "Once upon a time, in a sunny little town,"
S2 = "there lived a fluffy orange cat named Marmalade who was terrified of water."
stop = threading.Event()


def llm():
    while not stop.is_set():
        body = json.dumps(
            {
                "messages": [{"role": "user", "content": "Write a long story about a dog."}],
                "max_tokens": 200,
            }
        ).encode()
        urllib.request.urlopen(
            urllib.request.Request(
                "http://127.0.0.1:8080/v1/chat/completions",
                body,
                {"content-type": "application/json"},
            ),
            timeout=300,
        ).read()


def threads(n):
    torch.set_num_threads(n)
    cv2.setNumThreads(n)


threads(2)
steps.speak("Hello.", out / "w.wav")
steps.render(photo, out / "w.wav", out / "w.mp4")  # warm up
t = threading.Thread(target=llm, daemon=True)
t.start()
time.sleep(3)
res = {}
for _trial in range(2):
    steps.speak(S1, out / "1.wav")
    a = time.perf_counter()
    steps.render(photo, out / "1.wav", out / "1.mp4")
    b = time.perf_counter()
    steps.speak(S2, out / "2.wav")
    c = time.perf_counter()
    res.setdefault("sequential", []).append(
        {"render1": round(b - a, 2), "speak2": round(c - b, 2), "both": round(c - a, 2)}
    )
    for vt, st in ((1, 1), (1, 2), (2, 2)):
        done = {}

        def rend(vt: int = vt, done: dict = done) -> None:
            threads(vt)
            x = time.perf_counter()
            steps.render(photo, out / "1.wav", out / "1b.mp4")
            done["render1"] = round(time.perf_counter() - x, 2)

        def spk(st: int = st, done: dict = done) -> None:
            threads(st)
            x = time.perf_counter()
            steps.speak(S2, out / "2b.wav")
            done["speak2"] = round(time.perf_counter() - x, 2)

        a = time.perf_counter()
        r = threading.Thread(target=rend)
        s = threading.Thread(target=spk)
        r.start()
        s.start()
        r.join()
        s.join()
        done["both"] = round(time.perf_counter() - a, 2)
        res.setdefault(f"overlap video {vt} voice {st} threads", []).append(done)
        threads(2)
stop.set()
print(json.dumps(res, indent=1))
