# Lip-reading test: photoreal mouth shapes timed to each sound

A test, not part of the app. It covers roadmap R4a (mouth alignment and tuning) and the
timing half of R4b (per-sound timings), and checks Larry's acceptance goal: with the sound
off, can you follow the words from the lips? The test sentences are:

> Hello, my name is Mary. Would you like some more popcorn? Please move the blue boat.
> I see three green trees.

## What changed from the photoreal test (PR #8)

- **The mouth opens straight down.** The old "open" edit moved one LivePortrait keypoint
  (19) on its own, and the lower lip drifted sideways. Opening now goes through
  LivePortrait's lip retargeting model, which moves the mouth keypoints together.
  `before_after.png` shows AA, OH and OO both ways.
- **10 mouth shapes** (`lip_shapes.py`), each a lip opening plus rounding or spreading,
  with a small gap between the lips: rest, MBP (lips pressed), FV (teeth on lower lip),
  AA, EH, EE, IH (small opening for t, d, n, s, k, l), OH, OO (also w) and SH (also r).
- **Timed to each sound.** Kokoro's ONNX model is patched in memory to also return how long
  it makes each phoneme (25 ms steps that add up exactly to the audio), so the mouth lines
  up with the voice. `sounds.json` lists the shapes and times.
- **Smooth in-betweens.** Shapes blend over several frames, the way lips start the next
  sound early. m, b, p, f and v always get one frame with the lips touching, even when the
  sound is shorter than a frame.
- **Fast per reply.** Setup renders the 10 shapes once and the optical flow between each
  pair. Per reply no model runs: each frame morphs between its two strongest shapes along
  the flow (no double lips from a plain cross-fade), is pasted into the photo and encoded.
  `--direct` also renders every frame with LivePortrait as a slow reference.

- **Softer, calmer lips.** Larry found the full shapes too pronounced on his photo, and
  then 60% still too strong, mostly the upper lip (2026-10-06). Now:
  - `--strength 0.45` (default): each shape moves only 45% of the way from the photo's rest
    position; 1.0 is the full shape. m, b, p, f and v still close the lips.
  - `--upper 0.3` (default): the upper lip (LivePortrait keypoint 20) moves only 30% as far
    as the rest of the mouth, which keeps it from lifting and baring the teeth.
  - `--smooth 0.06` and `--lead 0.03` (defaults): sounds blend over 60 ms, so the lips
    move more slowly with more in-between frames, and each shape starts 30 ms before its
    sound so it still lands on time.

The head is still in this test; mood loops, blinks and head motion come back in R4c.

## Licenses

LivePortrait code and weights: MIT. MediaPipe Face Landmarker: Apache 2.0. Kokoro-82M
(ONNX build from github.com/thewh1teagle/kokoro-onnx, MIT code, Apache 2.0 weights). No
InsightFace models are downloaded or run.

## Results

Measured 2026-10-06 in a 4-core cloud container (Intel Xeon, PyTorch 2.14 CPU, 4 threads)
with the real weights, on two portraits from LivePortrait's examples: the Mona Lisa
(public domain, cropped to head and shoulders, 560 x 640, face turned slightly) and a
frontal photo (512 x 512, lips slightly apart at rest).

| Step | Mona Lisa | Frontal photo |
|---|---|---|
| Setup: 10 mouth shapes + 90 flows, once per photo | 49 s | 49 s |
| Per reply, speech + sound timings (Kokoro) | 2.0 s | 2.1 s |
| Per reply, frames + encode (8.5 s clip, 254 frames at 30 fps) | 4.4 s | 3.2 s |
| `--direct` reference, every frame through LivePortrait | 18 min | 18 min |

- Per reply the four sentences (8.5 s of speech) take about 6 s in all, faster than real
  time; scaled down, a two-second reply should take about 1.5 s (not measured). Streaming sentence by sentence (R4c or
  later) would let the video start after the first sentence.
- The fast clip and the frame-by-frame reference look nearly the same frame for frame, so
  the morph between pre-rendered shapes does not lose the lip shapes.
- Setup is under a minute because the head is still. With mood loops, blinks and head
  motion (R4c) it grows to the hours estimated in PR #8.
- The retargeting model opens the lips relative to how they are in the photo, so a photo
  with closed lips works best; on a photo with parted lips, rest and pauses keep that gap.

## Run it

This is a separate test script, not `imageskin sample`: `sample.mp4` from that command
still uses the old OpenCV mouth and will look the same as before. Get this PR's branch
first, from the repository folder:

```
git fetch origin test/lipread-photoreal
git checkout test/lipread-photoreal
```

Needs Python 3.11 or 3.12, git and ffmpeg (see the main README), and the photoreal setup:
if you ran PR #8's test, `experiments/photoreal/LivePortrait/` is already there and the
setup step finishes at once. The first run also downloads Kokoro's ONNX files (354 MB)
from github.com into `experiments/lipread/models/`, with a progress line every 5 s and
resume after a stall.

Use a clean-shaven, front-facing photo with the mouth closed; a moustache hides most of the
mouth. Swap `me.jpg` for your photo's path. `--voice am_adam` gives a male voice
(default `af_heart`).

macOS / Linux (on a Linux server, MediaPipe also needs `sudo apt install libegl1 libgles2`):

```
. .venv/bin/activate
pip install -r experiments/lipread/requirements.txt
python experiments/photoreal/setup_liveportrait.py
python experiments/lipread/lipread.py --photo me.jpg
```

Windows 11, Command Prompt:

```
.venv\Scripts\activate
pip install -r experiments\lipread\requirements.txt
python experiments\photoreal\setup_liveportrait.py
python experiments\lipread\lipread.py --photo me.jpg
```

Windows 11, PowerShell:

```
.venv\Scripts\Activate.ps1
pip install -r experiments\lipread\requirements.txt
python experiments\photoreal\setup_liveportrait.py
python experiments\lipread\lipread.py --photo me.jpg
```

To compare how pronounced the lips are, run it again with `--strength 1.0`, `--strength 0.4`
and so on, each with its own `--out` folder, for example
`--strength 0.4 --out lipread_40`.

Add `--direct` for the frame-by-frame reference (about 2 s per frame on a 4-core CPU, so
several minutes for the four sentences).

Output goes to `lipread_out\` (Windows) or `lipread_out/` in the folder you run it from
(change it with `--out`):

- `lipread_voice.mp4`: the four sentences with the voice
- `lipread_muted.mp4`: the same video with no sound, for the lip-reading check
- `mouth_shapes.png`: the 10 mouth shapes, zoomed on the mouth
- `before_after.png`: open shapes with the old single-keypoint edit and the new one
- `sounds.json`: each mouth shape with its start and end in seconds
- `voice.wav`, `timings.json`; with `--direct` also `direct_voice.mp4`, `direct_muted.mp4`

The log shows `Lips in the photo: gap ratio ...`, `Setup done: 10 mouth shapes and 90
flows`, one `Spoke ...` line per sentence with its phonemes, and `Reply clip built` with
the time taken.

### Play the results

Run these from the same folder you ran the test in. Watch `lipread_muted.mp4` first, with
no sound, and try to follow the four sentences; then `lipread_voice.mp4` to check.

Windows 11, Command Prompt:

```
start lipread_out\lipread_muted.mp4
start lipread_out\lipread_voice.mp4
start lipread_out\mouth_shapes.png
start lipread_out\before_after.png
```

Windows 11, PowerShell:

```
Invoke-Item lipread_out\lipread_muted.mp4
Invoke-Item lipread_out\lipread_voice.mp4
Invoke-Item lipread_out\mouth_shapes.png
Invoke-Item lipread_out\before_after.png
```

macOS: `open lipread_out/lipread_muted.mp4` (and so on). Linux: `xdg-open lipread_out/lipread_muted.mp4`.
