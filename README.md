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

The home page (http://127.0.0.1:8000/) offers **Start setup** until a sample video has been accepted. After that it shows the chosen photo and three equal choices: **Chat**, **Manage Content** and **Setup**. The browser console logs `Home loaded in … ms (setup done)` or `(setup not done)`; before consent it asks the server nothing and logs `Home loaded (setup not started: no consent yet)`.

## Uploading photos and recordings

The Setup page links to the **recording guide** (http://127.0.0.1:8000/#/guide), the same steps as [docs/guides/Photo-and-Voice-Recording-Guide.pdf](docs/guides/Photo-and-Voice-Recording-Guide.pdf) one step at a time: pick Windows 10, Windows 11 or Mac to see only that laptop's steps, take the five photos, read the seven recording scripts, then add the files on the Setup page. The browser remembers the step and laptop, so the guide reopens where it was left. The browser console logs `Guide step N of 16: …` and `Guide laptop: …`.

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

### PDF content

The PDFs that answers will come from are stored in `content/pdfs` inside the app's folder, apart from the photos and recordings, under random names with a small JSON file each that keeps the name it was uploaded with. The type is checked from the file's first bytes (`%PDF-`), not its name. Limits: 100 MB per PDF, 2 GB in total. These requests don't need consent, since PDFs aren't the person's likeness; administrator sign-on comes later.

| Request | What it does |
|---|---|
| `POST /api/content` | Add a PDF (form field `file`) |
| `GET /api/content` | List the PDFs, oldest first, with `name`, `size`, `added_at` and `replaced_at` |
| `GET /api/content/{id}` | Download one |
| `PUT /api/content/{id}` | Replace one with a new file (form field `file`), keeping its id |
| `DELETE /api/content/{id}` | Remove one |
| `GET /api/content/readings` | How far each PDF has got being read: `state` (`waiting`, `reading`, `done` or `failed`), `page` of `pages`, and once done its `kind` and how many paragraphs, slides and tables were found |
| `GET /api/content/{id}/reading` | What was read from one: each piece with its `page`, `kind` (`paragraph`, `slide` or `table`), `text`, and a table's `rows` |

The log has `PDF added`, `PDF replaced` and `PDF removed` with the id, size, stored path and time taken, or `PDF refused` with the reason.

To manage them in the browser, open **Manage Content** in the app's top bar (http://127.0.0.1:8000/#/content while `imageskin serve` is running). **Add PDFs** takes one or more PDFs at a time, each PDF's name opens it, **Replace** swaps in a new file for that PDF and **Remove** deletes it after asking. A refused file is listed with the reason. The browser console has `Added …`, `Replaced … with …` (each with the time taken in ms) and `Removed …`.

Each PDF is read in the background when it is added or replaced, one at a time, with [pdfplumber](https://github.com/jsvine/pdfplumber) (MIT): tables as rows and columns, a page wider than it is tall as one slide, and any other text as paragraphs, each with its page number. What was read is saved in `content/read/<id>.json`; on start, any PDF not read yet (or replaced since) is read again. Manage Content shows each PDF's progress ("Reading page 24 of 400…") and then what was found (the JSON stays at the address above, but the page no longer links to it, since it is raw data). Tables are found from their ruling lines, so a table drawn without lines is read as text. A scanned page (a picture with no text) is listed as having no text, since there is no OCR. The log has `Reading PDF`, then `PDF read` with the kind, page count, counts and time taken, or `Could not read the PDF` with the error; pages with no text are logged as a warning. A 400-page text PDF took about 40 seconds to read on a 4-core CPU.

Once a PDF has been read, the chat's LLM builds its **wiki pages** in the background (roadmap R37), one PDF at a time: one page per topic, each with a title, a summary of 2 or 3 sentences in the LLM's own words, and the PDF pages it comes from. What was read is cut into parts that fit the LLM's context window, with each piece marked with its page; for each part the LLM lists the topics it covers (at most 6) as JSON, and a topic that goes on into the next part keeps its title and becomes one page. A part whose answer can't be used is asked again once, then skipped and listed. Each PDF has its own pages, saved in `content/wiki/<id>.json`, so adding, replacing or removing a PDF builds, rebuilds or removes only that PDF's pages; on start, any PDF read but without up-to-date pages is built again. While llama-server can't be reached, the build waits and asks for the same part again every 30 seconds, keeping the parts already done. Manage Content shows "Building the wiki: part 2 of 3…", then "Wiki ready: N topics" with a **Read the wiki** link. The log has `Building wiki pages`, `Wiki part done` with the topics found and `duration_ms` for each part, then `Wiki pages built` with the page count, any `skipped_parts` and the time taken; or `Waiting for the LLM to build the wiki`, `The LLM's wiki answer could not be used` (with what it said) or `Could not build the wiki`. Each part takes the LLM about 20 to 40 seconds on a 4-core CPU (measured with Qwen 2.5 1.5B; a 4B model takes longer), so a long PDF takes a while. While a part is being written, a chat reply waits for llama-server.

Then the LLM builds the wiki's **outline** from those topics (roadmap R37a): the PDF's table of contents. With more than 3 topics, it groups them into sections, each with a title and a summary of a sentence or two; a topic it leaves out stays in the table of contents on its own. Each topic is shown with the LLM's few sentences on it. When what the PDF itself says on the topic's pages is simple enough (5 sentences and 600 characters or fewer), that is all. When the PDF says more, the topic gets a **detail page**: the LLM groups the PDF's paragraphs about the topic into parts, each with a title, and each part is again either shown in the PDF's own words or summarized with a detail page of its own, down to 4 levels in all. Whatever the LLM can't group or split stays as it is, and if it refuses the outline altogether the topics are kept as they are. Manage Content shows "Building the wiki outline: step 4 of about 9… (4 min 12 s so far, about 3 min left)", with the time the build has taken so far and an estimate of the time its stage has left (from how long its steps have taken so far; the outline's number of steps grows as long parts are found, so its estimate can grow too), then "Wiki: N pages, M detail pages, built in 5 min 48 s". The log has `Building wiki outline`, `Wiki outline step done` with the `step` (`sections` or `detail`) and `duration_ms` for each request, `The LLM's wiki outline answer could not be used`, and `Wiki outline built` with the entries, detail pages, requests and time taken. The LLM writes only titles and summaries, never the PDF's text again, because most of each request's time is spent writing the answer. Pages saved before the outline existed are built again on start.

The **Wiki** page in the top bar (roadmap R37b, `#/wiki`) shows every PDF's table of contents, built or not yet; Manage Content's **Read the wiki** link opens one PDF's (`#/wiki/<PDF id>`). Each entry shows its title, its summary and the PDF pages it came from; each page number opens that page of the PDF in a new tab. The table of contents shows every level of the outline: an entry with parts opens and closes when it is clicked, and **Open all** and **Close all** open or close every level at once. An entry with a detail page has its title and a **Read more** link to that page (`#/wiki/page/<entry id>`), which has the same layout: a trail back to the PDF and the detail pages above it, its summary, its PDF pages, and its parts, down to the next detail pages. The browser's console has `Wiki loaded in N ms` and `Wiki page loaded in N ms`, or `Could not load the wiki`. The JSON is still at `GET /api/content/{id}/wiki`, for checking what was built.

Any entry can be **edited** (roadmap R38): **Edit** turns its title and summary into text boxes, with **Save** and **Cancel**, and a saved entry says "Edited by you", with **Undo my edit** to go back to what the LLM built. Edits are kept on the server in `content/wiki/<id>.edits.json`, apart from what was built, so they are there whenever the wiki is opened again, after a restart too. **Rebuild the wiki**, under each PDF's name, asks once more, then builds that PDF's wiki again with the LLM, showing how far it has got; the pages built before stay as they are until the new ones are saved. A rebuild (or a replaced PDF's) keeps every edit and marks it for the user to check, showing what the new wiki says, with **Keep my edit** or **Use the new text**. An edit whose entry the rebuilt wiki no longer has is listed under the PDF's name until the user discards it. Removing a PDF removes its edits. The log has `Wiki entry edited` with `duration_ms`, `Wiki edit undone`, `Wiki edit checked`, `Rebuilding wiki`, `flagged_edits` on `Wiki pages built`, and `Could not save the wiki edits`; the browser's console has `Wiki edit saved in N ms` or `Could not save the wiki edit`.

Every change to a PDF's wiki keeps a **version** of the whole wiki (roadmap R38a): built or rebuilt by the LLM, an entry edited, an edit undone or kept, a lost edit discarded, a version restored, or a file loaded. Versions are kept in `content/wiki/<id>.history/`, all of them; a wiki built before this keeps its state then as the first version. **History**, under each PDF's name, lists them newest first with when they were made and what changed; **View** shows a version's table of contents, and **Restore** makes it the wiki again as a new version, so a restore can be undone too. **Save to a file** downloads the wiki as it is now with its whole history, and **Load from a file** reads one back: its wiki becomes the current one, and its versions join the history (the wiki before it stays there too). A file loads only into the PDF it was saved from; if that PDF has been replaced since, or the version to restore was built from its earlier copy, the page says so and asks first. Removing a PDF removes its history. The log has `Wiki version kept` with its `kind`, `Wiki version restored`, `Wiki saved to a file`, `Wiki loaded from a file` with `versions_added`, `Could not keep the wiki version` and `Could not read a wiki version`; the browser's console has `Wiki history loaded in N ms` and `Wiki version restored`.

| Request | What it does |
|---|---|
| `GET /api/wiki/builds` | How far each PDF's wiki pages have got: `state` (`waiting`, `building`, `done` or `failed`), `part` of `parts`, the `stage` (`topics` or `outline`) and the outline `steps` done, `elapsed_s`, the seconds the build has taken so far (or took, once done), `remaining_s`, about how long the stage has left, and `steps_planned`, and once done how many `pages`, `detail_pages` and any `skipped_parts` |
| `GET /api/wiki` | Every wiki page (or one PDF's, with `?pdf={id}`): `id`, `title`, `pages`, `pdf_id` and `pdf_name` |
| `GET /api/wiki/contents` | Every PDF's table of contents (or one PDF's, with `?pdf={id}`), as the Wiki page shows it: `pdf_id`, `pdf_name` and its `entries`, every level of the outline, each entry marked `edited` (and `review`, with what the rebuild `built`, after a rebuild), and any `lost_edits` |
| `GET /api/wiki/{page_id}` | One entry of the outline as its page shows it: `title`, `summary`, `pages`, whether it is a `detail` page, its `entries` (down to the next detail pages), and the `trail` of detail pages above it (`id` and `title`, from the top down); a topic's has its whole `text` too |
| `GET /api/content/{id}/wiki` | One PDF's wiki pages with their text, its whole `outline`, and the user's `edits` |
| `PUT /api/wiki/{page_id}` | Saves the user's `title` and `summary` for an entry (422 if either is empty or too long) and returns its page |
| `DELETE /api/wiki/{page_id}/edit` | Undoes an entry's edit, back to what the LLM built, or discards a lost edit |
| `POST /api/wiki/{page_id}/reviewed` | Marks an edit flagged after a rebuild as checked |
| `POST /api/content/{id}/wiki/rebuild` | Builds a PDF's wiki again with the LLM, keeping the edits (409 if it hasn't been read yet) |
| `GET /api/content/{id}/wiki/history` | The PDF's wiki versions, newest first: `id`, `at` and the `change` (`kind`, and the entry's `title` or the restored version's `restored_at`) |
| `GET /api/content/{id}/wiki/history/{version}` | One version as the Wiki page shows it: `entries` and `lost_edits` |
| `POST /api/content/{id}/wiki/history/{version}/restore` | Makes a version the wiki again, as a new version (409 while the wiki is being built; 412 if it was built from an earlier copy of the PDF, unless `?force=true`) |
| `GET /api/content/{id}/wiki/file` | Downloads the wiki as it is now with its whole history, as `<PDF name>-wiki.json` |
| `POST /api/content/{id}/wiki/file` | Loads a file saved from it (`file`, at most 50 MB): its wiki becomes the current one and its versions join the history; returns `versions_added` (422 if it isn't a wiki file or is another PDF's; 409 and 412 as for a restore) |

**Looking up a question** in the wiki and the PDFs (roadmap R39) is keyword search, so there is no model to download: every wiki entry (its title and summary, with the user's edits, every level of the outline) and every paragraph, slide and table read from the PDFs is ranked with BM25, which favours passages with more of the question's words, rarer words, and shorter text. Words are matched in lower case, without common words such as "the", with a plural "s", an "ing" or "ed" ending and a final "e" left off (so "used" matches "use"), and with Greek letters by name (so "zeta" matches "ζ"); a question word of 5 or more letters that the content doesn't have is taken as the content word one typo away, if there is one, in a passage that also has another of the question's words as typed ("Reimann" for "Riemann", but "What is polar?" isn't taken as "solar"); a wiki entry's title counts twice. A passage is found only when it has at least 40% of the question's words, each weighted by how rare it is in the content, and a word the content doesn't have at all weighs the most: so a passage sharing only a common word ("best" in "What lighting is best for the photo?") is left out, and a question the PDFs don't cover finds nothing. Answers from the content (R40) will use what is found. To try it, `imageskin lookup` prints the best wiki entries (3 by default, `--wiki N`) and PDF passages (5 by default, `--pdf N`) for each question, with their scores, PDF pages and the time the lookup took, from the PDFs in the app's folder:

```
imageskin lookup "How do I install llama-server?" "What does the voice sample need?"
```

The log has `Looked up a question` with the passages searched, the wiki entries found and `duration_ms`. If no PDF has been read yet, it says so and exits with 1.

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

1. **Get the voice ready** (roadmap R25b): when Chatterbox is installed (see [Your own voice](#your-own-voice-chatterbox-turbo-on-the-cpu)), loads it and learns the person's voice from the voice sample, so the clips below are spoken in their own voice. With Pocket TTS installed too, Pocket learns it instead, for replies within 2 seconds (see [Replies within 2 seconds in your own voice](#replies-within-2-seconds-in-your-own-voice-pocket-tts)). Loading takes about 30 seconds; the first time it downloads about 3 GB. Without Chatterbox it loads Kokoro (the first time it downloads the model, about 330 MB) and the clips use a ready-made voice; the log says so at start with `Prepare speaks in a ready-made Kokoro voice, not the person's`. Needs `pip install -e ".[voice]"` either way.
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

**Answers from the content** (roadmap R40): each prompt is looked up in the wiki and the PDFs added on Manage Content (the R39 lookup), and what is found is quoted before the prompt, best first, each passage with its PDF and pages, between `<<<` and `>>>` as reference text: the LLM is told it is source material only, never instructions to follow (a PDF that says "ignore the question" is not obeyed), and to answer from it in its own words without mentioning documents or pages. Only the prompt as typed is kept in the conversation, and the system prompt is unchanged, so llama-server can reuse what it has read of the conversation. The passages take at most 300 tokens (each cut to 400 characters, and the last one cut at a word to fit), because the LLM reads them all before its first word: with Qwen 2.5 1.5B on 4 CPU cores, about 8 ms a token, so the first word comes about 3 s after Send instead of under 1 s. A prompt nothing matches is sent on its own when general prompts are allowed (see below). The log has `Content sent with the prompt` with `passages_found` and `passages_sent`, then `Looked up a question`; if the lookup fails, `Could not look the prompt up in the content; sending it alone`.

**Question scope** (roadmap R41): by default the chat keeps to the content. A prompt that nothing in the wiki or PDFs matches (a joke, the weather, the capital of Peru) gets a short, polite reply instead of an answer: "Sorry, I can only answer questions about the material I was given. Try asking about something in it." The LLM isn't asked, so the reply is spoken at once, and it isn't sent to the LLM with later prompts. To have such prompts answered too, put `general_prompts = true` in the config file (see `config.example.toml`); the Settings page (R27) will offer it later. Before any PDF is added, every prompt is answered, since there is nothing to keep to, and a prompt whose lookup fails is answered rather than declined. A follow-up such as "tell me more" has none of the content's words, so it is declined too: ask about the topic by name. The log has `Question scope` with `general_prompts` when the server starts, and `Prompt declined: general prompts are off` for each prompt declined.

| Request | What it does |
|---|---|
| `GET /api/chat` | The conversation so far |
| `POST /api/chat` | Send a prompt (JSON body `{"prompt": "…", "reply_id": "…"}`, the id chosen by the browser for the reply's clips) and get the reply with its `turn`; refused (403) until a sample is accepted, 502 when the LLM fails |
| `GET /api/chat/clips/{reply_id}?known=N&wait=S` | The reply's clips so far, each with `url`, `sentence_at` and `ready_at` (seconds on the server's clock, like `now`), `done` and `error`; with `known`, waits up to `wait` seconds (10 at most) for a clip beyond the N the browser has |
| `GET /api/chat/clips/{reply_id}/{n}` | Clip `n` of the reply, an MP4 |
| `POST /api/chat/video` | Speak a reply that wasn't streamed in one video (JSON body `{"turn": N}`); the video's address, or null when there is nothing to say aloud |
| `GET /api/chat/videos/{turn}` | That video |

### Spoken replies, sentence by sentence

Each reply is spoken in the person's voice on their photo (roadmap R17), a sentence at a time as the LLM writes it (R20 to R22): the server cleans each sentence for speech, speaks it and renders its clip while the LLM writes the next, and the browser plays the clips one after another, starting before the whole reply has arrived. Two video players take turns, so the next clip is loaded while the current one plays and the switch costs nothing. The first clip is the first sentence's first clause (R22b), cut at a comma, semicolon, colon or dash after at least 3 words, before a joining word such as "and" or "because", or after 5 words when there is none (R22e; on the last word before that doesn't lead into the next, or up to 8 words when every word does), so it is spoken while the LLM is still writing the rest of the sentence; a sentence that ends a word later stays whole. The limits are at the top of `src/imageskin/sentences.py`.

Under the video, when **Show timing metrics** is ticked in the **Settings** menu at the right of the top bar (roadmap R41a; it is off by default), a timing readout says how long each clip took from its text arriving to being spoken, and the pause after the clip before (R22a). A clip is in red when its wait passes the 2-second target: from its text for the first clip, and from the later of its text and the end of the clip before for the others, so a clip whose text arrived while the one before was still playing is on time if it follows straight on. Below the clips, the average wait for the reply, and for every reply since the page was opened. The video has no controls: the person speaks by themselves, as if live; only if the browser refuses to play with sound by itself is there a **Play the reply** button. The log has `Reply sentence ready` with `since_prompt_ms` for each sentence (the first clause counts as one), `Sentence spoken` with `speak_ms` for each clip's voice step, and `Sentence clip ready` with `render_ms` (both steps) and `since_sentence_ms` (text arrived to clip ready) for each clip. The two steps run one after the other: on a 4-core CPU, speaking a sentence while the one before it rendered made both about twice as slow. With the setting off, the pages also leave out how long a setup step or a wiki build took (how long is left is still shown). The setting is saved on the server, in `ui-settings.json` in the app's data folder, so it stays the same after a reload or a restart and in every browser; anyone can change it for now. The log has `Settings changed` when it is changed.

**Clean video playback** (roadmap R41c): the person keeps one place and size on the chat page from the moment it opens. Their photo shows there until the idle video plays, then the idle video fades in over it, and each reply's clips fade in over that, so there is no black or empty frame and nothing jumps. Stop pauses the person at once and fades back to the idle video. A clip that can't be played is skipped quietly (the browser console says which) and the reply's text still shows.

**A designed look** (roadmap R41e2): every page shares one design: the Inter typeface (SIL Open Font License, in `web/public/inter-OFL.txt`, bundled so the app needs no internet for it), white cards with soft shadows on a cool grey page, one indigo accent, a top bar with the app's mark and the pages as tabs, and a dark mode. The layout and the steps are the same as before.

**"What can you talk about?"** (roadmap R41f): ask "What topics can you talk about?" (or "What do you know about?", "What can I ask?") and the person names the topics in the content, the main entries of each PDF's wiki, and suggests one to start with. It is answered straight away, without the AI, even when general prompts are off; then it also says only these topics can be answered. A question that is declined names a few topics to ask about instead.

**Topic hints** (roadmap R41g): under the prompt box, the chat names a few of the topics, and says questions must be about them when general prompts are off. Below that are a few example questions drawn from the wiki; click one to send it. Each example is checked against the content first, so it is always answered.

**Professional teacher pages** (roadmap R41e): Setup, Manage Content and the Wiki look like the chat, each says in a line what it is for, and Setup numbers its four steps. Their messages are in plain words, without technical terms: what went wrong in detail is in the server log.

**A professional chat screen** (roadmap R41d): on a laptop the person is on the left and the conversation on the right; on a tablet held upright the person is above it. One status line says "Thinking…" and then "Getting ready to say it…". When there is no reply, the chat says only "Sorry, I couldn't answer that just now. Please try again in a moment."; why is in the browser console and the server log, not on the screen.

**Student view and teacher view** (roadmap R41b): the Settings menu also chooses the **View**. **Teacher**, the default, has every page and option. **Student** has only the chat and a read-only wiki: the top bar shows only Chat and Wiki, Home, Setup, the recording guide, Manage Content and the consent page show the chat instead when opened by their address, and the wiki has no way to edit, rebuild, save, load or see its history. Each PDF in the wiki has an **Open the PDF** link, and its page numbers open it at that page. Anyone can switch the view for now and the server doesn't check it; R44's sign-on will tie it to who is signed in.

Each frame of a clip is composited by OpenCV in 8-bit (R22c): about 4 ms a frame on a 4-core CPU, so a clip renders in about a fifth of its playing time and the voice is most of the wait before a clip. Reply clips are rendered on the photo scaled down to 720 pixels on its longest side, since the page shows them at most 640 pixels wide (`REPLY_SIDE` in `src/imageskin/prepare_job.py`); the sample video keeps the photo's size. The log's `Rendered video` line has each clip's `frames`, `duration_ms` and `real_time_factor`.

A clip is offered to the browser the moment its video starts to be written (R22d): the clip is a fragmented MP4 written half a second at a time, and the server streams it as it grows, so the video plays while the rest is rendered and only the voice step is waited for. The readout counts from the text to the clip playing; the log's `Sentence clip ready` line has `listed_since_sentence_ms` (text arrived to the clip listed for the browser, as its video starts to be written; it plays once its first half-second fragment is out) next to `since_sentence_ms` (text arrived to the clip whole). On a 4-core CPU, the voice step runs at about half real time while the LLM writes, and the browser on the same machine takes cores from it too, so later clips in a long reply can still pause between sentences: that is the engines' throughput, and a faster voice or a graphics card is what shortens it. In the person's own voice, Chatterbox takes several seconds per clip on a 4-core CPU; Pocket TTS brings the first clip to about 1.5 s after its text (see [Replies within 2 seconds in your own voice](#replies-within-2-seconds-in-your-own-voice-pocket-tts)).

For quick replies on a CPU, two things happen at startup once a sample has been accepted (`Warming up replies` in the log): the LLM reads the system prompt (`LLM warmed up`), so the first reply's words come about 2 s sooner, and the voice and video engines load and render a word (`Replies warmed up`), which takes a minute or two the first time. While the LLM is busy (writing the reply, or summarizing the conversation after one), the engines use half the cores and all of them once it has finished (`Engine threads set` with `threads` and `cores`); start llama-server with `--threads` set to the other half, as above. Leave `OMP_NUM_THREADS` unset: the app shares the cores itself, and a cap below the core count is logged as a warning (`OMP_NUM_THREADS caps the engines' cores`). On a CPU with performance and efficiency cores, such as Intel's 12th-generation and later laptop chips, the app keeps itself on the performance cores and counts only those (R22g; the log says `Kept the app on the performance cores`), since an efficiency core is about 3 times slower per thread; on a laptop with 4 performance and 8 efficiency cores this made the voice about 1.7 times faster. Set `IMAGESKIN_ALL_CORES=1` to spread over every core instead.

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

A chat reply is shown as written, but the voice leaves out what reads badly aloud (feature 11). Markdown markers, HTML tags and decorative emoji are silent. A link, a picture, a table, a code block or inline code of more than two words is replaced by a short phrase that points to the text, such as "the link in the text below" or "See the code shown below.", so no sentence breaks off. Shorter inline code, such as `main()`, is spoken as is, and a heart between two words ("I ❤️ it") is said as "love". Math is said in words (roadmap R16b): "$\\zeta(s)$" or "ζ(s)" is "zeta of s", "π ≈ 3.14" is "pi is approximately 3.14", and an equation too long to say is "the equation in the text below". `imageskin spoken-text` prints what the voice will say for a reply, with nothing to install beyond the base package. Pass the reply in quotes, or, for a reply with several lines or code blocks, save it in a UTF-8 text file and pass `--file`:

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

### Replies within 2 seconds in your own voice (Pocket TTS)

Chatterbox is too slow for replies on a 4-core CPU: a 4-word clause took 7 s on 2 cores, so a reply waits several seconds per clip. [Pocket TTS](https://huggingface.co/kyutai/pocket-tts) (Kyutai; code MIT, weights CC-BY-4.0) also clones the voice from 10 seconds of the voice sample with no training and keeps the person's own accent, and it speaks the same clause in about 0.6 s (roadmap R22f). With it installed next to Chatterbox, Pocket speaks everything in the person's own accent: the replies, the sample video and the fixed lines, so they all sound the same. With an American or British accent, Prepare has a Kokoro voice of that accent read a passage once, converts it to the person's voice with Chatterbox's converter (this adds about a minute to Prepare), and Pocket learns from that, so it speaks every reply in the person's voice with that accent, as fast as with their own. Without Pocket, every clip of another accent is converted as it is spoken, about 17 to 22 s a clip on a laptop. Measured in the chat page on a 4-core CPU with Gemma 3 4B writing on 2 of the cores: the first clip of a reply started 1.5 to 1.6 s after its text, and the average wait before a clip was 0.8 s.

Its weights that clone a voice are gated on Hugging Face, free but behind a one-time step. Make a free account, accept the terms on the [model page](https://huggingface.co/kyutai/pocket-tts), make a read token under [Access Tokens](https://huggingface.co/settings/tokens), then sign in with `hf auth login` and paste the token (it is saved, so this is done once). Install Pocket TTS with Chatterbox already installed as above (about 530 MB of models are downloaded the first time), then start the app and click **Prepare** on the Setup page: the clips are spoken again in Pocket's voice.

macOS / Linux:

```
source .venv/bin/activate
hf auth login
pip freeze --all --exclude-editable > app-constraints.txt
pip install --retries 10 pocket-tts==3.3.0 -c app-constraints.txt
```

Windows 11, Command Prompt:

```
.venv\Scripts\activate.bat
hf auth login
pip freeze --all --exclude-editable > app-constraints.txt
pip install --retries 10 pocket-tts==3.3.0 -c app-constraints.txt
```

Windows 11, PowerShell:

```
.venv\Scripts\Activate.ps1
hf auth login
pip freeze --all --exclude-editable | Set-Content -Encoding ascii app-constraints.txt
pip install --retries 10 pocket-tts==3.3.0 -c app-constraints.txt
```

The log says `Prepare speaks in the person's own voice, cloned with Pocket TTS` at start, `Loaded Pocket TTS`, and `Spoke text in cloned voice` with `"model": "Pocket TTS"` for each clip. `imageskin say --voice-sample` uses Pocket too when it is installed, so you can hear it on its own. If Prepare fails with `could not load Pocket TTS: its weights that clone a voice need the terms accepted`, the terms are not accepted yet or `hf auth login` was not run. To go back to Chatterbox, run `pip uninstall pocket-tts`, restart `imageskin serve` (the app picks its voice engine when it starts) and click **Prepare** again.

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
