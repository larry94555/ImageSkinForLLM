# Can the OpenCV mouth look natural?

Larry found the PR #7 mouth looks like a ventriloquist's dummy. This experiment answers whether tuning that engine can fix it, by rendering one photo and one text three ways side by side, with the voice:

1. **PR #7**: the current engine: the mouth opens with loudness, with a wide dark opening.
2. **Softer**: opens about 40% as far, lighter warm opening, faint upper teeth on open vowels.
3. **Sounds**: the softer mouth driven by the phonemes Kokoro speaks. It closes on m, b and p (even when the sound is shorter than a frame), rounds and narrows on "oo", "oh" and "w", opens widest on "ah", and eases between shapes. Loudness scales each shape.

Both new versions also move the mouth line onto the darkest row near it (the seam between the lips), which fixes cases where PR #7's redness search lands a few pixels high.

It is a test, not part of the app; PR #7 is unchanged. Speech comes from Kokoro's ONNX build ([kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx), MIT; model Apache 2.0), downloaded once (about 337 MB) from GitHub, not Hugging Face, into `experiments/mouth_opencv/models/`. The download logs MB done, speed and time left every 5 seconds, retries after 30 seconds without data, resumes from the saved `.part` file (also when you run the script again), and checks each file's SHA-256. The script patches a copy of the model to also return each phoneme's length.

## Run it

Needs the app's `video` extra, ffmpeg on PATH, and Python 3.11 or 3.12. Use a front-facing, closed-mouth photo.

macOS / Linux:
```
. .venv/bin/activate
pip install -e ".[video]" -r experiments/mouth_opencv/requirements.txt
python experiments/mouth_opencv/compare.py --photo me.jpg
```

Windows 11, Command Prompt:
```
.venv\Scripts\activate
pip install -e ".[video]" -r experiments\mouth_opencv\requirements.txt
python experiments\mouth_opencv\compare.py --photo me.jpg
```

Windows 11, PowerShell:
```
.venv\Scripts\Activate.ps1
pip install -e ".[video]" -r experiments\mouth_opencv\requirements.txt
python experiments\mouth_opencv\compare.py --photo me.jpg
```

It prints `Spoke N s of audio` and `Wrote ...mouth_compare.mp4`, written to the folder you run from. `--text "..."` speaks other text (default: the item 6 test script), `--voice am_michael` picks another voice, `--panel 360` makes the video smaller.
