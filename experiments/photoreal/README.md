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
| LivePortrait weights (huggingface.co/KwaiVGI/LivePortrait) | to be confirmed on Hugging Face | models |

LivePortrait's own face detector comes from InsightFace, whose models are
non-commercial, so this test never downloads or runs them. The animal models (X-Pose)
are skipped for the same reason.

## Results so far

Measured in a 4-core cloud container (Intel Xeon 2.8 GHz, PyTorch 2.5.1, 4 threads) with
stand-in weights of the exact LivePortrait architecture and size (random values), because
Hugging Face was not reachable. Speed depends only on the architecture, so the timings
hold; the pictures do not, so real samples come with the next run.

| Step | Time |
|---|---|
| Prepare the photo (find face, extract features) | 7.1 s, once |
| Render one frame | about 5 s (warp 2 s, decode 3 to 5 s) |
| Setup in this run: 2 moods x 8 mouth shapes x 10 frames = 160 frames | 13 min |
| Per reply: 2.5 s clip, assemble + encode | 0.66 s, about 4x faster than real time |

bfloat16 on this CPU was twice as slow, so the test uses float32.

Full plan estimate at 5 s per frame: 4 moods x 15 mouth shapes x a 2 s loop at 25 fps is
3000 frames, about 4 hours of setup on a 4-core CPU. Halving the loop length or the number
of moods halves that. A faster laptop CPU should beat the cloud container.

## Run it

Needs Python 3.11 or 3.12, git and ffmpeg (see the main README). About 500 MB downloads
once from github.com, huggingface.co and storage.googleapis.com. The default run renders
2 moods x 8 mouth shapes x 50 frames = 800 frames, which takes about an hour at 5 s per
frame; add `--loop-seconds 0.4` for a 10-minute run.

macOS / Linux (on a Linux server, MediaPipe also needs `sudo apt install libegl1`):

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

- Tune the mouth shapes and add the rest of the 12 to 15.
- Drive mouth shapes from Kokoro's phoneme timings and add the voice track.
- Cut setup time: fewer loop frames with interpolation, or an ONNX export of the models.
