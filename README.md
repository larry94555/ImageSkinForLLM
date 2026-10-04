# ImageSkinForLLM

A video "skin" over an LLM chatbot: from one photo and a voice sample, the person in the photo speaks the chatbot's replies in their own voice. See [docs/requirements/features.md](docs/requirements/features.md) and the [roadmap](docs/requirements/roadmap.md).

## Development

Requires Python 3.11 or later, and [ffmpeg](https://ffmpeg.org) on PATH for audio conversion. Install ffmpeg once:

- Windows (Command Prompt or PowerShell): `winget install Gyan.FFmpeg`, then open a new terminal
- macOS: `brew install ffmpeg`
- Linux (Debian or Ubuntu): `sudo apt install ffmpeg`

Check it with `ffmpeg -version`. Create a virtual environment and install the project once:

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

`imageskin say` speaks text with [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), a free open-source voice model (Apache 2.0) that runs on the CPU, with no account and no per-use cost. It writes the audio as WAV and, next to it, a JSON file with when each word starts and ends (in seconds). Kokoro uses ready-made voices; it does not clone the person's voice yet. With Kokoro, use Python 3.11 or 3.12. Setup, voices and troubleshooting: [docs/guides/Local-Voice-Setup-Guide.pdf](docs/guides/Local-Voice-Setup-Guide.pdf).

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

This writes `hello.wav` and `hello.json` into the folder you run the command from (the project folder, if you followed the steps above), and prints their full paths. `-o` also takes a full path, such as `-o C:\Users\you\Desktop\hello.wav` or `-o ~/Desktop/hello.wav`; without `-o` the file is `speech.wav`. List the files with `dir hello.*` (Command Prompt), `Get-ChildItem hello.*` (PowerShell) or `ls -l hello.*` (macOS/Linux). Play `hello.wav` the same way as the voice sample above. American voices include `af_heart` (the default), `af_bella`, `af_nicole`, `am_michael` and `am_fenrir`.

## Making the sample video (on the CPU)

`imageskin sample` makes the sample video from features.md item 6: the person in the photo says the test script, in a Kokoro voice, as an MP4 (H.264 video, AAC audio, 25 frames per second). It needs the voice extra from the section above, the video extra below, and ffmpeg on PATH.

The video engine is part of this project: it finds the face with the face detector that ships with OpenCV (no model download, no account, no per-use cost; OpenCV is Apache 2.0) and opens and closes the mouth in time with how loud the speech is. It renders faster than real time on a laptop CPU. The rest of the face stays still for now; blinking and head motion come later. Use a front-facing photo with the mouth closed or slightly open, as the photo guide asks: a big grin with teeth showing looks wrong when the mouth opens.

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
