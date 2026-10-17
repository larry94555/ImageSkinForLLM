"""R24b: make, check and pack the 36 default people.

    python tools/default_people/make_default_people.py [-o default-people]

For each person in `imageskin.default_people.people()` it makes the picture with Segmind SSD-1B
(picked in R24a), runs the app's photo checks on it, and, if a check fails, tries the next seed
(up to MAX_SEEDS), so a person who fails every seed is reported and not shipped. Then it
prepares each picture with the photoreal engine, renders a short line in one of the person's
voices and checks that the mouth moves with the speech and the idle loop plays, and packs the
picture with its prepared frames as <name>.zip, which must be within the 50 MB budget. It
writes results.json, a contact sheet of all the pictures and index.html with the report.

A run picks up where an earlier one stopped: a person whose pack is done is kept (unless
--again), and a picture already made is reused, as its seed is in results.json.
"""

import argparse
import json
import logging
import os
import time
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from html import escape
from pathlib import Path
from typing import Any

import numpy as np

from imageskin.default_people import MAX_PACK_BYTES, Person, pack, people, voices_for

logger = logging.getLogger("default_people")

# Segmind SSD-1B (Apache 2.0), at the revision R24a's pictures were made with.
IMAGE_MODEL = "segmind/SSD-1B"
IMAGE_REVISION = "60987f37e94cd59c36b1cba832b9f97b57395a10"
STEPS = 25
SIZE = 1024
MAX_SEEDS = 3
LINE = "Hello! It's nice to meet you. What would you like to talk about today?"
# The mouth must move this many times more while talking than in the idle loop.
MIN_MOUTH_RATIO = 1.5

# What suits each role: an age, clothes and a setting. No real person or public figure is named.
ROLE_LOOKS = {
    "Professor": ("in their late fifties", "a tweed jacket", "a university office with books"),
    "Teaching Assistant": (
        "in their late twenties",
        "a cardigan over a collared shirt",
        "a university seminar room",
    ),
    "Student": ("about twenty years old", "a casual denim jacket", "a university library"),
    "Parent": ("in their early forties", "a casual sweater", "a warm family kitchen"),
    "Teenager": ("aged sixteen", "a hoodie", "a bright bedroom"),
    "Boss": ("in their late forties", "a tailored dark suit", "a modern glass office"),
    "Office Manager": (
        "in their late thirties",
        "a smart blazer over a plain top",
        "an open-plan office",
    ),
    "High School Teacher": (
        "in their mid forties",
        "a neat collared shirt",
        "a high school classroom with a chalkboard",
    ),
    "Business Consultant": (
        "in their mid thirties",
        "a navy blazer",
        "a bright meeting room",
    ),
}
REALISM = {
    "photoreal": "headshot photograph, natural skin texture, soft daylight, sharp focus",
    "animated": "3D animated film character, stylized cartoon, soft lighting",
}
FRAMING = (
    "head and shoulders, facing and looking at the camera, neutral expression, mouth closed, "
    "eyes open"
)
NEGATIVE = (
    "two people, profile, turned head, tilted head, hands, glasses, sunglasses, hat, mask, "
    "hair over eyes, open mouth, teeth, blurry, dark, low quality, deformed, text, watermark"
)


def prompt(person: Person) -> str:
    """The text the picture is made from. The person and the setting come first: SSD-1B's text
    encoders keep only 77 tokens, so what is past them is dropped, and a look put after the
    style and framing was ignored (R24a2)."""
    age, clothes, setting = ROLE_LOOKS[person.role]
    who = "woman" if person.gender == "female" else "man"
    if person.role == "Teenager":
        who = "girl" if person.gender == "female" else "boy"
    elif person.role == "Student":
        who = f"young {who}"
    return (
        f"one {who} {age}, {person.look}, wearing {clothes}, in {setting} softly blurred, "
        f"{REALISM[person.realism]}, {FRAMING}"
    )


@dataclass
class Result:
    person: str
    prompt: str
    seed: int = 0
    picture: str = ""
    picture_ms: float = 0.0
    problems: list[str] = field(default_factory=list)  # from the photo checks, last seed tried
    score: int | None = None
    prepare_ms: float = 0.0
    video: str = ""
    mouth_ratio: float | None = None  # mouth movement while talking over that while idle
    idle_seconds: float = 0.0
    pack: str = ""
    pack_bytes: int = 0
    error: str = ""  # the step that failed and why

    @property
    def passed(self) -> bool:
        return bool(self.pack) and not self.error and not self.problems


MakePicture = Callable[[str, int, Path], None]
CheckPhoto = Callable[[Path], tuple[list[str], int | None]]


@dataclass
class VideoSteps:
    """The video pass's models, so tests can fake them."""

    prepare: Callable[[Path], Any]  # picture -> library
    render: Callable[[Any, str, str, Path], None]  # library, language code, voice, output
    idle: Callable[[Any, Path], float]  # library, output -> seconds
    mouth_motion: Callable[[Any, Path], float]  # library, video -> movement in the mouth
    library_folder: Callable[[Any], Path]


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def make_picture_for(
    person: Person, out: Path, make: MakePicture, check: CheckPhoto, result: Result
) -> None:
    """Make the picture, trying the next seed while the photo checks fail. A picture already
    there from an earlier run with a recorded seed is checked, not made again."""
    picture = out / f"{person.name}.png"
    first = result.seed if result.seed and picture.exists() else 0
    for seed in range(first or person.seed, person.seed + MAX_SEEDS):
        start = time.perf_counter()
        if seed != first:
            make(result.prompt, seed, picture)
            result.picture_ms = _ms(start)
        result.seed, result.picture = seed, picture.name
        result.problems, result.score = check(picture)
        logger.info(
            "Default picture checked",
            extra={
                "person": person.name,
                "seed": seed,
                "problems": result.problems,
                "score": result.score,
                "picture_ms": result.picture_ms,
            },
        )
        if not result.problems:
            return


def packed(result: Result, out: Path) -> bool:
    """Whether the person passed and their pack is still there as a zip: results.json is only a
    record of the last run, so a pack deleted or damaged since is made again."""
    return result.passed and zipfile.is_zipfile(out / result.pack)


def run_picture(
    person: Person, out: Path, make: MakePicture, check: CheckPhoto, earlier: Result | None
) -> Result:
    """The picture pass for one person. An earlier run's result for the same prompt is kept if
    its pack is there; otherwise its picture and seed are kept, to be checked rather than made
    again, and the rest is cleared so the video pass runs again."""
    result = Result(person.name, prompt(person))
    if earlier is not None and earlier.prompt == result.prompt:
        if packed(earlier, out):
            return earlier
        result.seed, result.picture, result.picture_ms = (
            earlier.seed,
            earlier.picture,
            earlier.picture_ms,
        )
    try:
        make_picture_for(person, out, make, check, result)
    except Exception as e:  # any model's error: record it and go on with the next person
        result.error = f"Could not make the picture: {e}"
        logger.exception("Default picture failed", extra={"person": person.name})
    return result


def run_video(person: Person, result: Result, out: Path, steps: VideoSteps) -> Result:
    """Prepare, render and check one person whose picture passed, then pack them."""
    if packed(result, out) or result.error or result.problems or not result.picture:
        return result
    step = "prepare"
    try:
        picture = out / result.picture
        start = time.perf_counter()
        lib = steps.prepare(picture)
        result.prepare_ms = _ms(start)

        step = "render the check line"
        _, lang, voice = voices_for(person.gender)[0]
        video = out / f"{person.name}.mp4"
        steps.render(lib, lang, voice, video)
        result.video = video.name

        step = "play the idle loop"
        idle = out / f"{person.name}_idle.mp4"
        result.idle_seconds = steps.idle(lib, idle)
        if result.idle_seconds <= 0:
            raise ValueError("the idle loop has no frames")

        step = "check the mouth moves"
        talking, still = steps.mouth_motion(lib, video), steps.mouth_motion(lib, idle)
        result.mouth_ratio = round(talking / max(still, 1e-6), 2)
        if result.mouth_ratio < MIN_MOUTH_RATIO:
            raise ValueError(f"the mouth moves only {result.mouth_ratio}x as much talking as idle")

        step = "pack"
        target = out / "packs" / f"{person.name}.zip"
        target.parent.mkdir(exist_ok=True)
        result.pack_bytes = pack(person, picture, steps.library_folder(lib), target)
        if result.pack_bytes > MAX_PACK_BYTES:
            raise ValueError(f"the pack is {result.pack_bytes / 1e6:.1f} MB, over 50 MB")
        result.pack = f"packs/{target.name}"
    except Exception as e:  # record it and go on with the next person
        result.error = f"Could not {step}: {e}"
        logger.exception("Default person failed", extra={"person": person.name, "step": step})
    logger.info(
        "Default person done",
        extra={
            "person": person.name,
            "passed": result.passed,
            "mouth_ratio": result.mouth_ratio,
            "pack_bytes": result.pack_bytes,
            "prepare_ms": result.prepare_ms,
            "error": result.error or None,
        },
    )
    return result


def load_results(out: Path) -> dict[str, Result]:
    path = out / "results.json"
    if not path.exists():
        return {}
    return {r["person"]: Result(**r) for r in json.loads(path.read_text(encoding="utf-8"))}


def contact_sheet(out: Path, results: list[Result], columns: int = 9, side: int = 200) -> Path:
    """All the pictures in one image, a row for each gender and realism, for a human look."""
    import cv2

    rows = (len(results) + columns - 1) // columns
    sheet = np.full((rows * (side + 24), columns * side, 3), 255, np.uint8)
    for i, r in enumerate(results):
        y, x = (i // columns) * (side + 24), (i % columns) * side
        picture = cv2.imread(str(out / r.picture)) if r.picture else None
        if picture is not None:
            sheet[y : y + side, x : x + side] = cv2.resize(picture, (side, side))
        label = r.person.split("_", 2)[2].replace("_", " ") + ("" if r.passed else " (FAILED)")
        cv2.putText(sheet, label, (x + 4, y + side + 17), 0, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    path = out / "contact-sheet.png"
    cv2.imwrite(str(path), sheet)
    return path


def build_page(results: list[Result]) -> str:
    passed = sum(r.passed for r in results)
    rows = "".join(
        f"<tr><td>{escape(r.person)}</td><td>{'yes' if r.passed else 'NO'}</td>"
        f"<td>{r.seed}</td><td>{r.score if r.score is not None else ''}</td>"
        f"<td>{r.mouth_ratio if r.mouth_ratio is not None else ''}</td>"
        f"<td>{r.pack_bytes / 1e6:.1f}</td>"
        f"<td>{escape(r.error or ' '.join(r.problems))}</td></tr>"
        for r in results
    )
    largest = max((r.pack_bytes for r in results), default=0) / 1e6
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Default people</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 16px; color: #1d1d1f; background: #fff; }}
table {{ border-collapse: collapse; }} td, th {{ border: 1px solid #ccc; padding: 4px 8px; }}
img {{ max-width: 100%; }}
</style></head><body>
<h1>Default people</h1>
<p>{passed} of {len(results)} passed the photo checks and the render check and are packed.
Largest pack: {largest:.1f} MB (budget 50 MB). Pictures by {IMAGE_MODEL}
(revision {IMAGE_REVISION[:7]}).</p>
<img src="contact-sheet.png" alt="All the default people">
<table><tr><th>Person</th><th>Passed</th><th>Seed</th><th>Photo score</th>
<th>Mouth moves (talking / idle)</th><th>Pack MB</th><th>Problem</th></tr>{rows}</table>
</body></html>
"""


def write_results(out: Path, results: list[Result]) -> None:
    (out / "results.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2) + "\n", encoding="utf-8"
    )
    (out / "index.html").write_text(build_page(results), encoding="utf-8")


def exit_status(results: list[Result], out: Path) -> int:
    """0 only if all 36 passed and their packs are there, so a script or a shell can tell a
    failed run."""
    expected = sorted(p.name for p in people())
    ok = sorted(r.person for r in results) == expected and all(packed(r, out) for r in results)
    return 0 if ok else 1


def ssd1b_maker() -> tuple[MakePicture, Callable[[], None]]:  # pragma: no cover - the model
    """The picture maker, and a call that frees the model's memory once the pictures are made."""
    import functools
    import gc

    import torch
    from diffusers import StableDiffusionXLPipeline

    torch.set_num_threads(os.cpu_count() or 4)

    @functools.cache
    def pipeline() -> StableDiffusionXLPipeline:
        pipe = StableDiffusionXLPipeline.from_pretrained(
            IMAGE_MODEL,
            revision=IMAGE_REVISION,
            variant="fp16",
            torch_dtype=torch.float32,
            use_safetensors=True,
        )
        pipe.vae.enable_tiling()
        return pipe

    def make(text: str, seed: int, path: Path) -> None:
        image = pipeline()(
            text,
            negative_prompt=NEGATIVE,
            num_inference_steps=STEPS,
            height=SIZE,
            width=SIZE,
            generator=torch.Generator().manual_seed(seed),
        ).images[0]
        image.save(path)

    def release() -> None:
        pipeline.cache_clear()
        gc.collect()

    return make, release


def mouth_box(lib: Any) -> tuple[int, int, int, int]:
    """The mouth's window in the photo's pixels: the crop's window moved by crop_to_photo."""
    x0, y0, x1, y1 = lib.window
    corners = np.array([[x0, y0, 1], [x1, y0, 1], [x0, y1, 1], [x1, y1, 1]], np.float64)
    pts = corners @ np.asarray(lib.crop_to_photo, np.float64).T
    h, w = lib.photo.shape[:2]
    xs, ys = np.clip(pts[:, 0], 0, w), np.clip(pts[:, 1], 0, h)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def mouth_motion(lib: Any, video: Path) -> float:  # pragma: no cover - decodes a real video
    """How much the mouth's window changes from frame to frame in a video, on average."""
    import cv2

    x0, y0, x1, y1 = mouth_box(lib)
    capture = cv2.VideoCapture(str(video))
    changes, last = [], None
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        part = frame[y0:y1, x0:x1].astype(np.float32)
        if last is not None:
            changes.append(float(np.abs(part - last).mean()))
        last = part
    capture.release()
    if not changes:
        raise ValueError(f"{video.name} has no frames")
    return float(np.mean(changes))


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - runs the real models
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # see experiments/voice/run_test.py
    from imageskin.config import default_home
    from imageskin.default_people import VOICES
    from imageskin.face_checks import FaceChecker
    from imageskin.kokoro_engine import kokoro_for
    from imageskin.logging_setup import setup_logging
    from imageskin.photoreal import PhotorealEngine
    from imageskin.photoreal_library import write_idle_preview
    from imageskin.sample import speak_and_render

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", type=Path, default=Path("default-people"))
    parser.add_argument("--again", action="store_true", help="make every person again")
    parser.add_argument("--only", nargs="*", help="only these people, by name")
    args = parser.parse_args(argv)
    setup_logging()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    everyone = [p for p in people() if not args.only or p.name in args.only]
    earlier = {} if args.again else load_results(out)
    make, release = ssd1b_maker()
    checker = FaceChecker(default_home() / "models" / "faces")
    checker.prepare()

    def check(photo: Path) -> tuple[list[str], int | None]:
        found = checker.check(photo)
        return found.problems, found.score

    # Every picture first, then the picture model is freed before the photoreal engine loads:
    # both at once ran out of 16 GB of memory (R24a).
    results: dict[str, Result] = dict(earlier)
    n = len(everyone)
    for i, person in enumerate(everyone):
        print(f"[{i + 1}/{n}] Picture: {person.name}", flush=True)
        results[person.name] = run_picture(person, out, make, check, earlier.get(person.name))
        write_results(out, [results[p.name] for p in people() if p.name in results])
    release()

    engine = PhotorealEngine()
    kokoro = {lang: kokoro_for(lang) for lang, _ in VOICES.values()}

    def render(lib: Any, lang: str, voice: str, output: Path) -> None:
        speak_and_render(lib, LINE, output, kokoro[lang], engine, voice)

    steps = VideoSteps(
        engine.prepare, render, write_idle_preview, mouth_motion, lambda lib: lib.folder
    )
    for i, person in enumerate(everyone):
        print(f"[{i + 1}/{n}] Video and pack: {person.name}", flush=True)
        results[person.name] = run_video(person, results[person.name], out, steps)
        write_results(out, [results[p.name] for p in people() if p.name in results])
    ordered = [results[p.name] for p in people() if p.name in results]
    contact_sheet(out, ordered)
    passed = sum(r.passed for r in ordered)
    logger.info(
        "Default people done",
        extra={"people": len(ordered), "passed": passed, "duration_ms": _ms(start)},
    )
    print(f"Done: {passed} of {len(ordered)} passed. Wrote {(out / 'index.html').resolve()}")
    return exit_status(ordered, out)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
