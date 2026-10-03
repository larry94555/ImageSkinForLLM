# ImageSkinForLLM: Features

A web app that puts a talking video of a real person on top of an LLM. The user types or speaks a prompt; the reply is shown as text and spoken by a video of the person, in their cloned voice, lip-synced to the text.

Items 1 to 16 match the original feature list. Items 17 onward were added after review. Items marked *(default)* are choices made pending Larry's confirmation.

## Deployment

- Runs locally for testing or on a hosted site.
- Hosted: single user for now *(default)*. Served over HTTPS (browsers only allow the microphone on HTTPS or localhost).
- Video generation is a pluggable engine: local GPU model or hosted avatar service *(default: support both; pick per deployment)*.

## Setup flow

1. **Upload.** Upload sound files (WAV, M4A, MP3; converted to WAV internally) and images (JPG, PNG, HEIC). Expected set, per the recording guide: 5 photos and 3 voice recordings, plus an optional 4th. Play any uploaded sound file and view any uploaded image.
2. **Validate images.** Check each image and report problems in short, plain language a nontechnical person can act on, so they can retake the photo. Checks, each with a fixed message:
   - exactly one face found
   - face at least ~512 px tall
   - sharp, not blurry
   - evenly lit, not too dark or bright
   - facing the camera (within ~20°)
   - nothing covering the face

   The app picks the best photo for the video; the user can choose a different one.
3. **Validate sound files.** Same plain-language feedback. Checks: long enough, not clipped (too loud), low background noise, one speaker. Valid files are combined into one voice sample.
4. **Accent choice.** Ask whether to Americanize the voice or keep it as is.
5. **Prepare.** Process images and sound into what video and voice generation need, with a progress indicator. A one-time delay is acceptable. Also pre-render the fixed lines "Goodbye." and "Welcome back."
6. **Sample video.** A ~30-second video, with progress shown while it renders, of the person saying:
   > This is a test. How do I sound? I'm speaking in my own voice, or as close to it as a computer can get. Let me try a few things. Numbers: one, two, three, forty-five, and nine hundred ninety-nine. A question: did you see that coming? And a little excitement: wow, that's great news! She sells seashells by the seashore. If anything looks or sounds wrong, tell me now so we can fix it.
7. **Review.** The user chooses one of:
   - **Accept** and go to the chat.
   - **Reject image** and upload new images.
   - **Reject voice** and upload new sound files.
   - **Change accent**, which toggles item 4 and reruns the sample.

## Settings

8. A **Settings** link is visible on every screen. It offers:
   - Change image files
   - Change sound files
   - Americanize voice or keep it as is
   - Play the sound files
   - View the image files
   - Revalidate image files
   - Revalidate sound files
   - Run the video test again
   - Clear conversation
   - Return to the web app

   Changing images, sound or accent requires revalidation and a newly accepted sample before chat resumes.

## Chat

9. **Prompt input.** Unlocked after the sample is accepted: a text box plus a microphone button. Speech is transcribed to text (e.g. whisper.cpp or browser speech recognition), push-to-talk *(default)*. The transcribed prompt is shown as sent.
10. **LLM.** The prompt goes to the LLM (a local llama.cpp model for testing). A system prompt asks for short, conversational replies.
11. **Response.** The reply is shown as text and spoken by the video, with each word highlighted as it is spoken. Markdown, code, URLs and emoji are shown as text but not voiced.
12. **Latency.** The video starts speaking within 2 seconds of the LLM's first words *(default target)*. To meet it, LLM text is streamed, split into sentences, and each sentence is voiced and animated while later ones are still generating.

## Exit and return

13. **Exit.** The user can exit: the video says "Goodbye." and the app moves to an exit screen.
14. **Start again.** The exit screen has a "Start again" link. The video says "Welcome back," then the prompt and microphone are ready. History is kept *(default)*.

## Conversation history

15. The app keeps the conversation history and sends it with each prompt so the LLM keeps context. When history exceeds the model's context window, the oldest turns are dropped.

## LLM interface

16. Connects to llama.cpp through its OpenAI-compatible chat API, so OpenAI is later a config change and Claude a small adapter. Later: the user supplies an API key to use a Claude or OpenAI model. Keys stay on the server, never in the browser.

## Added after review

17. **Idle video.** Between replies the person blinks and moves slightly instead of freezing.
18. **Stop.** A button stops the video mid-reply.
19. **Saved setup.** After acceptance, the prepared face and voice are saved so a returning user skips setup.
20. **Errors in chat.** If the voice or video step fails, the text reply still shows, with a short friendly note. If the LLM fails, a plain message says so.
21. **Volume and mute** controls.
22. **Consent.** Before setup, the user confirms the person in the photos and recordings agreed to be cloned.
23. **Delete my data.** One action deletes the uploaded files, prepared face and voice, and history.
