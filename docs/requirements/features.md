# ImageSkinForLLM: Features

A web app that puts a talking video of a real person on top of an LLM. The user types or speaks a prompt; the reply is shown as text and spoken by a video of the person, in their cloned voice, lip-synced to the text.

Items 1 to 16 match the original feature list. Items 17 to 23 were added after review. Items 24 onward add question and answer over PDF content (Larry, 2026-10-08). Items marked *(default)* are choices made pending Larry's confirmation.

## Deployment

- Runs locally for testing or on a hosted site.
- Hosted: single user for now *(default)*. Served over HTTPS (browsers only allow the microphone on HTTPS or localhost).
- Video generation is a pluggable engine: local GPU model or hosted avatar service. **Decided in R4 (2026-10-04):** the first engine is local and CPU-only, a mouth animation of the photo drawn with OpenCV, because Larry requires no per-use cost, CPU only and a license that allows hosted use. Other engines can be added later behind the same interface.

## Setup flow

1. **Upload.** Upload sound files (WAV, M4A, MP3; converted to WAV internally) and images (JPG, PNG, HEIC). At least 1 valid photo is required. The recording guide asks for 5 photos so the app can pick the best, and 3 voice recordings plus an optional 4th. Play any uploaded sound file and view any uploaded image.
2. **Validate images.** Check each image and report problems in short, plain language a nontechnical person can act on, so they can retake the photo. Checks, each with a fixed message:
   - exactly one face found
   - face large enough for the video engine: at least 180 px from mid-forehead to chin once the photo is shrunk to 1280 px on its longest side (changed in R8, 2026-10-07, from a ~512 px guess made before the engine existed; Larry's 1080p webcam photos measure 200 to 216)
   - sharp, not blurry
   - evenly lit, not too dark or bright
   - facing the camera (turned or tilted at most 25°; R8 chose 25° over ~20° so slightly turned portraits pass)
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
12. **Latency.** The target number is set once the first video engine is chosen. With a streaming-capable engine, the proposed target is that the video starts speaking within 2 seconds of the LLM's first words. To get there, LLM text is streamed, split into sentences, and each sentence is voiced and animated while later ones are still generating.

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

## Question and answer over PDF content

Added by Larry on 2026-10-08. The app becomes a question and answer app over a set of PDFs. An administrator manages the photos, voice, content and settings; students and anonymous visitors ask questions, and the person in the photo speaks the answers as in items 11 and 12.

### Content

24. **Manage Content page.** A single "Manage Content" link opens a separate page where the administrator adds, removes or replaces PDFs at any time. PDFs are kept apart from the image and sound files.
25. **Kinds of PDF.** Each PDF holds text, slides or data tables, and each kind is processed so its content can be used for answers.
26. **Knowledge wiki.** Because the PDFs can be large, processing builds a wiki that represents the knowledge in them. The wiki makes it easy for the administrator to review what was processed and to correct it. Adding, removing or replacing a PDF updates the wiki; a page the administrator corrected is not silently overwritten when its PDF is processed again *(default)*.
27. **Answers from the content.** A question is looked up in the wiki and the PDFs, and the chosen LLM (item 29) answers from what it finds.
28. **Question scope setting.** A setting chooses whether general prompts are allowed, or whether prompts must be questions about the content of the PDFs. When they must be, an off-topic prompt gets a short, polite message saying so *(default)*.

### LLM choice

29. **LLM setting.** Settings choose the LLM that answers. By default it is a local open-source model run with llama.cpp. Instead, the administrator can enter a subscription (Claude, OpenAI or Grok) or an API key for Claude, OpenAI, Grok or OpenRouter. Keys stay on the server (item 16).

### Users and sign-on

30. **Administrator sign-on.** A sign-on page gives the administrator the picture, voice, content and settings pages. Only the administrator can reach them.
31. **Anonymous questions.** Without signing on, the app is question and answer only: a visitor asks a question, it is looked up in the wiki and PDFs with the chosen LLM, and the answer is returned.
32. **Student accounts.** A sign-up page creates a student account. A student is identified by logging in through the login link, or by a cookie that remembers them *(default: the cookie keeps a student logged in on that browser)*. Students have no access to settings.
33. **Require sign-up setting.** A setting disallows anonymous use, so a visitor must sign up or log in before asking.

### History

34. **Interaction history.** Every question and answer is kept, with its date and time and whether it came from an anonymous visitor or from which signed-up user.
35. **My history.** A signed-in student sees their own history and can clear it, under the save rule in item 37. Clearing is soft: it disappears from what the student sees but stays available to the administrator.
36. **User history page.** The administrator has a page with every prompt and every answer, organized by date and time, by signed-in user, or as anonymous, to review everything that has happened.
37. **Save before clear, and load.** Larry, 2026-10-08:
   - **Save.** The conversation can be saved to a file.
   - **Clear only what was saved.** Clearing a conversation (item 8's "Clear conversation" and item 35's clear) needs the conversation to be saved first. Only the parts that were saved successfully can be cleared; anything not saved successfully cannot be cleared and stays.
   - **Load.** A saved file can be loaded back into the conversation history. Loading adds to the existing history and never replaces it, and it is idempotent: loading the same file again, or a file whose turns are already in the history, adds nothing twice.

### How this changes earlier items

These are noted here and applied when the PRs for these items are built; the earlier items keep their wording until then.

- **Item 8 (Settings):** the Settings link shows only to the signed-in administrator, not on every screen. Its "Clear conversation" follows item 37: save first, and only saved turns are cleared.
- **Deployment ("single user"):** the hosted app now has one administrator, student accounts and anonymous visitors.
- **Items 9 to 15 (Chat):** the chat becomes the question and answer screen; conversation history is kept per visitor.
- **Item 16 (LLM interface):** item 29 adds Grok, OpenRouter and subscriptions to the Claude and OpenAI keys planned there.
- **Item 23 (Delete my data):** an administrator action, since only the administrator has the photos and recordings.
