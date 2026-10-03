# ImageSkinForLLM: Roadmap

Every pull request needed to take ImageSkinForLLM from an empty repository to the full app in [features.md](features.md). Each PR is Simple or Medium under the pr-rules skill, and each one leaves something new that can be shown. The order gets a talking sample video working as early as possible (after the 3rd PR), then builds the browser setup, the chat, and the rest around it.

PRs are numbered R1 to R19 so they don't get mixed up with GitHub PR numbers. Item numbers like "item 6" refer to features.md.

## Milestones

| # | Milestone (what can be demonstrated) | PRs | Count | % of PRs |
|---|---|---|---|---|
| 1 | **Sample video from the command line.** One photo plus voice recordings in, a video of the person saying the sample script out. | R1 to R3 | 3 | 15.8% |
| 2 | **Setup in the browser.** Upload, validate, prepare, watch the sample video, accept or reject. | R4 to R8 | 5 | 26.3% |
| 3 | **Talking chat.** Type a prompt; the person speaks the LLM's reply with words highlighted. | R9 to R11 | 3 | 15.8% |
| 4 | **Real-time replies.** The video starts on the first sentence and idles naturally between replies. | R12 to R13 | 2 | 10.5% |
| 5 | **Spoken prompts.** Push-to-talk microphone input. | R14 | 1 | 5.3% |
| 6 | **Americanized voice.** The person's voice with an American accent, chosen in setup. | R15 | 1 | 5.3% |
| 7 | **Settings, exit and return.** Every setting, Goodbye and Welcome back, saved setup, delete my data. | R16 to R17 | 2 | 10.5% |
| 8 | **Hosted, with cloud LLMs.** Runs on a hosted HTTPS site; Claude or OpenAI with the user's key. | R18 to R19 | 2 | 10.5% |
| | **Total** | | **19** | **100%** |

Sizes: 4 Simple, 15 Medium, no Large or Very large.

## Assumptions and decisions needed

- **Stack (assumed, not yet confirmed by Larry):** Python with FastAPI on the server, TypeScript in the browser, ffmpeg for media conversion. If the stack changes, the PR list stays the same; only the tooling in R1 and R4 changes.
- **Decision before R2:** the first voice (TTS) engine. It must clone from a short sample and return word timings (needed for highlighting in R11).
- **Decision before R3:** the first video engine, local or hosted, and which tool. This is the biggest open decision in feature_evaluation.md. The roadmap builds one engine behind a pluggable interface; the second is optional (see the end).
- **Decision before R12:** the latency target. 2 seconds is only proposed; the real number comes from what R3's engine can do.
- **If the first video engine is a hosted streaming avatar** (D-ID, Simli and similar), R12 and R13 get smaller, because the service handles streaming and idle motion. If it is a local model, R13 needs a pre-rendered idle loop (for example LivePortrait plus MuseTalk-style lip sync).
- **Testing:** unit tests use fake voice and video engines so CI runs without a GPU or paid API. Each PR that touches a real engine proves it with a manual run and a short clip or log excerpt, per the pr-rules skill.
- **Every code PR** follows the pr-rules skill: build, lint and format pass; unit tests with about 80% line coverage on changed code; logging for errors, timing and meaningful operations; proof and manual test steps in the description.

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

### R4. Browser app and uploads (Medium) · items 1, 22
- TypeScript browser app served by FastAPI, with a consent checkbox (item 22) before setup.
- Upload images (JPG, PNG, HEIC) and sound files (WAV, M4A, MP3); files are stored on the server and converted (HEIC to JPG, audio to WAV).
- Lists uploaded files; images can be viewed and sound files played.
- **Can show:** a user confirms consent, uploads the 5 photos and 3 or 4 recordings from the guide, and views and plays them.

### R5. Image validation (Medium) · item 2
- The six checks from item 2 (one face, size, sharpness, lighting, facing the camera, nothing covering the face), each with its fixed plain-language message.
- Scores valid photos, picks the best, and lets the user choose another.
- **Can show:** a blurry or side-on photo is rejected with a message a nontechnical person can act on; the best photo is highlighted.

### R6. Sound validation (Medium) · item 3
- Checks: at least 30 seconds of usable speech in total, not clipped, low background noise, one speaker, each with a plain-language message.
- Combines the valid files into the voice sample R2 uses.
- **Can show:** a clipped or noisy recording is flagged; valid recordings are combined into one voice sample.

### R7. Prepare and sample video in the browser (Medium) · items 5, 6
- A background job runs prepare (clone voice, prepare face) and renders the sample video, with a progress bar in the browser.
- Also pre-renders "Goodbye." and "Welcome back."
- **Can show:** clicking Prepare shows progress, then the sample video plays in the browser.

### R8. Review screen (Simple) · item 7
- Accept, Reject image (back to image upload), Reject voice (back to sound upload). Change accent is added in R15.
- Chat stays locked until a sample is accepted.
- **Can show:** the full setup flow from upload to an accepted sample, with both reject paths working.

## Milestone 3: Talking chat

### R9. Text chat with the LLM (Medium) · items 10, 15, 16
- OpenAI-compatible client pointed at local llama.cpp, with the short-reply system prompt.
- Conversation history sent with each prompt; the oldest turns are dropped when it would overflow the context window.
- Chat screen with a text box, unlocked after acceptance. Replies are text only for now.
- **Can show:** a text conversation with the local LLM that remembers earlier turns.

### R10. Spoken video replies (Medium) · items 11, 20
- Each reply is cleaned for speech (Markdown, code, URLs and emoji are shown but not voiced), voiced with R2 and animated with R3, then played in the chat.
- If voice or video fails, the text still shows with a short friendly note; if the LLM fails, a plain message says so.
- **Can show:** the person speaks each LLM reply in their voice. This is the app's core experience, though slower than the target until Milestone 4.

### R11. Word highlighting and playback controls (Medium) · items 11, 18, 21
- Highlights each word as it is spoken, using the word timings from R2.
- Stop button, volume and mute.
- **Can show:** words light up in sync with the lips; a reply can be stopped mid-sentence; volume and mute work.

## Milestone 4: Real-time replies

### R12. Streaming, sentence by sentence (Medium) · item 12
- Streams LLM text, splits it into sentences, and voices and animates each sentence while later ones are still generating; the browser queues clips in order.
- Logs time from the LLM's first words to the video starting speaking.
- **Can show:** the video starts on the first sentence instead of waiting for the whole reply, with the measured latency in the logs.

### R13. Idle video and smooth joins (Medium) · item 17
- Between replies the person blinks and moves slightly instead of freezing.
- Returns to the idle pose between sentence clips and crossfades the joins.
- **Can show:** the person looks alive while waiting, and multi-sentence replies play without visible jumps.

## Milestone 5: Spoken prompts

### R14. Push-to-talk microphone (Medium) · item 9
- Microphone button, push-to-talk, transcribed with browser speech recognition or whisper.cpp; the transcribed prompt is shown as sent.
- **Can show:** hold the button, ask a question out loud, and the person answers on video.

## Milestone 6: Americanized voice

### R15. Accent choice (Medium) · items 4, 7 (Change accent)
- Voice-conversion adapter: an American base TTS voice converted to the person's timbre (for example OpenVoice or Seed-VC).
- Accent question in setup, and Change accent on the review screen, which reruns the sample.
- **Can show:** the same sample video in the original accent and Americanized, side by side.

## Milestone 7: Settings, exit and return

### R16. Settings (Medium) · item 8
- A Settings link on every screen with all of item 8's options, plus Delete my data (wired up in R17).
- Changing images, sound or accent requires revalidation and a newly accepted sample before chat resumes; "Goodbye" and "Welcome back" are re-rendered on each new acceptance.
- **Can show:** swap a photo from Settings, get sent through validation and a new sample, then return to the chat.

### R17. Exit, return, saved setup and data deletion (Medium) · items 13, 14, 19, 23
- Exit plays "Goodbye." and shows the exit screen; Start again plays "Welcome back." and keeps history.
- The prepared face, voice and chat history are saved, so a returning user skips setup.
- Delete my data removes uploads, the prepared face and voice, and history.
- **Can show:** exit, start again, close the browser and come back straight to the chat, then delete everything.

## Milestone 8: Hosted, with cloud LLMs

### R18. Hosted deployment (Simple) · Deployment
- Container image and deployment guide for an HTTPS host, single-user sign-in, secrets kept on the server.
- **Can show:** the full app running on a hosted HTTPS URL, with the microphone working.

### R19. Cloud LLMs with the user's key (Simple) · item 16 (later)
- OpenAI by config, and a small Claude adapter; the user enters an API key in Settings, stored on the server only.
- **Can show:** the same conversation answered by Claude or OpenAI instead of local llama.cpp.

At the end of R19 every item in features.md is built, and the application is fully functional.

## Optional, not counted

- **Second video engine** (the other of local or hosted), added behind R3's interface. Medium, 1 PR. features.md calls for it "later"; the app is complete without it.
- **Fine-tuned voice** from all the recordings, for a closer likeness. Medium to Large, 1 to 2 PRs.
