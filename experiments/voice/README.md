# Voice cloning test (R25a)

Can the app speak in the person's own voice, on the CPU, free per use? This test makes the
sample script (features.md item 6) and three short chat replies in the person's voice with two
candidate tools, times them, and builds a page to listen to them side by side with the person's
own recording and today's ready-made Kokoro voice. It is a test, not part of the app; R25 builds
the tool Larry picks.

| Voice | What it does | Accent | License |
|---|---|---|---|
| Kokoro | Today's ready-made voice (`am_michael`), for comparison | American | Apache 2.0 |
| Conversion | Kokoro speaks, then [Chatterbox](https://github.com/resemble-ai/chatterbox)'s voice converter changes the timbre to the person's. The timing is unchanged, so Kokoro's word and sound timings still drive the lips and the word highlighting. | American | MIT |
| Clone | Chatterbox Turbo speaks the text directly in a voice cloned from the sample | the person's own | MIT |

Both tools learn the voice from 10 seconds of the voice sample (leading silence skipped), with no
training. Chatterbox adds Resemble AI's inaudible Perth watermark to what it makes. The
converter uses the one-step decoder that ships with Chatterbox Turbo: on 4 CPU cores it converts
5.8 seconds of speech in 2.1 seconds, against 11.4 seconds with its default ten-step decoder, at
the same speaker similarity.

## Results on a stand-in voice (cloud, 4-core CPU)

Run on the R10 test recordings (`recording-1.m4a` and `recording-2.m4a`) while waiting for
Larry's. Seconds of work per second of speech (below 1 is faster than real time) and the speaker
similarity to the recording (SpeechBrain ECAPA; the two recordings score 0.98 against each
other, and above about 0.5 usually means the same speaker):

| Voice | Line 1 (24 s script) | Chat replies (3 to 5 s each) | Similarity |
|---|---|---|---|
| Kokoro | 0.52 (first call loads the model) | 0.22 to 0.29 | 0.07 to 0.18 |
| Conversion | 0.78 more | 0.43 to 0.56 more | 0.58 to 0.67 |
| Clone | 1.99 | 1.51 to 1.78 | 0.74 to 0.82 |

A speech recognizer (Whisper base) transcribed every chat reply in all three voices word for word.

So conversion fits the latency target per sentence (a 3-second reply sentence adds about 1.5
seconds), and cloning is about one and a half to two times slower than real time on this CPU,
too slow for replies without a faster machine. The clone also has no sound timings for the mouth,
so its clips are not rendered on video here; R25 would need a forced aligner for it. Loading
both tools takes about 22 seconds once; learning a voice takes under 2 seconds.

## Run it

Uses the app's own virtual environment (`.venv`, already set up with the `voice` and `photoreal`
extras), Python 3.11 or 3.12, and ffmpeg. Chatterbox pins old versions of torch, numpy and other
packages that would downgrade the app's, so it is installed without its pins (`--no-deps`), and
`requirements.txt` pins what it really needs to the versions that were measured (with torch
2.14.1 and numpy 2.4.6). The first command saves every package already installed, pip and setuptools
included (`--all`), as a constraint, so if the install would change any of them, pip stops with a
conflict instead (checked on a fresh Python 3.11 setup with setuptools 84: torch, numpy, OpenCV,
Starlette and setuptools stayed the same). Chatterbox's watermarker imports `pkg_resources`,
which setuptools 81 removed; the script stands in for the one call it makes rather than
downgrading setuptools.

The first run downloads about 2.8 GB of Chatterbox models from Hugging Face (plus Kokoro's and
the similarity model's if not already there), which dominates its time on a slow connection; they
are cached for later runs. The script turns off Hugging Face's Xet transfer, which crawled on a
Windows laptop, and skips a 1 GB file Chatterbox Turbo never loads. Replace `rec1.m4a rec2.m4a`
with your own recordings.

macOS / Linux:
```
source .venv/bin/activate
pip freeze --all --exclude-editable > app-constraints.txt
pip install --retries 10 -r experiments/voice/requirements.txt -c app-constraints.txt
pip install --no-deps chatterbox-tts==0.1.7
imageskin voice-sample rec1.m4a rec2.m4a -o voice-sample.wav
python experiments/voice/run_test.py --sample voice-sample.wav -o voice-test
```

Windows 11, Command Prompt:
```
.venv\Scripts\activate.bat
pip freeze --all --exclude-editable > app-constraints.txt
pip install --retries 10 -r experiments\voice\requirements.txt -c app-constraints.txt
pip install --no-deps chatterbox-tts==0.1.7
imageskin voice-sample rec1.m4a rec2.m4a -o voice-sample.wav
python experiments\voice\run_test.py --sample voice-sample.wav -o voice-test
```

Windows 11, PowerShell:
```
.venv\Scripts\Activate.ps1
pip freeze --all --exclude-editable | Set-Content -Encoding ascii app-constraints.txt
pip install --retries 10 -r experiments\voice\requirements.txt -c app-constraints.txt
pip install --no-deps chatterbox-tts==0.1.7
imageskin voice-sample rec1.m4a rec2.m4a -o voice-sample.wav
python experiments\voice\run_test.py --sample voice-sample.wav -o voice-test
```

Add `--photo me.jpg` to the last command to also get videos.

Open `voice-test/index.html` in a browser (double-click it; no server needed). With `--photo`, the photo is prepared first if it has not been (about 17 minutes on a 4-core CPU), then
the Kokoro and conversion clips are rendered on the photoreal video. Each line is logged as a
`Made line` JSON line with `duration_ms`, `seconds_per_speech_second` and `similarity`.
