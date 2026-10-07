# ImageSkinForLLM

A video "skin" over an LLM chatbot: from one photo and a voice sample, the person in the photo speaks the chatbot's replies in their own voice. See [docs/requirements/features.md](docs/requirements/features.md) and the [roadmap](docs/requirements/roadmap.md).

## Development

Requires Python 3.11 or later, and [ffmpeg](https://ffmpeg.org) on PATH for audio conversion. Install ffmpeg once:

- Windows (Command Prompt or PowerShell): `winget install Gyan.FFmpeg`, then open a new terminal
- macOS: `brew install ffmpeg`
- Linux (Debian or Ubuntu): `sudo apt install ffmpeg`

Check it with `ffmpeg -version`.

If Windows says `'ffmpeg' is not recognized` after installing (or winget says it is already installed), the terminal can't find it yet:

1. Close every terminal (and VS Code, if you use its terminal), open a new Command Prompt and run `where ffmpeg`. If it prints a path, you're done.
2. Check that winget's shortcut exists: `dir "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"` (Command Prompt) or `Test-Path "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ffmpeg.exe"` (PowerShell).
3. If it exists, add that folder to your PATH once, in PowerShell, then open a new terminal:

   ```
   [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";$env:LOCALAPPDATA\Microsoft\WinGet\Links", "User")
   ```

   For the current window only: `set PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links` (Command Prompt) or `$env:Path += ";$env:LOCALAPPDATA\Microsoft\WinGet\Links"` (PowerShell).
4. If it doesn't exist, find the real file in PowerShell with `Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ffmpeg.exe | Select-Object -ExpandProperty FullName` and add its `bin` folder to PATH the same way. A machine-wide install puts the shortcut in `C:\Program Files\WinGet\Links` instead.

Avoid `setx PATH`: it can cut a long PATH short.

Create a virtual environment and install the project once:

macOS or Linux:

```
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Windows Command Prompt:

```
py -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Windows PowerShell (if activation is blocked, first run `Set-ExecutionPolicy -Scope Process RemoteSigned`):

```
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

In a new terminal, run only the activation line again. Then, on any system:

```
ruff check .           # lint
ruff format --check .  # format
mypy                   # type check
pytest                 # unit tests with coverage
```

## Running

```
imageskin --version
imageskin serve                          # open http://127.0.0.1:8000/health, Ctrl+C to stop
imageskin --config config.toml serve     # settings from a file; see config.example.toml
```

Logs are written to stderr as one JSON object per line.

## Browser app

`imageskin serve` also serves the browser app: open http://127.0.0.1:8000/ in a browser. Setup asks you to confirm that the person in the photos and recordings agreed to be copied; the answer is saved in `consent.json` in the app's folder (`IMAGESKIN_HOME`, default `.imageskin` in your home folder). Delete that file to be asked again.

The browser app is TypeScript with [Preact](https://preactjs.com) (a small library that works like React), in `web/`. It is built with Vite into `src/imageskin/static`, which is committed, so running the app needs no Node.js. Read and edit the code in `web/src` (the pages in `pages.tsx`, the layout in `App.tsx`); `static/assets/app.js` is generated from it and `static/assets/preact.js` is the Preact library. They are kept readable (not minified); the server compresses them when it sends them. To change the browser code, install [Node.js](https://nodejs.org) 22 (Windows: `winget install OpenJS.NodeJS.LTS`, then open a new terminal), then on any system:

```
cd web
npm install
npm run dev     # live-reloading app at http://localhost:5173, with `imageskin serve` running for the API
npm test        # unit tests with coverage
npm run build   # type check and build into src/imageskin/static
```

Commit the built files with the source change; CI fails if they are out of date.

## Uploading photos and recordings

Open http://127.0.0.1:8000/#/setup while `imageskin serve` is running to upload photos and recordings in the browser: **Add photos** and **Add recordings** take one or more files at a time, uploaded photos are shown as pictures (click one to open it full size), recordings can be played, and **Remove** deletes a file. A refused file is listed with the reason. The files land in `uploads` inside the app data folder that the server logs at startup.

Behind the screen, the server stores uploaded photos (JPG, PNG, HEIC) and recordings (WAV, M4A, MP3) in `uploads` inside the app's folder, under random names. The type is checked from each file's contents, not its name. Photos are kept as JPG or PNG; recordings are converted to WAV with ffmpeg. Uploads are refused until consent is confirmed. Limits: 25 MB per photo, 100 MB per recording, 10 minutes per recording, 1 GB in total.

| Request | What it does |
|---|---|
| `POST /api/uploads/photos` or `/sounds` | Upload one file (form field `file`) |
| `GET /api/uploads/photos` or `/sounds` | List the uploads |
| `GET /api/uploads/photos/{id}` | Download one (also `/sounds/{id}`) |
| `DELETE /api/uploads/photos/{id}` | Remove one (also `/sounds/{id}`) |
| `POST /api/uploads/photos/{id}/check` | Run the photo checks on a stored photo (also `/sounds/{id}/check` for the sound checks) |
| `GET /api/uploads/photos/chosen` | The photo the video will be made from, and whether the app or you chose it |
| `PUT /api/uploads/photos/chosen` | Use another photo that passed the checks (JSON body `{"id": "…"}`) |
| `GET /api/voice-sample` | How many recordings the voice sample joins, its seconds of speech, and what it still needs |
| `GET /api/voice-sample/audio` | The voice sample as WAV |

Try them on the API docs page at http://127.0.0.1:8000/docs while `imageskin serve` is running.

HEIC photos (from iPhones) need an optional extra: `pip install -e ".[heic]"`. It is optional because pillow-heif's wheels include libheif and libde265 (LGPL-3) and x265 (GPL-2); the app only uses them to read HEIC files.

### Photo checks

Each uploaded photo is checked as it arrives, and the upload screen shows **Looks good** with the photo's score, or what to fix, under it. The checks, each with a fixed message:

| Check | Fails when | Message |
|---|---|---|
| One face | no face, or more than one | "No face was found. …" / "More than one face was found. …" |
| Large enough | the face, mid-forehead to chin, is under 180 px once the photo is shrunk to 1280 px on its longest side, as the video engine does (a 1080p webcam photo of your head and shoulders measures about 200) | "Your face is too small. …" |
| Facing the camera | the head is turned or tilted more than 25° | "Your face is turned away. …" |
| Nothing covering it | over 12% of the face below the eyebrows is hidden by hands, a mask, sunglasses or other things (hair and beards are fine) | "Something is covering your face. …" |
| Sharp | too little fine detail on the face once it is scaled to its size in the video (about 222 px tall): the spread of the Laplacian over the face's average grey level is under 0.05 (sharp phone photos measure 0.1 to 0.23, a 720p webcam photo 0.1) | "The photo is blurry. …" |
| Not too dark | 90% of the face below the eyebrows is darker than 75 of 255 (Lab lightness), so dark skin in good light still passes | "The photo is too dark. …" |
| Not too bright | over 25% of the face is pure white | "The photo is too bright. …" |
| Evenly lit | the darker side of the face is under 0.4 times as light as the other side (a face lit by a window to one side measures about 0.5 and passes) | "One side of your face is in shadow. …" |

Photos that pass every check get a score from 0 to 100: the average of how sharp, large, straight, uncovered, bright and evenly lit the face is, each counted only up to what the video needs. The best scoring photo is outlined and marked **Used for the video (best score)**; **Use this photo** under another photo that passed picks that one instead (**your choice**), which is saved in `uploads/chosen-photo.json`. If the chosen photo is removed, the best scoring one is used again.

The limits were set by measuring real phone and webcam photos and the same photos blurred, darkened, brightened and shaded on one side. They are at the top of `src/imageskin/face_checks.py`; when they change, raise `FACE_CHECKS` in `uploads.py` so photos checked before are checked again. The checks need MediaPipe (Apache 2.0), installed with the faces extra (the photoreal extra includes it too). It needs Python 3.11 or 3.12. On first use the server downloads two models, about 20 MB, into `models/faces` in the app data folder.

```
pip install -e ".[faces]"
```

On a Linux server, MediaPipe also needs `sudo apt install libegl1 libgles2`. Without MediaPipe the server logs `Face checks are off` at startup and photos show **Not checked**. The server downloads and loads the models when it starts (`Face checks ready` in the log), so the first photo isn't held up. Photos uploaded before the checks were on show **Waiting to check**, then **Checking photo…**, and are checked one at a time after the page shows, through `POST /api/uploads/photos/{id}/check`. Each check takes about a second and is logged as `Face checks done` with what it measured (including `sharpness`, `brightness`, `washed_out`, `evenness` and `score`). Choosing a photo is logged as `Photo chosen for the video`.

### Sound checks

Each uploaded recording is checked as it arrives (in about a second per minute of sound, most of it the one-speaker check), and the upload screen shows **Looks good** with its length of speech, or what to fix, under it. Speech is measured in 20 ms steps: the quietest tenth of them, in the pauses between words, gives the background noise level, and the loudest twentieth the speech level. Pauses don't count as speech. The checks, each with a fixed message:

| Check | Fails when | Message |
|---|---|---|
| Long enough | under 15 seconds of speech in the recording | "This recording has only N seconds of speech. …" |
| Not too loud | over 0.05% of the speech is clipped (at the top of what the file can hold) | "The recording is too loud, so parts of it are distorted. …" |
| Little background noise | the speech is less than 20 dB louder than the background noise | "There is too much background noise. …" |
| Only you speaking | a second voice talks for about 3 seconds or more | "Someone else can be heard talking in this recording. …" |

The recordings that pass are joined, in the order they were uploaded, into the voice sample `uploads/voice-sample.wav`, which the person's own voice will be made from (roadmap R25). It is shown under the recordings with a player. The voice needs at least 30 seconds of speech in all; until then the screen says how much there is. If joining fails (logged as `Could not make the voice sample`), the old sample is removed rather than served, and the screen says so. Each recording in the recording guide has a minute or more.

The noise limit was set on the VoiceBank-DEMAND test set: clean studio speech measures 29 to 38 dB, the same speech with cafe, street or office noise mixed in so the voice is still clear 22 to 25 dB, and with noise that competes with the voice 13 to 20 dB. The limits, including the speech lengths, are at the top of `src/imageskin/sound_checks.py`; when they change, raise `SOUND_CHECKS` in `uploads.py` so recordings checked before are checked again. Recordings uploaded before the checks show **Checking recording…** and are checked one at a time after the page shows. Each check is logged as `Sound checked` with what it measured (`speech_s`, `clipped`, `snr_db`), and each change to the voice sample as `Voice sample updated`.

The one-speaker check (roadmap R11) gives each 1.5 second stretch of speech a voice print with CAM++, a speaker recognition model from 3D-Speaker (Apache 2.0), run on the CPU by ONNX Runtime (MIT). The prints are split into the two groups that sound most different; when the two groups sound like different people and the smaller one has at least 3 stretches, the recording is flagged. A minute of sound takes about a second. The server downloads the model (28 MB) into `models/speakers` in the app data folder when it starts (`Speaker model ready` in the log); if that fails (`Speaker checks are off until restart`), new recordings show **Not checked** until the server is restarted. Each check is logged as `Speaker checked` with `stretches`, `other` (stretches in the smaller group) and `alike` (how alike the two groups sound, -1 to 1; flagged below 0.55). The limits were set on LibriSpeech: one-minute recordings of one reader measure 0.63 to 0.95, two readers taking turns -0.08 to 0.52. A recording that changes microphone or room halfway can also be flagged, since the voice then sounds different.

## Preparing the voice and the face

Under the uploads, the Setup page has a **Prepare** button (roadmap R12). It needs a photo that passed the checks and enough speech in the voice sample, and says which one is missing otherwise. Preparing runs in the server, in the background:

1. **Get the voice ready:** loads Kokoro (the first time it downloads the model, about 330 MB) and says one word. Needs `pip install -e ".[voice]"`.
2. **Load the face model:** downloads the photoreal models the first time (about 500 MB). Needs `pip install -e ".[photoreal]"`.
3. **Render the 10 mouth shapes**, then 4. **the idle video** (200 frames with blinks and head movement; most of the time, about 17 minutes on a 4-core CPU), then 5. **line up the mouth with the head**.
6. **Render the sample video and the fixed lines** (roadmap R13): the person says "Goodbye.", "Welcome back." and the sample script (about 25 seconds), saved in `clips` in the app data folder. About a minute.

When it is done the sample video plays under **Prepare**.

The page shows a progress bar, each step with how far it has got and about how long is left, and how long each finished step took. You can close the page meanwhile. If the server is stopped, the next `imageskin serve` carries on where it stopped (`Resuming prepare job` in the log); frames already rendered are kept. A photo prepared before takes seconds. The job's state is in `prepare.json` in the app data folder and the frames under `photoreal`. The log has `Prepare job started`, `Prepare step finished` with each step's `duration_s`, `Rendered idle loop frame N of 200` every 10 frames, `Rendered clip` with each clip's `duration_s`, and `Prepare job finished` or `Prepare job failed` with the reason. Choosing another photo afterwards shows **Prepare** again.

## Making a voice sample

Join the recordings from the recording guide (M4A, MP3 or WAV) into one WAV file, in the order given. Each recording is converted to 24 kHz mono WAV; `--timeout` sets how many seconds each conversion may take (default 60).

```
imageskin voice-sample rec1.m4a rec2.m4a rec3.m4a -o voice-sample.wav
```

Play the result to check it:

- Windows Command Prompt: `start voice-sample.wav`
- Windows PowerShell: `Invoke-Item voice-sample.wav`
- macOS: `afplay voice-sample.wav`
- Linux: `aplay voice-sample.wav`

## Speaking text (Kokoro, on the CPU)

`imageskin say` speaks text with [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), a free open-source voice model (Apache 2.0) that runs on the CPU, with no account and no per-use cost. It writes the audio as WAV and, next to it, a JSON file with when each word starts and ends (in seconds), when each sound (phoneme) starts and ends with the mouth shape it needs, and the mouth shapes over time, which the photoreal video engine (R4c) renders from. Kokoro uses ready-made voices; it does not clone the person's voice yet. With Kokoro, use Python 3.11 or 3.12. Setup, voices and troubleshooting: [docs/guides/Local-Voice-Setup-Guide.pdf](docs/guides/Local-Voice-Setup-Guide.pdf).

Install it once into the virtual environment (this adds PyTorch, about 1 GB on disk). The first `say` also downloads the model, about 330 MB. You don't need to install espeak-ng separately: Kokoro uses it for words that aren't in its dictionary, and pip installs a bundled copy (the `espeakng-loader` package, with builds for Windows, macOS and Linux).

```
pip install -e ".[voice]"
```

If `say` reports `DLL load failed` on Windows, install the Microsoft Visual C++ Redistributable that PyTorch needs (`winget install Microsoft.VCRedist.2015+.x64`) and open a new terminal. On a Linux server with no GPU, install the smaller CPU-only PyTorch first: `pip install torch --index-url https://download.pytorch.org/whl/cpu`.

Then, on any system:

```
imageskin say -o hello.wav "Hello there, how are you today?"
imageskin say --voice am_michael -o hello.wav "Hello there, how are you today?"
```

This writes `hello.wav` and `hello.json` into the folder you run the command from (the project folder, if you followed the steps above), and prints their full paths. `-o` also takes a full path, such as `-o C:\Users\you\Desktop\hello.wav` or `-o ~/Desktop/hello.wav`; without `-o` the file is `speech.wav`. List the files with `dir hello.*` (Command Prompt), `Get-ChildItem hello.*` (PowerShell) or `ls -l hello.*` (macOS/Linux). Play `hello.wav` the same way as the voice sample above. Open `hello.json` in any text editor (`notepad hello.json` on Windows, `open -e hello.json` on macOS, `xdg-open hello.json` on Linux).

The JSON looks like this (shortened). Each sound is one of Kokoro's phonemes, `.` and punctuation are pauses, and each mouth shape is one of `rest`, `MBP` (lips closed), `FV` (teeth on lip), `AA`, `EH`, `EE`, `IH` (small opening), `OH`, `OO` and `SH`. The sound times come from the voice model itself in 25 ms steps, so the last sound ends exactly at `seconds`. The word times are Kokoro's own estimate and can start up to about 0.1 seconds before the word's first sound.

```
{
  "seconds": 6.85,
  "words": [{"word": "Hello", "start": 0.275, "end": 0.688}, ...],
  "sounds": [{"sound": ".", "start": 0.0, "end": 0.35, "shape": "rest"},
             {"sound": "h", "start": 0.35, "end": 0.4, "shape": "IH"}, ...],
  "shapes": [{"shape": "rest", "start": 0.0, "end": 0.35},
             {"shape": "IH", "start": 0.35, "end": 0.65}, ...]
}
``` American voices include `af_heart` (the default), `af_bella`, `af_nicole`, `am_michael` and `am_fenrir`.

## Making the sample video (on the CPU)

`imageskin sample` makes the sample video from features.md item 6: the person in the photo says the test script, in a Kokoro voice, as an MP4 (H.264 video, AAC audio, 25 frames per second). It needs the voice extra from the section above, the video extra below, and ffmpeg on PATH (see [Development](#development); check with `ffmpeg -version`, and open a new terminal after installing it). Without ffmpeg the command stops at once with `ffmpeg not found`.

The video engine is part of this project: it finds the face with the face detector that ships with OpenCV (no model download, no account, no per-use cost; OpenCV is Apache 2.0) and opens and closes the mouth in time with how loud the speech is. It renders faster than real time on a laptop CPU. The rest of the face stays still; the photoreal engine below adds blinking and head motion. Use a front-facing photo with the mouth closed or slightly open, as the photo guide asks: a big grin with teeth showing looks wrong when the mouth opens.

Install it once into the virtual environment (OpenCV and NumPy, about 60 MB, with prebuilt wheels for Windows, macOS and Linux; nothing to compile):

```
pip install -e ".[video]"
```

Then, on any system:

```
imageskin sample --photo me.jpg
imageskin sample --photo me.jpg --voice am_michael -o my-sample.mp4
```

This writes `sample.mp4` (or the `-o` name) into the folder you run the command from and prints its full path and how long each step took (prepare the photo, speak, render). The same timings are logged as JSON lines on stderr: look for `Prepared face`, `Spoke text`, `Rendered video` and `Wrote sample video`. Play it with `start sample.mp4` (Command Prompt), `Invoke-Item sample.mp4` (PowerShell), `open sample.mp4` (macOS) or `xdg-open sample.mp4` (Linux).

If `import cv2` fails on Windows with `DLL load failed`, install the Microsoft Visual C++ Redistributable (`winget install Microsoft.VCRedist.2015+.x64`) and open a new terminal. On Windows, `winget install Gyan.FFmpeg` gives an ffmpeg that includes the H.264 encoder the video needs.

## Photoreal video (LivePortrait, on the CPU)

`--engine photoreal` makes the same videos with a photoreal face: the lips take a shape for each sound (closed for m, b and p, teeth on the lip for f and v, rounded for oo and oh, spread for ee), the head drifts by a degree or two and the eyes blink. It uses [LivePortrait](https://github.com/KwaiVGI/LivePortrait) (MIT license) and Google's MediaPipe face finder (Apache 2.0), both free for hosted use with no per-use cost, and runs on the CPU. The OpenCV engine above stays the default and the quick fallback.

It works in two steps:

1. **Prepare the photo, once.** LivePortrait renders the 10 mouth shapes and an 8-second idle loop of the face (200 frames). This takes about 15 to 20 minutes on a 4-core CPU, logs progress every 10 frames with the time left, and picks up where it stopped if interrupted (run the same command again). The frames are saved under `.imageskin\photoreal\` in your user folder (`%USERPROFILE%\.imageskin` on Windows, `~/.imageskin` on macOS and Linux), about 170 MB per photo, and reused for every video of that photo. Set `IMAGESKIN_HOME` to keep them somewhere else.
2. **Each video is quick.** No model runs: the frames are mixed from the saved ones, timed to each sound from the voice, at about a third of real time (6.9 seconds of speech in 2.2 seconds on a 4-core CPU).

The first prepare also downloads the models into `.imageskin\models\`, about 520 MB, with a progress line every few seconds; an interrupted download resumes. It needs git on PATH (for LivePortrait's code) and Python 3.11 or 3.12.

Use a clean-shaven, front-facing photo with the mouth closed or slightly open: a moustache hides the lips, and the lips open from where they are in the photo.

Install it once into the virtual environment (PyTorch, OpenCV and MediaPipe, about 1.5 GB; skip if you already installed the voice extra's PyTorch, it is shared):

```
pip install -e ".[photoreal]"
```

On a Linux server, MediaPipe also needs `sudo apt install libegl1 libgles2`. On Windows, if PyTorch reports `DLL load failed`, install the Visual C++ Redistributable (`winget install Microsoft.VCRedist.2015+.x64`) and open a new terminal.

Then, on any system (swap `me.jpg` for your photo's path):

```
imageskin prepare --photo me.jpg
imageskin sample --photo me.jpg --engine photoreal
imageskin sample --photo me.jpg --engine photoreal -o mary.mp4 --text "Hello, my name is Mary. Would you like some more popcorn? Please move the blue boat. I see three green trees."
```

`prepare` writes `idle.mp4` (or the `-o` name) in the current folder: the idle loop with no sound, to check the head motion and blinks, and prints its full path and where the frames are. The logs show `Rendered mouth shapes`, `Rendered idle loop frame N of 200` every 10 frames, `Photoreal library ready` and `Loaded photoreal library`. Running it again on the same photo finishes in about a second.

`sample --engine photoreal` writes `sample.mp4` (or the `-o` name) in the current folder and prints its full path; if the photo isn't prepared yet, it does that first. `--text` says something other than the sample script. The logs show `Loaded photoreal library`, `Spoke text` and `Rendered video` with `"engine": "photoreal"` and how long it took.

Play the results with `start idle.mp4`, `start sample.mp4` and `start mary.mp4` (Command Prompt), `Invoke-Item idle.mp4` and so on (PowerShell), `open mary.mp4` (macOS) or `xdg-open mary.mp4` (Linux).
