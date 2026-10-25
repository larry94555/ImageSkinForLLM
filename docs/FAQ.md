# ImageSkinForLLM: FAQ

Problems seen while running the app, and how to fix them. Add a new entry each time one comes up.

## How do I know `imageskin serve` has finished loading and is ready?

**Wait for this line.** `imageskin serve` logs it once everything the app needs before it can take input has loaded:

```
Loading has completed. The application is ready for use.
```

In the terminal it is one JSON line like this (the time, `url` and `duration_ms` will differ):

```
{"time": "...", "level": "INFO", "logger": "imageskin.cli", "message": "Loading has completed. The application is ready for use.", "url": "http://127.0.0.1:8000", "duration_ms": 1924.7, "background_jobs": []}
```

**Why it matters:** the app loads a lot at the start, on purpose, so the first photo, recording and reply are as quick as the later ones. After each change (a new PR, a new photo or voice, a restart), expect it to take a while: the face and speaker models load first, and once a sample is accepted, the voice, the video and the LLM are warmed up by speaking and rendering a word that is thrown away, and the idle video is made. On a 4-core CPU that can take minutes.

**Don't go by uvicorn's lines.** `Application startup complete.` and `Uvicorn running on http://127.0.0.1:8000` come early, before the loading has finished. A page opened or a prompt sent then still works, but waits for the loading, so it looks stuck. Lines such as `Speaker model ready`, `Replies warmed up`, `LLM warmed up` and `Idle video ready` are steps along the way; the ready line comes after all of them.

**After it:** open http://127.0.0.1:8000. When `background_jobs` is empty, the lines that follow come from what you do in the app (each request, a reply). If the server was stopped in the middle of reading a PDF, building the wiki or Prepare, that job carries on after a restart and `background_jobs` names it (`pdf-reading`, `wiki`, `prepare`). Its lines, such as `PDF read` or `Prepare job finished`, can then come after the ready line. The ready line doesn't wait for them, because building the wiki waits on the LLM and can take many minutes; the app takes input meanwhile and shows their progress. A step that fails doesn't stop the ready line: it is logged above it as an `ERROR` or `WARNING`, such as `Could not warm up replies` or `Could not warm up the LLM`, so look there if the app misbehaves (for the LLM, see "How do I start the local AI" below).

## How do I start the app on the hosted server with Docker?

**Where:** on the server (Ubuntu), after connecting with SSH as in [deploy/README.md](../deploy/README.md) step 4. The repository is at `~/github/ImageSkinForLLM` (the README clones it to `~/ImageSkinForLLM`; if yours is there, use that folder instead). The first-time setup (Docker, the firewall, `deploy/.env` with the address and password) is in that README, steps 5 and 6; this entry assumes it is done.

**Start it** (or start it again after a `git pull`, which rebuilds the app):

```
cd ~/github/ImageSkinForLLM/deploy
docker compose up -d --build
```

This starts three containers, from `deploy/compose.yaml`: `app` (the app itself), `llama` (the local LLM, llama.cpp's `llama-server` with Gemma 3 4B) and `caddy` (HTTPS and the password, in front of the app). `-d` runs them in the background, so closing the SSH window doesn't stop them, and they start again by themselves after the machine restarts. The first build takes 15 to 30 minutes; later ones reuse most of it. The first start of `llama` also downloads its model, about 2.5 GB.

**Check it is running** (every command here is run in `~/github/ImageSkinForLLM/deploy`):

```
docker compose ps
docker compose logs app | grep "Loading has completed"
docker compose logs llama | grep "server is listening"
```

- `docker compose ps` shows `app` as **healthy**, and `llama` and `caddy` as **Up**. Just after a start, `app` shows **health: starting** for up to a minute.
- The app is ready for use once its log has `Loading has completed. The application is ready for use.` (see the entry above). Until then a page opened or a prompt sent waits, so it looks stuck.
- The LLM is ready once its log has `server is listening on http://0.0.0.0:8080`. Until then the chat says the LLM can't be reached.

Then open `https://<SITE_ADDRESS>` (the address in `deploy/.env`, such as https://app.me0.ai) and sign in with the name and password.

**Watch the logs:**

```
docker compose logs -f app
docker compose logs -f llama
docker compose logs -f caddy
```

`-f` keeps showing new lines; Ctrl+C stops showing them but leaves the site running. Add `--tail 100` to see only the last 100 lines.

**Restart or stop it:**

| To | Run |
|---|---|
| Restart one container, such as after editing `config.toml` | `docker compose restart app` (or `llama`, `caddy`) |
| Restart everything | `docker compose restart` |
| Stop the site, keeping the containers | `docker compose stop` (start it again with `docker compose start`) |
| Stop the site and remove the containers | `docker compose down` (start it again with `docker compose up -d`) |

Both `stop` and `down` keep the data: the uploads, the prepared face, the settings, the API keys and the LLM's model stay in their volumes. `docker compose down -v` would delete them all, so don't use it unless you mean to start over.

**If it doesn't start:** `docker compose ps -a` shows a container that exited or keeps restarting, and `docker compose logs <name> --tail 50` says why. A missing `SITE_ADDRESS`, `LOGIN_NAME` or `LOGIN_PASSWORD_HASH` stops `docker compose up` with `set ... in .env`: fill in `deploy/.env` (README step 6d). For certificate errors, a port already in use, or the machine freezing during Prepare, see "If it doesn't work" in [deploy/README.md](../deploy/README.md#if-it-doesnt-work).

## Setup shows fewer (or different) photos and recordings than before

**Why:** the app keeps everything (consent, uploads, the prepared voice and face, the accepted sample) in one app data folder. It is `.imageskin` in your home folder unless the environment variable `IMAGESKIN_HOME` names another one. If `IMAGESKIN_HOME` is set in the terminal you start the app from, for example left over from a test, the app reads that folder instead and shows only what was uploaded there. Nothing is deleted: the files are still in the other folder.

**Check:** when `imageskin serve` starts, the log has a line `App data folder` with its `path`. That is the folder the app is using.

**Fix:** clear `IMAGESKIN_HOME` to go back to the default `.imageskin` folder, or set it to the folder you were using before, then start `imageskin serve` again in the same terminal.

macOS / Linux:

```
unset IMAGESKIN_HOME
# or: export IMAGESKIN_HOME="$HOME/path/you/used/before"
imageskin serve
```

Windows 11, Command Prompt:

```
set IMAGESKIN_HOME=
rem or: set IMAGESKIN_HOME=C:\path\you\used\before
imageskin serve
```

Windows 11, PowerShell:

```
Remove-Item Env:IMAGESKIN_HOME
# or: $env:IMAGESKIN_HOME = "C:\path\you\used\before"
imageskin serve
```

These change only the current terminal. If the setting comes back in every new terminal, it was set permanently: on Windows, remove it under Settings > System > About > Advanced system settings > Environment Variables; on macOS or Linux, remove the `export IMAGESKIN_HOME=…` line from your shell profile (such as `~/.zshrc` or `~/.bashrc`).

## How do I start the local AI on a laptop with only a CPU and 4 cores?

**Why:** the app doesn't contain the AI that writes the replies and builds the wiki. It asks a separate program, llama.cpp's `llama-server`, at `http://127.0.0.1:8080`. If that isn't running, the chat apologizes instead of answering, a clicked example question gets no answer, and the wiki waits. The log then has `Chat reply failed` or `Waiting for the LLM to build the wiki`. The steps for a PR assume `llama-server` is already running, as below.

**Install llama.cpp once** (it includes `llama-server`):

- Windows 11 (Command Prompt or PowerShell): `winget install llama.cpp`, then close the terminal and open a new one.
- macOS: `brew install llama.cpp`.
- Linux: `brew install llama.cpp` if you have Homebrew. Otherwise, download the `llama-…-bin-ubuntu-x64.zip` file from the [llama.cpp releases page](https://github.com/ggml-org/llama.cpp/releases), unzip it, and run `llama-server` from the unzipped folder.

**Start it in its own terminal and leave that terminal open.** The command is the same on macOS, Linux, Windows Command Prompt and Windows PowerShell:

```
llama-server -hf ggml-org/gemma-3-4b-it-GGUF --no-mmproj --port 8080 --ctx-size 4096 --threads 2 --threads-batch 4 --swa-full
```

- `-hf` downloads the model from Hugging Face the first time, about 2.5 GB, and keeps it, so later starts take seconds. This model is public, so no Hugging Face account or token is needed.
- `--threads 2` gives the AI 2 of the 4 cores and leaves the other 2 for the voice and the video. Without it they fight over the cores and both become very slow.
- `--threads-batch 4` lets the AI read your question on all 4 cores, before the voice starts, and `--swa-full` lets it reuse what it has already read, so its first words come seconds sooner.
- `--no-mmproj` skips the model's image part, which the app doesn't use. `--ctx-size 4096` is how much of the conversation and content it can read at once.

**Check:** it is ready when its terminal shows a line ending `listening on http://127.0.0.1:8080`. Opening http://127.0.0.1:8080/health in a browser then shows `{"status":"ok"}`.

**Then** start the app in a second terminal (`imageskin serve`, after activating `.venv` as usual).

**What to expect on 4 CPU cores:** a reply's first words come after a few seconds, and building the wiki takes about 20 to 40 seconds for each part of a PDF, longer with this 4B model. A smaller model is faster but forgets the conversation more often, so use one of about 4B parameters or more (see the README's chat section).

## Preparing the video failed. How does tech support find out why?

**What the customer sees:** setup stops with a message such as "The video couldn't be prepared on this computer" or "Something went wrong while preparing". The page keeps it short; the app's log has the full reason. Ask the customer roughly when it failed, then check the log as below. Once R134 on the roadmap is built, the page also shows a reference such as `P-7K3F9Q`; ask for it, and the log line with the same reference is the one to read:

```
docker compose logs app --since 24h | grep P-7K3F9Q
```

**What to look for:** every failed prepare writes one JSON line with `"message": "Prepare job failed"`. Its `error` field names what broke (a program, package, model file or step), and an unexpected failure also has an `exception` field with the traceback. The `Prepare step finished` lines just above it say which steps got through, and `Prepare job started` marks where the attempt began.

**On the hosted server (Docker),** after connecting with SSH as in [deploy/README.md](../deploy/README.md) step 4:

```
cd ~/github/ImageSkinForLLM/deploy
docker compose logs app --since 3h | grep -E "Prepare (job|step)"
docker compose logs app --since 3h | grep "Prepare job failed"
```

Use `--since 24h` if it failed earlier. If there is no `Prepare job failed` line at all, the app itself stopped part-way, most often for lack of memory. Check:

```
docker inspect imageskin-app-1 --format 'oom={{.State.OOMKilled}} restarts={{.RestartCount}}'
docker stats --no-stream
free -h
df -h /
```

`oom=true`, or a restart count that went up, means the container ran out of memory (it is capped at 14 GB in `compose.yaml`); `df -h` near 100% means the disk is full, which stops models from downloading and clips from being written.

**On a laptop (`imageskin serve`),** the log is the terminal the app runs in. Look there for the same `Prepare job failed` line, or save the log while trying again: `imageskin serve 2>&1 | tee imageskin.log` (Windows PowerShell: `imageskin serve 2>&1 | Tee-Object imageskin.log`).

**When reporting it,** copy the whole `Prepare job failed` line, with the `Prepare step finished` lines before it, into the support ticket.
