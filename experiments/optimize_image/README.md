# Optimize image test (R233)

How should the app find the head and neck in an uploaded photo, frame it like the default
people, and enlarge it to 1024 by 1024 (roadmap items 187 to 189)? This experiment compares two
ways to find the head and four ways to enlarge, on photos that show the body and the room, and
picks one of each for R234 and R235. It is a test, not part of the app. As Larry asked
(2026-11-01), it looks at the pictures only: no videos are made, since the photoreal engine
already takes any photo the checks pass.

## How to run it

```
python experiments/optimize_image/make_photos.py -o optimize-image/photos   # about an hour
python experiments/optimize_image/optimize_image.py optimize-image/photos -o optimize-image
```

It needs the `faces` and `video` extras, and `opencv-contrib-python>=4.8,<5` for FSRCNN and
ESPCN (the app's Docker image already installs it); `make_photos.py` needs the default person
test's packages (`experiments/default_person/requirements.txt`), and Real-ESRGAN's ONNX file is
written once with torch (the `photoreal` extra) and `onnx`. MediaPipe 0.10.35 installs
`opencv-contrib-python` 5, which FSRCNN and ESPCN can't load in, so pin it below 5 as the Docker
image does. The models go to `<IMAGESKIN_HOME>/models/enlarge-test`. Results:
`optimize-image/results.md` and `.json`, the sheets `framing.png`, `enlarging.png` and
`small-faces.png`, and every picture made, in a folder per photo. The log has
`Optimize image experiment started`, `Head and neck framed` for each photo and way (with the
box and how much was filled), `Head and neck framing failed` when no face is found,
`Small face found by looking again`, and `Optimize image experiment done` with the time.

## The test photos

| Photo | What it tests | Face (mid-forehead to chin) |
|---|---|---|
| Larry's webcam photo (1920 by 1080, from his `uploads`; not committed) | a real photo, head small, low in the picture, the body cut by the bottom edge | 312 px |
| `waist_up` | a man in a kitchen, waist up | 188 px |
| `full_length` (832 by 1216) | a woman in a park, head to shoes | 89 px |
| `turned` | a face turned a little | 381 px |
| `long_hair` | long red hair over the shoulders | 297 px |
| `high_collar` | a turtleneck and a coat collar turned up | 464 px |
| `near_edge` | `waist_up` cut so the hair is at the top edge and the face near the left | 188 px |
| two default people | the target: framing them again should change little | 449 and 510 px |

The made-up photos come from Segmind SSD-1B (Apache 2.0), as the default people did (R24a), each
from a fixed seed (`make_photos.py`), so no real person's photo is in the repository.

## Results (cloud, 4-core x86 CPU, 2026-11-01)

The full tables are in [results/results-cloud-2026-11-01.md](results/results-cloud-2026-11-01.md).
The sheets were shared with Larry and are not committed, as one shows his photo.

### The framing to match

The twelve default people, measured with the face points and the segmenter
(`measure_framing`), in face heights (mid-forehead to chin):

| | Median | Range |
|---|---|---|
| Face height over the picture's side | 0.471 | 0.43 to 0.51 |
| Picture top to the top of the hair | 0.04 | 0.00 to 0.08 |
| Chin to picture bottom (the neck and the top of the shoulders) | 0.60 | 0.49 to 0.76 |
| Head centre left or right of the picture's centre | +0.05 | -0.01 to +0.18 |

### Finding the head and neck

| | Face points only | With the segmenter's hair, face skin and body skin |
|---|---|---|
| Hair cut off at the top or sides (worst photo) | 0.7% (a default person's wide hair), 0.4% (full-length) | 0% on every photo |
| Neck cut off (body skin within half a face height of the chin) | 0% | 0% |
| Face share after (target 0.471) | 0.468 to 0.484 | 0.445 to 0.481 |

Both put every head where the default people's are; the segmenter keeps the top and sides of
big hair in, by growing the square up to 1.35 times (`MAX_GROW`) with the bottom kept, and
centres it on the head rather than the face. Where the square reaches past the photo (Larry's
photo, 13% of the square; `near_edge`, 12%), the edge's pixels are stretched outward and blurred
over a twelfth of the side, which reads as a soft wash with no line (a narrower blur left
streaks). The landmarker misses faces under about 100 px in a big photo (the full-length one):
looking again in a square three times the segmenter's face skin, enlarged to 512 px, found it.

### Enlarging

| Method | Licence | Model | 256 to 1024 px | Memory | Faces shrunk to 100 / 160 / 200 px and enlarged back: PSNR at the video's face size | Looks |
|---|---|---|---|---|---|---|
| **Lanczos** (OpenCV) | Apache 2.0 | none | 4 ms | 2 MB | 37.1 / 41.3 / 43.5 dB | soft, true to the person |
| FSRCNN x2 | Apache 2.0 | 38 KB | 258 ms | 276 MB | 37.1 / 40.8 / 42.6 dB | the same as Lanczos |
| ESPCN x2 | Apache 2.0 | 84 KB | 176 ms | 111 MB | 36.5 / 40.1 / 41.7 dB | the same as Lanczos |
| Real-ESRGAN general x4v3 (ONNX) | BSD 3-clause | 4.7 MB | 416 ms (1 to 9 s on the real photos) | 75 MB | 29.4 / 35.1 / 36.7 dB | sharp, but paints the eyes, lips and skin: a different-looking person |

Real-ESRGAN passes the sharpness check on every photo, even the 89 px full-length face, but it
does so by inventing detail: dark outlined eyes and smooth painted skin that are not the
person's (see `enlarging.png` and `small-faces.png`). It loses the likeness, which item 189
rules out. FSRCNN and ESPCN are no closer to the original than Lanczos and take 50 to 250 times
as long.

### The photo checks on the results

With Lanczos, every result passes R8 and R9's checks with a score of 84 to 96, except the
full-length photo (89 px face), which fails as blurry with every method but Real-ESRGAN. The
waist-up and near-edge photos (188 px faces) pass at 86 and 87.

## Recommended

- **Finding the head:** the face points with the segmenter's hair and face skin
  (`box_from_segments`), since it never cut hair off where the points alone did, and the
  segmenter is already run by the photo checks. When the landmarker finds no face, look again
  around the segmenter's face skin (`find_small_face`).
- **Framing:** a square with the face 0.47 of its side, the chin 0.60 face heights above the
  bottom, at least 0.04 face heights above the hair (growing up to 1.35 times for tall hair),
  centred on the head; past the photo's edge, stretched and blurred over a twelfth of the side.
- **Enlarging:** Lanczos, with no model. It is the closest to the original, takes milliseconds
  and needs no download; so R235 needs no `models/enlarge` folder and no fallback.
- **The smallest face:** 180 px from mid-forehead to chin in the original photo, the same number
  R8 uses today (`MIN_FACE_PX`). The 188 px faces enlarge and pass; the faces shrunk to 160 px
  lose 2 dB more and start to fail the sharpness check, and the 89 px face is blurry. R235 should
  judge it on the original, as planned, since the enlarged picture's face is always about
  480 px.
