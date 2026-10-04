# ImageSkinForLLM: Roadmap

Every pull request needed to take ImageSkinForLLM from an empty repository to the full app in [features.md](features.md). Each PR is Simple or Medium under the pr-rules skill, and each one leaves something new that can be shown. The order gets a talking sample video working as early as possible (after the 4th PR), then builds the browser setup, the chat, and the rest around it.

PRs are numbered R1 to R33 so they don't get mixed up with GitHub PR numbers. Item numbers like "item 6" refer to features.md.

This is the plan as of today. The first video engine is not chosen yet, and that choice changes several PRs (see [After the engine decision](#after-the-engine-decision)). The PR list will be revised once R4's engine is picked.

## Milestones

| # | Milestone (what can be demonstrated) | PRs | Count | % of PRs | Done |
|---|---|---|---|---|---|
| 1 | **Sample video from the command line.** One photo plus voice recordings in, a video of the person saying the sample script out. | R1 to R4 | 4 | 12.1% | 3 of 4 |
| 2 | **Setup in the browser.** Upload, validate, prepare, watch the sample video, accept or reject. | R5 to R14 | 10 | 30.3% | 0 |
| 3 | **Talking chat.** Type a prompt; the person speaks the LLM's reply with words highlighted. | R15 to R19 | 5 | 15.2% | 0 |
| 4 | **Real-time replies.** The video starts on the first sentence and idles naturally between replies. | R20 to R23 | 4 | 12.1% | 0 |
| 5 | **Spoken prompts.** Push-to-talk microphone input. | R24 | 1 | 3.0% | 0 |
| 6 | **Americanized voice.** The person's voice with an American accent, chosen in setup. | R25 to R26 | 2 | 6.1% | 0 |
| 7 | **Settings, exit and return.** Every setting, Goodbye and Welcome back, saved setup, delete my data. | R27 to R31 | 5 | 15.2% | 0 |
| 8 | **Hosted, with cloud LLMs.** Runs on a hosted HTTPS site; Claude or OpenAI with the user's key. | R32 to R33 | 2 | 6.1% | 0 |
| | **Total** | | **33** | **100%** | **3 of 33** |

Sizes: 10 Simple, 23 Medium, no Large or Very large. Percentages are rounded to one decimal. A PR counts as done when its pull request is open with everything the pr-rules skill asks for; its entry below links the pull request.

## How sizes were judged

The pr-rules skill sizes a PR by review time: Simple is 10 minutes or less, Medium is 10 to 20. As a rough yardstick for this roadmap, Simple means one focused piece, under about 200 changed lines including tests; Medium means up to about 400 changed lines, or fewer if the logic is tricky (concurrency, media processing, a new model). Each PR below does one job: a server piece and the screen that uses it are separate PRs when together they would pass that line. If a PR still grows past Medium while it is being built, it is split before it is opened.

## Assumptions and decisions needed

- **Stack (assumed, not yet confirmed by Larry):** Python with FastAPI on the server, TypeScript in the browser, ffmpeg for media conversion. If the stack changes, the PR list stays the same; only the tooling in R1 and R5 changes.
- **Testing:** unit tests use fake voice and video engines so CI runs without a GPU or paid API. Each PR that touches a real engine proves it with a manual run and a short clip or log excerpt, per the pr-rules skill.
- **Every code PR** follows the pr-rules skill: build, lint and format pass; unit tests with about 80% line coverage on changed code; logging for errors, timing and meaningful operations; proof and manual test steps in the description.

Decisions to make before a PR starts. The roadmap does not decide these; features.md should be updated with each answer first.

| Before | Decision |
|---|---|
| R3 | The first voice (TTS) engine. It must clone from a short sample and return word timings (needed for highlighting in R18). **Picked in R3: Kokoro-82M** (free, Apache 2.0, runs on CPU on Windows and on a Linux server, reports word timings). It uses ready-made voices, so the person's own voice moves to a later voice-conversion step; see R3. Rejected: ElevenLabs (per-use cost), XTTS-v2 and F5-TTS (non-commercial model licenses), MeloTTS plus OpenVoice v2 (install pins packages too old for Python 3.11), Chatterbox (reported slower than real time on CPU). |
| R4 | The first video engine, local or hosted, and which tool. This is the biggest open decision in feature_evaluation.md. |
| R10 | The minimum length of speech for sound validation. features.md says only "long enough"; feature_evaluation.md suggests 30 seconds. |
| R21 | The latency target. 2 seconds is only proposed; the real number comes from what R4's engine can do. |
| R32 | How the hosted site restricts access to its one user. features.md says single-user and HTTPS but names no mechanism. The simplest option is one password checked at the HTTPS proxy, with no accounts. |

## After the engine decision

The PRs below are written for either kind of video engine, but these are the ones that change shape once R4's engine is chosen. Their definitions will be revised then.

| PR | Hosted streaming avatar (D-ID, Simli and similar) | Local rendering model |
|---|---|---|
| R4 | Adapter calls the service; the sample is rendered remotely. | Adapter runs the model on a GPU; prepare may take minutes. |
| R17 | Reply audio is sent to the avatar stream. | Each reply is rendered to a clip, then played. |
| R21, R22 | The service streams video; the browser plays one stream. | The server renders sentence clips; the browser queues them. |
| R23 | Idle motion likely comes from the service; small or dropped. | Needs a pre-rendered idle loop (for example LivePortrait plus MuseTalk-style lip sync). |

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
- Voice engine interface (`clone(sample) -> voice`, `speak(voice, text) -> audio + word timings`) and the first real adapter.
- Command: `imageskin say --voice sample.wav "Hello there"` writes a WAV and a word-timings JSON file.
- **Can show:** any sentence spoken in the person's cloned voice.
- **Built:** `VoiceEngine` protocol in `voice.py` and a Kokoro adapter (`pip install -e ".[voice]"`, CPU only, 24 kHz, word timings from the model). `imageskin say [--voice af_heart] "text"` writes `speech.wav` and `speech.json`. Changed from the plan: Kokoro cannot clone, so this PR speaks with a ready-made voice and has no `clone()` yet. Larry chose this on 2026-10-04 (no per-use cost, CPU only, a generic voice is fine for now). Cloning the person's voice is still to be planned as a CPU voice-conversion step, alongside R25 and R26.

### R4. Video engine and the sample video (Medium) · item 6
- Video engine interface (`prepare(photo) -> face`, `render(face, audio) -> video`) and the first real adapter.
- Command: `imageskin sample --photo me.jpg --voice sample.wav` renders the item 6 script to an MP4, logging how long each step takes.
- **Can show:** the ~30-second sample video of the person speaking the test script in their own voice. This is the first end-to-end test of the whole idea, and the timings it logs set the latency target.

## Milestone 2: Setup in the browser

### R5. Browser app and consent (Simple) · item 22
- TypeScript browser app served by FastAPI, with page routing and a shared layout.
- Consent checkbox before setup (item 22).
- **Can show:** the app opens in the browser and setup is blocked until consent is confirmed.

### R6. Upload API with safe storage (Medium) · item 1
- Server endpoints to upload, list, fetch and remove images (JPG, PNG, HEIC) and sound files (WAV, M4A, MP3).
- Hardening, built in from the start: file type checked from the file's content, not its name or extension; stored under generated names, never the uploaded name or path; size limits per file and in total, and a duration limit for audio; conversion (HEIC to JPG, audio to WAV via R2) runs with a timeout.
- **Can show:** with curl or the API docs page, a valid photo and recording are stored and converted; a renamed non-image file or an oversized file is rejected with a plain message, and the logs show why.

### R7. Upload screen (Medium) · item 1
- Browser screen for uploading photos and recordings, listing them, viewing images and playing sound files. At least one photo is needed; the guide asks for five so the app can pick the best.
- **Can show:** upload one or more photos and the recordings, then view and play them in the browser.

### R8. Face checks (Medium) · item 2 (part 1)
- Four checks from item 2, each with its fixed plain-language message on the upload screen: exactly one face, face large enough, facing the camera, nothing covering the face.
- **Can show:** a group photo, a small face or a side-on photo is rejected with a message a nontechnical person can act on.

### R9. Photo quality checks and best photo (Medium) · item 2 (part 2)
- The remaining two checks: sharp, and evenly lit.
- Scores valid photos, picks the best, and lets the user choose another.
- **Can show:** a blurry or dark photo is rejected; the best photo is highlighted and can be changed.

### R10. Sound checks (Medium) · item 3 (part 1)
- Checks: long enough (threshold decided before this PR), not clipped, low background noise, each with a plain-language message.
- Combines the valid files into the voice sample used by R3.
- **Can show:** a short, clipped or noisy recording is flagged; valid recordings are combined into one voice sample.

### R11. One-speaker check (Medium) · item 3 (part 2)
- Detects a second voice in a recording (speaker diarization) and flags it with a plain-language message.
- **Can show:** a recording with two people talking is flagged; a single-speaker recording passes.

### R12. Prepare job with progress (Medium) · item 5
- A background job runs prepare (clone the voice, prepare the face) and reports progress; the browser shows a progress bar.
- **Can show:** clicking Prepare shows progress moving through each step, with step timings in the logs.

### R13. Sample video in the browser (Medium) · items 5, 6
- After prepare, the job renders the sample video and pre-renders "Goodbye." and "Welcome back."; the browser plays the sample.
- **Can show:** the sample video plays in the browser after prepare finishes.

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

## Milestone 6: Americanized voice

### R25. Voice conversion (Medium) · item 4
- Voice-conversion adapter: an American base TTS voice converted to the person's timbre (for example OpenVoice or Seed-VC).
- Command: `imageskin sample --americanize` renders the sample with it.
- **Can show:** the same sample video in the original accent and Americanized, side by side.

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

After R33, every item in features.md is covered by a PR. The PRs marked in [After the engine decision](#after-the-engine-decision) will be redefined once R4's engine is chosen, and the count may change by a PR or two.

## Optional, not counted

- **Second video engine** (the other of local or hosted), added behind R4's interface. Medium, 1 PR. features.md calls for it "later"; the app is complete without it.
- **Fine-tuned voice** from all the recordings, for a closer likeness. 2 or more Medium PRs.
- **whisper.cpp speech-to-text** on the server, if browser speech recognition isn't good enough. Medium, 1 PR.
