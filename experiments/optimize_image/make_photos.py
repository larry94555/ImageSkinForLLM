"""R233: the made-up test photos for the optimize image test. An experiment, not part of the app.

    python experiments/optimize_image/make_photos.py [-o optimize-image/photos]

The test needs photos that show the body and the room: waist-up, full-length, a face turned a
little, long hair and a high collar. No such photos of real people come with the app, so they are
made with the same open picture model as the default people (Segmind SSD-1B, Apache 2.0, R24a),
each from a fixed seed so a rerun makes the same picture. A photo with the head near an edge is
cut from the waist-up one. Each takes about 11 minutes on a 4-core CPU; photos already in the
folder are kept.
"""

import argparse
import functools
import logging
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger("optimize_image")

IMAGE_MODEL = "segmind/SSD-1B"
IMAGE_REVISION = "60987f37e94cd59c36b1cba832b9f97b57395a10"  # as R24a's default people
STEPS = 25
STYLE = "candid phone photograph, natural light, realistic, sharp focus"
NEGATIVE = (
    "two people, hands on face, glasses, sunglasses, hat, mask, blurry, low quality, deformed, "
    "text, watermark, cartoon, painting"
)


@dataclass(frozen=True)
class TestPhoto:
    name: str
    text: str
    width: int = 1024
    height: int = 1024
    seed: int = 1


PHOTOS = [
    TestPhoto(
        "waist_up",
        "waist-up photo of a man in his fifties with short grey hair standing in a home "
        "kitchen, wearing a blue shirt, looking at the camera, cupboards behind him",
        seed=3,
    ),
    TestPhoto(
        "full_length",
        "full-length photo of a woman in her thirties standing in a city park, the whole body "
        "visible from head to shoes, wearing a green dress, looking at the camera",
        width=832,
        height=1216,
        seed=5,
    ),
    TestPhoto(
        "turned",
        "upper body photo of a woman in her forties with short dark hair in a living room, "
        "her head turned slightly to one side, three-quarter view, looking near the camera",
        seed=7,
    ),
    TestPhoto(
        "long_hair",
        "upper body photo of a young adult woman with very long wavy red hair falling over "
        "her shoulders and down her chest, sitting in a cafe, looking at the camera",
        seed=11,
    ),
    TestPhoto(
        "high_collar",
        "upper body photo of a man in his sixties wearing a black turtleneck sweater and a "
        "winter coat with a high collar turned up, outdoors on a city street, looking at the "
        "camera",
        seed=13,
    ),
]


def prompt(photo: TestPhoto) -> str:
    return f"{photo.text}, {STYLE}"


def near_edge(waist_up: Image.Image) -> Image.Image:
    """The waist-up photo cut so the head is near the top-left corner: the top 12% and the left
    40% go, so the hair is close to the top edge and the face close to the left one."""
    w, h = waist_up.size
    return waist_up.crop((int(w * 0.40), int(h * 0.12), w, h))


def ssd1b() -> Any:  # pragma: no cover - the real model
    import torch
    from diffusers import StableDiffusionXLPipeline

    torch.set_num_threads(os.cpu_count() or 4)

    @functools.cache
    def pipeline() -> Any:
        pipe = StableDiffusionXLPipeline.from_pretrained(
            IMAGE_MODEL,
            revision=IMAGE_REVISION,
            variant="fp16",
            torch_dtype=torch.float32,
            use_safetensors=True,
        )
        pipe.vae.enable_tiling()
        return pipe

    def make(photo: TestPhoto, path: Path) -> None:
        image = pipeline()(
            prompt(photo),
            negative_prompt=NEGATIVE,
            num_inference_steps=STEPS,
            width=photo.width,
            height=photo.height,
            generator=torch.Generator().manual_seed(photo.seed),
        ).images[0]
        image.save(path)

    return make


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - runs the real model
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from imageskin.logging_setup import setup_logging

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", type=Path, default=Path("optimize-image/photos"))
    args = parser.parse_args(argv)
    setup_logging()
    args.output.mkdir(parents=True, exist_ok=True)
    make = ssd1b()
    for i, photo in enumerate(PHOTOS):
        path = args.output / f"{photo.name}.png"
        if path.exists():
            continue
        print(f"[{i + 1}/{len(PHOTOS)}] {photo.name} (about 11 minutes)", flush=True)
        start = time.perf_counter()
        make(photo, path)
        logger.info(
            "Test photo made",
            extra={
                "photo": photo.name,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
    edge = args.output / "near_edge.png"
    if not edge.exists():
        near_edge(Image.open(args.output / "waist_up.png")).save(edge)
    print(f"Photos in {args.output}: {sorted(p.name for p in args.output.glob('*.png'))}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
