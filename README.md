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
