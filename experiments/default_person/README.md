# Default person test (R24a, R24a2)

Can the app start with a made-up person instead of the user's own photo and voice (features.md
items 56 to 58)? This test makes eight default people, photoreal and animated, male and female,
in four roles, with an open text-to-image model, runs the app's own photo checks on each picture,
prepares it with the photoreal engine (R4c), and renders a short line in both of Kokoro's
ready-made voices for the person's gender, American and British. It is a test, not part of the
app; R24b makes and packs all 36 people with the tool Larry accepts here.

| Person | Role's look |
|---|---|
| Photoreal man, Professor; animated woman, Professor | late fifties, tweed jacket, university office |
| Photoreal woman, Boss; animated man, Boss | late forties, dark suit, glass office |
| Photoreal woman, Parent; animated man, Parent | early forties, casual sweater, family kitchen |
| Photoreal boy, Teenager; animated girl, Teenager | sixteen, hoodie, bright bedroom |

Every prompt asks for one person facing the camera with a closed mouth and the whole face
visible, and names no real person or public figure (item 57). The prompts are in
`default_person.py` (`prompt`), and the page shows each one under its picture.

## The picture tool

**[Segmind SSD-1B](https://huggingface.co/segmind/SSD-1B)**, through Hugging Face's Diffusers
(Apache 2.0), 25 steps at 1024 by 1024, a fixed seed per person so a rerun makes the same
picture.

- **License:** Apache 2.0, so the pictures can be used commercially and on a hosted site, and
  each costs nothing to make. No sign-in is needed to download it.
- **Size:** a distilled Stable Diffusion XL, half its size (1.3 billion parameters in its UNet),
  so it runs on a CPU: about 11 minutes a picture on a 4-core cloud CPU. That is fine because
  the pictures are made once, ahead of time (item 57), never while the user waits.
- **To note:** Segmind says it was trained on several datasets, including Grit and "Midjourney
  scrape data", and distilled from SDXL. The license covers the model and what it makes; where
  its training pictures came from is Segmind's responsibility, as with any model of this kind.
- **Rejected:** FLUX.1-schnell (Apache 2.0, but its download is gated behind a Hugging Face
  sign-in, and at 12 billion parameters it is too large for a CPU); SDXL-Turbo and SD-Turbo
  (non-commercial license); Stable Diffusion XL base (OpenRAIL++, which allows commercial use
  with use restrictions; about twice as slow on the CPU; kept as the fallback if SSD-1B's
  pictures don't look right to Larry).

## The voices

One of [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)'s ready-made voices for each
gender and accent, the best rated of each kind in Kokoro's
[VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) (its grade estimates
the quality and amount of each voice's training data):

| Gender, accent | Voice | Kokoro language code | Grade |
|---|---|---|---|
| Female, American | `af_heart` | `a` | A |
| Male, American | `am_michael` | `a` | C+ (the best American man's grade, shared with `am_fenrir` and `am_puck`) |
| Female, British | `bf_emma` | `b` | B- |
| Male, British | `bm_george` | `b` | C (shared with `bm_fable`) |

- **Where they come from:** `voices/<name>.pt` in the
  [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) repository on Hugging Face
  (Kokoro v1.0, 2025-01-27, trained by hexgrad), downloaded with the model the first time a
  voice is used, as the app already does for `af_heart`.
- **License:** Apache 2.0, for the model and its voices. Kokoro's model card says it was trained
  only on permissive or non-copyrighted audio (such as Apache- or MIT-licensed audio, and
  synthetic audio from closed TTS models), with no audio from open TTS models or voice clones.
  The English voices list no CC BY training data.
- **Attribution:** Apache 2.0 asks that a copy of the license and any NOTICE file go with the
  model if it is redistributed. Speech made with it needs no credit. The app already credits
  Kokoro (Apache 2.0) in `pyproject.toml`; R24c should name these four voices where the app
  lists its third-party parts.
- **Use terms:** none beyond Apache 2.0. They are presets, not clones of anyone the user brings,
  which is why item 58 asks for no consent.

## Results (cloud, 4-core CPU, 2026-10-16)

All eight pictures passed every photo check (one face, size, head turn, covering, light and
sharpness) and all eight prepared and talked in both voices: 16 videos, none failed. The
animated faces were found by the photoreal engine's face finder like the photoreal ones.

| Person | Photo check score | Head turn |
|---|---|---|
| Photoreal man, Professor | 84 | 15° |
| Photoreal woman, Boss | 82 | 16° |
| Photoreal woman, Parent | 80 | 18° |
| Photoreal boy, Teenager | 82 | 16° |
| Animated woman, Professor | 86 | 15° |
| Animated man, Boss | 88 | 10° |
| Animated man, Parent | 89 | 3° |
| Animated girl, Teenager | 91 | 8° |

- **Time:** 11.2 to 11.7 minutes to make each picture, 4.7 to 6.2 minutes to prepare it, and
  2.7 to 5.1 seconds to speak and render the 4-second line (7.3 for the first, which loads
  Kokoro), as for any other photo.
- **Memory:** the picture model and the photoreal engine together ran out of 16 GB, so the
  script makes every picture first and frees the picture model before preparing.
- **What to look at:** every photoreal face is turned 15 to 18 degrees despite the prompt
  (the limit is 25), and all eight people came out white and look alike in age within each
  realism (the professors look about forty, not late fifties). R24b's prompts should ask for a
  range of skin tones, ages and hair, and may need a second seed when a face is turned too far.

## More varied faces (R24a2)

R24a's eight people all came out white and alike, so `--varied` makes a second face for each of
them (`VARIED_PEOPLE`), each of a different heritage with hair to suit: Black, East Asian, South
Asian, Latino, Middle Eastern, Southeast Asian and Indigenous, beside R24a's white faces. Only the
prompt describes the look; files are named by number (`photoreal_male_professor_2.png`), and no
page a user sees names anyone's heritage (features.md item 60).

The person goes first in these prompts (`a man in their late fifties, <look>, wearing ...`, then
the style and framing). Added at the end of R24a's prompt, the look was ignored, and the first
try made a white professor again; the end of a long prompt has little effect, and the text
encoder keeps only the first 77 tokens, so the setting now comes last and is cut. R24a's own
prompts are unchanged, so its pictures can be made again from the same seed.

### Results (cloud, 4-core CPU, 2026-10-17)

All eight passed every photo check and all eight prepared and talked in both voices: 16 videos,
none failed. The darker and the animated faces were found like the others.

| Second face | Photo check score |
|---|---|
| Photoreal man, Professor | 95 |
| Photoreal woman, Boss | 84 |
| Photoreal woman, Parent | 84 |
| Photoreal boy, Teenager | 82 |
| Animated woman, Professor | 83 |
| Animated man, Boss | 91 |
| Animated man, Parent | 86 |
| Animated girl, Teenager | 82 |

- **Time:** 8.6 to 9.2 minutes to make each picture and 3.7 to 4.4 to prepare it.
- **Look:** `resources/default-people/contact-sheet.png` shows R24a's eight above the new
  eight. Each new face has the clothes its role asks for.

## Run it

Uses the app's own virtual environment (`.venv`, already set up with the `voice`, `photoreal`
and `faces` extras), Python 3.11 or 3.12, and ffmpeg. The first run downloads about 4.2 GB for
SSD-1B (its half-size weights), plus Kokoro's and the photoreal engine's models if not already
there; they are cached for later runs. The install changes nothing the app or the
cloned voice uses. Its first command puts transformers in the cloned voice's tested range (5.18
or 5.19) if it isn't already, for example after an earlier version of these steps upgraded it to
5.20, and otherwise does nothing. The next saves every installed package as a constraint, so the
third adds only Accelerate (and psutil) and stops with a conflict rather than change anything.
pip's warnings that `chatterbox-tts` wants older torch, numpy and other packages are expected:
it is installed without its own pins (see `clone-requirements.txt`). They print as a red "ERROR: pip's
dependency resolver ..." block, but the step worked if it ends with `Successfully installed ...`
or only `Requirement already satisfied` lines; a real failure ends with `ResolutionImpossible`.

It takes about 17 minutes a person on a 4-core CPU:
about 11 to make the picture and 6 to prepare it. Pictures and prepared people are kept, so a
rerun after an interruption skips what is done. `--pictures-only` makes and checks the pictures
without preparing them. On Linux without a desktop, MediaPipe needs `libegl1`
(`sudo apt-get install libegl1`).

macOS / Linux:
```
source .venv/bin/activate
pip install "transformers>=5.18,<5.20"
pip freeze --all --exclude-editable > app-constraints.txt
pip install -r experiments/default_person/requirements.txt -c app-constraints.txt
cd experiments/default_person
python default_person.py -o ../../default-person-test
python default_person.py --varied -o ../../default-person-varied
```

Windows 11, Command Prompt:
```
.venv\Scripts\activate.bat
pip install "transformers>=5.18,<5.20"
pip freeze --all --exclude-editable > app-constraints.txt
pip install -r experiments\default_person\requirements.txt -c app-constraints.txt
cd experiments\default_person
python default_person.py -o ..\..\default-person-test
python default_person.py --varied -o ..\..\default-person-varied
```

Windows 11, PowerShell:
```
.venv\Scripts\Activate.ps1
pip install "transformers>=5.18,<5.20"
pip freeze --all --exclude-editable | Set-Content -Encoding ascii app-constraints.txt
pip install -r experiments\default_person\requirements.txt -c app-constraints.txt
cd experiments\default_person
python default_person.py -o ..\..\default-person-test
python default_person.py --varied -o ..\..\default-person-varied
```

The second line is R24a2's eight second faces, run the same way into their own folder.

Open `default-person-test/index.html` (or `default-person-varied/index.html`) in a browser (double-click it; no server needed). It fills
in as each person is done. While it runs, the window shows `[3/8] Picture: …` for each picture,
then `[3/8] Video: …` for each person being prepared and rendered, between the JSON log lines. It
is finished when it logs `"message": "Default person test done"` (with `passed_photo_checks`,
`talked_in_both_voices` and the run's `duration_ms`), prints `Done: 8 of 8 passed the photo
checks, 8 talked in both voices.` and `Wrote …index.html`, and the prompt comes back. The folder then holds 8 pictures, 16 videos
(`<person>_american.mp4` and `<person>_british.mp4`), `index.html` and `results.json`. Each person is logged as a `Default person done` JSON line with their
photo check result (`problems`, `score`), `videos`, `picture_ms` and `prepare_ms`; a step that
fails is logged as `Default person failed` with the step, and the run goes on to the next
person.
