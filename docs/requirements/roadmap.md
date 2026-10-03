# ImageSkinForLLM: Roadmap

Every pull request needed to take ImageSkinForLLM from an empty repository to the full app in [features.md](features.md). Each PR is Simple or Medium under the pr-rules skill, and each one leaves something new that can be shown. The order gets a talking sample video working as early as possible (after the 3rd PR), then builds the browser setup, the chat, and the rest around it.

PRs are numbered R1 to R25 so they don't get mixed up with GitHub PR numbers. Item numbers like "item 6" refer to features.md.

This is the plan as of today. The first video engine is not chosen yet, and that choice changes several PRs (see [After the engine decision](#after-the-engine-decision)). The PR list will be revised once R3's engine is picked.

## Milestones

| # | Milestone (what can be demonstrated) | PRs | Count | % of PRs |
|---|---|---|---|---|
| 1 | **Sample video from the command line.** One photo plus voice recordings in, a video of the person saying the sample script out. | R1 to R3 | 3 | 12% |
| 2 | **Setup in the browser.** Upload, validate, prepare, watch the sample video, accept or reject. | R4 to R10 | 7 | 28% |
| 3 | **Talking chat.** Type a prompt; the person speaks the LLM's reply with words highlighted. | R11 to R13 | 3 | 12% |
| 4 | **Real-time replies.** The video starts on the first sentence and idles naturally between replies. | R14 to R16 | 3 | 12% |
| 5 | **Spoken prompts.** Push-to-talk microphone input. | R17 | 1 | 4% |
| 6 | **Americanized voice.** The person's voice with an American accent, chosen in setup. | R18 | 1 | 4% |
| 7 | **Settings, exit and return.** Every setting, Goodbye and Welcome back, saved setup, delete my data. | R19 to R23 | 5 | 20% |
| 8 | **Hosted, with cloud LLMs.** Runs on a hosted HTTPS site; Claude or OpenAI with the user's key. | R24 to R25 | 2 | 8% |
| | **Total** | | **25** | **100%** |

Sizes: 6 Simple, 19 Medium, no Large or Very large.

## Assumptions and decisions needed

- **Stack (assumed, not yet confirmed by Larry):** Python with FastAPI on the server, TypeScript in the browser, ffmpeg for media conversion. If the stack changes, the PR list stays the same; only the tooling in R1 and R4 changes.
- **Testing:** unit tests use fake voice and video engines so CI runs without a GPU or paid API. Each PR that touches a real engine proves it with a manual run and a short clip or log excerpt, per the pr-rules skill.
- **Every code PR** follows the pr-rules skill: build, lint and format pass; unit tests with about 80% line coverage on changed code; logging for errors, timing and meaningful operations; proof and manual test steps in the description.

Decisions to make before a PR starts. The roadmap does not decide these; features.md should be updated with each answer first.

| Before | Decision |
|---|---|
| R2 | The first voice (TTS) engine. It must clone from a short sample and return word timings (needed for highlighting in R13). |
| R3 | The first video engine, local or hosted, and which tool. This is the biggest open decision in feature_evaluation.md. |
| R8 | The minimum length of speech for sound validation. features.md says only "long enough"; feature_evaluation.md suggests 30 seconds. |
| R14 | The latency target. 2 seconds is only proposed; the real number comes from what R3's engine can do. |
| R24 | How the hosted site restricts access to its one user. features.md says single-user and HTTPS but names no mechanism. The simplest option is one password checked at the HTTPS proxy, with no accounts. |

## After the engine decision

The PRs below are written for either kind of video engine, but these are the ones that change shape once R3's engine is chosen. Their definitions will be revised then.

| PR | Hosted streaming avatar (D-ID, Simli and similar) | Local rendering model |
|---|---|---|
| R3 | Adapter calls the service; the sample is rendered remotely. | Adapter runs the model on a GPU; prepare may take minutes. |
| R12 | Reply audio is sent to the avatar stream. | Each reply is rendered to a clip, then played. |
| R14, R15 | The service streams video; the browser plays one stream. | The server renders sentence clips; the browser queues them. |
| R16 | Idle motion likely comes from the service; small or dropped. | Needs a pre-rendered idle loop (for example LivePortrait plus MuseTalk-style lip sync). |

## Milestone 1: Sample video from the command line

### R1. Project skeleton (Simple)
- Python package with FastAPI app, a `/health` endpoint, and an `imageskin` command-line entry point.
- Structured logging setup, config file loading, lint, format, type check and unit tests wired into CI.
- **Can show:** `imageskin --version` runs, `/health` returns OK, CI is green.

### R2. Voice engine and cloned speech (Medium) · items 1, 3 (partial), 11 (timings)
- Voice engine interface (`clone(samples) -> voice`, `speak(voice, text) -> audio + word timings`) and the first real adapter.
- Converts M4A and MP3 to WAV with ffmpeg and joins several recordings into one voice sample.
- Command: `imageskin say --voice rec1.m4a rec2.m4a rec3.m4a "Hello there"` writes a WAV and a word-timings JSON file.
- **Can show:** any sentence spoken in the person's cloned voice.

### R3. Video engine and the sample video (Medium) · item 6
- Video engine interface (`prepare(photo) -> face`, `render(face, audio) -> video`) and the first real adapter.
- Command: `imageskin sample --photo me.jpg --voice rec1.m4a rec2.m4a rec3.m4a` renders the item 6 script to an MP4, logging how long each step takes.
- **Can show:** the ~30-second sample video of the person speaking the test script in their own voice. This is the first end-to-end test of the whole idea, and the timings it logs set the latency target.

## Milestone 2: Setup in the browser

### R4. Browser app and consent (Simple) · item 22
- TypeScript browser app served by FastAPI, with page routing and a shared layout.
- Consent checkbox before setup (item 22).
- **Can show:** the app opens in the browser and setup is blocked until consent is confirmed.

### R5. Safe uploads and media playback (Medium) · item 1
- Upload images (JPG, PNG, HEIC) and sound files (WAV, M4A, MP3). At least one photo is needed; the guide asks for five so the app can pick the best.
- Hardening, built in from the start: file type checked from the file's content, not its name or extension; stored under generated names, never the uploaded name or path; size limits per file and in total, and a duration limit for audio; conversion runs with a timeout.
- Converts HEIC to JPG and audio to WAV. Lists uploaded files; images can be viewed and sound files played.
- **Can show:** uploading one or more photos and the recordings, then viewing and playing them; a renamed non-image file or an oversized file is rejected with a plain message.

### R6. Face checks (Medium) · item 2 (part 1)
- Four checks from item 2, each with its fixed plain-language message: exactly one face, face large enough, facing the camera, nothing covering the face.
- **Can show:** a group photo, a small face or a side-on photo is rejected with a message a nontechnical person can act on.

### R7. Photo quality checks and best photo (Medium) · item 2 (part 2)
- The remaining two checks: sharp, and evenly lit.
- Scores valid photos, picks the best, and lets the user choose another.
- **Can show:** a blurry or dark photo is rejected; the best photo is highlighted and can be changed.

### R8. Sound validation (Medium) · item 3
- Checks: long enough (threshold decided before this PR), not clipped, low background noise, one speaker, each with a plain-language message.
- Combines the valid files into the voice sample R2 uses.
- **Can show:** a clipped or noisy recording is flagged; valid recordings are combined into one voice sample.

### R9. Prepare and sample video in the browser (Medium) · items 5, 6
- A background job runs prepare (clone voice, prepare face) and renders the sample video, with a progress bar in the browser.
- Also pre-renders "Goodbye." and "Welcome back."
- **Can show:** clicking Prepare shows progress, then the sample video plays in the browser.

### R10. Review screen (Simple) · item 7
- Accept, Reject image (back to image upload), Reject voice (back to sound upload). Change accent is added in R18.
- Chat stays locked until a sample is accepted.
- **Can show:** the full setup flow from upload to an accepted sample, with both reject paths working.

## Milestone 3: Talking chat

### R11. Text chat with the LLM (Medium) · items 10, 15, 16
- OpenAI-compatible client pointed at local llama.cpp, with the short-reply system prompt.
- Conversation history sent with each prompt; the oldest turns are dropped when it would overflow the context window.
- Chat screen with a text box, unlocked after acceptance. Replies are text only for now.
- **Can show:** a text conversation with the local LLM that remembers earlier turns.

### R12. Spoken video replies (Medium) · items 11, 20
- Each reply is cleaned for speech (Markdown, code, URLs and emoji are shown but not voiced), voiced with R2 and animated with R3, then played in the chat.
- If voice or video fails, the text still shows with a short friendly note; if the LLM fails, a plain message says so.
- **Can show:** the person speaks each LLM reply in their voice. This is the app's core experience, though slower than the target until Milestone 4.

### R13. Word highlighting and playback controls (Medium) · items 11, 18, 21
- Highlights each word as it is spoken, using the word timings from R2.
- Stop button, volume and mute.
- **Can show:** words light up in sync with the lips; a reply can be stopped mid-sentence; volume and mute work.

## Milestone 4: Real-time replies

### R14. Sentence-by-sentence pipeline on the server (Medium) · item 12
- Streams LLM text, splits it into sentences, and voices and animates each sentence while later ones are still generating.
- Logs time from the LLM's first words to the first sentence being ready.
- **Can show:** in the logs, the first sentence's video is ready before the LLM has finished the reply, with the measured time.

### R15. Ordered playback in the browser (Medium) · item 12
- The browser receives sentence clips as they are ready and plays them in order, with highlighting following along.
- **Can show:** the video starts on the first sentence instead of waiting for the whole reply.

### R16. Idle video and smooth joins (Medium) · item 17
- Between replies the person blinks and moves slightly instead of freezing.
- Returns to the idle pose between sentence clips and crossfades the joins.
- **Can show:** the person looks alive while waiting, and multi-sentence replies play without visible jumps.

## Milestone 5: Spoken prompts

### R17. Push-to-talk microphone (Medium) · item 9
- Microphone button, push-to-talk, transcribed with browser speech recognition or whisper.cpp; the transcribed prompt is shown as sent.
- **Can show:** hold the button, ask a question out loud, and the person answers on video.

## Milestone 6: Americanized voice

### R18. Accent choice (Medium) · items 4, 7 (Change accent)
- Voice-conversion adapter: an American base TTS voice converted to the person's timbre (for example OpenVoice or Seed-VC).
- Accent question in setup, and Change accent on the review screen, which reruns the sample.
- **Can show:** the same sample video in the original accent and Americanized, side by side.

## Milestone 7: Settings, exit and return

### R19. Settings page (Medium) · item 8 (part 1)
- A Settings link on every screen.
- The options that don't change the setup: play the sound files, view the image files, revalidate images, revalidate sound, run the video test again, clear conversation, return to the app.
- **Can show:** open Settings from any screen, replay the recordings, rerun the sample, clear the conversation and return.

### R20. Changing photos, voice or accent (Medium) · item 8 (part 2)
- Change image files, change sound files, and switch accent from Settings.
- Any of these requires revalidation and a newly accepted sample before chat resumes; "Goodbye" and "Welcome back" are re-rendered on each new acceptance.
- **Can show:** swap a photo from Settings, get sent through validation and a new sample, then return to the chat.

### R21. Exit and Start again (Simple) · items 13, 14
- Exit plays "Goodbye." and shows the exit screen; Start again plays "Welcome back." and keeps history.
- **Can show:** exit, then start again with the conversation still there.

### R22. Saved setup and history (Medium) · item 19
- The prepared face, voice and chat history are saved after acceptance and restored on a return visit, so setup is skipped.
- **Can show:** close the browser, come back, and go straight to the chat with history intact.

### R23. Delete my data (Simple) · item 23
- One action in Settings deletes uploads, the prepared face and voice, and history, then returns to the start of setup.
- **Can show:** delete everything and confirm in the logs and on disk that nothing remains.

## Milestone 8: Hosted, with cloud LLMs

### R24. Hosted deployment (Medium) · Deployment
- Container image and deployment guide for an HTTPS host, with secrets kept on the server.
- Access restricted to the one user by the mechanism decided before this PR.
- **Can show:** the full app running on a hosted HTTPS URL, with the microphone working.

### R25. Cloud LLMs with the user's key (Simple) · item 16 (later)
- OpenAI by config, and a small Claude adapter; the user enters an API key in Settings, stored on the server only.
- **Can show:** the same conversation answered by Claude or OpenAI instead of local llama.cpp.

After R25, every item in features.md is covered by a PR. The PRs marked in [After the engine decision](#after-the-engine-decision) will be redefined once R3's engine is chosen, and the count may change by a PR or two.

## Optional, not counted

- **Second video engine** (the other of local or hosted), added behind R3's interface. Medium, 1 PR. features.md calls for it "later"; the app is complete without it.
- **Fine-tuned voice** from all the recordings, for a closer likeness. Medium to Large, 1 to 2 PRs.
