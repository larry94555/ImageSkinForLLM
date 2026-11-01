"""R233: how to find, frame and enlarge the head and neck. An experiment, not part of the app.

    python experiments/optimize_image/optimize_image.py PHOTO_FOLDER [-o optimize-image]

For each photo in PHOTO_FOLDER (and two default people, as the target to match) it frames the
head and neck two ways, from the face points alone and with the segmenter's hair and skin too,
crops a square framed like the default people, and enlarges it to 1024 by 1024 with plain
resizing (Lanczos) and three small super-resolution models that run on the CPU (FSRCNN, ESPCN,
Real-ESRGAN's general model). Every result goes through the app's photo checks (R8, R9). A second
test shrinks the default people's faces to known sizes, enlarges them back with each method and
compares them with the originals, which gives the smallest face that still enlarges well.
Results: <out>/results.md and .json, and the sheets framing.png, enlarging.png and
small-faces.png.
"""

import argparse
import json
import logging
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from framing import (
    CHIN,
    SEARCH_PX,
    Box,
    Framing,
    Image,
    Labels,
    Points,
    Upscale,
    box_from_landmarks,
    box_from_segments,
    crop_square,
    enlarge,
    face_height,
    face_search_box,
    hair_cut,
    head_mask,
    lanczos,
    measure_framing,
    median_framing,
    neck_cut,
    psnr,
)

logger = logging.getLogger("optimize_image")

SIZE = 1024
REPO = Path(__file__).resolve().parents[2]
DEFAULT_PEOPLE = REPO / "resources" / "default-people"
# Two default people go through the whole test too: framing them again should change little.
DEFAULT_SAMPLES = ("photoreal_male_professor.png", "photoreal_female_parent_2.png")
# Face heights (mid-forehead to chin, in the original photo's pixels) for the small-face test.
FACE_SIZES = (60, 80, 100, 130, 160, 200)
VIDEO_FACE_PX = 222  # the face's height in the video (face_checks.VIDEO_FACE_PX)

# The models, pinned by size and SHA-256. FSRCNN (Saafke/FSRCNN_Tensorflow) and ESPCN
# (fannymonori/TF-ESPCN) are Apache 2.0; Real-ESRGAN (xinntao/Real-ESRGAN) is BSD 3-clause.
RAW = "https://raw.githubusercontent.com"
MODELS: dict[str, tuple[str, int, str]] = {
    "FSRCNN_x2.pb": (
        f"{RAW}/Saafke/FSRCNN_Tensorflow/master/models/FSRCNN_x2.pb",
        38973,
        "366b33f0084c7b3f2bf6724f0a2c77bca94fcec9d7b6d72389d330073b380d5c",
    ),
    "ESPCN_x2.pb": (
        f"{RAW}/fannymonori/TF-ESPCN/master/export/ESPCN_x2.pb",
        86446,
        "59f77351e1d7c0057bf6fe088b4a8a07e42c468c8c8aebb674a6b4ea1823221d",
    ),
    "realesr-general-x4v3.pth": (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
        "realesr-general-x4v3.pth",
        4885111,
        "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292",
    ),
}
METHODS = ("lanczos", "fsrcnn", "espcn", "realesrgan")


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def superres_model(sr: Any) -> Upscale:
    """FSRCNN and ESPCN through OpenCV's dnn_superres (opencv-contrib, which the app's Docker
    image already installs): they enlarge the brightness only and resize the colour."""

    def run(rgb: Image) -> Image:
        bgr = sr.upsample(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        return np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

    return run


def realesrgan_onnx(pth: Path, onnx_path: Path) -> Path:  # pragma: no cover - needs torch
    """Real-ESRGAN's small general model (SRVGGNetCompact, 32 layers, x4) written as ONNX, so
    the app could run it with onnxruntime, which it already has, instead of torch."""
    if onnx_path.exists():
        return onnx_path
    import torch
    from torch import nn

    class Compact(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            layers: list[nn.Module] = [nn.Conv2d(3, 64, 3, 1, 1), nn.PReLU(64)]
            for _ in range(32):
                layers += [nn.Conv2d(64, 64, 3, 1, 1), nn.PReLU(64)]
            layers.append(nn.Conv2d(64, 48, 3, 1, 1))
            self.body = nn.ModuleList(layers)
            self.up = nn.PixelShuffle(4)

        def forward(self, x: Any) -> Any:
            out = x
            for layer in self.body:
                out = layer(out)
            return self.up(out) + nn.functional.interpolate(x, scale_factor=4, mode="nearest")

    model = Compact()
    model.load_state_dict(torch.load(pth, map_location="cpu", weights_only=True)["params"])
    model.eval()
    torch.onnx.export(
        model,
        (torch.zeros(1, 3, 64, 64),),
        str(onnx_path),
        input_names=["x"],
        output_names=["y"],
        dynamic_axes={"x": {2: "h", 3: "w"}, "y": {2: "h4", 3: "w4"}},
        opset_version=17,
        dynamo=False,
    )
    return onnx_path


def onnx_model(path: Path) -> Upscale:  # pragma: no cover - needs the model
    import onnxruntime as ort

    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])

    def run(rgb: Image) -> Image:
        x = rgb.astype(np.float32).transpose(2, 0, 1)[None] / 255.0
        y = session.run(None, {"x": x})[0][0].transpose(1, 2, 0)
        return np.clip(y * 255.0 + 0.5, 0, 255).astype(np.uint8)

    return run


Loads = dict[str, tuple[float, float]]  # method: load ms, memory added by loading and a first run


def load_models(folder: Path) -> tuple[dict[str, Upscale | None], Loads]:  # pragma: no cover
    """The four methods, and what loading each (with one run, which sets up its buffers) took
    in time and memory."""
    import psutil

    from imageskin.download import download

    folder.mkdir(parents=True, exist_ok=True)
    for name, (url, size, sha) in MODELS.items():
        download(url, folder / name, size, sha)
    onnx = realesrgan_onnx(
        folder / "realesr-general-x4v3.pth", folder / "realesr-general-x4v3.onnx"
    )

    def superres(name: str) -> Upscale:
        upper = "FSRCNN" if name == "fsrcnn" else "ESPCN"
        sr = cv2.dnn_superres.DnnSuperResImpl_create()
        sr.readModel(str(folder / f"{upper}_x2.pb"))
        sr.setModel(name, 2)
        return superres_model(sr)

    makers: dict[str, Callable[[], Upscale | None]] = {
        "lanczos": lambda: None,
        "fsrcnn": lambda: superres("fsrcnn"),
        "espcn": lambda: superres("espcn"),
        "realesrgan": lambda: onnx_model(onnx),
    }
    models: dict[str, Upscale | None] = {}
    loads: Loads = {}
    square = np.zeros((256, 256, 3), np.uint8)
    for method, make in makers.items():
        before = psutil.Process().memory_info().rss
        start = time.perf_counter()
        models[method] = make()
        load_ms = _ms(start)
        enlarge(square, SIZE, models[method])
        added = max(0, psutil.Process().memory_info().rss - before) / 2**20
        loads[method] = (load_ms, round(added, 1))
    return models, loads


def find_small_face(
    rgb: Image, labels: Labels, landmarks: Callable[[Image], Points | None]
) -> Points | None:
    """Look again for a face too small for the landmarker: in a square around the face skin
    the segmenter found, enlarged to SEARCH_PX. The points come back in the photo's pixels."""
    box = face_search_box(labels)
    if box is None:
        return None
    square, _ = crop_square(rgb, box)
    found = landmarks(lanczos(square, SEARCH_PX))
    if found is None:
        return None
    return (found * (box.size / SEARCH_PX) + (box.left, box.top)).astype(np.float32)


class Detector:  # pragma: no cover - runs MediaPipe
    """The face points and the segmenter's labels, from the same models the photo checks use.
    A face the landmarker misses is looked for again around the segmenter's face skin."""

    def __init__(self, models_dir: Path) -> None:
        from imageskin.face_checks import ensure_models

        self.face_model, self.segment_model = ensure_models(models_dir)
        self.searched = 0  # faces found only by looking again

    def landmarks(self, rgb: Image) -> Points | None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self.face_model)), num_faces=1
        )
        with vision.FaceLandmarker.create_from_options(options) as landmarker:
            found = landmarker.detect(image)
        if not found.face_landmarks:
            return None
        h, w = rgb.shape[:2]
        return np.array([[p.x * w, p.y * h] for p in found.face_landmarks[0]], np.float32)

    def labels(self, rgb: Image) -> Labels:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        seg = vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(self.segment_model)),
            output_category_mask=True,
        )
        with vision.ImageSegmenter.create_from_options(seg) as segmenter:
            # Copied before the segmenter closes: the view points into its memory.
            mask = segmenter.segment(image).category_mask.numpy_view().copy()
        return mask.reshape(rgb.shape[:2])

    def __call__(self, rgb: Image) -> tuple[Points, Labels] | None:
        points = self.landmarks(rgb)
        labels = self.labels(rgb)
        if points is None:
            points = find_small_face(rgb, labels, self.landmarks)
            if points is None:
                return None
            self.searched += 1
            logger.info("Small face found by looking again", extra={"face_px": face_height(points)})
        return points, labels


Detect = Callable[[Image], tuple[Points, Labels] | None]
Check = Callable[[Image], tuple[list[str], int | None, float]]  # problems, score, face px


@dataclass
class MethodResult:
    ms: float = 0.0
    problems: list[str] = field(default_factory=list)
    score: int | None = None
    sharpness_px: float = 0.0  # face height the check measured


@dataclass
class PhotoResult:
    photo: str
    size: tuple[int, int] = (0, 0)
    face_px: float = 0.0  # mid-forehead to chin in the original
    detect_ms: float = 0.0
    boxes: dict[str, list[int]] = field(default_factory=dict)  # left, top, size
    hair_cut: dict[str, float] = field(default_factory=dict)
    neck_cut: dict[str, float] = field(default_factory=dict)
    filled: dict[str, float] = field(default_factory=dict)
    framing: dict[str, dict[str, float]] = field(default_factory=dict)  # of the result
    methods: dict[str, MethodResult] = field(default_factory=dict)
    error: str = ""


def frame_photo(
    name: str,
    rgb: Image,
    target: Framing,
    detect: Detect,
    check: Check,
    models: dict[str, Upscale | None],
    out: Path,
) -> PhotoResult:
    """Both framings of one photo, each enlarged with plain resizing, and the segmenter framing
    enlarged with every method. Every picture is written to <out>/<photo>/."""
    result = PhotoResult(photo=name, size=(rgb.shape[1], rgb.shape[0]))
    start = time.perf_counter()
    found = detect(rgb)
    result.detect_ms = _ms(start)
    if found is None:
        result.error = "no face found"
        logger.error("Head and neck framing failed", extra={"photo": name, "reason": "no face"})
        return result
    points, labels = found
    result.face_px = round(face_height(points), 1)
    head = head_mask(labels, points)
    folder = out / Path(name).stem
    folder.mkdir(parents=True, exist_ok=True)
    for how, box in (
        ("landmarks", box_from_landmarks(points, target)),
        ("segments", box_from_segments(points, labels, target)),
    ):
        result.boxes[how] = [box.left, box.top, box.size]
        result.hair_cut[how] = round(hair_cut(head, box, float(points[CHIN, 1])), 4)
        result.neck_cut[how] = round(neck_cut(labels, points, box), 4)
        square, filled = crop_square(rgb, box)
        result.filled[how] = round(filled, 3)
        methods = METHODS if how == "segments" else ("lanczos",)
        for method in methods:
            start = time.perf_counter()
            big = enlarge(square, SIZE, models[method])
            ms = _ms(start)
            path = folder / f"{how}_{method}.png"
            cv2.imwrite(str(path), cv2.cvtColor(big, cv2.COLOR_RGB2BGR))
            problems, score, face_px = check(big)
            key = f"{how}_{method}"
            result.methods[key] = MethodResult(ms, problems, score, round(face_px, 1))
            if method == "lanczos":
                again = detect(big)
                if again is not None:
                    result.framing[how] = {
                        k: round(v, 3) for k, v in asdict(measure_framing(*again)).items()
                    }
        logger.info(
            "Head and neck framed",
            extra={"photo": name, "how": how, "box": result.boxes[how], "filled": filled},
        )
    return result


@dataclass
class SmallFace:
    person: str
    face_px: int
    psnr: dict[str, float] = field(default_factory=dict)  # at the video's face size
    sharpness: dict[str, float] = field(default_factory=dict)  # R9's measure, as in the check
    ms: dict[str, float] = field(default_factory=dict)


def small_faces(
    name: str,
    rgb: Image,
    points: Points,
    sizes: Sequence[int],
    models: dict[str, Upscale | None],
    sharpness: Callable[[Image, Points], float],
) -> list[SmallFace]:
    """Shrink a default person so the face is each size, enlarge it back with each method, and
    compare it with the original at the size the video shows the face."""
    fh = face_height(points)
    video = VIDEO_FACE_PX / fh
    side = rgb.shape[0]
    reference = cv2.resize(rgb, None, fx=video, fy=video, interpolation=cv2.INTER_AREA)
    rows = []
    for px in sizes:
        small_side = max(8, round(side * px / fh))
        small = cv2.resize(rgb, (small_side, small_side), interpolation=cv2.INTER_AREA)
        row = SmallFace(name, px)
        for method, model in models.items():
            start = time.perf_counter()
            big = enlarge(small, side, model, max_passes=3)
            row.ms[method] = _ms(start)
            seen = cv2.resize(big, reference.shape[1::-1], interpolation=cv2.INTER_AREA)
            top, bottom = (int(points[:, 1].min() * video), int(points[:, 1].max() * video))
            left, right = (int(points[:, 0].min() * video), int(points[:, 0].max() * video))
            row.psnr[method] = round(
                psnr(seen[top:bottom, left:right], reference[top:bottom, left:right]), 2
            )
            row.sharpness[method] = round(sharpness(big, points), 4)
        rows.append(row)
    return rows


def label(img: Image, text: str) -> Image:
    out = img.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], 26), (255, 255, 255), -1)
    cv2.putText(out, text, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
    return out


def thumb(img: Image, side: int) -> Image:
    """The picture fitted into a side by side square on white."""
    h, w = img.shape[:2]
    s = side / max(h, w)
    small = cv2.resize(
        img, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA
    )
    out = np.full((side, side, 3), 255, np.uint8)
    y, x = (side - small.shape[0]) // 2, (side - small.shape[1]) // 2
    out[y : y + small.shape[0], x : x + small.shape[1]] = small
    return out


def draw_box(img: Image, box: Box, colour: tuple[int, int, int]) -> None:
    t = max(2, img.shape[0] // 200)
    cv2.rectangle(img, (box.left, box.top), (box.right, box.bottom), colour, t)


def grid(rows: list[list[Image]]) -> Image:
    width = max(sum(c.shape[1] for c in r) for r in rows)
    lines = []
    for r in rows:
        line = np.hstack(r)
        pad = np.full((line.shape[0], width - line.shape[1], 3), 255, np.uint8)
        lines.append(np.hstack([line, pad]))
    return np.vstack(lines)


def markdown(
    target: Framing,
    defaults: list[tuple[str, Framing]],
    photos: list[PhotoResult],
    faces: list[SmallFace],
    speed: dict[str, dict[str, float]],
) -> str:
    out = ["# R233 optimize image results", "", "## The default people's framing", ""]
    out.append("| Picture | Margin above hair | Face share | Chin to bottom | Centre offset |")
    out.append("|---|---|---|---|---|")
    for name, f in [*defaults, ("**Median (the target)**", target)]:
        out.append(
            f"| {name} | {f.margin_above_hair:.2f} | {f.face_share:.3f} | "
            f"{f.chin_to_bottom:.2f} | {f.centre_offset:+.2f} |"
        )
    out += ["", "## Framing each photo", ""]
    out.append(
        "| Photo | Size | Face px | Hair cut (landmarks / segments) | Neck cut (landmarks / "
        "segments) | Filled (landmarks / segments) | Face share after (landmarks / segments) |"
    )
    out.append("|---|---|---|---|---|---|---|")
    for p in photos:
        if p.error:
            out.append(f"| {p.photo} | {p.size[0]}x{p.size[1]} | {p.error} | | | | |")
            continue
        share = " / ".join(f"{p.framing.get(h, {}).get('face_share', 0):.3f}" for h in p.boxes)
        out.append(
            f"| {p.photo} | {p.size[0]}x{p.size[1]} | {p.face_px:.0f} | "
            f"{p.hair_cut['landmarks']:.1%} / {p.hair_cut['segments']:.1%} | "
            f"{p.neck_cut['landmarks']:.1%} / {p.neck_cut['segments']:.1%} | "
            f"{p.filled['landmarks']:.0%} / {p.filled['segments']:.0%} | {share} |"
        )
    out += ["", "## Photo checks on each result (segments framing)", ""]
    out.append("| Photo | " + " | ".join(METHODS) + " |")
    out.append("|---|" + "---|" * len(METHODS))
    for p in photos:
        if p.error:
            continue
        cells = []
        for m in METHODS:
            r = p.methods.get(f"segments_{m}")
            if r is None:
                cells.append("")
            elif r.problems:
                cells.append("fails: " + "; ".join(x.split(".")[0] for x in r.problems))
            else:
                cells.append(f"passes, score {r.score} ({r.ms:.0f} ms)")
        out.append(f"| {p.photo} | " + " | ".join(cells) + " |")
    out += ["", "## Small faces: enlarged back and compared with the original", ""]
    out.append(
        "PSNR in dB on the face at the video's size (higher is closer to the original), then "
        "R9's sharpness (the check needs 0.05)."
    )
    out.append("")
    out.append("| Face px | " + " | ".join(METHODS) + " |")
    out.append("|---|" + "---|" * len(METHODS))
    for px in sorted({f.face_px for f in faces}):
        rows = [f for f in faces if f.face_px == px]
        cells = [
            f"{np.mean([r.psnr[m] for r in rows]):.2f} dB, "
            f"{np.mean([r.sharpness[m] for r in rows]):.3f}"
            for m in METHODS
        ]
        out.append(f"| {px} | " + " | ".join(cells) + " |")
    out += ["", "## Speed and size of each method", ""]
    out.append("| Method | Model file | Load ms | Memory added (MB) | 256 px to 1024 px, ms |")
    out.append("|---|---|---|---|---|")
    for m, s in speed.items():
        out.append(
            f"| {m} | {s['model_kb']:.0f} KB | {s['load_ms']:.0f} | {s['memory_mb']:.0f} | "
            f"{s['ms']:.0f} |"
        )
    return "\n".join(out) + "\n"


def method_speed(
    folder: Path, models: dict[str, Upscale | None], loads: Loads
) -> dict[str, dict[str, float]]:
    """Each method enlarging a 256 px square to 1024, the median of five runs."""
    files = {
        "lanczos": [],
        "fsrcnn": ["FSRCNN_x2.pb"],
        "espcn": ["ESPCN_x2.pb"],
        "realesrgan": ["realesr-general-x4v3.onnx"],
    }
    rng = np.random.default_rng(1)
    square = cv2.GaussianBlur(rng.integers(0, 255, (256, 256, 3), dtype=np.uint8), (0, 0), 2)
    out = {}
    for method, model in models.items():
        times = []
        for _ in range(5):
            start = time.perf_counter()
            enlarge(square, SIZE, model)
            times.append(_ms(start))
        out[method] = {
            "model_kb": sum((folder / f).stat().st_size for f in files[method]) / 1024,
            "load_ms": loads.get(method, (0.0, 0.0))[0],
            "memory_mb": loads.get(method, (0.0, 0.0))[1],
            "ms": float(np.median(times)),
        }
    return out


def read_rgb(path: Path) -> Image:
    from imageskin.face_checks import read_rgb as app_read

    return app_read(path)


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - runs the real models
    from imageskin.config import default_home
    from imageskin.face_checks import FaceChecker, light_and_sharpness, problems, score
    from imageskin.logging_setup import setup_logging

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("photos", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("optimize-image"))
    args = parser.parse_args(argv)
    setup_logging()
    out: Path = args.output
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    logger.info("Optimize image experiment started", extra={"photos": str(args.photos)})

    home = default_home()
    detect = Detector(home / "models" / "faces")
    checker = FaceChecker(home / "models" / "faces")
    model_dir = home / "models" / "enlarge-test"
    start = time.perf_counter()
    models, loads = load_models(model_dir)
    logger.info("Enlarging models ready", extra={"duration_ms": _ms(start)})

    def check(rgb: Image) -> tuple[list[str], int | None, float]:
        m = checker.measure_rgb(rgb)
        found = problems(m)
        return found, None if found else score(m), m.height_px

    # The target: the median framing of the default people.
    defaults: list[tuple[str, Framing]] = []
    default_found: dict[str, tuple[Image, Points]] = {}
    for path in sorted(DEFAULT_PEOPLE.glob("*.png")):
        if path.name == "contact-sheet.png":
            continue
        rgb = read_rgb(path)
        found = detect(rgb)
        if found is None:
            continue
        defaults.append((path.stem, measure_framing(*found)))
        default_found[path.name] = (rgb, found[0])
    target = median_framing([f for _, f in defaults])
    logger.info("Target framing", extra=asdict(target))

    photos = sorted(p for p in args.photos.iterdir() if p.suffix.lower() in (".png", ".jpg"))
    inputs = [(p.name, read_rgb(p)) for p in photos]
    inputs += [(f"default_{n}", default_found[n][0]) for n in DEFAULT_SAMPLES]
    results: list[PhotoResult] = []
    framing_rows: list[list[Image]] = []
    enlarging_rows: list[list[Image]] = []
    for name, rgb in inputs:
        r = frame_photo(name, rgb, target, detect, check, models, out)
        results.append(r)
        if r.error:
            continue
        shown = rgb.copy()
        draw_box(shown, Box(*r.boxes["landmarks"]), (230, 60, 60))
        draw_box(shown, Box(*r.boxes["segments"]), (40, 170, 60))
        folder = out / Path(name).stem
        pics = {k: read_rgb(folder / f"{k}.png") for k in r.methods}
        framing_rows.append(
            [
                label(thumb(shown, 320), f"{name} ({r.face_px:.0f} px face)"),
                label(thumb(pics["landmarks_lanczos"], 320), "landmarks only (red)"),
                label(thumb(pics["segments_lanczos"], 320), "with segmenter (green)"),
            ]
        )
        # The face close up, where enlarging shows.
        box = Box(256, 200, 512)
        enlarging_rows.append(
            [
                label(
                    cv2.resize(
                        pics[f"segments_{m}"][box.top : box.bottom, box.left : box.right],
                        (300, 300),
                        interpolation=cv2.INTER_AREA,
                    ),
                    f"{m} {r.methods[f'segments_{m}'].ms:.0f} ms",
                )
                for m in METHODS
            ]
        )
        json_path = out / "results.json"
        json_path.write_text(json.dumps([asdict(x) for x in results], indent=2))

    faces: list[SmallFace] = []
    small_rows: list[list[Image]] = []
    for n in DEFAULT_SAMPLES:
        rgb, points = default_found[n]
        faces += small_faces(
            n,
            rgb,
            points,
            FACE_SIZES,
            models,
            lambda big, p: light_and_sharpness(big, p)["sharpness"],
        )
        fh = face_height(points)
        for px in (80, 130):
            small_side = round(rgb.shape[0] * px / fh)
            small = cv2.resize(rgb, (small_side, small_side), interpolation=cv2.INTER_AREA)
            crop = Box(256, 160, 512)
            cells = [
                label(
                    cv2.resize(
                        rgb[crop.top : crop.bottom, crop.left : crop.right],
                        (300, 300),
                        interpolation=cv2.INTER_AREA,
                    ),
                    f"original, face shrunk to {px} px",
                )
            ]
            for m in METHODS:
                big = enlarge(small, rgb.shape[0], models[m], max_passes=3)
                cells.append(
                    label(
                        cv2.resize(
                            big[crop.top : crop.bottom, crop.left : crop.right],
                            (300, 300),
                            interpolation=cv2.INTER_AREA,
                        ),
                        m,
                    )
                )
            small_rows.append(cells)

    speed = method_speed(model_dir, models, loads)
    for name, rows in (
        ("framing.png", framing_rows),
        ("enlarging.png", enlarging_rows),
        ("small-faces.png", small_rows),
    ):
        cv2.imwrite(str(out / name), cv2.cvtColor(grid(rows), cv2.COLOR_RGB2BGR))
    (out / "results.json").write_text(
        json.dumps(
            {
                "target": asdict(target),
                "defaults": {n: asdict(f) for n, f in defaults},
                "photos": [asdict(x) for x in results],
                "small_faces": [asdict(f) for f in faces],
                "speed": speed,
            },
            indent=2,
        )
    )
    (out / "results.md").write_text(markdown(target, defaults, results, faces, speed))

    logger.info(
        "Optimize image experiment done",
        extra={"photos": len(results), "duration_ms": _ms(started)},
    )
    print(f"Wrote {out / 'results.md'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    raise SystemExit(main())
