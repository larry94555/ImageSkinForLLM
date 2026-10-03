# ImageSkinForLLM

A video "skin" over an LLM chatbot: from one photo and a voice sample, the person in the photo speaks the chatbot's replies in their own voice. See [docs/requirements/features.md](docs/requirements/features.md) and the [roadmap](docs/requirements/roadmap.md).

## Development

Requires Python 3.11 or later.

```
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

ruff check . && ruff format --check .   # lint and format
mypy                                    # type check
pytest                                  # unit tests with coverage
```

## Running

```
imageskin --version
imageskin serve                          # http://127.0.0.1:8000/health
imageskin --config config.toml serve     # settings from a file; see config.example.toml
```

Logs are written to stderr as one JSON object per line.
