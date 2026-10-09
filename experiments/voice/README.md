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

# Accent test (R26a)

Can the app speak in the person's own voice with a different accent? Voice conversion keeps the
person's timbre and takes the accent from whatever voice speaks first, so `accent_test.py` makes
three chat replies four ways, all in the person's voice:

| Column | Where the accent comes from | Tools |
|---|---|---|
| Your accent | the person's own clone, as the app speaks today | Chatterbox Turbo |
| American | one of Kokoro's 19 American voices, converted | Kokoro, Chatterbox's converter |
| British | one of Kokoro's 8 British voices, converted | Kokoro, Chatterbox's converter |
| A donor (`--donor NAME=recording.wav`) | a recording of someone with that accent: the clone speaks in their voice, then it is converted | Chatterbox Turbo, Chatterbox's converter |

The Kokoro voice is picked to suit the person, because conversion keeps more of the base voice
when it starts far from the person: every voice of the accent says a probe line and is
converted, and the closest to the person's recording after conversion wins (about 95 seconds for
American, 40 for British, logged as `Picked base voice`). R25a converted only
`am_michael`, which Larry said did not sound like him.

The page shows each clip's speaker similarity to the recording (SpeechBrain ECAPA, as in R25a)
and the English accent a classifier hears ([CommonAccent ECAPA](https://huggingface.co/Jzuluaga/accent-id-commonaccent_ecapa),
MIT, 16 accents such as `us` and `england`, none of them Slavic), with its score (each accent is
scored on its own, so the scores don't add up to 1).

## Results on Larry's voice (cloud, 4-core CPU, 2026-10-09)

Donor: a Bulgarian man from the [EdAcc](https://groups.inf.ed.ac.uk/edacc/) accent corpus
(CC BY-SA 4.0), standing in for Russian-English until a recording is found. It is in
[`donors/`](donors/README.md) with a Polish woman from the same corpus. Means over the three replies:

| Column | Base voice picked | Similarity to Larry | Seconds per second of speech | Accent heard |
|---|---|---|---|---|
| Your accent | | 0.76 | 2.67 | Canadian, American, South Atlantic |
| American | `am_onyx` | 0.76 | 1.06 | American, 3 of 3 |
| British | `bm_lewis` | 0.66 | 1.04 | British, 3 of 3 |
| Slavic donor | | 0.65 | 3.00 | American, New Zealand 2 (no Slavic class) |

A changed accent's seconds per second of speech count the base voice speaking and the conversion,
since every reply pays both. Every Kokoro voice of the accent is converted before picking:
conversion reorders them. `am_onyx` was not among the three closest before conversion, so an
earlier version that converted only those three never tried it and picked `am_liam` (0.73). The
accent classifier is pinned to the revision these results were heard with. Timings vary with the
machine's load: an earlier run of the same lines measured 2.12 for the clone and 0.75 for British.

So British comes through clearly in Larry's voice, at about real time, at a lower similarity than
his clone (0.66 against 0.76; above about 0.5 usually means the same speaker). Converted American
scores as close as the clone. Whether the Slavic donor's accent survives the
conversion needs ears: the classifier has no Slavic accent to hear.

A second run added real American and British speakers as donors (`donors/american-male.wav` and
`donors/british-male.wav`, from EdAcc) to compare with Kokoro's voices. They sounded about as much
like Larry (American 0.71 against 0.70, British 0.67 against 0.64), but the British donor's accent
came through less (heard as British in 1 of 3 replies, against 3 of 3 for Kokoro's), and a donor
takes about three times as long (2.9 against 0.8 seconds per second of speech).

## Run it

Set up as for the voice cloning test above, then (Windows: `experiments\voice\accent_test.py`):
```
python experiments/voice/accent_test.py --sample voice-sample.wav --donor Slavic=experiments/voice/donors/slavic-bulgarian-male.wav -o accent-test
```
Pick the donor that matches the person (`slavic-polish-female.wav` for a woman). Your own donor
recording must be a 24 kHz mono WAV like the voice sample; make it with
`imageskin voice-sample donor.m4a -o donor.wav`. The first run also downloads Kokoro's British
voices and the accent classifier (about 100 MB). Open `accent-test/index.html` in a browser.
