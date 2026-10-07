# ImageSkinForLLM: Roadmap

Every pull request needed to take ImageSkinForLLM from an empty repository to the full app in [features.md](features.md). Each PR is Simple or Medium under the pr-rules skill, and each one leaves something new that can be shown. The order gets a talking sample video working as early as possible (after the 4th PR, photoreal after R4c), then builds the browser setup, the chat, and the rest around it.

PRs are numbered R1 to R33 so they don't get mixed up with GitHub PR numbers. R4a to R4c were added after R4 for the photoreal engine (R4a, mouth alignment, is described in GitHub PR #8), so the later numbers stay the same. Item numbers like "item 6" refer to features.md.

This is the plan as of today. R4 picked the first video engine, a CPU mouth animation of the photo. Larry found its mouth too puppet-like and preferred the photoreal LivePortrait test in GitHub PR #8 (2026-10-05), so R4b and R4c add a photoreal engine and the OpenCV engine stays as a quick fallback. The PRs it changes are listed in [After the engine decision](#after-the-engine-decision), and their definitions will be revised when each one starts.

## Milestones

| # | Milestone (what can be demonstrated) | PRs | Count | % of PRs | Done |
|---|---|---|---|---|---|
| 1 | **Sample video from the command line.** One photo in, a photoreal video of the person saying the sample script out, in a ready-made Kokoro voice (the person's own voice comes in R25). | R1 to R4c | 7 | 19.4% | 7 of 7 |
| 2 | **Setup in the browser.** Upload, validate, prepare, watch the sample video, accept or reject. | R5 to R14 | 10 | 27.8% | 9 of 10 |
| 3 | **Talking chat.** Type a prompt; the person speaks the LLM's reply with words highlighted. | R15 to R19 | 5 | 13.9% | 0 |
| 4 | **Real-time replies.** The video starts on the first sentence and idles naturally between replies. | R20 to R23 | 4 | 11.1% | 0 |
| 5 | **Spoken prompts.** Push-to-talk microphone input. | R24 | 1 | 2.8% | 0 |
| 6 | **The person's voice.** Replies in the person's own voice (by voice conversion, with an American accent), and the accent choice in setup. | R25 to R26 | 2 | 5.6% | 0 |
| 7 | **Settings, exit and return.** Every setting, Goodbye and Welcome back, saved setup, delete my data. | R27 to R31 | 5 | 13.9% | 0 |
| 8 | **Hosted, with cloud LLMs.** Runs on a hosted HTTPS site; Claude or OpenAI with the user's key. | R32 to R33 | 2 | 5.6% | 0 |
| | **Total** | | **36** | **100%** | **14 of 36** |

Sizes: 10 Simple, 26 Medium, no Large or Very large. Percentages are rounded to one decimal. A PR counts as done when its pull request is open with everything the pr-rules skill asks for; its entry below links the pull request.

## How sizes were judged

The pr-rules skill sizes a PR by review time: Simple is 10 minutes or less, Medium is 10 to 20. As a rough yardstick for this roadmap, Simple means one focused piece, under about 200 changed lines including tests; Medium means up to about 400 changed lines, or fewer if the logic is tricky (concurrency, media processing, a new model). Each PR below does one job: a server piece and the screen that uses it are separate PRs when together they would pass that line. If a PR still grows past Medium while it is being built, it is split before it is opened.

## Assumptions and decisions needed

- **Stack:** Python with FastAPI on the server, TypeScript with Preact in the browser (built with Vite; Larry chose a React-style library, 2026-10-06, and Preact for its small size), ffmpeg for media conversion. If the stack changes, the PR list stays the same; only the tooling in R1 and R5 changes.
- **Testing:** unit tests use fake voice and video engines so CI runs without a GPU or paid API. Each PR that touches a real engine proves it with a manual run and a short clip or log excerpt, per the pr-rules skill.
- **Every code PR** follows the pr-rules skill: build, lint and format pass; unit tests with about 80% line coverage on changed code; logging for errors, timing and meaningful operations; proof and manual test steps in the description.

Decisions to make before a PR starts. The roadmap does not decide these; features.md should be updated with each answer first.

| Before | Decision |
|---|---|
| R3 | The first voice (TTS) engine. It must return word timings (needed for highlighting in R18), be free per use and run on CPU (Larry, 2026-10-04). **Picked in R3: Kokoro-82M** (Apache 2.0, runs on CPU on Windows and on a Linux server, reports word timings). It uses ready-made voices and cannot clone, so the person's own voice moves to R25. Rejected: ElevenLabs (per-use cost), XTTS-v2 and F5-TTS (non-commercial model licenses), MeloTTS plus OpenVoice v2 (install pins packages too old for Python 3.11), Chatterbox (reported slower than real time on CPU). |
| R4 | The first video engine, local or hosted, and which tool. It must be free per use, run on CPU, allow hosted use and work on Python 3.11 and 3.12 (Larry, 2026-10-04). **Picked in R4: our own mouth animation with OpenCV** (Apache 2.0): OpenCV's bundled face detector finds the face, and the mouth opens with the loudness of the speech. No model download, renders faster than real time on a CPU; it looks like a puppet mouth rather than a photoreal talking head. Rejected: Wav2Lip (non-commercial weights), SadTalker (non-commercial Basel Face Model, pins Python 3.8, minutes per clip on CPU), MuseTalk (needs a base video, no Python 3.12, GPU-bound), LivePortrait (video-driven, non-commercial InsightFace models), diffusion models such as Hallo and LatentSync (GPU only), hosted avatars (per-use cost). **Changed after R4:** LivePortrait turned out usable (its weights are MIT, and MediaPipe replaces the non-commercial InsightFace), and pre-rendering its frames once makes each reply fast on the CPU (GitHub PR #8). Larry chose it for photoreal quality (2026-10-05); R4b and R4c build it. |
| R10 | The minimum length of speech for sound validation. features.md says only "long enough"; feature_evaluation.md suggests 30 seconds. **Picked in R10:** at least 30 seconds of speech in the voice sample, and at least 15 in each recording (pauses not counted); constants in `sound_checks.py`. |
| R21 | The latency target. Larry: a reply video that takes more than a few seconds to generate is unacceptable (2026-10-04). The photoreal test built a 2.5-second reply clip in 0.5 to 1.5 seconds on a 4-core CPU, so per-sentence clips should fit. Measured in R4c with the real voice on a 4-core CPU: the video for 6.9 seconds of speech renders in 2.2 seconds (about a third of real time), after Kokoro's 2 seconds to speak it. |
| R25 | The CPU voice-conversion tool that turns Kokoro's output into the person's voice (for example OpenVoice's tone-color converter or Seed-VC). It must be free per use, run on CPU and allow hosted use. Keeping the person's original accent (item 4) would need a different, cloning TTS and is left open. |
| R32 | How the hosted site restricts access to its one user. features.md says single-user and HTTPS but names no mechanism. The simplest option is one password checked at the HTTPS proxy, with no accounts. |

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
- **Built:** a sixth prepare step renders "Goodbye.", "Welcome back." and the sample script (Kokoro voice, photoreal engine) into `<IMAGESKIN_HOME>/clips/`, with progress counted in words so the time left allows for the long sample. Each clip is written aside and then moved into place, so a restart keeps finished clips and redoes only a cut-short one; preparing again removes the old clips first. `GET /api/prepare/clips/{sample|goodbye|welcome-back}` serves a clip while the job is done for the uploads as they are now (404 otherwise), and the Setup page plays the sample under Prepare when it is ready. Larry found the mouth barely moved in the sample (the timing matched the voice, but the shapes opened only 45% of the way, R4a's setting); the vowel openings are now 1.7 times wider and applied in full, with the lip spread and rounding still at 45%. A prepared photo re-renders only its 10 mouth shapes (about a minute) on the next Prepare.

### R14. Review screen (Simple) · item 7
- Accept, Reject image (back to image upload), Reject voice (back to sound upload). Change accent is added in R26.
- Chat stays locked until a sample is accepted.
- **Can show:** the full setup flow from upload to an accepted sample, with both reject paths working.

## Milestone 3: Talking chat

### R15. Text chat with the LLM (Medium) · items 10, 15, 16
- OpenAI-compatible client pointed at local llama.cpp, with the short-reply system prompt.
- Conversation history sent with each prompt; the oldest turns are dropped when it would overflow the context window.
- Chat screen with a text box, unlocked after acceptance. Replies are text only for now.
- **Can show:** a text conversation with the local LLM that remembers earlier turns.

### R16. Text cleaning for speech (Simple) · item 11
- A function that removes what should not be voiced (Markdown, code, URLs, emoji) and keeps a map back to the displayed text for highlighting.
- **Can show:** unit tests on sample replies; a command prints the spoken version of a reply.

### R17. Spoken video replies (Medium) · items 11, 20
- Each cleaned reply is voiced with R3 and animated with R4, then played in the chat.
- If voice or video fails, the text still shows with a short friendly note; if the LLM fails, a plain message says so.
- **Can show:** the person speaks each LLM reply in their voice. This is the app's core experience, though slower than the target until Milestone 4.

### R18. Word highlighting (Medium) · item 11
- Highlights each word as it is spoken, using the word timings from R3 and the map from R16.
- **Can show:** words light up in sync with the lips.

### R19. Stop, volume and mute (Simple) · items 18, 21
- Stop button ends playback and cancels any rendering still in progress; volume and mute controls.
- **Can show:** a reply can be stopped mid-sentence; volume and mute work.

## Milestone 4: Real-time replies

### R20. Streaming LLM text and sentence splitting (Simple) · item 12
- The LLM client streams text; a splitter turns it into sentences as they complete, handling abbreviations, numbers and decimals.
- **Can show:** in the logs, sentences arriving one at a time while the LLM is still writing.

### R21. Sentence-by-sentence rendering on the server (Medium) · item 12
- Voices and animates each sentence while later ones are still generating, keeping them in order.
- Logs time from the LLM's first words to the first sentence being ready.
- **Can show:** in the logs, the first sentence's video is ready before the LLM has finished the reply, with the measured time.

### R22. Ordered playback in the browser (Medium) · item 12
- The browser receives sentence clips as they are ready and plays them in order, with highlighting following along.
- **Can show:** the video starts on the first sentence instead of waiting for the whole reply.

### R23. Idle video and smooth joins (Medium) · item 17
- Between replies the person blinks and moves slightly instead of freezing.
- Returns to the idle pose between sentence clips and crossfades the joins.
- **Can show:** the person looks alive while waiting, and multi-sentence replies play without visible jumps.

## Milestone 5: Spoken prompts

### R24. Push-to-talk microphone (Medium) · item 9
- Microphone button, push-to-talk, transcribed with browser speech recognition (whisper.cpp can be added later as a separate PR if needed); the transcribed prompt is shown as sent.
- **Can show:** hold the button, ask a question out loud, and the person answers on video.

## Milestone 6: The person's voice

### R25. The person's voice by voice conversion (Medium) · items 3, 4
- Voice-conversion adapter on the CPU: R3's American Kokoro voice is converted to the person's timbre, learned from the R2 voice sample (tool decided before this PR, for example OpenVoice's tone-color converter or Seed-VC). Word timings from R3 still apply because conversion keeps the timing.
- Commands: `imageskin say --voice-sample voice-sample.wav "Hello there"` and `imageskin sample --photo me.jpg --voice-sample voice-sample.wav`.
- **Can show:** the same sentence in the ready-made voice and in the person's voice, side by side, with the time conversion adds per sentence in the logs.

### R26. Accent choice in setup and review (Simple) · items 4, 7 (Change accent)
- Accent question in setup, and Change accent on the review screen, which reruns the sample.
- **Can show:** choose Americanize in setup, then switch back with Change accent and see the sample rerun.

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

After R33, every item in features.md is covered by a PR. The PRs marked in [After the engine decision](#after-the-engine-decision) are redefined when each one starts, and the count may change by a PR or two.

## Optional, not counted

- **Second video engine** (the other of local or hosted), added behind R4's interface. Medium, 1 PR. features.md calls for it "later"; the app is complete without it.
- **Fine-tuned voice** from all the recordings, for a closer likeness. 2 or more Medium PRs.
- **whisper.cpp speech-to-text** on the server, if browser speech recognition isn't good enough. Medium, 1 PR.
