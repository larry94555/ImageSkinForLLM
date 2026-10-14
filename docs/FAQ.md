# ImageSkinForLLM: FAQ

Problems seen while running the app, and how to fix them. Add a new entry each time one comes up.

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
llama-server -hf ggml-org/gemma-3-4b-it-GGUF --no-mmproj --port 8080 --ctx-size 4096 --threads 2
```

- `-hf` downloads the model from Hugging Face the first time, about 2.5 GB, and keeps it, so later starts take seconds. This model is public, so no Hugging Face account or token is needed.
- `--threads 2` gives the AI 2 of the 4 cores and leaves the other 2 for the voice and the video. Without it they fight over the cores and both become very slow.
- `--no-mmproj` skips the model's image part, which the app doesn't use. `--ctx-size 4096` is how much of the conversation and content it can read at once.

**Check:** it is ready when its terminal shows a line ending `listening on http://127.0.0.1:8080`. Opening http://127.0.0.1:8080/health in a browser then shows `{"status":"ok"}`.

**Then** start the app in a second terminal (`imageskin serve`, after activating `.venv` as usual).

**What to expect on 4 CPU cores:** a reply's first words come after a few seconds, and building the wiki takes about 20 to 40 seconds for each part of a PDF, longer with this 4B model. A smaller model is faster but forgets the conversation more often, so use one of about 4B parameters or more (see the README's chat section).
