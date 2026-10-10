# ImageSkinForLLM: Roadmap

Every pull request needed to take ImageSkinForLLM from an empty repository to the full app in [features.md](features.md). Each PR is Simple or Medium under the pr-rules skill, and each one leaves something new that can be shown. The order gets a talking sample video working as early as possible (after the 4th PR, photoreal after R4c), then builds the browser setup. Next it proves the person's own voice can be cloned convincingly, before any chat work, because the project fails if the voice doesn't work (Larry, 2026-10-07). Then it builds the chat and the rest around it. Milestones 9 to 13, added on 2026-10-08, come last and turn the app into question and answer over PDF content, with an administrator sign-on, student accounts and a history of every interaction (items 24 to 37). Milestones 14 to 17, added on 2026-10-09, come after them and add student insights: questions tagged by topic and rated for understanding, search across histories, topic statistics, student summary pages, and a heads-up before clearing history (items 38 to 46). Milestone 18, added later on 2026-10-09, comes last and adds a profile of each student's interests and personality (item 47).

PRs are numbered R1 to R60 so they don't get mixed up with GitHub PR numbers. R4a to R4c were added after R4 for the photoreal engine (R4a, mouth alignment, is described in GitHub PR #8), R25a and R25b for the voice, R26a for the accent, R16a for saying what a reply leaves out, and R22a to R22e for replies within 1 to 2 seconds after Larry's test of R22, so the other numbers stay the same. **PRs are built in the order they appear in this file, not in number order:** after R13 come R25a, R25, R25b, R26a, R26 and R14, then R15; after R17 come R20, R21 and R22, then R18 and R19, because Larry found the reply video too slow to wait for and replies must be quick (2026-10-10). Item numbers like "item 6" refer to features.md.

This is the plan as of today. R4 picked the first video engine, a CPU mouth animation of the photo. Larry found its mouth too puppet-like and preferred the photoreal LivePortrait test in GitHub PR #8 (2026-10-05), so R4b and R4c add a photoreal engine and the OpenCV engine stays as a quick fallback. The PRs it changes are listed in [After the engine decision](#after-the-engine-decision), and their definitions will be revised when each one starts.

## Milestones

| # | Milestone (what can be demonstrated) | PRs | Count | % of PRs | Done |
|---|---|---|---|---|---|
| 1 | **Sample video from the command line.** One photo in, a photoreal video of the person saying the sample script out, in a ready-made Kokoro voice (the person's own voice comes in Milestone 3). | R1 to R4c | 7 | 9.7% | 7 of 7 |
| 2 | **Setup in the browser.** Upload, validate, prepare, watch the sample video. | R5 to R13 | 9 | 12.5% | 9 of 9 |
| 3 | **The person's voice, reviewed.** A test proves the person's voice can be cloned from their recordings; then the sample video speaks in their voice, in their own accent or another one (American or British), and setup ends with accept or reject. | R25a, R25, R25b, R26a, R26, R14 | 6 | 8.3% | 6 of 6 |
| 4 | **Talking chat.** Type a prompt; the person speaks the LLM's reply in their voice, saying briefly what is left out (links, code), with the written reply in a text panel that opens on request. | R15 to R19 | 6 | 8.3% | 4 of 6 |
| 5 | **Real-time replies.** The video starts on the first sentence, within 1 to 2 seconds of the text, and idles naturally between replies. | R20 to R23 | 9 | 12.5% | 8 of 9 |
| 6 | **Spoken prompts.** Push-to-talk microphone input. | R24 | 1 | 1.4% | 0 |
| 7 | **Settings, exit and return.** Every setting, Goodbye and Welcome back, saved setup, delete my data. | R27 to R31 | 5 | 6.9% | 0 |
| 8 | **Hosted, with cloud LLMs.** Runs on a hosted HTTPS site; Claude or OpenAI with the user's key. | R32 to R33 | 2 | 2.8% | 0 |
| 9 | **Content and the wiki.** Add, remove or replace PDFs on a Manage Content page; review and correct the wiki built from them. | R34 to R38 | 5 | 6.9% | 0 |
| 10 | **Answers from the content.** Ask a question; the person speaks an answer drawn from the wiki and PDFs, with general prompts allowed or not. | R39 to R41 | 3 | 4.2% | 0 |
| 11 | **Choice of LLM.** Local llama.cpp by default, or Claude, OpenAI, Grok or OpenRouter by API key or subscription. | R42 to R43 | 2 | 2.8% | 0 |
| 12 | **Sign-on and accounts.** Administrator sign-on, question and answer only without it, student sign-up and login, and a setting to require sign-up. | R44 to R47 | 4 | 5.6% | 0 |
| 13 | **Interaction history.** Every question and answer kept; students see and soft-clear their own; the administrator reviews all of it; conversations are saved to a file before clearing and can be loaded back. | R48 to R52 | 5 | 6.9% | 0 |
| 14 | **Topics and understanding.** Every question tagged with its topics; students' questions rated strong, weak or unrated for each topic, with administrator corrections. | R53 to R54 | 2 | 2.8% | 0 |
| 15 | **Search.** The administrator searches one student's history or everyone's on the user history page. | R55 | 1 | 1.4% | 0 |
| 16 | **Statistics and summaries.** A topic statistics page and a summary page per student. | R56 to R57 | 2 | 2.8% | 0 |
| 17 | **Heads-up before clearing.** Students are told a cleared conversation stays available to the administrator. | R58 | 1 | 1.4% | 0 |
| 18 | **Interests and personality.** A profile of each student's interests and personality, drawn from the questions they ask and how they respond to the answers, for the administrator. | R59 to R60 | 2 | 2.8% | 0 |
| | **Total** | | **72** | **100%** | **34 of 72** |

Sizes: 17 Simple, 55 Medium, no Large or Very large. Percentages are rounded to one decimal. A PR counts as done when its pull request is open with everything the pr-rules skill asks for; its entry below links the pull request.

## How sizes were judged

The pr-rules skill sizes a PR by review time: Simple is 10 minutes or less, Medium is 10 to 20. As a rough yardstick for this roadmap, Simple means one focused piece, under about 200 changed lines including tests; Medium means up to about 400 changed lines, or fewer if the logic is tricky (concurrency, media processing, a new model). Each PR below does one job: a server piece and the screen that uses it are separate PRs when together they would pass that line. If a PR still grows past Medium while it is being built, it is split before it is opened.

## Assumptions and decisions needed

- **Stack:** Python with FastAPI on the server, TypeScript with Preact in the browser (built with Vite; Larry chose a React-style library, 2026-10-06, and Preact for its small size), ffmpeg for media conversion. If the stack changes, the PR list stays the same; only the tooling in R1 and R5 changes.
- **Testing:** unit tests use fake voice and video engines so CI runs without a GPU or paid API. Each PR that touches a real engine proves it with a manual run and a short clip or log excerpt, per the pr-rules skill.
- **Every code PR** follows the pr-rules skill: build, lint and format pass; unit tests with about 80% line coverage on changed code; logging for errors, timing and meaningful operations; proof and manual test steps in the description.

Decisions to make before a PR starts. The roadmap does not decide these; features.md should be updated with each answer first.

| Before | Decision |
|---|---|
| R3 | The first voice (TTS) engine. It must return word timings (planned for highlighting in R18, dropped on 2026-10-09; still used for the mouth), be free per use and run on CPU (Larry, 2026-10-04). **Picked in R3: Kokoro-82M** (Apache 2.0, runs on CPU on Windows and on a Linux server, reports word timings). It uses ready-made voices and cannot clone, so the person's own voice moves to R25. Rejected: ElevenLabs (per-use cost), XTTS-v2 and F5-TTS (non-commercial model licenses), MeloTTS plus OpenVoice v2 (install pins packages too old for Python 3.11), Chatterbox (reported slower than real time on CPU). |
| R4 | The first video engine, local or hosted, and which tool. It must be free per use, run on CPU, allow hosted use and work on Python 3.11 and 3.12 (Larry, 2026-10-04). **Picked in R4: our own mouth animation with OpenCV** (Apache 2.0): OpenCV's bundled face detector finds the face, and the mouth opens with the loudness of the speech. No model download, renders faster than real time on a CPU; it looks like a puppet mouth rather than a photoreal talking head. Rejected: Wav2Lip (non-commercial weights), SadTalker (non-commercial Basel Face Model, pins Python 3.8, minutes per clip on CPU), MuseTalk (needs a base video, no Python 3.12, GPU-bound), LivePortrait (video-driven, non-commercial InsightFace models), diffusion models such as Hallo and LatentSync (GPU only), hosted avatars (per-use cost). **Changed after R4:** LivePortrait turned out usable (its weights are MIT, and MediaPipe replaces the non-commercial InsightFace), and pre-rendering its frames once makes each reply fast on the CPU (GitHub PR #8). Larry chose it for photoreal quality (2026-10-05); R4b and R4c build it. |
| R10 | The minimum length of speech for sound validation. features.md says only "long enough"; feature_evaluation.md suggests 30 seconds. **Picked in R10:** at least 30 seconds of speech in the voice sample, and at least 15 in each recording (pauses not counted); constants in `sound_checks.py`. |
| R21 | The latency target. Larry: a reply video that takes more than a few seconds to generate is unacceptable (2026-10-04). The photoreal test built a 2.5-second reply clip in 0.5 to 1.5 seconds on a 4-core CPU, so per-sentence clips should fit. Measured in R4c with the real voice on a 4-core CPU: the video for 6.9 seconds of speech renders in 2.2 seconds (about a third of real time), after Kokoro's 2 seconds to speak it. |
| R25 | The voice tool that makes the person's voice: a CPU voice-conversion tool that turns Kokoro's output into the person's voice (for example OpenVoice's tone-color converter or Seed-VC), and, for keeping the person's own accent (item 4), possibly a cloning TTS. It must be free per use, run on CPU and allow hosted use. **Picked in R25a: cloning with Chatterbox Turbo** (MIT, Resemble AI), which speaks the text directly in the person's voice and keeps their accent. Larry: "The clone sounds very reasonable. The others do not sound like me." (2026-10-08). Rejected: converting Kokoro's voice with Chatterbox's converter (did not sound like him), OpenVoice v2 and kNN-VC (not published as packages), Seed-VC (GPL-3), Pocket TTS (cloning weights gated behind a Hugging Face sign-in). Costs to handle in R25: on a 4-core CPU it takes 1.5 to 2 seconds per second of speech, and it reports no word or sound timings. |
| R32 | How the hosted site restricts access to its one user. features.md says single-user and HTTPS but names no mechanism. The simplest option is one password checked at the HTTPS proxy, with no accounts. R44 later replaces this with the administrator sign-on. |
| R36 | The PDF tool that reads text, slides and tables. It must be free, run on CPU and allow hosted use. Scanned PDFs (pictures of pages) would also need OCR; whether they must be supported is open. |
| R39 | How questions are looked up: keyword search over the wiki and PDF text, or a local embedding model. The simplest option is keyword search first, adding embeddings only if answers miss. |
| R43 | Whether a Claude, OpenAI or Grok subscription can be used by a separate app at all. Not checked yet: these subscriptions are mainly for the providers' own apps, and an API key may be the only supported route. If a subscription can't be used, R43 is dropped and features.md updated. |
| R44 | How the administrator account is created. The simplest option is that the first run asks for an administrator password, stored hashed on the server. |
| R54 | How a question is rated for each topic, using the definitions in item 40. The simplest option is to ask the chosen LLM (item 29) with the question, each topic's wiki page and those definitions, and to keep its one-line reason with each rating. |
| R59 | How the interests and personality profile is worked out, and how often. The simplest option is to ask the chosen LLM (item 29) with the student's recent questions, the answers and their next messages, and the list of signals in item 47, and to run it after a student's session ends rather than after every question. |

## After the engine decision

The PRs below are written for either kind of video engine, but these are the ones that change shape once R4's engine is chosen. R4 picked a local engine that runs on the CPU, so the right-hand column applies, without a GPU.

| PR | Hosted streaming avatar (D-ID, Simli and similar) | Local rendering model |
|---|---|---|
| R4 | Adapter calls the service; the sample is rendered remotely. | Adapter runs on the CPU (as built: prepare takes under a second, render about 0.15 times real time). The photoreal engine (R4c) prepares each photo once (about 17 minutes on a 4-core CPU), then renders each reply from the saved frames at about a third of real time. |
| R17 | Reply audio is sent to the avatar stream. | Each reply is rendered to a clip, then played. |
| R21, R22 | The service streams video; the browser plays one stream. | The server renders sentence clips; the browser queues them. |
| R23 | Idle motion likely comes from the service; small or dropped. | Needs idle motion (blinks, small head movement) drawn by the same engine. With R4c, the pre-rendered idle loop already blinks and moves, so R23 plays it between replies. |

## Milestone 1: Sample video from the command line

### R1. Project skeleton (Simple) · Done in [PR #3](https://github.com/larry94555/ImageSkinForLLM/pull/3)
- Python package with FastAPI app, a `/health` endpoint, and an `imageskin` command-line entry point.
- Structured logging setup, config file loading, lint, format, type check and unit tests wired into CI.
- **Can show:** `imageskin --version` runs, `/health` returns OK, CI is green.
- **Built:** package `imageskin` under `src/`, `imageskin serve` and `--config` (see `config.example.toml`), JSON-lines logs on stderr, ruff, mypy (strict) and pytest with coverage in GitHub Actions. It reviewed as Medium (about 460 lines, half of them tests), larger than the Simple estimate.

### R2. Audio conversion and the voice sample (Simple) · items 1, 3 (partial) · Done in [PR #5](https://github.com/larry94555/ImageSkinForLLM/pull/5)
- Converts M4A and MP3 to WAV with ffmpeg, with a timeout, and joins several recordings into one voice sample.
- Command: `imageskin voice-sample rec1.m4a rec2.m4a rec3.m4a` writes one WAV.
- **Can show:** the guide's recordings turned into a single voice sample that plays correctly.
- **Built:** `imageskin voice-sample ... -o voice-sample.wav` converts each file to 24 kHz mono 16-bit WAV (`--timeout`, default 60 seconds per file) and joins them in order. ffmpeg must be on PATH; CI installs it.

### R3. Voice engine and speech (Medium) · item 11 (timings) · Done in [PR #6](https://github.com/larry94555/ImageSkinForLLM/pull/6)
- Voice engine interface (`speak(voice, text) -> audio + word timings`) and the first real adapter, Kokoro-82M on the CPU, with ready-made voices.
- Command: `imageskin say [--voice af_heart] "Hello there"` writes a WAV and a word-timings JSON file.
- **Can show:** any sentence spoken in a ready-made voice on the CPU, with each word's start and end time.
- **Built:** `VoiceEngine` protocol in `voice.py` and a Kokoro adapter installed with `pip install -e ".[voice]"`. Changed from the first plan, which was `clone(sample)` and speech in the person's cloned voice: Larry chose a free, CPU-only engine and a ready-made voice for now (2026-10-04), so cloning moved to R25 and the R2 voice sample is first used there.

### R4. Video engine and the sample video (Medium) · item 6 · Done in [PR #7](https://github.com/larry94555/ImageSkinForLLM/pull/7)
- Video engine interface (`prepare(photo) -> face`, `render(face, audio) -> video`) and the first real adapter.
- Command: `imageskin sample --photo me.jpg` renders the item 6 script, spoken by R3's Kokoro voice, to an MP4, logging how long each step takes.
- **Can show:** the ~30-second sample video of the person speaking the test script (in a ready-made voice until R25). This is the first end-to-end test of the whole idea, and the timings it logs set the latency target.
- **Built:** `VideoEngine` protocol in `video.py`, the OpenCV engine in `mouth_warp.py` installed with `pip install -e ".[video]"`, and `imageskin sample --photo me.jpg [--voice ...] [-o sample.mp4]`, which logs `prepare_ms`, `speak_ms` and `render_ms`. The rest of the face stays still until R23.

### R4a. Photoreal mouth alignment and tuning (Medium) · item 6 · Done in [PR #13](https://github.com/larry94555/ImageSkinForLLM/pull/13)
- Found in Larry's laptop test of the photoreal engine (GitHub PR #8, 2026-10-05): on open mouth shapes (AA, OH, OO), the lower lip and jaw shift sideways instead of opening straight down. The likely cause is that the "open" edit moves only one of LivePortrait's 21 face points, which sits off the centre line.
- Open the mouth symmetrically, probably by driving it with LivePortrait's lip retargeting model, then re-tune every mouth shape on at least two photos (one with the face turned slightly).
- **Goal (Larry, 2026-10-05): the lips show each sound clearly enough to lip-read.** So the shape set covers the distinct lip positions: closed (m, b, p), lip on teeth (f, v), rounded (oo, w, oh), spread (ee), open (ah), and a small opening for the other consonants. Keep the opening small and the transitions gentle; a wide or square mouth looks like a dummy. A test of the OpenCV engine timed to each sound showed that warping a still photo cannot round or spread the lips, so these shapes must come from LivePortrait.
- **Can show:** `mouth_shapes.png` and the reply clips before and after, side by side, with the mouth opening straight down, and each shape clearly different from the others.
- **Result (PR #13, 2026-10-06):** the lip retargeting model opens the mouth straight down; 10 mouth shapes; tuned with Larry to soft, calm lips: shapes move 45% of the way from rest, the upper lip 30% as far as the rest of the mouth, sounds blend over 60 ms with the lips 30 ms ahead, and r stays neutral so the corners don't pulse. Larry accepted this as the minimum for now; further mouth polish can come later.

### R4b. Sound timings from the voice (Simple) · items 6, 11 · Done in [PR #14](https://github.com/larry94555/ImageSkinForLLM/pull/14)
- Kokoro also reports when each sound (phoneme) starts and ends, not only each word, and each sound is mapped to a mouth shape (viseme). Closed-lip sounds (m, b, p) always get a frame, even when shorter than one.
- **Can show:** `imageskin say` writes the sound timings and mouth shapes next to the word timings.
- **Partly done in [PR #13](https://github.com/larry94555/ImageSkinForLLM/pull/13) (experiment):** Kokoro's per-sound timings, the sound-to-mouth-shape mapping and the closed-lip frame rule work in `experiments/lipread/`.
- **Built:** the app's Kokoro engine reads each sound's length straight from the model's results (no model patch needed with the PyTorch build), and `imageskin say` writes `sounds` (each phoneme, its time and mouth shape) and `shapes` (the mouth shapes over time) next to the word timings. `imageskin.visemes` holds the mapping (with Kokoro's diphthong letters added) and `frame_weights`, which turns shapes into per-frame weights with Larry's 60 ms blend and 30 ms lead and gives each m, b, p, f and v its own frame. R4c renders from these.

### R4c. Photoreal video engine (Medium) · item 6 · Done in [PR #15](https://github.com/larry94555/ImageSkinForLLM/pull/15) and [PR #16](https://github.com/larry94555/ImageSkinForLLM/pull/16)
- A second adapter behind R4's `VideoEngine` interface, using the mouth shapes as tuned in R4a. `prepare` renders the frame library once with LivePortrait (mood loops and mouth shapes, hours on the CPU), logs progress and resumes after an interruption. `render` picks frames from R4b's sound timings and adds the voice, in about a second per short reply.
- Command: `imageskin sample --photo me.jpg --engine photoreal`. The OpenCV engine stays the default until this one is accepted, as a quick fallback.
- **Can show:** the sample video of the person in photoreal quality, lip-synced to the voice, with the render time logged. If it grows past Medium, preparing the library and rendering split into two PRs.
- **Acceptance (lip-reading test):** a clip of the person saying "Hello, my name is Mary. Would you like some more popcorn? Please move the blue boat. I see three green trees." Watched with the sound off, the lips visibly close on m, p and b, round on "oo" and "oh", and spread on "ee", so the words can be followed. Larry checks it on his own photo.
- **Split in two** because together it reviewed as Large: [PR #15](https://github.com/larry94555/ImageSkinForLLM/pull/15) moves LivePortrait into the app and prepares a photo (`imageskin prepare`), and [PR #16](https://github.com/larry94555/ImageSkinForLLM/pull/16) renders replies from it (`imageskin sample --engine photoreal`).
- **Built:** `imageskin prepare --photo me.jpg` renders, once per photo, the 10 mouth shapes on the still head with Larry's accepted settings and an 8-second idle loop with a slight head drift (a degree or two) and two blinks, saved under `~/.imageskin/photoreal/` (about 170 MB) and resumed after an interruption. It takes about 17 minutes on a 4-core CPU, not hours: the mouth shapes are rendered on the still head only, and each reply moves the mouth with the head (a shift and slight turn measured from the loop frames, accurate to under half a pixel), instead of rendering every mouth shape at every head position. `imageskin sample --photo me.jpg --engine photoreal [--text ...]` renders from R4b's sound timings with no model run. One neutral loop for now; moods come with the settings that use them. The experiments in `experiments/` were removed: the app now does what they tested.

## Milestone 2: Setup in the browser

### R5. Browser app and consent (Medium) · item 22 · Done in [PR #17](https://github.com/larry94555/ImageSkinForLLM/pull/17)
- TypeScript browser app served by FastAPI, with page routing and a shared layout.
- Consent checkbox before setup (item 22).
- **Can show:** the app opens in the browser and setup is blocked until consent is confirmed.
- **Built:** TypeScript with Preact (works like React, library about 400 lines) in `web/`, built by Vite into `src/imageskin/static`. The built files are committed, so running the app needs no Node.js; only changing the browser code does, and CI checks the committed files match the source. Pages use hash routes (`#/`, `#/consent`, `#/setup`). Consent is saved on the server as `consent.json` in the app's home folder (`IMAGESKIN_HOME`, default `~/.imageskin`) via `GET` and `POST /api/consent`; R6's upload endpoints should refuse requests until it is given. It reviewed as Medium, not the Simple estimated, because of the browser build setup. Preact's MIT notice ships next to it as `preact-LICENSE.txt`.

### R6. Upload API with safe storage (Medium) · item 1 · Done in [PR #18](https://github.com/larry94555/ImageSkinForLLM/pull/18)
- Server endpoints to upload, list, fetch and remove images (JPG, PNG, HEIC) and sound files (WAV, M4A, MP3).
- Hardening, built in from the start: file type checked from the file's content, not its name or extension; stored under generated names, never the uploaded name or path; size limits per file and in total, and a duration limit for audio; conversion (HEIC to JPG, audio to WAV via R2) runs with a timeout.
- **Can show:** with curl or the API docs page, a valid photo and recording are stored and converted; a renamed non-image file or an oversized file is rejected with a plain message, and the logs show why.
- **Built:** `GET`/`POST /api/uploads/{photos|sounds}` and `GET`/`DELETE /api/uploads/{photos|sounds}/{id}` in `app.py`, storage in `uploads.py`. All four refuse with 403 until consent is given. Files live in `<IMAGESKIN_HOME>/uploads/photos` and `/sounds` as `<random id>.jpg|.png|.wav`, each with a `.json` holding the uploaded name for display. Limits: 25 MB per photo, 100 MB per sound file, 10 minutes per recording, 1 GB in total; conversion stops after 60 seconds. HEIC needs the optional extra `.[heic]` (pillow-heif, whose wheels bundle LGPL-3 libheif/libde265 and GPL-2 x265; decode only), and is converted to JPG in a separate process so it can be timed out.

### R7. Upload screen (Medium) · item 1 · Done in [PR #19](https://github.com/larry94555/ImageSkinForLLM/pull/19)
- Browser screen for uploading photos and recordings, listing them, viewing images and playing sound files. At least one photo is needed; the guide asks for five so the app can pick the best.
- **Can show:** upload one or more photos and the recordings, then view and play them in the browser.
- **Built:** the Setup page (`#/setup`, in `web/src/pages.tsx`) has a Photos and a Recordings section, each with an Add button taking several files at once (uploaded one at a time through R6's API), the server's reason shown next to any refused file, photo thumbnails that open full size, a player and length for each recording, and Remove (asks first). No server changes.

### R8. Face checks (Medium) · item 2 (part 1) · Done in [PR #20](https://github.com/larry94555/ImageSkinForLLM/pull/20)
- Four checks from item 2, each with its fixed plain-language message on the upload screen: exactly one face, face large enough, facing the camera, nothing covering the face.
- **Can show:** a group photo, a small face or a side-on photo is rejected with a message a nontechnical person can act on.
- **Built:** `face_checks.py` runs MediaPipe's face landmarker (faces, size, head turn) and multiclass selfie segmenter (hands, masks, sunglasses over the face) on each photo as it is uploaded; about 20 MB of models are downloaded to `<IMAGESKIN_HOME>/models/faces` on first use. Limits: face at least 180 px from mid-forehead to chin, measured after shrinking the photo to 1280 px on its longest side as the photoreal engine does (Larry's 1080p webcam photos measure 200 to 216; the ~512 px in features.md was a guess before the engine existed), turned or tilted at most 25°, at most 12% of the face below the eyebrows covered (hair and beards allowed). The problems are saved in each photo's `.json`, returned as `problems` by the uploads API, and shown under each photo (Looks good, the messages, or Not checked). The models load when the server starts; photos uploaded before the checks are checked one at a time after the list shows (`POST /api/uploads/photos/{id}/check`), with Waiting to check / Checking face… (Checking photo… since R9) under each, and the screen says Loading… while the list loads. Needs the optional extra `.[faces]` (or `.[photoreal]`); without it photos show Not checked. A group photo whose other faces are small or turned may be found as one face; the size check usually rejects it.

### R9. Photo quality checks and best photo (Medium) · item 2 (part 2) · Done in [PR #21](https://github.com/larry94555/ImageSkinForLLM/pull/21)
- The remaining two checks: sharp, and evenly lit.
- Scores valid photos, picks the best, and lets the user choose another.
- **Can show:** a blurry or dark photo is rejected; the best photo is highlighted and can be changed.
- **Built:** `face_checks.light_and_sharpness` measures the face scaled to its size in the video (about 222 px tall): sharpness is the spread of the Laplacian over the face's average grey level (at least 0.05; sharp phone photos measure 0.1 to 0.23, a 720p webcam photo 0.1, a 1.5 px blur 0.02 to 0.04), brightness is the lightness 90% of the face below the eyebrows is under (at least 75 of 255, so dark skin in good light passes), at most 25% of the face pure white, and the darker side of the face at least 0.4 times as light as the other (window light to one side measures about 0.5 and passes). Limits were set on real phone and webcam photos and blurred, darkened, brightened and side-shaded copies. Photos that pass get a 0 to 100 score averaging sharpness, size, head angle, covering, brightness and evenness, each capped where more stops helping the video. The best scoring photo is outlined as **Used for the video**; **Use this photo** picks another (saved in `uploads/chosen-photo.json`, read and set through `GET`/`PUT /api/uploads/photos/chosen`); removing the chosen photo falls back to the best. `FACE_CHECKS` went to 3 so earlier photos are rechecked.

### R10. Sound checks (Medium) · item 3 (part 1) · Done in [PR #22](https://github.com/larry94555/ImageSkinForLLM/pull/22)
- Checks: long enough (threshold decided before this PR), not clipped, low background noise, each with a plain-language message.
- Combines the valid files into the voice sample used by R25.
- **Can show:** a short, clipped or noisy recording is flagged; valid recordings are combined into one voice sample.
- **Built:** `sound_checks.py` (numpy only, no model): at least 15 seconds of speech per recording (pauses not counted), at most 0.05% of the speech clipped, speech at least 20 dB above the background noise (set on the VoiceBank-DEMAND test set). The recordings that pass are joined into `uploads/voice-sample.wav`, shown with a player under the recordings; the voice needs at least 30 seconds of speech in all. Both lengths are constants at the top of `sound_checks.py`, so they are easy to change.

### R11. One-speaker check (Medium) · item 3 (part 2) · Done in [PR #23](https://github.com/larry94555/ImageSkinForLLM/pull/23)
- Detects a second voice in a recording (speaker diarization) and flags it with a plain-language message.
- **Can show:** a recording with two people talking is flagged; a single-speaker recording passes.
- **Built:** `speaker_checks.py`: a voice print for each 1.5 second stretch of speech from CAM++ (3D-Speaker, Apache 2.0, 28 MB, downloaded on first use) run by ONNX Runtime (MIT, now a core dependency); the prints are split into the two most different groups, and the recording is flagged when the groups sound like different people (alike below 0.55, set on LibriSpeech) and the smaller has at least 3 stretches. About a second per minute of sound.

### R12. Prepare job with progress (Medium) · item 5 · Done in [PR #24](https://github.com/larry94555/ImageSkinForLLM/pull/24)
- A background job runs prepare (prepare the voice, prepare the face) and reports progress; the browser shows a progress bar. With the photoreal engine the face step takes hours, so the job survives a restart and continues where it stopped.
- **Can show:** clicking Prepare shows progress moving through each step, with step timings in the logs.
- **Built:** `prepare_job.py`: Prepare on the Setup page starts a background job (`POST /api/prepare`; `GET /api/prepare` reports it) with five steps: load Kokoro, load the photoreal models, render the mouth shapes, render the idle loop, line up the mouth. The browser shows a progress bar weighted by how long each step takes, each step's count and time left, and asks every second while it runs. The state is saved in `prepare.json`; a job the server was stopped in the middle of is resumed at the next start, keeping the frames already rendered. The face step uses the photoreal engine only.

### R13. Sample video in the browser (Medium) · items 5, 6 · Done in [PR #26](https://github.com/larry94555/ImageSkinForLLM/pull/26)
- After prepare, the job renders the sample video and pre-renders "Goodbye." and "Welcome back."; the browser plays the sample.
- **Can show:** the sample video plays in the browser after prepare finishes.
- **Built:** a sixth prepare step renders "Goodbye.", "Welcome back." and the sample script (Kokoro voice, photoreal engine) into `<IMAGESKIN_HOME>/clips/`, with progress counted in words so the time left allows for the long sample. Each clip is written aside and then moved into place, so a restart keeps finished clips and redoes only a cut-short one; preparing again removes the old clips first. `GET /api/prepare/clips/{sample|goodbye|welcome-back}` serves a clip while the job is done for the uploads as they are now (404 otherwise), and the Setup page plays the sample under Prepare when it is ready. Larry found the mouth barely moved in the sample (the timing matched the voice, but the shapes opened only 45% of the way, R4a's setting); the vowel openings are now 1.7 times wider and the mouth opens 60% of the way to them (halfway between the old setting and the full wider one, which opened too far), with the lip spread and rounding still at 45%. A prepared photo re-renders only its 10 mouth shapes (about a minute) on the next Prepare.

## Milestone 3: The person's voice, reviewed

### R25a. Voice cloning test (Medium) · items 3, 4 · Done in [PR #30](https://github.com/larry94555/ImageSkinForLLM/pull/30)
- **Why first:** if the person's voice can't be cloned convincingly, the project fails, so this is proven before any chat work (Larry, 2026-10-07). Done so far: R2 and R10 turn the recordings into a checked voice sample, R11 checks there is one speaker, and R13 renders the sample video, but every clip so far uses a ready-made Kokoro voice; nothing has been made in the person's voice yet.
- An experiment in `experiments/voice/`, like the photoreal test in GitHub PR #8: take Larry's voice sample (the R10 `voice-sample.wav`) and make the sample script (item 6) and a few chat-like replies in his voice with at least two candidate tools that are free per use, run on the CPU and allow hosted use (licenses checked first). Candidates: voice conversion of Kokoro's output (for example OpenVoice v2's tone-color converter, Seed-VC or kNN-VC), which gives an American accent, and, for keeping the person's own accent, a cloning TTS if one meets the limits.
- Logs the time each tool adds per sentence on a 4-core CPU, since every reply will pay it.
- **Can show:** a page of clips side by side: a stretch of Larry's own recording, the Kokoro voice, and each tool's version of the same lines, plus the same lines rendered on the photoreal video.
- **Acceptance:** Larry listens and says whether a tool sounds like him, and picks one (the R25 decision). If none does, the work stops here and Larry decides what to relax (GPU, a paid service, longer recordings, a fine-tuned voice) before anything else is built.
- **Result (PR #30, 2026-10-08):** `experiments/voice/run_test.py` made the lines in three voices on the CPU: Kokoro, Kokoro converted with Chatterbox's voice converter, and Chatterbox Turbo cloning. Larry picked the clone: it sounds like him, the others do not. On a 4-core cloud CPU the clone took 1.5 to 2 seconds per second of speech (conversion added about 0.5), and a speaker-recognition model scored it closest to the recording. The first run downloads about 2.8 GB of models.

### R25. The person's voice by cloning (Medium) · items 3, 4 · Done in [PR #31](https://github.com/larry94555/ImageSkinForLLM/pull/31)
- Cloning adapter behind R3's `VoiceEngine` interface: Chatterbox Turbo (picked in R25a) speaks the text in the person's voice, learned from the R2 voice sample, on the CPU.
- Chatterbox reports no word or sound timings, which the mouth (R4b) and word highlighting (R18) need, so the adapter also finds them in its audio, for example by forced alignment of the known text; the tool is chosen when R25 starts (free, CPU, hosted use allowed).
- Commands: `imageskin say --voice-sample voice-sample.wav "Hello there"` and `imageskin sample --photo me.jpg --voice-sample voice-sample.wav`.
- **Can show:** the same sentence in the ready-made voice and in the person's voice, side by side, with the time cloning and alignment take per sentence in the logs, and the mouth in sync on the sample video.
- **Built:** `ChatterboxEngine` in `chatterbox_engine.py` speaks in a voice cloned from 10 seconds of the voice sample, and `--voice-sample` on `say` and `sample` uses it. The timings come from forced alignment in `alignment.py`: wav2vec2 (facebook/wav2vec2-base-960h, Apache 2.0, 360 MB) hears when each word's letters are said, each word runs on into the next (or up to 0.2 seconds into a pause), and Kokoro's pronunciation step splits each word into sounds that share its time equally. On Kokoro's own audio, where the true sound timings are known, the mouth shapes matched them 62% to 65% of the time (a copy of Kokoro's own shapes moved 40 ms later matches 68% to 73%). On a 4-core cloud CPU, cloning took 2.5 to 2.8 seconds per second of speech and alignment added 0.2 to 0.26 seconds per sentence. Chatterbox is installed from `clone-requirements.txt` with `--no-deps` under a constraint of the app's own packages, so nothing in the app changes (checked on a fresh Python 3.11 environment).

### R25b. The person's voice in prepare and the sample video (Medium) · items 5, 6 · Done in [PR #34](https://github.com/larry94555/ImageSkinForLLM/pull/34)
- The prepare job gets a voice step that prepares the person's voice from the voice sample with R25's tool, and the sample video, "Goodbye." and "Welcome back." are rendered in that voice instead of the Kokoro voice. Changing the recordings means preparing again.
- **Can show:** in the browser, after Prepare, the sample video plays in the person's own voice, lip-synced, with the voice step's time in the logs.
- **Built:** when Chatterbox is installed, Prepare's voice step loads it and learns the voice from the voice sample afresh (`ChatterboxEngine.learn_voice`), and the same engine speaks the three clips; without it, Prepare falls back to Kokoro and logs a warning at start. The job saves which voice spoke the clips, clone or Kokoro, with a fingerprint of the voice sample (`voice_id` in `prepare.json`), so adding or removing a recording, or installing Chatterbox after a Kokoro prepare, shows Prepare again, as choosing another photo does; a job saved before R25b needs preparing again too. A job resumed after a restart in another voice renders all its clips again rather than mixing voices.

### R26a. Accent test (Medium) · item 4 · Done in [PR #36](https://github.com/larry94555/ImageSkinForLLM/pull/36)
- **Why:** R25a's only Americanizing option (Kokoro's `am_michael` converted to the person's voice) did not sound like Larry, so dropping the accent question was proposed. Larry kept it and widened it (2026-10-09): he already sounds American, so the choice should be to change the accent, for example to British or to Russian-English.
- An experiment, `experiments/voice/accent_test.py`, on Larry's voice sample: the person's clone (their own accent), then each accent's base voice converted to the person's voice with Chatterbox's converter. American and British use Kokoro's ready-made voices of that accent, picked to suit the person: every one says a probe line and is converted to the person's voice, and the closest after conversion wins. An accent Kokoro doesn't have (Russian-English) uses a donor: the clone speaks in the voice of a recording of someone with that accent, then it is converted to the person's voice. A Bulgarian speaker from the EdAcc accent corpus (CC BY-SA 4.0) stands in until a Russian-English recording is found.
- **Can show:** a page of clips side by side, with how much each sounds like the person, the accent a classifier hears, and the time each takes.
- **Acceptance:** Larry listens and says which accents sound like him with the new accent; R26 offers those.
- **Result (PR #36, 2026-10-09):** on Larry's voice, British came through in his voice (an accent classifier heard British in all 3 replies; similarity to him 0.66, against 0.76 for his clone) at about real time (1.04 seconds per second of speech on a 4-core CPU, counting Kokoro speaking and the conversion; 0.75 on a less loaded run). Converted American scored 0.76, as close as the clone. Every Kokoro voice is converted before picking, since conversion reorders them: the American pick, `am_onyx`, was not among the three closest before conversion. The Slavic donor scored 0.65 but took 3.0 seconds per second of speech, and whether its accent survives needs Larry's ears (the classifier has no Slavic accent). Base voices picked for Larry: `am_onyx` and `bm_lewis`. Waiting on Larry's listening.

### R26. Accent choice in setup (Medium) · item 4 · Done in [PR #37](https://github.com/larry94555/ImageSkinForLLM/pull/37)
- Accent question in setup: keep the person's own accent (the clone), or change it to one that R26a showed works (American, British, and a donor accent once a recording is found), saved with the setup; changing it reruns the sample. With a changed accent, prepare picks the base voice as R26a does, and each line is spoken by the base voice and converted to the person's voice.
- **Can show:** choose British in setup and see the sample rerun in the person's voice with a British accent.
- **Built:** an Accent section in setup (own, American, British), saved in `accent.json`; Larry chose to build it before training a model of his voice (2026-10-09). With American or British, Prepare's voice step picks the base voice (`accent.py`), comparing voices with the one-speaker check's CAM++ model instead of R26a's ECAPA, so no new package is needed, and the clips are spoken by Kokoro and converted with Chatterbox's converter, sharing Turbo's loaded model. The accent is part of the job's `voice_id`, so changing it shows Prepare again, and when a sample was ready the server starts Prepare at once; the face is kept. The donor accent (Russian-English) is left out until a Russian-English recording is found. On Larry's voice sample (4-core cloud CPU), every base voice converted, the picks were `bm_daniel` and `af_river`, each just ahead of R26a's ECAPA picks (`bm_lewis`, `am_onyx`); picking took about 1 to 1.5 minutes, and the sample script about 0.9 to 1.1 seconds per second of speech, against 2.3 for his clone. Size grew from Simple to Medium: the conversion engine moved from the experiment into the app.

### R14. Review screen (Medium) · item 7 · Done in [PR #38](https://github.com/larry94555/ImageSkinForLLM/pull/38)
- Accept, Reject image (back to image upload), Reject voice (back to sound upload), and Change accent, which goes back to R26's choice and reruns the sample.
- Chat stays locked until a sample is accepted.
- **Can show:** the full setup flow from upload to an accepted sample, with both reject paths working.
- **Built:** four buttons under the sample video. Accept saves `review.json` with the sample it was given for (the photo, the voice and when the sample was made), so a sample made again, for any reason, needs accepting again; it then opens the new Chat page. Reject image, Reject voice and Change accent withdraw an acceptance and scroll back to the photos, the recordings or the accent, which show what to do there. Uploads are kept: the user removes the ones they don't want. The Chat page says it is locked until a sample is accepted (`GET /api/review`); the chat itself comes in R15.

## Milestone 4: Talking chat

### R15. Text chat with the LLM (Medium) · items 10, 15, 16 · Done in [PR #39](https://github.com/larry94555/ImageSkinForLLM/pull/39)
- OpenAI-compatible client pointed at local llama.cpp, with the short-reply system prompt.
- Conversation history sent with each prompt; the oldest turns are dropped when it would overflow the context window.
- Chat screen with a text box, unlocked after acceptance. Replies are text only for now.
- **Can show:** a text conversation with the local LLM that remembers earlier turns.
- **Built:** `chat.py` posts to `/chat/completions` at `llm_url` (default `http://127.0.0.1:8080/v1`, llama-server's) with the standard library, so no new package is needed, and the Chat page sends prompts through `POST /api/chat`, which is refused until a sample is accepted. The conversation is kept in the server's memory until it stops (saved history comes in Milestone 13). Changed from the plan after Larry's test (2026-10-09): instead of only dropping the oldest turns, the history (counted by llama-server's `/tokenize`, or estimated on the safe side at one token per byte of text, since review showed 3 characters a token can undercount code and hashes) is kept to at most half of the context window, which is read from llama-server's `/props` (`llm_context_tokens`, default 4096, when the server doesn't report it); when it passes that, the LLM summarizes the older turns right after the reply (Larry chose this over summarizing before the next prompt, after review pointed out that a 28-second summary on a 4-core CPU held up a reply), and the summary is sent in the system message with the latest two prompts and replies word for word; a prompt sent while a summary is being made waits for it. If summarizing fails, the oldest turns are dropped instead. A prompt too long for the other half is refused. If the LLM fails, the chat shows why and the prompt goes back in the box. Larry's test with Gemma 3 1B answered "Sarah" to "What is my name?" although the history was sent; Gemma 3 4B and Qwen2.5 0.5B and 1.5B answered "Larry" every time, so the test steps use Gemma 3 4B. In Larry's next test Gemma 3 4B once called his name a good one for a dog; replaying the same prompt gave right answers, so replies use temperature 0.3 instead of llama-server's 0.8, and the system prompt asks that every reply agree with what was said earlier, who said what and every name and fact (Larry, 2026-10-09). A first wording that asked the LLM to work out its answer, check it against the conversation and check once more, silently, made it say the checking aloud in Larry's test, so it states only what the reply must get right. Replayed five times each, "What is my name?" and "What is my dog's name?" were answered right every time, and replies read as plain conversation, with no checking aloud. With a 1024-token window to force it, Gemma 3 4B (4-core cloud CPU) summarized 8 turns in 28 seconds and still answered name, dog, city and job from the summary; replies took 5 to 12 seconds.

### R16. Text cleaning for speech (Simple) · item 11 · Done in [PR #42](https://github.com/larry94555/ImageSkinForLLM/pull/42)
- A function that removes what should not be voiced (Markdown, code, URLs, emoji). The planned map back to the displayed text for highlighting was left out once highlighting was dropped (see R18).
- **Can show:** unit tests on sample replies; a command prints the spoken version of a reply.
- **Built:** `speech_text.spoken_text()` leaves out code blocks (even unclosed ones, and a longer fence holding a shorter one), inline code (with any number of backticks), images, HTML tags, URLs (bare or in brackets; punctuation after a URL is kept), emoji (with skin tones, joiners and flags) and the Markdown markers for headings, quotes, bullets, list numbers, bold, italic, strikethrough, links and tables; underscores inside a word (snake_case) and a star between spaces (2 * 3) stay. A heading, list item, quote, table row or paragraph that ends without punctuation gets a full stop so the voice pauses; a single line break inside a paragraph is only a space. `imageskin spoken-text "reply"` or `--file reply.md` prints the spoken version.

### R16a. Saying what was left out (Simple) · item 11 · Done in [PR #43](https://github.com/larry94555/ImageSkinForLLM/pull/43)
- Added after Larry's review of R16 (2026-10-09): R16 drops URLs, code and emoji, which can leave a sentence that breaks off ("Hi Larry, see the guide or."). The spoken sentence must still make sense, so each left-out part is replaced by a short phrase that says what it is and points to the reply text panel (R18), for example "see the guide or the links in the text below".
- Proposed phrases (to be checked by ear with Larry when it is built): a bare URL says "the link in the text below", several in a row "the links in the text below"; a code block says "the code shown below"; inline code of a word or two is spoken as is, and longer inline code says "the code shown below"; an image says "the picture in the text below"; a table says "the table in the text below" instead of reading its cells. Emoji on their own (decoration) stay silent; an emoji that stands for a word ("I ❤️ it") is spoken by its short name. Link text is still spoken as is.
- **Can show:** `imageskin spoken-text` prints whole sentences for replies with links, code, pictures and tables.
- Built as proposed, with these choices to check by ear: a code block or table is a sentence of its own ("See the code shown below.", "See the table in the text below."); bare URLs separated only by commas, spaces or "and" are one "the links in the text below"; a URL in brackets or angle brackets also says "the link in the text below", while a Markdown link speaks its text; inline code of up to two words is spoken exactly as written, without its backticks (stars and underscores kept), unless it holds a URL; only ❤️ and ♥ between two words count as a word ("love"), every other emoji stays silent.

### R17. Spoken video replies (Medium) · items 11, 20 · Done in [PR #45](https://github.com/larry94555/ImageSkinForLLM/pull/45)
- Each cleaned reply is voiced in the person's voice (R25) and animated with R4c, then played in the chat.
- If voice or video fails, the reply text panel (R18, until then the reply text) opens with the reply and a short friendly note; if the LLM fails, a plain message says so.
- **Can show:** the person speaks each LLM reply in their voice. This is the app's core experience, though slower than the target until Milestone 5.
- **Built:** `reply_video.py` speaks each reply's cleaned text (R16, R16a) and renders it with the prepare job's voice and photoreal engines, one reply at a time; only the latest reply's video is kept, in `<data folder>/replies`. The reply text shows at once and the video follows from a second request (`POST /api/chat/video`), since the cloned voice takes 1.5 to 2 seconds per second of speech; it plays above the conversation. After a server restart the first reply makes the voice ready again with the chosen accent. If the voice or video fails, the reply stays as text with a short note and the reason.

### R18. Reply text panel (Medium) · item 11
- Changed from word highlighting after Larry's review of R16 (2026-10-09): reading along with the words being spoken is distracting, and a highlight kept in sync would complicate the screen and could slow replies. Words are not highlighted.
- The written replies, with URLs, code and emoji in full, go in a text panel that is closed by default. A button opens it; it scrolls through the conversation, has a search box that finds and steps through matches, and closes again.
- **Can show:** a reply is spoken with the panel closed; opening it shows the full text, a search finds a word in an earlier reply, and the panel closes.

### R19. Stop, volume and mute (Simple) · items 18, 21
- Stop button ends playback and cancels any rendering still in progress; volume and mute controls.
- **Can show:** a reply can be stopped mid-sentence; volume and mute work.

## Milestone 5: Real-time replies

### R20. Streaming LLM text and sentence splitting (Simple) · item 12 · Done in [PR #46](https://github.com/larry94555/ImageSkinForLLM/pull/46)
- The LLM client streams text; a splitter turns it into sentences as they complete, handling abbreviations, numbers and decimals.
- **Can show:** in the logs, sentences arriving one at a time while the LLM is still writing.
- **Built:** `LlmClient.stream()` asks with `"stream": true` and reads the server-sent events; `sentences.SentenceSplitter` hands back each sentence once the next one starts. A sentence ends at ".", "!", "?" or an ellipsis followed by a space, at a blank line, and at the end of a heading or list item. It doesn't end after an abbreviation (Dr., e.g.), an initial (J.), a list number (1.), a dotted abbreviation (U.S.) or a full stop followed by a lowercase word or a digit; code blocks stay whole. The log shows `Reply started` and `Reply sentence ready` with the time since the prompt. The summary is still asked for in one piece.

### R21. Sentence-by-sentence rendering on the server (Medium) · item 12 · Done in [PR #47](https://github.com/larry94555/ImageSkinForLLM/pull/47)
- Voices and animates each sentence while later ones are still generating, keeping them in order.
- Logs time from the LLM's first words to the first sentence being ready.
- **Can show:** in the logs, the first sentence's video is ready before the LLM has finished the reply, with the measured time.
- **Built:** each streamed sentence goes to `SentenceClips`, which cleans it for speech and renders its clip on a background thread, in order, while the LLM writes the next one; the engines render one clip at a time. R21 joined the clips into one video per reply with ffmpeg; R22 replaced that by playing the clips themselves. A reply that fails drops its clips. The log shows `Sentence clip ready` with `render_ms` and `since_first_words_ms`. Measured with Gemma 3 4B, Kokoro and the photoreal engine on a 4-core cloud CPU: the first sentence's clip was ready 6.5 s after the LLM's first words, while the LLM was still writing (its reply took 11.8 s); the LLM and the rendering share the CPU, so each slows the other.

### R22. Ordered playback in the browser (Medium) · item 12 · Done in [PR #48](https://github.com/larry94555/ImageSkinForLLM/pull/48)
- The browser receives sentence clips as they are ready and plays them in order.
- **Can show:** the video starts on the first sentence instead of waiting for the whole reply.
- **Built:** the chat page gives each prompt a reply id and asks `GET /api/chat/clips/{id}` every 0.3 s for the clips ready so far; it plays them one after another, starting before the reply text arrives. An LLM that doesn't stream still gets one video per reply. Measured with Gemma 3 4B, Kokoro and the photoreal engine on a 4-core cloud CPU: the first clip played 4.9 s after Send, while the reply text took 12.6 s. That needed the LLM and the engines to split the cores (llama-server `--threads 2`, `OMP_NUM_THREADS=2` for imageskin); with both using every core the first clip took 13.5 s, after the text. Later clips render a little slower than they play, so there are short pauses between sentences until Milestone 5. Review fixes: the reply says whether it was `streamed`, so a reply whose clips a newer prompt took (from another tab, say) is not spoken again as one video; a clip that fails leaves no file behind; clips that can't be removed (a browser still has one open, as on Windows) are logged and removed with the next reply; a clip failing before the reply is in is reported with it, not as an unhandled rejection.

### R22a. Quick clips: shared cores, warm start and the timing readout (Medium) · item 12 · Done in [PR #49](https://github.com/larry94555/ImageSkinForLLM/pull/49)
- Added after Larry's test of R22 (2026-10-10): the gap between a sentence's text arriving and the person speaking it must be 1 to 2 seconds, on a 4-core CPU with no graphics card, and the page must show how long it took. This is make or break for the project.
- Measured first, with Gemma 3 4B in llama-server and Kokoro on a 4-core CPU: with both using every core (their defaults), Kokoro took 14.5 s to speak a 3-second sentence while the LLM wrote, and the LLM fell from 8.4 to 0.3 tokens a second, because each one's threads spin waiting for cores the other holds. With 2 threads each: 1.3 s, and the LLM kept 4.7 tokens a second.
- While the LLM is busy (writing, or summarizing the conversation after a reply), the engines use half the cores (PyTorch and OpenCV threads, applied on the thread that runs them, as PyTorch keeps a count per thread), and all of them once it has finished; llama-server is started with `--threads` set to the other half, and `OMP_NUM_THREADS` is left unset (README).
- Startup also warms the LLM: it reads the system prompt once, so the first reply's words come about 2 s sooner (0.6 s instead of 2.5 s to the first token).
- The browser asks for clips with the count it has, and the server answers the moment there is a new one (or after 10 s), instead of every 0.3 s; the next clip loads in a second player while the current one plays, so the switch between sentences costs nothing.
- Under the video, the chat page shows how long each sentence took from its text arriving to being spoken, and the pause after the sentence before. The first sentence is in red when its wait passes 2 s, the others when their pause does. The log has `Engine threads set`, `LLM warmed up` and `since_sentence_ms` on `Sentence clip ready`.
- Measured with this PR on the 4-core CPU (Gemma 3 4B, Kokoro, photoreal), for a reply of three sentences of about 5.5 s of speech each: the first sentence was spoken 8.2 s after its text arrived (Kokoro 3.8 s and the video 4.3 s, each on 2 threads while the LLM wrote the rest), and the next two followed it with no pause. The first clip's wait is now the whole problem.
- **Can show:** the timing readout under the video, with the measured gaps.
- **Built:** as above. The first clip's wait comes from speaking and then rendering the whole first sentence after its text arrives, on half the cores; R22b cuts the first sentence at a clause so the first clip is short. With the person's own voice (Chatterbox, about 2.3 s of work per second of speech on 4 cores) the target is out of reach on the CPU alone; see the PR.

### R22b. Quick clips: the first clause first (Medium) · item 12 · Done in [PR #50](https://github.com/larry94555/ImageSkinForLLM/pull/50)
- The reply's first sentence is handed to the clips at its first clause, so the first clip is short and is spoken while the LLM is still writing the rest of the sentence: at a comma, semicolon, colon or dash after at least 3 words, before a joining word such as "and" or "because", or after 8 to 12 words when there is none (not on a word that leads into the next). The clause counts as a sentence in the log and the readout, whose rows are now "Clip N".
- Each clip's two steps, the voice and the video, are apart in the code (`ClipSteps`, `Sentence spoken` with `speak_ms` in the log), so the next PRs can play the video while it is still being made. They run one after the other: measured on the 4-core CPU, speaking a sentence while the one before it rendered made Kokoro about twice as slow (real-time factor 0.5 to 1.1) and the video too, with nothing gained.
- Measured with this PR (Gemma 3 4B in llama-server with 2 threads, Kokoro, photoreal, on the 4-core CPU): the first clause's text arrived 2.8 s after Send instead of 4.6 s for the whole sentence, and its clip was spoken 4.2 s after its text for a 6-word clause (Kokoro 1.1 s, the video 3.1 s) and 9.2 s for an 8-word one on a slower run (Kokoro 3.5 s, the video 5.5 s). While the LLM writes, the video step runs at a real-time factor of 1.4 to 1.6 against 0.45 once it has finished, and Kokoro at 0.5 to 1.0 against 0.45: the LLM's memory traffic slows both. So the next steps are R22c, cheaper frames (the pasting and blending of each frame is done in floating point over the whole face; about 3 times less memory traffic is possible), and R22d, playing each clip while it is still being written, so the video step leaves the wait.
- **Can show:** the first clip playing while the LLM is still writing the first sentence, and the readout.
- **Built:** as above. The video step's slowness beside the LLM measured here turned out to be the proof harness's WebM encoder, not the product's (see R22c).

### R22c. Quick clips: cheaper frames (Medium) · item 12 · Done in [PR #51](https://github.com/larry94555/ImageSkinForLLM/pull/51)
- Each frame of a clip is composited by OpenCV in 8-bit where it was blended in floating point over the whole face: the mouth and eyes are blended into the face with `cv2.blendLinear`, the head's movement is one `cv2.remap` whose maps are made by `cv2.addWeighted` and `cv2.scaleAdd` from grids made once, the face is pasted into the photo the same way, and the stills around the mouth and eyes are kept rather than copied for each frame. Measured on the 4-core CPU: about 4 ms a frame instead of 10 to 13, so the video step's real-time factor once the LLM has finished is 0.17 to 0.2 instead of 0.4 to 0.5; the frames differ from before by at most 2 of 255 in any pixel (rounding).
- Reply clips are rendered on the photo scaled down to 720 pixels on its longest side (`REPLY_SIDE` in `prepare_job.py`): the chat page shows them at most 640 pixels wide, and a frame of a 1280-pixel photo took 34 ms to paste and encode against 8 ms at 720 and 3.5 ms at 512. The sample video keeps the photo's size.
- Found on the way: the video step's slowness beside the LLM measured for R22b (real-time factor 1.4 to 1.6) was the proof harness's WebM encoder (libvpx) with its default of one thread per core, which took 80 ms a frame beside the LLM against 4 ms with two threads; the product's x264 encoder takes 4 ms a frame either way, and the compositing is not slowed by the LLM at all (6 ms a frame both ways, measured apart from the app). The harness now gives libvpx two threads. So the voice is the wait that is left: measured with this PR (same setup as R22b), the first clip was spoken 2.4 s after its text for a 6-word clause (Kokoro 1.6 s, the video 0.8 s) and 4.3 s for an 8-word one (Kokoro 3.3 s, the video 1.1 s); beside the LLM Kokoro runs at a real-time factor of 0.5 to 0.9 against 0.45 alone. Over the API with the product's own MP4 encoder (no browser), the first clip was ready 1.7 s after its text for the 6-word clause (Kokoro 1.1 s, the video 0.6 s) and 3.0 s for the 8-word one (Kokoro 2.0 s, the video 1.0 s). Next: R22d plays each clip while it is still being written, so the video leaves the wait; then R22e cuts the first clause shorter; the voice step itself is the floor (see the note on a faster voice for a 4-core CPU in the project files).
- **Can show:** the first clip about 2.5 s after its text for a short clause, with the readout saying so.
- **Built:** as above.

### R22d. Quick clips: play each clip while it is written (Medium) · item 12 · Done in [PR #52](https://github.com/larry94555/ImageSkinForLLM/pull/52)
- A reply clip is listed for the browser the moment its video step starts, not once its video is whole: the clip is written as a fragmented MP4, half a second of video at a time with no look-ahead in the encoder (`progressive` in `video.write_mp4`), and `GET /api/chat/clips/{id}/{n}` streams it as it grows (`SentenceClips.follow`), whole as a file once it is rendered. A plain `<video>` plays a clip served that way while the rest is written, so the video step leaves the wait before a clip; `SentenceClips.rendered` counts the whole clips, and a clip whose video fails is unlisted and its stream ended. The timing readout's "spoken after its text" now measures from the text to the clip starting to play; the log's `Sentence clip ready` has `playable_since_sentence_ms` (text to playable) next to `since_sentence_ms` (text to whole).
- Measured with this PR (same setup as R22c, the two prompts of R22b): over the API with the product's MP4 encoder, the first clip was playable 1.8 s after its text for the 8-word clause and 1.1 s for the 6-word one, against 2.6 s and 1.9 s to whole; the later clips 1.1 to 3.6 s after their text, all of it the voice step. In Chromium on the same 4 cores (the browser's decoding takes cores from the engines, and it buffers about half a second of a live stream before it plays), the first clip was spoken 3.9 s and 2.6 s after its text (R22c: 4.5 s and 2.4 s). Chromium starts a live stream the same 0.7 to 0.9 s in whether its fragments are 100, 250 or 500 ms long, so the fragment length stays at half a second.
- Found on the way: the voice step is now the whole wait before a clip, and beside the LLM it runs at a real-time factor of 0.5 to 0.9 (Kokoro, 2 threads), so clips cannot keep up with playing while the LLM writes: the pauses between later clips are the engines' throughput, not a wait that code can remove. What is left to reach 1 to 2 s for the first clip: a shorter first clause (R22e), and a faster voice (see the note on a faster voice for a 4-core CPU in the project files) or a graphics card for the rest.
- **Can show:** the clip starts playing before its video is finished; the readout counts from the text to the clip playing.
- **Built:** as above.

### R22e. Quick clips: a shorter first clause (Simple) · item 12 · Done in [PR #53](https://github.com/larry94555/ImageSkinForLLM/pull/53)
- The first clause is cut after 5 words instead of 8 when the first sentence has no clause boundary (`FIRST_CLAUSE_MAX` in `sentences.py`; the stretch for a word that leads into the next is now up to 8 words, `FIRST_CLAUSE_LIMIT`, instead of 12). When the fifth word leads into the next ("Martin Luther King Jr. was"), the clause ends on the last word before it that doesn't ("Martin Luther King Jr."), rather than running on. A cut by word count waits for the word after the next, so a sentence that ends on the next word ("The capital of France is Paris.") stays whole and no clip is left with one word.
- Measured apart from the app (Kokoro, 2 threads, idle): the voice step grows with the clause, 1.5 s for the 4-word "Martin Luther King Junior." (2.2 s of speech) against 2.2 s for the 8-word clause (3.55 s), so the first clip is playable about 0.7 s sooner alone and more beside the LLM. The cost: the rest of the sentence is a longer clip whose text arrives when the sentence ends, so the pause before clip 2 can grow by about as much; the engines' throughput beside the LLM sets the total.
- **Can show:** the first clip is a few words and starts sooner; the readout says so.
- **Built:** as above.

### R23. Idle video and smooth joins (Medium) · item 17
- Between replies the person blinks and moves slightly instead of freezing.
- Returns to the idle pose between sentence clips and crossfades the joins.
- **Can show:** the person looks alive while waiting, and multi-sentence replies play without visible jumps.

## Milestone 6: Spoken prompts

### R24. Push-to-talk microphone (Medium) · item 9
- Microphone button, push-to-talk, transcribed with browser speech recognition (whisper.cpp can be added later as a separate PR if needed); the transcribed prompt is shown as sent.
- **Can show:** hold the button, ask a question out loud, and the person answers on video.

## Milestone 7: Settings, exit and return

### R27. Settings page (Medium) · item 8 (part 1)
- A Settings link on every screen.
- The options that don't change the setup: play the sound files, view the image files, revalidate images, revalidate sound, run the video test again, clear conversation, return to the app.
- **Can show:** open Settings from any screen, replay the recordings, rerun the sample, clear the conversation and return.

### R28. Changing photos, voice or accent (Medium) · item 8 (part 2)
- Change image files, change sound files, and switch accent from Settings.
- Any of these requires revalidation and a newly accepted sample before chat resumes; "Goodbye" and "Welcome back" are re-rendered on each new acceptance.
- **Can show:** swap a photo from Settings, get sent through validation and a new sample, then return to the chat.

### R29. Exit and Start again (Simple) · items 13, 14
- Exit plays "Goodbye." and shows the exit screen; Start again plays "Welcome back." and keeps history.
- **Can show:** exit, then start again with the conversation still there.

### R30. Saved setup and history (Medium) · item 19
- The prepared face, voice and chat history are saved after acceptance and restored on a return visit, so setup is skipped.
- **Can show:** close the browser, come back, and go straight to the chat with history intact.

### R31. Delete my data (Simple) · item 23
- One action in Settings deletes uploads, the prepared face and voice, and history, then returns to the start of setup.
- **Can show:** delete everything and confirm in the logs and on disk that nothing remains.

## Milestone 8: Hosted, with cloud LLMs

### R32. Hosted deployment (Medium) · Deployment
- Container image and deployment guide for an HTTPS host, with secrets kept on the server.
- Access restricted to the one user by the mechanism decided before this PR.
- **Can show:** the full app running on a hosted HTTPS URL, with the microphone working.

### R33. Cloud LLMs with the user's key (Medium) · item 16 (later)
- OpenAI by config, and a small Claude adapter; the user enters an API key in Settings, stored on the server only.
- **Can show:** the same conversation answered by Claude or OpenAI instead of local llama.cpp.

## Milestone 9: Content and the wiki

### R34. PDF storage and content API (Medium) · item 24
- Server API to add, remove and replace PDFs, stored apart from the image and sound files, with the same safe-storage rules as R6 (size limit, type check, safe names).
- **Can show:** add, replace and remove a PDF with API calls, and the logs and folder showing each change.

### R35. Manage Content page (Medium) · item 24
- A "Manage Content" link opens a separate page listing the PDFs, with add, remove and replace.
- **Can show:** in the browser, upload two PDFs, replace one and remove the other.

### R36. Reading text, slides and tables (Medium) · item 25
- Extracts each PDF by kind: text as paragraphs, slides page by page, tables as rows and columns, with the page number kept for each piece. Runs when a PDF is added or replaced, as a job with progress like R12.
- **Can show:** one PDF of each kind, and the extracted text and tables it produced.

### R37. Building the wiki (Medium) · item 26
- The LLM turns the extracted content into wiki pages (one per topic, linking back to the PDF pages it came from). Adding, replacing or removing a PDF rebuilds only the pages that PDF affects.
- **Can show:** the wiki pages built from a sample PDF, and the logs showing how long the build took.

### R38. Wiki review and corrections (Medium) · item 26
- A wiki page in Manage Content to browse the pages, see the PDF pages each came from, and edit a page. A corrected page is marked so a rebuild doesn't overwrite it silently.
- **Can show:** correct a wiki page, replace its PDF, and see the correction kept and flagged for review.

## Milestone 10: Answers from the content

### R39. Looking up questions in the wiki and PDFs (Medium) · item 27
- Finds the wiki pages and PDF passages that match a question, using the method decided before this PR.
- **Can show:** a command that prints the passages found for a few sample questions, with the time the lookup took.

### R40. Answering from the content (Medium) · item 27
- The chat sends the passages found by R39 with the question, and the LLM answers from them; the answer is shown and spoken as in Milestones 4 and 5.
- **Can show:** ask a question about a sample PDF and hear the person answer it correctly.

### R41. Question scope setting (Simple) · item 28
- A setting for whether general prompts are allowed. When they aren't, an off-topic prompt gets a short, polite message instead of an answer.
- **Can show:** the same off-topic question answered with the setting on and politely declined with it off.

## Milestone 11: Choice of LLM

### R42. LLM setting with API keys (Medium) · item 29
- A setting that picks the LLM: local llama.cpp (the default), or Claude, OpenAI, Grok or OpenRouter with an API key, building on R33's Claude and OpenAI support. Keys stay on the server.
- **Can show:** the same question answered by the local model and by each provider with a key.

### R43. LLM by subscription (Medium) · item 29
- Use a Claude, OpenAI or Grok subscription instead of an API key, if the decision before this PR finds a supported way to do it.
- **Can show:** a question answered through a subscription.

## Milestone 12: Sign-on and accounts

### R44. Administrator sign-on (Medium) · item 30
- A sign-on page for the administrator. The picture, voice, content and settings pages, and their API calls, only work after sign-on.
- **Can show:** the setup and Manage Content pages refuse a visitor and open after the administrator signs on.

### R45. Question and answer screen for visitors (Simple) · item 31
- Without sign-on, the app shows only the question box and the person's spoken answers, with no links to setup, content or settings.
- **Can show:** an anonymous visitor asks a question and gets a spoken answer, with nothing else reachable.

### R46. Student sign-up and login (Medium) · item 32
- A sign-up page and the login link for students; a cookie keeps a student logged in on that browser. Students never see settings.
- **Can show:** sign up, close the browser, come back still logged in, and see no settings.

### R47. Require sign-up setting (Simple) · item 33
- A setting that disallows anonymous use; visitors are sent to sign up or log in before asking.
- **Can show:** with the setting on, an anonymous visitor is sent to the login page.

## Milestone 13: Interaction history

### R48. Saving every interaction (Simple) · item 34
- Every question and answer is saved with its date and time, and the student's account or "anonymous".
- **Can show:** ask questions anonymously and as a student, and see both saved in the logs and the store.

### R49. My history with soft clear (Medium) · item 35
- A signed-in student sees their own questions and answers and can clear them. Clearing hides them from the student but keeps them for the administrator.
- **Can show:** clear a student's history, see it gone for the student and still in the store.

### R50. User history page (Medium) · item 36
- An administrator page with every prompt and answer, including cleared ones, viewable by date and time, by student, or anonymous only.
- **Can show:** the administrator reviews a day's questions, then one student's, then the anonymous ones.

### R51. Save a conversation, and clear only what was saved (Medium) · items 8, 35, 37
- Save writes the conversation to a file the user downloads, each turn with an id and its time. Clear (in Settings and in a student's history) is offered only after a successful save, and clears only the turns that file holds; turns added since, or a save that failed, are not cleared.
- **Can show:** try to clear without saving and be told to save first; save, add one more question, clear, and see only that last question remain.

### R52. Load a saved conversation (Simple) · item 37
- Loads a saved file into the conversation history, adding only the turns not already there (matched by their ids), so loading the same file twice changes nothing.
- **Can show:** load a file twice and see its turns added once, after the existing history, with the count of turns added in the logs.

## Milestone 14: Topics and understanding

### R53. Tagging questions with topics (Medium) · items 38, 39
- Each new question keeps the wiki page ids the R39 lookup already found for it as its topics (none, one or several); there is no second classification. A one-off job runs the R39 lookup over the existing history, with progress like R12, and history loaded through R52 is tagged the same way. Tags are never rewritten when the wiki changes; a removed topic is shown as removed.
- **Can show:** ask a question on one topic, one spanning two topics and a general one, and see one, two and no topics in the store; then the backfill job's run time in the logs.

### R54. Rating the understanding a question shows (Medium) · item 40
- Each question from a signed-in student is rated strong, weak or unrated for each of its topics, as defined in item 40 and using the method decided before this PR, with the reason kept. Existing questions are rated by the same job as R53. On the user history page (R50) the administrator can correct a rating; the correction is stored with the rating and reason, and is never overwritten by a re-rating.
- **Can show:** a question with a clear misconception rated weak, a plain fact-seeking question left unrated, and a two-topic question rated differently for each topic; then correct one rating and see it kept after the job runs again.

## Milestone 15: Search

### R55. Search on the user history page (Medium) · items 42, 43
- Adds search to the R50 user history page rather than a second page: words to find in questions and answers, plus filters for topic and date range alongside R50's existing student and anonymous views. Covers cleared turns too.
- **Can show:** find a phrase across all students, then narrow it to one student and one topic, with the search time in the logs.

## Milestone 16: Statistics and summaries

### R56. Topic statistics page (Medium) · item 44
- An administrator page listing every topic with its question count and its counts of strong, weak and unrated questions (no single score), with topics nobody asked about listed separately.
- **Can show:** after a few questions on some topics, the page shows their counts and lists the untouched topics as not asked about.

### R57. Student summary page (Medium) · items 41, 45
- One page per student, worked out from the stored topic tags and ratings when it is opened (no separate profile is kept): each topic the student asked about, with counts of their strong, weak and unrated questions on it and the questions themselves. No score or overall judgment per topic; mixed evidence stays mixed.
- **Can show:** a student asks a strong and a weak question on the same topic and an unrated one on another; their summary shows the first topic with one strong and one weak question, the second with one unrated, and each question can be opened.

## Milestone 17: Heads-up before clearing

### R58. Heads-up before clearing history (Simple) · item 46
- The confirmation step inside R51's save-then-clear flow says "Clearing hides this conversation from your view. It remains available to the administrator." The clear runs only after the student confirms. No new way to clear is added.
- **Can show:** a student clicks clear, reads the notice, cancels and keeps their history, then confirms and sees it cleared from their view and still in the store.

## Milestone 18: Interests and personality

### R59. Working out interests and personality (Medium) · item 47
- For each signed-in student, a job reads their questions, the answers and their next message after each answer, and keeps a short profile: interests, and how they respond to answers, each with its one-line evidence and the questions it came from. Uses the method decided before this PR. Runs per the R59 decision and keeps the previous profile until a new one is ready; anonymous questions are not used. Students with too few questions get no profile.
- **Can show:** a student who keeps asking for real-world examples and follows up with "why" gets interests and a response style that cite those questions; a student with two questions gets none; the job's run time per student in the logs.

### R60. Profile on the student summary page, with corrections (Simple) · item 47
- Adds the profile from R59 to the R57 student summary page, under the topics, labelled as an impression drawn from their questions. Each line shows its evidence and links to its questions. The administrator can edit or remove a line; the change is kept and never overwritten when the profile is worked out again.
- **Can show:** open a student's summary, see their interests and response style with evidence, remove one line, rerun R59 and see it stay removed.

After R60, every item in features.md is covered by a PR. The PRs marked in [After the engine decision](#after-the-engine-decision) are redefined when each one starts, and the count may change by a PR or two.

## Optional, not counted

- **Second video engine** (the other of local or hosted), added behind R4's interface. Medium, 1 PR. features.md calls for it "later"; the app is complete without it.
- **Fine-tuned voice** from all the recordings, for a closer likeness. 2 or more Medium PRs.
- **whisper.cpp speech-to-text** on the server, if browser speech recognition isn't good enough. Medium, 1 PR.
