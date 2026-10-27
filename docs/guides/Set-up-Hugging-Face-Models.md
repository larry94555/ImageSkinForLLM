# Set up Hugging Face models

Every model ImageSkin downloads from Hugging Face, what it is for, and how to set up access from scratch on a laptop or on the hosted site. Source of `Set-up-Hugging-Face-Models.pdf`. Last checked against the code on 2026-10-27 (roadmap R160).

## In short

- Only one model needs anything from you: **Pocket TTS** (`kyutai/pocket-tts`), whose weights that clone a voice are gated. You accept its terms once on Hugging Face and give the app a read token.
- Every other model is public. It downloads by itself the first time it is used, with no account.
- On the hosted site, the token goes in `deploy/.env` as `HF_TOKEN`. On a laptop, sign in once with `hf auth login`.
- Without a token, the app still works. It speaks the person's own voice with Chatterbox, which is about ten times slower, so a reply can pause for many seconds between sentences.

## The models the app uses

Each model is downloaded once, the first time it is needed, and kept in the Hugging Face cache. On the hosted site the cache is `/data/huggingface`, inside the app's data volume, so it survives rebuilds. On a laptop it is `~/.cache/huggingface` unless `HF_HOME` says otherwise. Revisions are pinned in the code, so every machine gets the weights that were tested.

| Model (Hugging Face repository) | What the app uses it for | Size | Access | Where in the code |
|---|---|---|---|---|
| `hexgrad/Kokoro-82M` | The ready-made voices (such as `af_heart`), the default people's voices, and the pronunciation step that splits words into sounds for the mouth | about 330 MB | Public | `kokoro_engine.py` (`REPO_ID`) |
| `kyutai/pocket-tts` | **Pocket TTS**: speaks in the person's own voice, cloned from 10 s of their voice sample, about ten times faster than Chatterbox (R22f, R160) | about 530 MB, with the next row | **Gated: accept the terms, then a read token** | `pocket_engine.py` (`TERMS_URL`) |
| `kyutai/pocket-tts-without-voice-cloning` | Pocket TTS's tokenizer, downloaded with the row above | (included above) | Public | the `pocket-tts` package |
| `ResembleAI/chatterbox-turbo` (revision `749d1c1a`) | **Chatterbox Turbo**: the person's own voice when Pocket TTS can't be used, and the converter that gives a voice another accent (American or British) once, in Prepare | about 3 GB with its libraries' models | Public | `chatterbox_engine.py` (`TURBO_REVISION`) |
| `facebook/wav2vec2-base-960h` (revision `22aad52d`) | Forced alignment: hears when each word of a cloned voice is said, so the mouth moves in time | about 360 MB | Public | `alignment.py` (`ALIGNER_REPO`) |
| `KlingTeam/LivePortrait` (revision `82a4fa67`) | The photoreal face: the models that move the photo's head, eyes and mouth | about 520 MB | Public | `liveportrait.py` (`HF_REPO`) |
| `csukuangfj/speaker-embedding-models` (revision `0743f301`) | Speaker checks: whether the recordings are all the same person (one ONNX file) | about 30 MB | Public | `speaker_checks.py` (`MODEL_URL`) |

## The LLM

The local LLM is also downloaded from Hugging Face, by llama.cpp's `llama-server` rather than by the app. It is public and needs no token.

| Model | Where | Size | Kept in |
|---|---|---|---|
| `unsloth/gemma-3-4b-it-GGUF`, quantization `Q4_0` | The hosted site (`deploy/compose.yaml`, the `llama` service) | about 2.4 GB | the `llama-models` volume (`LLAMA_CACHE=/models`) |
| `ggml-org/gemma-3-4b-it-GGUF` | A laptop (README, "Chat with the LLM") | about 2.5 GB | llama.cpp's own cache |

## Only for making the default people

The tools in `tools/default_people/` make the 60 default people once, on a machine with a graphics card. The app never downloads these.

| Model | What it is for | Access |
|---|---|---|
| `segmind/SSD-1B` (revision `60987f37`) | Makes each default person's picture (`make_default_people.py`) | Public |
| `hexgrad/Kokoro-82M` | Lets you hear the voices to choose from (`hear_voices.py`) | Public |

## Not from Hugging Face

For a complete picture, these are downloaded from elsewhere and need no account:

- spaCy's English model `en_core_web_sm`, used by Kokoro, which is installed in the Docker image's build.
- MediaPipe's face landmarker and image segmenter, from Google's storage.
- LivePortrait's code, fetched from GitHub with git on the first Prepare.

## Set up access: the hosted site

You do this once per Hugging Face account and once per site.

1. **Make an account.** Make a free account at https://huggingface.co/join, or sign in.
2. **Accept Pocket TTS's terms.** Open https://huggingface.co/kyutai/pocket-tts. Near the top there is a box about sharing your contact information to access the model; click its button (**Agree and access repository**). If the page already says "You have been granted access to this model", this is done.
3. **Make a read token.** Open https://huggingface.co/settings/tokens and click **Create new token**. Pick **Read**, give it any name and click **Create token**. Copy it: it starts with `hf_`. An existing token works too, if it is a Read token, or a fine-grained token with "Read access to contents of all public gated repos you can access" turned on.
4. **Put it in `.env`.** On the server, in `~/ImageSkinForLLM/deploy`, run `nano .env` and paste the token after `HF_TOKEN=`, such as `HF_TOKEN=hf_AbCd...`. Save with Ctrl+O and Enter, and close with Ctrl+X.
5. **Rebuild and restart:** `docker compose up -d --build`. The token reaches the app only when the container starts.
6. **Check it.** This prints `True` once the app has the token:

    ```
    docker compose exec app python -c "from huggingface_hub import get_token; print(get_token() is not None)"
    ```

7. **Prepare again.** On the Setup page, click **Prepare**. Then `docker compose logs app | grep "Prepare speaks"` should say `cloned with Pocket TTS`.

## The `.env` file

`deploy/.env` holds the hosted site's settings and secrets. It stays on the server only: it is never committed, and `chmod 600 .env` makes it readable only by you. Start from the example with `cp .env.example .env`. It has four settings:

| Setting | What it is | Example |
|---|---|---|
| `SITE_ADDRESS` | The site's name, whose A record points at the server. With no domain, the server's IP with dashes and `.sslip.io`. | `app.me0.ai` |
| `LOGIN_NAME` | The name the browser asks for. | `larry` |
| `LOGIN_PASSWORD_HASH` | The password's hash, from `docker run --rm -it caddy:2 caddy hash-password`, between single quotes. | `'$2a$14$...'` |
| `HF_TOKEN` | The Hugging Face read token, for Pocket TTS. Leave it empty to speak with Chatterbox. | `hf_AbCd...` |

`deploy/compose.yaml` passes `HF_TOKEN` to the app's container; `huggingface_hub` reads it from there. A change to `.env` takes effect with `docker compose up -d` (add `--build` when the code changed too).

## Set up access: a laptop

1. Do steps 1 to 3 above.
2. In the app's virtual environment, run `hf auth login` and paste the token. It is saved in the Hugging Face cache, so this is done once.
3. Install Pocket TTS as the README's "Replies within 2 seconds in your own voice" says, then start `imageskin serve` and click **Prepare**.

## When something goes wrong

- **The log says `Pocket TTS is installed but not signed in to Hugging Face; speaking with Chatterbox`.** The app has no token. On the site, check that `HF_TOKEN` is set in `.env` and that the container was started again after; on a laptop, run `hf auth login`.
- **Prepare fails with `could not load Pocket TTS: its weights that clone a voice need the terms accepted`.** The token works, but the terms on https://huggingface.co/kyutai/pocket-tts were not accepted for that account, or the token can't read gated models. The message ends with what Hugging Face said.
- **A download is slow or stops.** Each model downloads once, then is kept. A stopped download carries on the next time. `docker compose logs -f app` shows progress.
- **To start over** with the models (rarely needed), remove the cache folder `/data/huggingface` inside the app's volume, or `~/.cache/huggingface` on a laptop. They download again on next use.
