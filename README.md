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

The browser app is React with TypeScript, in `web/`. It is built with Vite into `src/imageskin/static`, which is committed, so running the app needs no Node.js. Read and edit the code in `web/src` (one `.tsx` file per page under `web/src/pages`, the layout in `App.tsx`); `static/assets/app.js` is generated from it and `static/assets/react.js` is the React library. They are kept readable (not minified); the server compresses them when it sends them (react.js goes from about 565 KB to 107 KB). To change the browser code, install [Node.js](https://nodejs.org) 22 (Windows: `winget install OpenJS.NodeJS.LTS`, then open a new terminal), then on any system:

```
cd web
npm install
npm run dev     # live-reloading app at http://localhost:5173, with `imageskin serve` running for the API
npm test        # unit tests with coverage
npm run build   # type check and build into src/imageskin/static
```

Commit the built files with the source change; CI fails if they are out of date.

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
