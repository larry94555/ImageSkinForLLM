# ImageSkinForLLM

A video "skin" over an LLM chatbot: from one photo and a voice sample, the person in the photo speaks the chatbot's replies in their own voice. See [docs/requirements/features.md](docs/requirements/features.md) and the [roadmap](docs/requirements/roadmap.md). If something looks wrong while running it, see the [FAQ](docs/FAQ.md).

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

1. **Get the voice ready** (roadmap R25b): when Chatterbox is installed (see [Your own voice](#your-own-voice-chatterbox-turbo-on-the-cpu)), loads it and learns the person's voice from the voice sample, so the clips below are spoken in their own voice. Loading takes about 30 seconds; the first time it downloads about 3 GB. Without Chatterbox it loads Kokoro (the first time it downloads the model, about 330 MB) and the clips use a ready-made voice; the log says so at start with `Prepare speaks in a ready-made Kokoro voice, not the person's`. Needs `pip install -e ".[voice]"` either way.
2. **Load the face model:** downloads the photoreal models the first time (about 500 MB). Needs `pip install -e ".[photoreal]"`.
3. **Render the 10 mouth shapes and the blinking eyes**, then 4. **the idle video** (head movement; most of the time, about 5 minutes on a 4-core CPU; 50 of its 200 frames are rendered and the rest filled in), then 5. **line up the mouth with the head**.
6. **Render the sample video and the fixed lines** (roadmap R13): the person says "Goodbye.", "Welcome back." and the sample script (about 25 seconds), saved in `clips` in the app data folder. About a minute with Kokoro; about two minutes on a 4-core CPU in the cloned voice, which takes about 2.5 seconds per second of speech.

When it is done the sample video plays under **Prepare**.

The page shows a progress bar, each step with how far it has got and about how long is left, and how long each finished step took. You can close the page meanwhile. If the server is stopped, the next `imageskin serve` carries on where it stopped (`Resuming prepare job` in the log); frames already rendered are kept. A photo prepared before reuses its frames, so preparing it again takes about a minute, mostly for the clips. The job's state is in `prepare.json` in the app data folder and the frames under `photoreal`. The log has `Prepare job started`, `Prepare step finished` with each step's `duration_s`, `Rendered idle loop frame N of 50` every 10 frames, `Filled in idle loop frames`, `Rendered clip` with each clip's `duration_s`, and `Prepare job finished` or `Prepare job failed` with the reason. With the cloned voice, the log also has `Prepare speaks in the person's own voice, cloned with Chatterbox Turbo` at start, `Learned voice` and `Voice ready: the person's own` with its `duration_s`, and a `Spoke text in cloned voice` line for each clip. Choosing another photo, adding or removing a recording, or installing Chatterbox after preparing with Kokoro, afterwards shows **Prepare** again: the clips were spoken in another voice. A job resumed after the recordings changed renders all its clips again (`Voice changed; rendering the clips again` in the log).

## Chat with the LLM

Once the sample video is accepted at the end of setup, the **Chat** page (roadmap R15) is a text chat with an LLM: type a message and press Enter or **Send** (Shift+Enter starts a new line). Replies are text only for now; the person speaks them from roadmap R17. A system prompt asks for short, conversational replies, and asks that everything the LLM says agrees with what was said earlier (who said what, every name and fact), replying only with the words it would say out loud. Replies are asked for with a temperature of 0.3 (llama-server's default is 0.8), so a small model mixes up facts less often.

The server keeps the conversation in memory, until it stops, and sends it with each prompt so the LLM remembers earlier turns. The history never takes more than half of the model's context window, so the rest is free for the new prompt and the reply. When it passes that, the LLM summarizes the older turns (keeping names, facts and preferences) right after the reply is shown, so the reply doesn't wait for it, and the summary is sent in their place with the latest two prompts and replies word for word. A message sent while a summary is still being made waits for it. The chat still shows everything. A message too long for the other half of the window is refused with a message saying to shorten it. The context window is read from llama-server when the first message is sent (its `--ctx-size`); with a server that doesn't report it, `llm_context_tokens` in the config file is used (default 4096). Tokens are counted by llama-server's own tokenizer; with a server that can't count them, they are estimated on the safe side, one token per byte of text (so code, hashes, Chinese and emoji can't be undercounted, though plain English then gets about a quarter of the history it would with a real count), and the log says `The LLM server can't count tokens; estimating them instead`.

The app talks to [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server` through its OpenAI-compatible API, at `http://127.0.0.1:8080/v1` unless `llm_url` in the config file says otherwise (see `config.example.toml`). Install llama.cpp once:

- Windows (Command Prompt or PowerShell): `winget install llama.cpp`, then open a new terminal
- macOS (or Linux with Homebrew): `brew install llama.cpp`

Then start it in its own terminal and leave it running. The first time, it downloads the model (Gemma 3 4B, about 2.5 GB):

```
llama-server -hf ggml-org/gemma-3-4b-it-GGUF --no-mmproj --port 8080 --ctx-size 4096 --threads 2
```

`--threads` gives the LLM half of the cores (2 of 4 here) and leaves the other half to the voice and the video while it writes (roadmap R22a). Without it, on a 4-core CPU, the two fight for the cores and both crawl: speaking a 3-second sentence took 14.5 s instead of 1.3 s, and the LLM fell from 8 to 0.3 tokens a second. On a graphics card, leave `--threads` out.

Use a model of about 4B parameters or more: Gemma 3 1B is given the earlier turns but often ignores them (asked "What is my name?" right after "Hi, my name is Larry", it answers "Sarah").

The log has `LLM context window from the server` (or `from the config`) at the first message, `Chat prompt sent` with how many turns were sent, whether a summary was, and `history_tokens`, `Conversation summarized` with how many turns it replaced, and `Chat reply received` with `duration_ms`. If the LLM can't be reached, the chat shows why, the prompt stays in the box to send again, and the log has `Chat reply failed`; if only summarizing fails, the oldest turns are left out instead and the log says `Could not summarize the conversation`.

| Request | What it does |
|---|---|
| `GET /api/chat` | The conversation so far |
| `POST /api/chat` | Send a prompt (JSON body `{"prompt": "…", "reply_id": "…"}`, the id chosen by the browser for the reply's clips) and get the reply with its `turn`; refused (403) until a sample is accepted, 502 when the LLM fails |
| `GET /api/chat/clips/{reply_id}?known=N&wait=S` | The reply's clips so far, each with `url`, `sentence_at` and `ready_at` (seconds on the server's clock, like `now`), `done` and `error`; with `known`, waits up to `wait` seconds (10 at most) for a clip beyond the N the browser has |
| `GET /api/chat/clips/{reply_id}/{n}` | Clip `n` of the reply, an MP4 |
| `POST /api/chat/video` | Speak a reply that wasn't streamed in one video (JSON body `{"turn": N}`); the video's address, or null when there is nothing to say aloud |
| `GET /api/chat/videos/{turn}` | That video |

### Spoken replies, sentence by sentence

Each reply is spoken in the person's voice on their photo (roadmap R17), a sentence at a time as the LLM writes it (R20 to R22): the server cleans each sentence for speech, speaks it and renders its clip while the LLM writes the next, and the browser plays the clips one after another, starting before the whole reply has arrived. Two video players take turns, so the next clip is loaded while the current one plays and the switch costs nothing. The first clip is the first sentence's first clause (R22b), cut at a comma, semicolon, colon or dash after at least 3 words, before a joining word such as "and" or "because", or after 8 to 12 words when there is none, so it is spoken while the LLM is still writing the rest of the sentence; the limits are at the top of `src/imageskin/sentences.py`.

Under the video, a timing readout says how long each clip took from its text arriving to being spoken, and the pause after the clip before (R22a). The first clip is in red when its wait passes the 2-second target, the others when their pause does: a clip whose text arrived while the one before was still playing is on time if it follows straight on. The log has `Reply sentence ready` with `since_prompt_ms` for each sentence (the first clause counts as one), `Sentence spoken` with `speak_ms` for each clip's voice step, and `Sentence clip ready` with `render_ms` (both steps) and `since_sentence_ms` (text arrived to clip ready) for each clip. The two steps run one after the other: on a 4-core CPU, speaking a sentence while the one before it rendered made both about twice as slow.

Each frame of a clip is composited by OpenCV in 8-bit (R22c): about 4 ms a frame on a 4-core CPU, so a clip renders in about a fifth of its playing time and the voice is most of the wait before a clip. Reply clips are rendered on the photo scaled down to 720 pixels on its longest side, since the page shows them at most 640 pixels wide (`REPLY_SIDE` in `src/imageskin/prepare_job.py`); the sample video keeps the photo's size. The log's `Rendered video` line has each clip's `frames`, `duration_ms` and `real_time_factor`.

A clip is offered to the browser the moment its video starts to be written (R22d): the clip is a fragmented MP4 written half a second at a time, and the server streams it as it grows, so the video plays while the rest is rendered and only the voice step is waited for. The readout counts from the text to the clip playing; the log's `Sentence clip ready` line has `playable_since_sentence_ms` (text arrived to the clip playable) next to `since_sentence_ms` (text arrived to the clip whole). On a 4-core CPU, the voice step runs at about half real time while the LLM writes, and the browser on the same machine takes cores from it too, so later clips in a long reply can still pause between sentences: that is the engines' throughput, and a faster voice or a graphics card is what shortens it.

For quick replies on a CPU, two things happen at startup once a sample has been accepted (`Warming up replies` in the log): the LLM reads the system prompt (`LLM warmed up`), so the first reply's words come about 2 s sooner, and the voice and video engines load and render a word (`Replies warmed up`), which takes a minute or two the first time. While the LLM is busy (writing the reply, or summarizing the conversation after one), the engines use half the cores and all of them once it has finished (`Engine threads set` with `threads` and `cores`); start llama-server with `--threads` set to the other half, as above. Leave `OMP_NUM_THREADS` unset: the app shares the cores itself, and a cap below the core count is logged as a warning (`OMP_NUM_THREADS caps the engines' cores`).

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

## What the voice says for a reply

A chat reply is shown as written, but the voice leaves out what reads badly aloud (feature 11). Markdown markers, HTML tags and decorative emoji are silent. A link, a picture, a table, a code block or inline code of more than two words is replaced by a short phrase that points to the text, such as "the link in the text below" or "See the code shown below.", so no sentence breaks off. Shorter inline code, such as `main()`, is spoken as is, and a heart between two words ("I ❤️ it") is said as "love". `imageskin spoken-text` prints what the voice will say for a reply, with nothing to install beyond the base package. Pass the reply in quotes, or, for a reply with several lines or code blocks, save it in a UTF-8 text file and pass `--file`:

```
imageskin spoken-text "**Hi** Larry 👋, see https://example.com."
imageskin spoken-text --file docs/examples/sample-reply.md
```

The first prints `Hi Larry, see the link in the text below.`: link text is kept, a URL on its own is replaced by the phrase, and a line without punctuation at its end (a heading or a list item) gets a full stop so the voice pauses. The second reads a sample reply with a list, a link, code, an emoji and a table. A log line `Cleaned reply for speech` gives the reply's length, the spoken length and the time taken.

## Speaking text (Kokoro, on the CPU)

`imageskin say` speaks text with [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), a free open-source voice model (Apache 2.0) that runs on the CPU, with no account and no per-use cost. It writes the audio as WAV and, next to it, a JSON file with when each word starts and ends (in seconds), when each sound (phoneme) starts and ends with the mouth shape it needs, and the mouth shapes over time, which the photoreal video engine (R4c) renders from. Kokoro uses ready-made voices; for the person's own voice, see [Your own voice](#your-own-voice-chatterbox-turbo-on-the-cpu). With Kokoro, use Python 3.11 or 3.12. Setup, voices and troubleshooting: [docs/guides/Local-Voice-Setup-Guide.pdf](docs/guides/Local-Voice-Setup-Guide.pdf).

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

## Your own voice (Chatterbox Turbo, on the CPU)

`--voice-sample` makes `say` and `sample` speak in the person's own voice instead of a Kokoro voice. [Chatterbox Turbo](https://huggingface.co/ResembleAI/chatterbox-turbo) (MIT, Resemble AI), picked in R25a because it sounds like Larry, learns the voice from 10 seconds of the voice sample (see [Making a voice sample](#making-a-voice-sample)) with no training, keeps the person's own accent and runs on the CPU, with no account and no per-use cost. Chatterbox adds Resemble AI's inaudible Perth watermark to what it makes.

In the browser, setup asks which accent the voice speaks with (R26): the person's own, American or British. With American or British, Prepare picks the Kokoro voice of that accent that sounds most like the person once converted (every voice says a short line, compared with the speaker model the one-speaker check uses), Kokoro speaks each line, and Chatterbox's voice converter changes it into the person's voice, keeping the accent and Kokoro's timings. Picking the voice converts every voice of the accent, which adds about 1 to 1.5 minutes to Prepare's voice step; speaking and converting together take about 1 second per second of speech on 4 cores, against about 2.3 for the clone. Changing the accent after the sample is ready makes the sample again, keeping the face.

Chatterbox reports no timings, so the app finds them in its audio: a speech recognizer, [wav2vec2](https://huggingface.co/facebook/wav2vec2-base-960h) (Apache 2.0), hears when each word starts and ends (forced alignment of the known text), and Kokoro's pronunciation step supplies each word's sounds for the mouth. The JSON next to the WAV has the same layout as with Kokoro.

It is slow: on a 4-core CPU, cloning takes 1.5 to 2.5 seconds per second of speech, and finding the timings adds about 0.2 seconds per sentence. Loading the models takes about 30 seconds once per command and learning the voice about 2 seconds. The first run downloads about 2.8 GB of Chatterbox models (into the Hugging Face cache) and 360 MB for the recognizer (into `models` in the app data folder, `%USERPROFILE%\.imageskin` on Windows or `~/.imageskin` on macOS and Linux), logging its progress every few seconds; both are kept for later runs. If the connection drops, the recognizer's download picks up where it stopped, and running the command again resumes it too.

Chatterbox pins old versions of PyTorch, NumPy and other packages that would downgrade the app's, so it is installed without its pins (`--no-deps`), and `clone-requirements.txt` lists what it really needs at the tested versions. The second command below saves every package already installed as a constraint, so if the install would change any of them, pip stops with a conflict and nothing is changed. Use Python 3.11 or 3.12, and replace `rec1.m4a rec2.m4a` with your recordings and `me.jpg` with your photo.

macOS / Linux:

```
source .venv/bin/activate
pip install -e ".[voice,video]"
pip freeze --all --exclude-editable > app-constraints.txt
pip install --retries 10 -r clone-requirements.txt -c app-constraints.txt
pip install --no-deps chatterbox-tts==0.1.7
imageskin voice-sample rec1.m4a rec2.m4a -o voice-sample.wav
imageskin say -o kokoro.wav "Hello there, how are you today?"
imageskin say --voice-sample voice-sample.wav -o mine.wav "Hello there, how are you today?"
imageskin sample --photo me.jpg --voice-sample voice-sample.wav -o sample-mine.mp4
```

Windows 11, Command Prompt:

```
.venv\Scripts\activate.bat
pip install -e ".[voice,video]"
pip freeze --all --exclude-editable > app-constraints.txt
pip install --retries 10 -r clone-requirements.txt -c app-constraints.txt
pip install --no-deps chatterbox-tts==0.1.7
imageskin voice-sample rec1.m4a rec2.m4a -o voice-sample.wav
imageskin say -o kokoro.wav "Hello there, how are you today?"
imageskin say --voice-sample voice-sample.wav -o mine.wav "Hello there, how are you today?"
imageskin sample --photo me.jpg --voice-sample voice-sample.wav -o sample-mine.mp4
```

Windows 11, PowerShell (`>` would write the constraints file in a format pip can't read, so it goes through `Set-Content`):

```
.venv\Scripts\Activate.ps1
pip install -e ".[voice,video]"
pip freeze --all --exclude-editable | Set-Content -Encoding ascii app-constraints.txt
pip install --retries 10 -r clone-requirements.txt -c app-constraints.txt
pip install --no-deps chatterbox-tts==0.1.7
imageskin voice-sample rec1.m4a rec2.m4a -o voice-sample.wav
imageskin say -o kokoro.wav "Hello there, how are you today?"
imageskin say --voice-sample voice-sample.wav -o mine.wav "Hello there, how are you today?"
imageskin sample --photo me.jpg --voice-sample voice-sample.wav -o sample-mine.mp4
```

Add `--engine photoreal` to the last command for the photoreal video (see [Photoreal video](#photoreal-video-liveportrait-on-the-cpu)). Play `kokoro.wav` and `mine.wav` one after the other to hear the ready-made voice and your own (`start mine.wav` in Command Prompt, `Invoke-Item mine.wav` in PowerShell, `open mine.wav` on macOS, `xdg-open mine.wav` on Linux). The logs (JSON lines on stderr) show `Loaded Chatterbox Turbo`, `Learned voice`, `Loaded aligner`, `Aligned words` and then `Spoke text in cloned voice` with `clone_ms` and `align_ms` (the time each took) and `real_time_factor` (seconds of work per second of speech).

If pip stops with `ResolutionImpossible` or `conflict`, nothing was installed: one of the pinned packages needs a different version of something the app already has; report the message. If `say` reports `Chatterbox is not installed`, run the last `pip install` line again. Before this was fixed, the first run also printed a `Wav2Vec2ForCTC LOAD REPORT` saying `wav2vec2.masked_spec_embed` is `MISSING`; the app now hides it. If you see it, it is harmless: that value is only used while the model is being trained, and the published model ships without it.

## Making the sample video (on the CPU)

`imageskin sample` makes the sample video from features.md item 6: the person in the photo says the test script, in a Kokoro voice or with `--voice-sample` in their own voice, as an MP4 (H.264 video, AAC audio, 25 frames per second). It needs the voice extra from the section above, the video extra below, and ffmpeg on PATH (see [Development](#development); check with `ffmpeg -version`, and open a new terminal after installing it). Without ffmpeg the command stops at once with `ffmpeg not found`.

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

`--engine photoreal` makes the same videos with a photoreal face: the lips take a shape for each sound (closed for m, b and p, teeth on the lip for f and v, rounded for oo and oh, spread for ee), the head drifts by a degree or two and the eyes blink at natural, irregular times. It uses [LivePortrait](https://github.com/KwaiVGI/LivePortrait) (MIT license) and Google's MediaPipe face finder (Apache 2.0), both free for hosted use with no per-use cost, and runs on the CPU. The OpenCV engine above stays the default and the quick fallback.

It works in two steps:

1. **Prepare the photo, once.** LivePortrait renders the 10 mouth shapes, the eyes part-way and fully closed, and an 8-second idle loop of the face (200 frames). Only 50 of the loop frames are rendered: every 4th one. The head moves less than a tenth of a degree per frame, so the 150 between them are filled in along the optical flow, which looks the same (45 to 55 dB PSNR against fully rendered frames). This takes about 7 minutes on a 4-core CPU, logs progress every 10 frames with the time left, and picks up where it stopped if interrupted (run the same command again). The frames are saved under `.imageskin\photoreal\` in your user folder (`%USERPROFILE%\.imageskin` on Windows, `~/.imageskin` on macOS and Linux), about 170 MB per photo, and reused for every video of that photo. Set `IMAGESKIN_HOME` to keep them somewhere else.
2. **Each video is quick.** No model runs: the frames are mixed from the saved ones, timed to each sound from the voice, at about a third of real time (6.9 seconds of speech in 2.2 seconds on a 4-core CPU). The blinks are added here, at their own times, so they never repeat with the loop: about every 3 seconds but never on a beat, now and then a half blink or two in a row, the lids closing fast and opening more slowly, and the brows dipping slightly with them. The face also follows the voice: louder syllables open the mouth wider and quiet ones a little less (the lips still close for m, b, p, f and v), the brows lift on high or stressed words, and the head nods gently on the strongest beat of a phrase, tilts with the pitch and drifts slowly side to side. This is measured from the speech's loudness and pitch in about 40 ms and adds about 10% to the render; the logs show `Measured voice expression` with the beats and nods found.

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

`prepare` writes `idle.mp4` (or the `-o` name) in the current folder: the idle loop with no sound and no blinks, to check the head motion, and prints its full path and where the frames are. The logs show `Rendered mouth and eye shapes`, `Rendered idle loop frame N of 50` every 10 frames, `Filled in idle loop frames` (150, about 5 seconds), `Photoreal library ready` and `Loaded photoreal library`. Running it again on the same photo finishes in about a second.

`sample --engine photoreal` writes `sample.mp4` (or the `-o` name) in the current folder and prints its full path; if the photo isn't prepared yet, it does that first. `--text` says something other than the sample script. The logs show `Loaded photoreal library`, `Spoke text` and `Rendered video` with `"engine": "photoreal"` and how long it took.

Play the results with `start idle.mp4`, `start sample.mp4` and `start mary.mp4` (Command Prompt), `Invoke-Item idle.mp4` and so on (PowerShell), `open mary.mp4` (macOS) or `xdg-open mary.mp4` (Linux).
