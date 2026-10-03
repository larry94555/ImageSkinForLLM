# ImageSkinForLLM

A video "skin" over an LLM chatbot: from one photo and a voice sample, the person in the photo speaks the chatbot's replies in their own voice. See [docs/requirements/features.md](docs/requirements/features.md) and the [roadmap](docs/requirements/roadmap.md).

## Development

Requires Python 3.11 or later. Create a virtual environment and install the project once:

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
