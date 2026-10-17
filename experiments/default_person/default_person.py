"""R24a default person test: make a few made-up people, check them and hear them talk.

    python experiments/default_person/default_person.py [-o default-person-test]

For each person below it makes a picture with an open text-to-image model, runs the app's own
photo checks on it, prepares it with the photoreal engine and renders a short line in both
Kokoro voices for the person's gender (American and British), then writes index.html to look
at them side by side. A step that fails is recorded and the person is skipped from then on,
so one bad picture doesn't stop the rest. It is a test, not part of the app; R24b makes all 36.
"""

import argparse
import json
import logging
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from html import escape
from pathlib import Path
from typing import Any

logger = logging.getLogger("default_person_test")

# Segmind SSD-1B (Apache 2.0): a distilled Stable Diffusion XL, half its size, so it fits a CPU.
IMAGE_MODEL = "segmind/SSD-1B"
STEPS = 25
SIZE = 1024
LINE = "Hello! It's nice to meet you. What would you like to talk about today?"

# Kokoro-82M's ready-made voices (Apache 2.0, hexgrad), by gender and accent: the best rated
# voice of each kind in Kokoro's VOICES.md. The language code sets the accent's pronunciation.
VOICES: dict[tuple[str, str], tuple[str, str]] = {
    ("female", "American"): ("a", "af_heart"),
    ("male", "American"): ("a", "am_michael"),
    ("female", "British"): ("b", "bf_emma"),
    ("male", "British"): ("b", "bm_george"),
}

# What suits each role: an age, clothes and a setting. No real person or public figure is named.
ROLE_LOOKS = {
    "Professor": ("in their late fifties", "a tweed jacket", "a university office with books"),
    "Boss": ("in their late forties", "a tailored dark suit", "a modern glass office"),
    "Parent": ("in their early forties", "a casual sweater", "a warm family kitchen"),
    "Teenager": ("aged sixteen", "a hoodie", "a bright bedroom"),
}
REALISM = {
    "photoreal": "professional headshot photograph, natural skin texture, soft daylight, "
    "sharp focus, 85mm lens",
    "animated": "3D animated film character, stylized cartoon, soft studio lighting, "
    "smooth shading",
}
FRAMING = (
    "head and shoulders portrait, one person, facing the camera directly, looking straight at "
    "the camera, neutral relaxed expression, mouth closed, eyes open, whole face visible, "
    "plain softly blurred background"
)
NEGATIVE = (
    "two people, profile, turned head, tilted head, hands, glasses, sunglasses, hat, mask, "
    "hair over eyes, open mouth, teeth, blurry, dark, low quality, deformed, text, watermark"
)


@dataclass
class Person:
    gender: str  # "female" or "male"
    realism: str  # "photoreal" or "animated"
    role: str
    seed: int = 1

    @property
    def name(self) -> str:
        return f"{self.realism}_{self.gender}_{self.role.lower()}"


# Two of each gender and realism, four roles, each role once in every realism.
PEOPLE = [
    Person("male", "photoreal", "Professor"),
    Person("female", "photoreal", "Boss"),
    Person("female", "photoreal", "Parent"),
    Person("male", "photoreal", "Teenager"),
    Person("female", "animated", "Professor"),
    Person("male", "animated", "Boss"),
    Person("male", "animated", "Parent"),
    Person("female", "animated", "Teenager"),
]


def prompt(person: Person) -> str:
    """The text the picture is made from."""
    age, clothes, setting = ROLE_LOOKS[person.role]
    who = "woman" if person.gender == "female" else "man"
    if person.role == "Teenager":
        who = "girl" if person.gender == "female" else "boy"
    return f"{REALISM[person.realism]}, {FRAMING}, a {who} {age} wearing {clothes}, in {setting}"


@dataclass
class Result:
    person: str
    prompt: str
    picture: str = ""
    picture_ms: float = 0.0
    reused: bool = False  # the picture was kept from an earlier run, not made from this prompt
    problems: list[str] = field(default_factory=list)  # from the photo checks
    score: int | None = None
    prepare_ms: float = 0.0
    videos: dict[str, str] = field(default_factory=dict)  # by accent
    render_ms: dict[str, float] = field(default_factory=dict)
    error: str = ""  # the step that failed and why


MakePicture = Callable[[str, int, Path], None]
CheckPhoto = Callable[[Path], tuple[list[str], int | None]]
Prepare = Callable[[Path], Any]
Render = Callable[[Any, str, str, Path], None]  # face, language code, voice, output


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def voices_for(gender: str) -> list[tuple[str, str, str]]:
    """The accent, Kokoro language code and voice of each voice for a gender."""
    return [(a, lang, v) for (g, a), (lang, v) in VOICES.items() if g == gender]


def run_person(
    person: Person,
    out: Path,
    make_picture: MakePicture,
    check: CheckPhoto,
    prepare: Prepare | None,
    render: Render | None,
    reuse_picture: bool = False,
) -> Result:
    """Make, check, prepare and render one person; a failed step ends that person's run.

    The picture is made again even if one is there, since its name says nothing of the prompt,
    seed or model it came from, unless reuse_picture is set.
    """
    result = Result(person.name, prompt(person))
    step = "make the picture"
    try:
        picture = out / f"{person.name}.png"
        start = time.perf_counter()
        result.reused = reuse_picture and picture.exists()
        if not result.reused:
            make_picture(result.prompt, person.seed, picture)
        result.picture, result.picture_ms = picture.name, _ms(start)

        step = "check the photo"
        result.problems, result.score = check(picture)
        if not result.problems and prepare is not None and render is not None:
            step = "prepare"
            start = time.perf_counter()
            face = prepare(picture)
            result.prepare_ms = _ms(start)
            for accent, lang, voice in voices_for(person.gender):
                step = f"render the {accent} voice"
                video = out / f"{person.name}_{accent.lower()}.mp4"
                start = time.perf_counter()
                render(face, lang, voice, video)
                result.videos[accent], result.render_ms[accent] = video.name, _ms(start)
    except Exception as e:  # any model's error: record it and go on with the next person
        result.error = f"Could not {step}: {e}"
        logger.exception("Default person failed", extra={"person": person.name, "step": step})
    logger.info(
        "Default person done",
        extra={
            "person": person.name,
            "problems": len(result.problems),
            "score": result.score,
            "videos": len(result.videos),
            "picture_ms": result.picture_ms,
            "reused_picture": result.reused,
            "prepare_ms": result.prepare_ms,
            "error": result.error or None,
        },
    )
    return result


def _cell(r: Result) -> str:
    if r.error:
        verdict = f"<b>Failed.</b> {escape(r.error)}"
    elif r.problems:
        verdict = "<b>Photo checks failed:</b> " + escape(" ".join(r.problems))
    else:
        verdict = f"Photo checks passed, score {r.score}"
    if r.reused:
        verdict += " (picture kept from an earlier run, so it may not match the prompt below)"
    image = f'<img src="{escape(r.picture)}" alt="">' if r.picture else ""
    videos = "".join(
        f'<p>{escape(accent)} voice<br><video controls preload="none" src="{escape(v)}">'
        f"</video></p>"
        for accent, v in r.videos.items()
    )
    return (
        f"<td><h2>{escape(r.person.replace('_', ' '))}</h2>{image}<p>{verdict}</p>{videos}"
        f"<details><summary>Prompt</summary><small>{escape(r.prompt)}</small></details></td>"
    )


def build_page(results: list[Result]) -> str:
    """HTML for the page: each person's picture, check result and videos."""
    passed = sum(1 for r in results if not r.problems and not r.error and r.picture)
    voices = ", ".join(f"{a} {g}: {v}" for (g, a), (_, v) in VOICES.items())
    cells = "".join(_cell(r) for r in results)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Default person test</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 16px; color: #1d1d1f; background: #fff; }}
.grid {{ display: flex; flex-wrap: wrap; gap: 12px; }}
td {{ display: block; border: 1px solid #ccc; padding: 8px; width: 300px; vertical-align: top; }}
img, video {{ width: 100%; display: block; }} h2 {{ font-size: 1rem; margin: 0 0 6px; }}
</style></head><body>
<h1>Default person test</h1>
<p>{passed} of {len(results)} pictures passed the photo checks. Pictures by {IMAGE_MODEL};
voices by Kokoro-82M ({escape(voices)}). Each says: "{escape(LINE)}"</p>
<table><tr class="grid">{cells}</tr></table>
</body></html>
"""


def write_results(out: Path, results: list[Result]) -> Path:
    (out / "results.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2) + "\n", encoding="utf-8"
    )
    page = out / "index.html"
    page.write_text(build_page(results), encoding="utf-8")
    return page


def ssd1b_maker() -> tuple[MakePicture, Callable[[], None]]:  # pragma: no cover - the model
    """The picture maker, and a call that frees the model's memory once the pictures are made."""
    import functools
    import gc

    import torch
    from diffusers import StableDiffusionXLPipeline

    torch.set_num_threads(os.cpu_count() or 4)

    @functools.cache
    def pipeline() -> StableDiffusionXLPipeline:
        # Loaded on first use, so a rerun with every picture made never loads it. The
        # half-size fp16 weights download in half the time; the CPU runs them as float32.
        # Decoding in tiles keeps memory down at 1024 by 1024.
        pipe = StableDiffusionXLPipeline.from_pretrained(
            IMAGE_MODEL, variant="fp16", torch_dtype=torch.float32, use_safetensors=True
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


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - runs the real models
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # see experiments/voice/run_test.py
    from imageskin.config import default_home
    from imageskin.face_checks import FaceChecker
    from imageskin.kokoro_engine import kokoro_for
    from imageskin.logging_setup import setup_logging
    from imageskin.photoreal import PhotorealEngine
    from imageskin.sample import speak_and_render

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", type=Path, default=Path("default-person-test"))
    parser.add_argument("--pictures-only", action="store_true", help="skip prepare and videos")
    parser.add_argument(
        "--reuse-pictures",
        action="store_true",
        help="keep pictures already in the output folder instead of making them again",
    )
    args = parser.parse_args(argv)
    setup_logging()
    args.output.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    make_picture, release = ssd1b_maker()
    checker = FaceChecker(default_home() / "models" / "faces")
    checker.prepare()

    def check(photo: Path) -> tuple[list[str], int | None]:
        found = checker.check(photo)
        return found.problems, found.score

    logger.info("Loaded the models", extra={"duration_ms": _ms(start)})
    # Every picture first, then the picture model is freed before the photoreal engine loads:
    # both at once ran out of 16 GB of memory.
    results: list[Result] = []
    n = len(PEOPLE)
    for i, person in enumerate(PEOPLE):
        print(
            f"[{i + 1}/{n}] Picture: {person.name} (about 11 minutes if not made yet)", flush=True
        )
        results.append(
            run_person(person, args.output, make_picture, check, None, None, args.reuse_pictures)
        )
        write_results(args.output, results)  # so the page fills in as the run goes
    release()
    if not args.pictures_only:
        video = PhotorealEngine()
        kokoro = {lang: kokoro_for(lang) for lang, _ in VOICES.values()}

        def render(face: Any, lang: str, voice: str, output: Path) -> None:
            speak_and_render(face, LINE, output, kokoro[lang], video, voice)

        for i, person in enumerate(PEOPLE):
            print(f"[{i + 1}/{n}] Video: {person.name} (about 6 minutes)", flush=True)
            # The picture was made or kept in the first pass, so this pass always keeps it.
            first = results[i]
            results[i] = run_person(
                person, args.output, make_picture, check, video.prepare, render, True
            )
            results[i].picture_ms, results[i].reused = first.picture_ms, first.reused
            write_results(args.output, results)
    passed = sum(1 for r in results if r.picture and not r.problems and not r.error)
    talked = sum(1 for r in results if len(r.videos) == 2)
    page = (args.output / "index.html").resolve()
    logger.info(
        "Default person test done",
        extra={
            "people": n,
            "passed_photo_checks": passed,
            "talked_in_both_voices": talked,
            "page": str(page),
            "duration_ms": _ms(start),
        },
    )
    print(f"Done: {passed} of {n} passed the photo checks, {talked} talked in both voices.")
    print(f"Wrote {page}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
