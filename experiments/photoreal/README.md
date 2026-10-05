# Photoreal test: LivePortrait on the CPU

A test, not part of the app. It checks whether photoreal video can work on a CPU with the
pre-rendered plan:

- **Setup, once per photo (slow is fine):** LivePortrait renders each mood's base loop
  (small head motion and a blink) once for every mouth shape (viseme).
- **Per reply (must be fast):** no model runs. For each video frame, pick the cached frames
  for the current and next mouth shape, cross-fade them, paste the face back into the
  photo and encode.

## Licenses

| Part | License | Used for |
|---|---|---|
| LivePortrait code (KwaiVGI/LivePortrait) | MIT | warp + decode |
| MediaPipe Face Landmarker | Apache 2.0 | finding the face (replaces InsightFace) |
| LivePortrait weights (huggingface.co/KlingTeam/LivePortrait, formerly KwaiVGI) | MIT (model card, checked 2026-10-05) | models |

LivePortrait's own face detector comes from InsightFace, whose models are
non-commercial, so this test never downloads or runs them. The animal models (X-Pose)
are skipped for the same reason.

## Results with the real weights

Measured 2026-10-05 in a 4-core cloud container (Intel Xeon, PyTorch 2.14 CPU, 4 threads,
float32) with the real LivePortrait weights. Test photos: LivePortrait's example portraits
of the Mona Lisa (1280 x 720) and Einstein around 1904 (500 x 375), both public domain.

| Step | Mona Lisa | Einstein |
|---|---|---|
| Prepare the photo (find face, extract features) | 2.6 s, once | 13.6 s, once (first run) |
| Render one frame | 4.8 s | 5.3 s |
| Setup in this run (2 moods x 8 mouth shapes x N frames) | 400 frames, 31 min | 160 frames, 12 min |
| Per reply: 2.5 s clip, assemble + encode | 1.3 to 1.5 s | 0.49 s |

- The pictures are photoreal: skin, teeth and lips come from the photo, with no puppet look.
  Mouth opening shows best on a clean-shaven face; a heavy moustache hides most of it.
- Per-reply time grows with photo size, because each frame is pasted back into the full
  photo and encoded. At 1280 x 720 it is still about 1.7x faster than real time; a 720 px
  photo would be about 3x.
- Mouth shapes were tuned by eye on the Mona Lisa: pressed lips (MBP) and the f/v shape
  were too strong before. Blinks now use an expression edit on both eyelids, because
  LivePortrait's eye retargeting model closed only one eye on a turned head. That also
  removed the 114 MB landmark model from the download.
- bfloat16 on this CPU was twice as slow in the earlier stand-in run, so the test uses
  float32.

Full plan estimate at 5 s per frame: 4 moods x 15 mouth shapes x a 2 s loop at 25 fps is
3000 frames, about 4 hours of setup on a 4-core CPU. Halving the loop length or the number
of moods halves that. A faster laptop CPU should beat the cloud container.

## Run it

Needs Python 3.11 or 3.12, git and ffmpeg (see the main README). Setup downloads about
540 MB once: 37 MB of code from github.com, 522 MB of weights from huggingface.co (files
are served from us.aws.cdn.hf.co) and 4 MB from storage.googleapis.com.

Setup prints git's progress, then a line every 5 seconds per weights file with MB done,
speed and time left, for example
`spade_generator.pth: 120.3 of 211.5 MB (56%), 3.20 MB/s, about 28 s left`.
If no data arrives for 30 seconds (`--timeout`) it retries and resumes from the bytes
already saved in a `.part` file; it gives up after 5 tries in a row with no progress
(`--retries`). Running it again also resumes, and skips files that are already complete
(each is checked against its SHA-256). Everything lands in
`experiments/photoreal/LivePortrait/` (weights under `pretrained_weights/`).
An earlier version used `huggingface_hub`; its leftover
`pretrained_weights/.cache` folder can be deleted.

The default run renders 2 moods x 8 mouth shapes x 50 frames = 800 frames, which takes
about an hour at 5 s per frame; add `--loop-seconds 0.4` for a 10-minute run (loops under
1 s skip the blink).

macOS / Linux (on a Linux server, MediaPipe also needs `sudo apt install libegl1 libgles2`):

```
. .venv/bin/activate
pip install -r experiments/photoreal/requirements.txt
python experiments/photoreal/setup_liveportrait.py
python experiments/photoreal/liveportrait_cpu.py --photo me.jpg
```

Windows 11, Command Prompt:

```
.venv\Scripts\activate
pip install -r experiments\photoreal\requirements.txt
python experiments\photoreal\setup_liveportrait.py
python experiments\photoreal\liveportrait_cpu.py --photo me.jpg
```

Windows 11, PowerShell:

```
.venv\Scripts\Activate.ps1
pip install -r experiments\photoreal\requirements.txt
python experiments\photoreal\setup_liveportrait.py
python experiments\photoreal\liveportrait_cpu.py --photo me.jpg
```

The setup step puts LivePortrait and its weights in `experiments/photoreal/LivePortrait/`
(ignored by git). The test writes to `photoreal_out/` in the folder you run it from
(change it with `--out`):

- `mouth_shapes.png`: the 8 mouth shapes side by side
- `loop_neutral.mp4`, `loop_happy.mp4`: each mood's base loop with the mouth at rest
- `reply_neutral.mp4`, `reply_happy.mp4`: "Hello, how are you today?" built from the cache
  (silent; timings are hand-set)
- `timings.json`: the numbers above for your CPU

The log shows `Portrait ready`, `Mouth shapes rendered: N s per frame`, one
`Mood ... rendered` line per mood and one `Reply clip ... built` line per mood.

## Next steps if it looks right

- Add the rest of the 12 to 15 mouth shapes.
- Drive mouth shapes from Kokoro's phoneme timings and add the voice track.
- Cut setup time: fewer loop frames with interpolation, or an ONNX export of the models.
