"""HEIC to JPG, run as `python -m imageskin.heic SRC DST` so the server can time it out.

Needs the optional extra `.[heic]` (pillow-heif). Its wheels bundle libheif and libde265 (LGPL-3)
and x265 (GPL-2), which is why it is optional; only decoding is used here.
"""

import sys
from pathlib import Path


def convert(src: Path, dst: Path) -> None:
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()
    with Image.open(src) as image:
        # Phones store photos sideways with a rotation tag; apply it so the face is upright.
        ImageOps.exif_transpose(image).convert("RGB").save(dst, "JPEG", quality=95)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m imageskin.heic SRC DST", file=sys.stderr)
        return 2
    try:
        convert(Path(argv[0]), Path(argv[1]))
    except Exception as e:  # reported to the parent process on stderr
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
