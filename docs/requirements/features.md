# ImageSkinForLLM: Features

A web app that puts a talking video of a real person on top of an LLM. The user types or speaks a prompt; the reply is shown as text and spoken by a video of the person, in their cloned voice, lip-synced to the text.

Items 1 to 16 match the original feature list. Items 17 to 23 were added after review. Items 24 onward add question and answer over PDF content (Larry, 2026-10-08), items 48 to 51 give it a professional look with a participant and a host view (Larry, 2026-10-13), items 56 to 59 let a user start at once with a default person, and item 60 gives them a range of faces to choose from (Larry, 2026-10-16). Items 61 to 76 turn the app into a paid service for many customers (then called teachers) on me0.ai, with a support site and an AI that gathers feedback and contact information (Larry, 2026-10-17); items 73 to 76 come after everything else; items 61 to 72 come right after sign-on and accounts (items 30 to 33), before items 77 to 88 (moved by Larry, 2026-10-18), and items 61 to 66, the customers' sites, now come right after the default person (items 56 to 60), before sign-on and accounts, as the next priority (Larry, 2026-10-19); teachers are now called customers. Also on 2026-10-19, Larry renamed the teacher and student views and roles to host and participant, since teacher and student are only one context (items 77 on); the Settings page shows them as "Host (Teacher)" and "Participant (Student)", the parentheses later following the primary context. Items 77 to 83 add contexts, which decide how the AI responds to each prompt (Larry, 2026-10-17); they come after the customers' sites and support (items 61 to 72) and before interaction history (items 34 to 37) (moved by Larry, 2026-10-18). Items 84 to 88 add an identity and guidelines the user can customize, with a history of changes (Larry, 2026-10-18); they come right after contexts. Items 89 to 95 add handling disputes over a photo or voice used without the right to it, with an admin role distinct from the host, messages with a clear notification, and a fall back to a default person (Larry, 2026-10-21); they come last, after every other item. Items 96 to 101 add iOS and Android: the app in a phone's browser, then apps for both in the App Store and Google Play, which connect to the hosted service (Larry, 2026-10-22); they come after items 89 to 95. Items 102 to 105 add safe photos: no nudity or sexual content, only a photograph of a real person's face, and only the head and shoulders animated (Larry, 2026-10-24); they come right after the identity and guidelines (items 84 to 88). Items 115 to 118 simplify every page, hiding or removing the details that were there for debugging (Larry, 2026-10-25); they come right after the safe photos. Items 106, 107 and 112 to 114 fix bugs, so the mouth moves in step with the voice and the cheeks and face move with it, long replies are spoken at a steady pace, a failed prepare gives a reason and a reference for support, and prepare shows it is still working (item 119, added on 2026-10-26, answers an example question picked again at once), and items 108 to 111 add a setup wizard that takes the photo with the camera and records the voice in the browser (Larry, 2026-10-25); both come right after the speed-ups and before the customers' sites (items 61 to 66). Items marked *(default)* are choices made pending Larry's confirmation.

## Deployment

- Runs locally for testing or on a hosted site.
- Hosted: single user for now *(default)*. Served over HTTPS (browsers only allow the microphone on HTTPS or localhost).
- Video generation is a pluggable engine: local GPU model or hosted avatar service. **Decided in R4 (2026-10-04):** the first engine is local and CPU-only, a mouth animation of the photo drawn with OpenCV, because Larry requires no per-use cost, CPU only and a license that allows hosted use. Other engines can be added later behind the same interface.

## Setup flow

1. **Upload.** Upload sound files (WAV, M4A, MP3; converted to WAV internally) and images (JPG, PNG, HEIC). At least 1 valid photo is required. The recording guide asks for 5 photos so the app can pick the best, and 7 voice recordings (about 15 minutes; the first 3 are enough for today's voice, the rest are kept for a trained voice later) plus an optional 8th. Play any uploaded sound file and view any uploaded image.
2. **Validate images.** Check each image and report problems in short, plain language a nontechnical person can act on, so they can retake the photo. Checks, each with a fixed message:
   - exactly one face found
   - face large enough for the video engine: at least 180 px from mid-forehead to chin once the photo is shrunk to 1280 px on its longest side (changed in R8, 2026-10-07, from a ~512 px guess made before the engine existed; Larry's 1080p webcam photos measure 200 to 216)
   - sharp, not blurry
   - evenly lit, not too dark or bright
   - facing the camera (turned or tilted at most 25°; R8 chose 25° over ~20° so slightly turned portraits pass)
   - nothing covering the face

   The app picks the best photo for the video; the user can choose a different one.
3. **Validate sound files.** Same plain-language feedback. Checks: long enough, not clipped (too loud), low background noise, one speaker. Valid files are combined into one voice sample.
4. **Accent choice.** Ask whether to keep the person's own accent or change it, for example to American, British or Russian-English. (Widened by Larry, 2026-10-09: he already sounds American, so Americanizing alone could not be tested on him, and other accents are wanted too.)
5. **Prepare.** Process images and sound into what video and voice generation need, with a progress indicator. A one-time delay is acceptable. Also pre-render the fixed lines "Goodbye." and "Welcome back."
6. **Sample video.** A ~30-second video, with progress shown while it renders, of the person saying:
   > This is a test. How do I sound? I'm speaking in my own voice, or as close to it as a computer can get. Let me try a few things. Numbers: one, two, three, forty-five, and nine hundred ninety-nine. A question: did you see that coming? And a little excitement: wow, that's great news! She sells seashells by the seashore. If anything looks or sounds wrong, tell me now so we can fix it.
7. **Review.** The user chooses one of:
   - **Accept** and go to the chat.
   - **Reject image** and upload new images.
   - **Reject voice** and upload new sound files.
   - **Change accent**, which goes back to item 4's choice and reruns the sample.

## Settings

8. A **Settings** link is visible on every screen. It offers:
   - Change image files
   - Change sound files
   - Keep the voice's own accent or change it
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
11. **Response.** The reply is spoken by the video. Markdown markers, code, URLs, emoji and other parts that read badly aloud are not voiced in full, but the spoken sentence must still make sense: a left-out part is replaced by a short phrase that says what it is and points to the text, such as "the links in the text below" or "the code shown below", never dropped so that the sentence breaks off (for example "see the guide or examples referenced", not "see the guide or"). The words are not highlighted as they are spoken: reading along with the same words is distracting, and keeping a highlight in sync would complicate the screen and could slow replies (Larry, 2026-10-09).
    - **Reply text panel.** The written reply, with its URLs, code and emoji in full, is in a text panel that is closed by default. The user can open it to read the conversation, scroll through it and search it, and close it again.
12. **Latency.** The target number is set once the first video engine is chosen. With a streaming-capable engine, the proposed target is that the video starts speaking within 2 seconds of the LLM's first words. To get there, LLM text is streamed, split into sentences, and each sentence is voiced and animated while later ones are still generating.

## Exit and return

13. **Exit.** The user can exit: the video says "Goodbye." and the app moves to an exit screen.
14. **Start again.** The exit screen has a "Start again" link. The video says "Welcome back," then the prompt and microphone are ready. History is kept *(default)*.

## Conversation history

15. The app keeps the conversation history and sends it with each prompt so the LLM keeps context. The history never uses more than half of the model's context window, leaving room for the prompt and the reply; when it grows past that, the LLM summarizes the older turns after a reply, and the summary is sent in their place (Larry, 2026-10-09). If summarizing fails, the oldest turns are dropped.

## LLM interface

16. Connects to llama.cpp through its OpenAI-compatible chat API, so OpenAI is later a config change and Claude a small adapter. Later: the user supplies an API key to use a Claude or OpenAI model. Keys stay on the server, never in the browser.

## Added after review

17. **Idle video.** Between replies the person blinks and moves slightly instead of freezing.
18. **Stop.** A button stops the video mid-reply, and stops the thinking too while the reply is still being written: the prompt goes back in the box (Larry, 2026-10-21).
19. **Saved setup.** After acceptance, the prepared face and voice are saved so a returning user skips setup.
20. **Errors in chat.** If the voice or video step fails, the text reply still shows, with a short friendly note. If the LLM fails, a plain message says so.
21. **Volume and mute** controls.
22. **Consent.** Before setup, the user confirms the person in the photos and recordings agreed to be cloned.
23. **Delete my data.** One action deletes the uploaded files, prepared face and voice, and history, and the PDFs with everything made from them (their wiki, edits, saved versions and lessons).

## Question and answer over PDF content

Added by Larry on 2026-10-08. The app becomes a question and answer app over a set of PDFs. An administrator manages the photos, voice, content and settings; participants and anonymous visitors ask questions, and the person in the photo speaks the answers as in items 11 and 12.

### Content

24. **Manage Content page.** A single "Manage Content" link opens a separate page where the administrator adds, removes or replaces PDFs at any time. PDFs are kept apart from the image and sound files.
25. **Kinds of PDF.** Each PDF holds text, slides or data tables, and each kind is processed so its content can be used for answers. Scanned PDFs (pictures of pages, which would need OCR) are not read for now; their pages are shown as having no text *(default)*.
26. **Knowledge wiki.** Because the PDFs can be large, processing builds a wiki that represents the knowledge in them. The wiki makes it easy for the administrator to review what was processed and to correct it. Adding, removing or replacing a PDF updates the wiki; a page the administrator corrected is not silently overwritten when its PDF is processed again *(default)*. The wiki reads as an outline (Larry, 2026-10-12): each PDF has a table of contents whose entries are either summarized in a few sentences, when simple enough, or summarized briefly with a link to a detail page of their own, which follows the same pattern for its parts.
27. **Answers from the content.** A question is looked up in the wiki and the PDFs, and the chosen LLM (item 29) answers from what it finds.
28. **Question scope setting.** A setting chooses whether general prompts are allowed, or whether prompts must be questions about the content of the PDFs. When they must be, an off-topic prompt gets a short, polite message saying so *(default)*.

### LLM choice

29. **LLM setting.** Settings choose the LLM that answers. By default it is a local open-source model run with llama.cpp. Instead, the administrator can enter an API key for Claude, OpenAI, Grok or OpenRouter, or sign in with ChatGPT to use their ChatGPT plan. Keys and sign-ins stay on the server (item 16). OpenAI allows a ChatGPT plan to be used by open-source apps that run on the user's own computer, so the ChatGPT sign-in is offered while the app runs locally; a hosted or paid site would need OpenAI's approval first. Claude's and Grok's subscriptions can't be used: Anthropic's terms allow a Claude subscription only in Anthropic's own apps, and xAI publishes no sign-in for other apps (checked 2026-10-19).

### Users and sign-on

30. **Administrator sign-on.** A sign-on page gives the administrator the picture, voice, content and settings pages. Only the administrator can reach them.
31. **Anonymous questions.** Without signing on, the app is question and answer only: a visitor asks a question, it is looked up in the wiki and PDFs with the chosen LLM, and the answer is returned.
32. **Participant accounts.** A sign-up page creates a participant account. A participant is identified by logging in through the login link, or by a cookie that remembers them *(default: the cookie keeps a participant logged in on that browser)*. Participants have no access to settings.
33. **Require sign-up setting.** A setting disallows anonymous use, so a visitor must sign up or log in before asking.

### History

34. **Interaction history.** Every question and answer is kept, with its date and time and whether it came from an anonymous visitor or from which signed-up user.
35. **My history, and deleting from the record.** A signed-in participant sees their own history. Changed by Larry on 2026-10-17 (before, a participant's clear only hid their history from them and kept it for the administrator):
   - **The host (the administrator) can delete** any question, with its answer, from the chat history, on the user history page (item 36).
   - **The participant can delete** any of their own questions, with its answer, from their history, so a statement they don't want on their record is not kept, but only when the setting below allows it.
   - **Participant deleting setting.** A setting chooses whether participants can delete parts of their chat history. A business would usually turn it off, so the record stays complete; a school may need it on. Off by default *(default)*.

   A deleted question is removed from the record for everyone, the administrator included: it is no longer in the history, search, topics, ratings, statistics, summaries or profile (items 36 to 47). The log notes only that a question was deleted and by whom, never its words *(default)*. Deleting one question needs no save first (item 37). The delete is permanent: the app keeps a list of deleted turn ids, without their words, so a file saved before the delete can't load the turn back (item 37), and any summary of older turns sent to the LLM (item 15) that included it is rebuilt without it.
36. **User history page.** The administrator has a page with every prompt and every answer not deleted (item 35), organized by date and time, by signed-in user, or as anonymous, to review everything that has happened.
37. **Save before clear, and load.** Larry, 2026-10-08:
   - **Save.** The conversation can be saved to a file.
   - **Clear only what was saved.** Clearing a conversation (item 8's "Clear conversation") needs the conversation to be saved first. Only the parts that were saved successfully can be cleared; anything not saved successfully cannot be cleared and stays.
   - **Load.** A saved file can be loaded back into the conversation history. Loading adds to the existing history and never replaces it, and it is idempotent: loading the same file again, or a file whose turns are already in the history, adds nothing twice. A turn deleted since the file was saved (item 35) is skipped, never added back.

### How this changes earlier items

These are noted here and applied when the PRs for these items are built; the earlier items keep their wording until then.

- **Item 8 (Settings):** the Settings link shows only to the signed-in administrator, not on every screen. Its "Clear conversation" follows item 37: save first, and only saved turns are cleared.
- **Deployment ("single user"):** the hosted app now has one administrator, participant accounts and anonymous visitors.
- **Items 9 to 15 (Chat):** the chat becomes the question and answer screen; conversation history is kept per visitor.
- **Item 16 (LLM interface):** item 29 adds Grok, OpenRouter and subscriptions to the Claude and OpenAI keys planned there.
- **Item 23 (Delete my data):** an administrator action, since only the administrator has the photos and recordings.

## Participant insights

Added by Larry on 2026-10-09. These build on the history in items 34 to 37 and change none of the items above. They are for the administrator, except item 46, which participants see.

### Topics and understanding

38. **Topics.** The topics are the knowledge wiki's topic pages (item 26), so they follow the content as PDFs are added, removed or replaced *(default)*.
39. **Topic of each question.** A question's topics are the wiki pages the lookup in item 27 found for it, kept with the question; there is no second classification. A question can have no topic (for example a general prompt allowed by item 28), one, or several. Questions already in the history when this is added, and history loaded later from a file (item 37), are tagged the same way. Tags are not rewritten when the wiki changes; a topic whose page was removed is shown as removed.
40. **Understanding shown by each question.** Every question from a signed-in participant is rated for each of its topics, so one question can be strong for one topic and unrated or weak for another:
   - **strong:** the question itself shows correct use or connection of the topic's concepts.
   - **weak:** the question contains a clear misconception about the topic.
   - **unrated:** the question gives no clear evidence either way, including ordinary fact-seeking questions. A basic but reasonable question is unrated, not weak.

   Each rating keeps a one-line reason. The administrator can correct a rating; the correction is kept with it and is never silently overwritten. Ratings are seen only by the administrator, never by participants *(default)*.
41. **Participant profile.** For each participant: each topic they asked about, with their strong, weak and unrated questions on it (item 40). There is no score: topics are broad and made of subtopics, so a participant can be strong on some subtopics and weak on others, and a topic with both strong and weak questions shows both. The questions listed under the topic show which subtopics they were about. It is worked out from items 39 and 40 whenever it is needed, not kept separately, and shown on the participant summary page (item 45).

### Search

42. **Search one participant's history.** On the user history page (item 36), the administrator searches the conversation history of a chosen participant, by words in the questions and answers, and can narrow by date and topic.
43. **Search all histories.** The same search on the same page across the conversation histories of all participants. Anonymous questions are included and marked as anonymous *(default)*.

Search never finds a deleted question or its answer (item 35).

### Statistics and summaries

44. **Topic statistics page.** For each topic: how many questions were asked about it, which topics were not asked about at all, and how many strong, weak and unrated questions it drew (item 40), as counts by question type rather than a single score. Topic counts include anonymous questions; strong and weak come from signed-in participants only.
45. **Participant summary page.** One page per participant showing their profile (item 41): each topic they asked about, with the counts of their strong, weak and unrated questions on it and the questions themselves.

### Deleting from history

46. **Heads-up before deleting.** When a participant or the host deletes a question (item 35), a confirmation says: "Deleting removes this question and its answer from the record for everyone. This can't be undone." The delete goes ahead only after they confirm. Changed by Larry on 2026-10-17; before, it said a cleared conversation stays available to the administrator.

## Interests and personality

Added by Larry on 2026-10-09, after the participant insights above. It builds on the history (items 34 to 37) and the participant profile (item 41) and changes none of the items above.

47. **Interests and personality profile.** For each signed-in participant, a short profile that tries to characterize their interests and personality from the questions they ask and how they respond to the answers:
   - **Interests:** what they keep coming back to, inside the content and outside it, and the kind of question they like to ask (for example real-world examples, the reasons behind something, or its history).
   - **How they respond to answers:** from their next message after each answer, such as asking follow-ups and how deep they go, asking for examples or a simpler explanation, questioning or pushing back on an answer, moving straight on, or showing frustration or enthusiasm.

   Each line of the profile gives its evidence in one line and links to the questions it came from, and it is worded as an impression from their questions, not a fact or a judgment of the participant. Anonymous questions are not used, and a participant with too few questions has no profile yet. The administrator can edit or remove a line, and the change is never silently overwritten. The profile is seen only by the administrator, never by participants, and is shown on the participant summary page (item 45) *(default)*.

## A professional look

Added by Larry on 2026-10-13. The chat must be clean and professional enough to use in a commercial setting: judged only on how it looks and on answering typed questions, the app is clearly of professional quality. The host view must be usable by a non-technical host and the participant view by a non-technical participant. These come before spoken prompts (item 9's microphone).

48. **Professional look and clean video.** The video plays cleanly, as one steady picture of the person, with no controls, empty frames, flicker or jumps. Every page has one consistent look, and every message is short and plain, with no technical words, ids or error codes; the detail goes to the log.
49. **Metrics setting.** The timing metrics (such as the timing readout under the video) are hidden unless a setting turns them on. Off by default *(default)*.
50. **Participant view and host view.** A setting chooses the view:
   - **Participant view:** the chat, and read-only use of the wiki and the existing PDFs. The options to manage content, edit the wiki or change the setup are hidden.
   - **Host view:** every page and option. Host by default *(default)*.
51. **Anyone can change these settings for now.** Items 49 and 50 can be changed at will by anyone. Later this is restricted, and the view follows who is using the app:
   - **Administrator** (signed on, item 30): the host view.
   - **Signed-in participant** (item 32): the participant view.
   - **Anonymous visitor** (item 31): question and answer only, with no wiki or PDFs.

## Knowing what to ask, teach me, quiz me and the assessment

Added by Larry on 2026-10-14. Today nothing tells a participant which topics they can ask about and which ones they can't, and the app only answers questions. Larry added the assessment (item 55) later the same day: Teach me should prepare a participant to score 100% on it. These come after the professional look (items 48 to 51) and before spoken prompts (item 9's microphone). They work in the participant and host views. Once accounts exist (items 30 to 32), anonymous visitors, who are question and answer only (item 51), get items 52 and 53 but not Teach me, Quiz me or the assessment *(default)*.

52. **"What can you talk about?"** A question like "What topics can you talk about?" or "What do you know about?" is answered with the topics in the content: the wiki's main entries (item 26), each named in plain words, in a short spoken answer that ends by suggesting one to ask about. It is answered even when general prompts are off (item 28), and then also says that questions outside these topics can't be answered. Before any PDF is added it says it can talk about anything.
53. **Topic hints.** The chat shows what can be asked before the participant asks anything: a short line under the prompt box naming a few of the topics, and a few example questions drawn from the wiki that send the question when clicked. When general prompts are off, the line says questions must be about these topics. A prompt declined by item 28 names a few topics it can answer instead. The hints follow the content as PDFs are added, removed or replaced *(default)*.
54. **Teach me and quiz me.** Two buttons by the prompt box, also started by typing "teach me about …" or "quiz me on …". When no topic is named, each asks the participant to choose one from the list in item 52; Teach me's list also offers **Everything, from the start**, which teaches the topics in order. Both use only the content, as answers do (item 27), and are spoken like any reply.
   - **Teach me:** the person explains the topic in short parts, one at a time, from the wiki and PDFs, going from the main ideas into the detail. After each part the participant can ask a question about it, say "next", or ask for it again more simply. It goes on for as long as the participant wants: when a topic is finished it gives a one-line summary, offers a quick quiz, and moves on to the next topic, until the whole content has been taught. The aim is that a participant who stays to the end is ready to score 100% on the assessment (item 55). A participant who stops can pick up where they left off: on that browser until accounts exist, then for each signed-in participant, so participants sharing a device don't share progress *(default)*.
   - **Quiz me:** the person asks one question at a time about the topic, drawn from the wiki and PDFs. The participant types an answer; the reply says whether it is right, partly right or wrong, in a friendly way, with the correct answer and a one-line reason from the content. A quiz has 5 questions *(default)*, the participant can stop at any time, and it ends with how many they got right and the parts worth going over again.
55. **Assessment.** An **Assessment** button, also started by typing "assess me" or "test me on everything", evaluates the participant's knowledge of all the content, not one topic. It asks a sample of questions rather than everything. Each question is about one main topic and at one level, and counts toward both:
   - **Breadth:** every main topic in the wiki gets at least one question, and no topic gets a second until every topic has one.
   - **Depth:** questions come at three levels: recalling a fact, explaining an idea in their own words, and applying or connecting ideas. Deeper questions come from the wiki's detail pages. The questions are split as evenly as possible across the three levels, so each level has at least a third of them, rounded down.

   Questions come one at a time and are judged as in quiz me, but the correct answer is shown only at the end, so the assessment isn't taught as it goes. It has 15 questions, or one per main topic when there are more than 15 topics, so every level has at least 5 *(default)*. It ends with an evaluation: the overall result, a breadth result (the topics answered well out of all the topics), a depth result for each level, and the topics and levels to go over again, with an offer to start Teach me on them.

## Starting with a default person

Added by Larry on 2026-10-16, for testing. A user can start chatting at once, without uploading a photo or recording their voice, by choosing a default person. The app makes a picture of that person and gives them a ready-made voice, and the user can replace either with their own later.

56. **Default person choices.** The first setup screen offers **Start now with a default person** beside the usual upload. The user picks:
   - **Accent:** British or American.
   - **Realism:** photorealistic or animated.
   - **Face:** one of the people of that realism, women, men and nonbinary people together (item 60), shown as pictures.

   There is no gender to pick (Larry, 2026-10-21): the face shows the person, and the person's gender picks the voice (item 58). There is no role to pick either (Larry, 2026-10-21). The people were made for nine roles (Professor, Teaching Assistant, Student, Parent, Young Adult, Boss, Office Manager, High School Teacher and Business Consultant; Young Adult replaced Teenager, since every default person is an adult, Larry, 2026-10-24), which set their clothes and setting, but each role has only one or two people, so picking a role would tie it to one look. The point of the range is that each user can imagine any role in their own way, so the user picks only the face.
57. **Generated picture.** The picture is made to fit the choices: the person's gender, an age, clothes and a setting that suit the role, photoreal or animated. Each of the 36 is checked before it ships: it passes the same checks as an uploaded photo (item 2), and a short line is rendered to show it talks and idles like one. That is why the sample video and review can be skipped (item 58). Every picture is of a made-up person: it is not based on a real person or a public figure, and the prompts used to make it name none. Since accent doesn't change the picture, there is one picture for each gender, realism and role: 36 in all, 24 of them with a second face (item 60). They are made and prepared ahead of time, so choosing one doesn't wait for the one-time prepare step (item 5) *(default)*.
   - **Getting the picture.** Only the chosen person's picture and prepared frames are downloaded, when they are first chosen, and kept for next time; the others are never fetched unless chosen *(default)*. Only the small thumbnails used to pick a face (item 60), under 1 MB for all of them, ship with the app. A person already downloaded starts at once. Otherwise the screen shows the download's progress and goes to the chat when it ends. If it fails, a plain message says so with **Try again**, and the usual upload is still offered.
   - **Start now means:** no uploads, recordings or prepare step. The only wait is that one person's download the first time they are chosen, which is at most 50 MB, so it takes 20 seconds or less at 25 Mbit/s.
58. **Default voice.** The voice is one of Kokoro's ready-made voices for the chosen person's gender and the chosen accent, which ship with the app under its license, not a clone, so there are no recordings to check. They are `af_heart` (American woman), `am_michael` (American man), `bf_emma` (British woman) and `bm_george` (British man), picked in R24a for their grades in Kokoro's voice list; Kokoro and its voices are Apache 2.0. A nonbinary person (item 60) speaks in an even blend of the accent's woman's and man's voice (`af_heart,am_michael` or `bf_emma,bm_george`), which Kokoro makes from the two voices, with a pitch between them (Larry, 2026-10-21). The user isn't asked for consent (item 22): they supply no one's picture or voice, the picture is of a made-up person (item 57), and the voice is a licensed preset rather than a clone of someone the user brings. Setup goes straight to the chat; the sample video and review (items 6 and 7) are skipped, and the Goodbye and Welcome back lines are spoken in the default voice.
59. **Replace with your own.** At any time the user can replace the default voice with their own recordings, keeping the default picture, or replace both with their own photos and recordings through setup. Each goes through the usual checks, prepare and review for what is replaced (items 1 to 7). Consent (item 22) is asked for each real person brought in:
   - **Default picture, own voice:** the user confirms the person in the recordings agreed to have their voice cloned. Until the sample of the avatar in that voice is accepted, the avatar keeps its ready-made voice and the chat stays open; choosing an avatar again starts it in its ready-made voice.
   - **Own photo and own voice:** as in item 22, the user confirms they are the same person and that this person agreed to be cloned. A photo of one real person with the voice of another is not allowed *(default)*.
   - **Own photo, no recordings:** recordings are optional. While none has passed the checks (none added, or all rejected or removed), the user's own photo speaks in a ready-made voice (item 58): the last default person's, or the one chosen in setup, and setup says so. Once recordings pass, the voice is made from them (Larry, 2026-10-21). An own photo is not otherwise given a default voice.
60. **A range of faces.** 68 default people for now: the 36 of item 57, a second face for 24 of the choices, six for each gender and realism (Larry, 2026-10-17), and 8 nonbinary people, four for each realism (Larry, 2026-10-21) *(default)*. Across the 15 people of each gender and realism, every one of eight broad heritages appears with hair to suit, at least one has red hair and one blond hair, at least three wear glasses, at least three are in their 60s or 70s where the role suits it (not Young Adult, Student or Teaching Assistant), and at least two have a visible disability, such as a wheelchair or a hearing aid (Larry, 2026-10-17), so more people can find a default person who looks like them. Every default person is an adult, 18 or over, and looks it (Larry, 2026-10-24). Across the 8 nonbinary people, each of the eight heritages appears once, and each realism has one older person and one with glasses; none uses a wheelchair, which Larry said isn't needed for them (2026-10-21). Each is checked, prepared and downloaded like the 36 (item 57). After the accent and realism, all the people of that realism, of every gender, show as small pictures and the user picks one (Larry, 2026-10-21). No face is labelled with a heritage, skin tone, ethnicity, age or disability anywhere the user sees: they are shown only as pictures (Larry, 2026-10-16).

## Bug fixing

Added by Larry on 2026-10-25, to build right after the speed-ups (Milestone 10b), before the customers' sites (items 61 to 66). Two bugs seen with the default people (items 106 and 107), a failed prepare that tells the customer nothing they can act on (item 112, added later that day), a prepare that looks frozen while it works (item 113), and cheeks and a face that don't move with the mouth (item 114), both also added that day. Larry added item 119 on 2026-10-26, while testing the cheeks: an example question under the prompt box was made again from the start every time it was picked.

106. **Mouth in step with the voice.** The mouth never moves before the voice is heard, in any clip of a reply, the sample video or the fixed lines, for a default person or a person's own photo and voice. It opens with the sound, at most 80 ms ahead of it *(default)*, as lips lead the sound slightly in real speech, and closes when the sound stops.
107. **A steady rhythm in long replies.** A long reply is spoken from start to end at a constant pace, as one person would say it: at a normal speaking rate, about 150 to 170 words a minute *(default)*, not slowed down, with pauses only where the text has them (a comma, a full stop, a new paragraph), each as long as a speaker would leave, and no gap longer than that while the next part is made. If the next part can't be ready in time, the reply waits a little longer before it starts rather than stopping partway *(default)*.

114. **Cheeks and face that move with the mouth.** When the mouth moves, the cheeks and the muscles around the mouth move with it, as on a real face: the cheeks lift a little on a smile-shaped sound such as "ee", draw in slightly on a rounded one such as "oo", and the lower cheeks and chin stretch as the jaw opens; the lines from the nose to the corners of the mouth deepen and soften with them. The movement is human, not mechanical: it eases in and out with the mouth rather than snapping, is never larger than the mouth's own movement calls for, and settles back between words. When in doubt it is smooth and slight rather than sharp and rigid (Larry, 2026-10-25). It applies to every person, photoreal and animated, a default person or a person's own photo.
112. **A reason and a reference when prepare fails.** When preparing the video and voice from the user's own photo and recordings fails, the page says in plain words which step failed and why, as far as the app can tell (a program or add-on missing, not enough memory or disk space, a model that couldn't be downloaded, a photo or recording that couldn't be read, a step that took too long, or something unexpected), whether trying again may help, and a short reference such as `P-7K3F9Q` to give support. **Copy details for support** copies the reference, the step, the reason, the time, the app's version and the browser, and a **Details** line, closed until opened, shows the error itself without the server's folders or file names *(default)*. Never "find the reason in the log": a customer can't read the log. The log keeps the full error under the same reference, so support can find it. The same applies to making the sample video again (item 8) and to getting a default person ready (item 56).

113. **Prepare never looks frozen.** While the video and voice are prepared, the page shows, every few seconds, that the work is going on: the step running, what it is doing within the step in plain words (such as "Loading the voice", "Downloading the face models, 120 of 500 MB" or "Mouth shape 4 of 10"), how long the step and the whole prepare have taken so far, and about how long is left once that can be told. The percentage moves within a step, not only when it finishes. If nothing has changed for longer than the step usually takes *(default)*, the page says it is taking longer than usual but still working, and if the app has stopped working on it (the app restarted, say), it says so, with Try again, rather than staying at the same percentage.

119. **Example questions answered at once.** The example questions under the prompt box (item 53) are the same until the PDFs change, so once one has been answered and its video made, the reply and its video are kept, and picking it again plays them at once, with no wait for the LLM or the video (Larry, 2026-10-26). A kept reply is used only for the same person, voice, prepare and wiki, and whether general prompts are allowed; after any of them changes, it is made again the next time and kept in its place. Delete my data removes them.

120. **Answers from the PDFs start sooner.** The "Thinking…" before an answer from the PDFs is as short as the LLM allows (Larry, 2026-10-26): no question waits for the conversation to be summarized, the LLM doesn't read the same instructions again with every question, and a typed question is read ahead while it is typed. Nothing changes in what the user sees but the speed, and every answer is as good as before.

## Setup wizard

Added by Larry on 2026-10-25, to build right after items 106 and 107, before the customers' sites (items 61 to 66). A first-time user who wants to use their own photo and voice is walked through setup one step at a time, and can take the photo and make the recordings in the browser, without other apps or files.

108. **One step at a time.** A **Set up with your own photo and voice** link on the home page and on the Setup page opens a wizard that shows one step per screen, with Back and Next: what is needed and the consent (items 21, 22), the photo, the recordings, the accent (item 4), Prepare (item 5), the sample video (item 6) and the review (item 7). Each step says in a sentence what to do and how long it takes, shows the checks' plain messages (items 2, 3) as soon as they are known, and lets Next go on only once the step is done. Leaving the wizard and coming back opens it at the step reached. It uses the same uploads, checks and prepare as the Setup page, which stays for users who want everything on one screen.
109. **Take the photo with the camera.** Where the browser has a camera and the user allows it, the photo step shows the camera's live picture with an outline where the head and shoulders go and the recording guide's tips (light in front, look at the camera), takes the picture after a short countdown, and checks it at once, with **Retake** if a check fails. The camera is used only while that step is open and turned off as soon as it is left.
110. **Record the voice in the browser.** Where the browser has a microphone and the user allows it, the recordings step shows what to say for each recording, one at a time, from the recording script ([input-voice.md](../planning/input-voice.md)): the passage to read aloud, or what to talk about freely, with a level meter, a timer and Stop, plays the recording back, and checks it at once (item 3), with **Record again** if a check fails. The microphone is used only while recording.
111. **Without a camera or microphone.** If the browser has no camera or microphone, the user refuses access, or the page isn't served over HTTPS or from localhost (see Deployment), the step says so in a sentence and offers picking a file instead, with the recording guide's instructions, so the wizard works the same from there. Photos and recordings from the wizard are stored, converted and checked like any upload (items 1 to 3), and later the safe-photo checks (items 102 to 105).

## Many customers on me0.ai

Added by Larry on 2026-10-17, to build after every item above; on 2026-10-18 Larry moved it to build right after sign-on and accounts (items 30 to 33), before contexts (item 77 on), and on 2026-10-19 to build right after the default person (items 56 to 60), before sign-on and accounts, as the next priority: a customer signs up for a membership, gets their own subdomain, and manages the settings of that subdomain alone. Customers, the content administrators who pay for a site, were called teachers until 2026-10-19; elsewhere, the host view and the host who reviews participants' history are the customer on their own site. The app becomes a service for many customers, each with their own site at their own subdomain of me0.ai, a free trial and a monthly plan. Each site works like the whole app does today, for its own customer and visitors, and later its participants. Features built after it (items 30 to 47 and 67 to 88) belong to a site from the start.

61. **Customer sign-up and the customer's account.** A customer signs up on me0.ai with their email address and a password, confirms the address from an email, and becomes the administrator (item 30) of their own new site, which starts as a free trial (item 62). Any number of customers can sign up. One customer account owns exactly one site *(default)*; a customer who wants a second site signs up again with another email address.
   - **Forgot password.** The sign-in page has **Forgot password**, which emails a link to set a new password. The link works once and for one hour *(default)*.
   - **Change email.** The customer can change their email address in the site's settings; the change takes effect only after they confirm it from an email sent to the new address, and the old address is told of the change.
   - **Support staff** (item 67) recover their own access the same way, by email; if that fails, a command on the server resets a staff password *(default)*.
62. **Free trial.** A new site starts a free one-week trial with the Light plan's limits (item 63) *(default)*. During the trial the site is reached at a path of random characters, such as `me0.ai/t/k7q2x9mf3a8w`, which works for the life of the trial; it has no subdomain yet (item 65). Apart from the address, a trial site works exactly as a paid one (Larry, 2026-10-19). No payment details are asked for to start it *(default)*, so there is one trial per email address, and the low limits keep the cost of repeated trials small *(default)*. The customer can cancel the trial at any time and is never charged. The site shows the days left in the trial to its customer, and when the trial ends without a plan, or is cancelled, the site pauses (item 64) until the customer picks a plan.
63. **Plans and upgrades.** Three monthly plans, most likely priced:
   - **Light:** $1 a month, for light use.
   - **Moderate:** $10 a month, for moderate use.
   - **Power:** $50 a month, for power users.

   What each plan allows (for example how many questions a month, PDFs or participants) is decided before the plans are built. Payment goes through a payment provider, so card details never reach our server *(default)*. A customer can upgrade from Light to Moderate or Power, or from Moderate to Power, at any time, and the new plan starts at once *(default: the provider charges the difference for the rest of the month)*. When a site reaches its plan's limit, the customer is told plainly and offered an upgrade; participants and visitors see a short, friendly notice *(default)*.
64. **Cancel, and a paused site.** A customer can cancel the trial or the subscription at any time from their site's settings. A cancelled subscription keeps the site working until the end of the billing period already paid for, then the site pauses; a cancelled trial pauses at once.
   - **A failed payment.** When a renewal charge fails, the site keeps working while the payment provider retries it, and the customer sees a notice asking them to update their payment details; visitors and participants see nothing *(default)*. If a retry or new card succeeds, the notice goes. If the provider finally gives up and ends the subscription, the site pauses as below, and the 30 days start then.
   - **While paused,** visitors and participants see a short notice and nothing else. The customer can still sign in, pick a plan to bring the site back as it was, save conversations and download their PDFs, or delete the site at once *(default)*.
   - **After 30 days paused,** the site is deleted *(default)*. Its subdomain stays reserved for it until then.
   - **Deleting a site.** The customer can delete their site at any time from its settings, paused or not, after confirming. Deleting a site, by the customer or after 30 days paused, removes everything it owns: the photo and voice and their prepared files, the content and wiki, the settings, the participant accounts, visitor conversations and history, and the feedback, contacts and tickets (items 66 and 73 to 76), along with the customer's account (item 61), and releases the subdomain. Any subscription is cancelled with the payment provider at once, so there is no further charge, with no refund for the current billing period *(default)*. Only billing records are kept (dates, plan and amounts, as the law requires), with none of the site's content *(default)*.
65. **Own subdomain.** The customer picks their site's name only when they sign up for the $1 Light membership, or go straight to a higher plan *(default)*, and are charged (Larry, 2026-10-19); it becomes the site's address, for example `smith-biology.me0.ai`, and shows the same site, with the same person, content, settings and history, that the trial path did. The trial path then redirects to the subdomain automatically, and is reserved so it is never used again, even if the site is later deleted (Larry, 2026-10-19). The name is checked as it is typed: it must be free, use only letters, numbers and hyphens, and not be a reserved name such as `support`, `www`, `api` or `admin`. The customer can change it later to any free name; the old name is released at once and the old address stops working *(default)*.
66. **Each site is separate.** Each site has its own person (photo and voice, or a default person), its own content (PDFs and wiki), its own settings, and its own participants, visitors and history (items 24 to 60). Nothing from one site is visible on another, and a customer can reach only their own site. Only the site's customer, signed in, manages its settings (items 8, 28, 29, 49 and 50), and a change applies to that site alone. The participant and visitor experience is saved per site: a participant's account, history and Teach me progress belong to that site, and an anonymous visitor's conversation is remembered on that browser for that site *(default)*.

### How this changes earlier items

Noted here and applied when the PRs for these items are built.

- **Deployment:** the hosted app serves every site from one service on me0.ai, each at its own subdomain over HTTPS.
- **Item 23 (Delete my data) and item 30 (Administrator sign-on):** they apply to one site, for that site's customer. Item 30 is built with the customers' sites, since each site's administrator is its customer, who signs in with the account from item 61 *(default)*.
- **Items 31 to 33 (anonymous questions, participant accounts, require sign-up):** built after the customers' sites, on each site for its own visitors and participants.
- **Item 29 (LLM choice):** chosen per site.

## Support at support.me0.ai

Added by Larry on 2026-10-17, to build after the customers' sites (items 61 to 66). Help for customers, participants and visitors, at `support.me0.ai`, open to anyone without signing in.

67. **Support site.** `support.me0.ai` has five things, each one click from its first page: the support guide (item 68), the support person (item 69), asking the AI (item 70), tickets (item 71) and feedback (item 72). A support administrator (the service's own staff) signs in to manage the guide, tickets and feedback.
68. **Support guide.** A PDF that explains the service: signing up, the trial, plans, upgrading and cancelling, picking and changing the subdomain, and setting up the person, content, settings and participants. Anyone can read or download it, and it is the content the support person and the AI answer from.
69. **Support person.** A video of a person who answers questions, made with the app itself: a talking person on the support site whose content is the support guide, answering spoken or typed questions as a customer's site does (items 9 to 12 and 27).
70. **Ask the AI.** A question typed to the AI service is answered in text from the support guide, for those who would rather read than watch. When it can't answer, it says so and offers to open a ticket. Answers that also draw on the tickets come with item 76.
71. **Tickets.** Anyone can open a support ticket with a title and a description. Tickets are open: anyone can see the list, search it and read any ticket with its replies. Each ticket has a status: Open, In progress, Waiting for reply, Resolved or Closed *(default)*, changed by the support staff, who can also reply.
   - **Public by design, private where it must be.** Before a ticket is opened, a clear warning says its title and description will be public. Only the exact title and description the visitor approves become public; an email address or other contact detail is never shown. Support staff can hide or delete a ticket or a reply, for spam, abuse or personal information shared by mistake.
   - **Replying.** Whoever opens a ticket gets a private link to it, shown when it is opened and sent by email if they gave an address. Only that link lets someone reply as the opener, so the staff can ask a follow-up (setting the status to Waiting for reply) and the opener can answer; other visitors can read a public ticket but not reply to it *(default)*.
   - **Email updates.** Whoever opens a ticket, and anyone else interested in it, can give an email address to be told by email whenever its status changes or the staff reply; the opener's emails carry their private link. It is optional, updates start only after the address is confirmed from a first email, so no one can sign up someone else's address, and each email has a link to stop them.
72. **Feedback.** A short form for feedback on the service, with an optional email address for a reply. Feedback is seen only by the support staff, not shown publicly *(default)*.

## Gathering information from visitors and tickets

Added by Larry on 2026-10-17, as its own milestone after support (items 67 to 72). The AI can gather feedback and contact information in conversation, and the service can get information back out of what visitors said and what tickets hold. It works on the support site, and on a customer's site when its customer turns it on (off by default) *(default)*.

**Where it is kept.** What is gathered belongs to the site it was gathered on *(default)*. On the support site, feedback and tickets are the support site's own (items 71 and 72). On a customer's site, feedback, contact details and tickets are kept for that site only: its customer sees and manages them on a feedback page and a tickets page of their own, and they are private, never in the public list on support.me0.ai and never seen by other sites, their visitors or the support staff. A customer's site's tickets have the same statuses and confirmed email updates as item 71, with the customer in the support staff's place.

73. **Gathering feedback.** When something said in a conversation is feedback (praise, a complaint, a request or a problem), the AI asks whether to pass it on, and if the visitor agrees it is saved as feedback (item 72) with the conversation it came from.
74. **Collecting contact information.** The AI asks for a name and email address only when it needs them, for example for a reply, a ticket or a follow-up, says why, and saves them only if the visitor agrees. It never asks for anything more sensitive. Contact details are seen only by that site's customer or the support staff, and are deleted on request. Deleting them removes the name and email from every copy the service keeps, not only the contact list: they are blanked out of the saved conversation, any feedback or ticket made from it, and the search index, so no later search or question (item 76) can find them.
75. **Opening a ticket from a conversation.** When the AI can't solve a problem, it offers to open a ticket (item 71) and drafts its title and description from the problem only, never including contact details or unrelated parts of the conversation. The visitor can edit the draft, and the ticket is opened only once they approve it, with their email for updates if they gave one (confirmed as in item 71). On the support site the visitor first sees the public warning and the ticket joins the public list; on a customer's site the ticket is private to that site and its customer, so no public warning is shown.
76. **Retrieving information.** On the support site, the AI answers visitors from the public tickets as well as the content; a customer's site never answers visitors from its private tickets. Ticket text written by visitors is treated as an unconfirmed report and never as instructions; only the status and replies of whoever manages the ticket count as confirmed (the support staff on the support site, the customer on their own site). So a support-site visitor asking about a known problem is told it has been reported, or that support has confirmed it, with the ticket linked. A customer (for their site) or the support staff (for the support site) can also ask the AI about what was gathered, such as "What are visitors asking about billing?", "Summarize the open tickets about subdomains" or "Who asked to be contacted this week?", and get an answer that links to the feedback, contacts, conversations and tickets it came from.

## Contexts

Added by Larry on 2026-10-17, first planned to build after settings, exit and return (items 8, 13, 14, 19 and 23). On 2026-10-18 Larry moved it to build after sign-on and accounts (items 30 to 33), the customers' sites (items 61 to 66) and support (items 67 to 72), and before interaction history (items 34 to 37). Depending on the prompt, different contexts are relevant, and they decide how the AI responds. So far the app has two without naming them: **Teacher/Student** (answering questions, Teach me, Quiz me and the assessment) and **Meta** (talking about the process or a step in it rather than the content, such as repeating a question or giving examples). Many more are possible, such as Salesperson/Customer, Support Staff/Customer and Person Away/Person Contacting, and each one should be customizable and open to specification.

77. **What a context is.** A context has five parts (Larry, 2026-10-17):
   - **Guidelines:** text describing how the AI behaves in it, which the administrator can change.
   - **Criteria:** what triggers it: a statement or question, or a description of the statements or questions that do.
   - **Logic:** the code and prompts that carry it out.
   - **Available:** a setting that turns it on or off.
   - **Debug:** a way to see which context was taken for a given response (item 82).
78. **Primary and supplementary contexts at once.** Contexts are simultaneous. One primary context is going on all the time, such as Teacher/Student, and supplementary contexts, such as Meta or support, sit alongside it. Each prompt is checked against the criteria of the available supplementary contexts first; one whose criteria match responds, and otherwise the primary context does. A supplementary context responding doesn't end the primary one: asking for a quiz question again (Meta) leaves the quiz where it was (Teacher/Student). The guidelines of the primary context always apply, with those of a supplementary context that responds added *(default)*.
   - **The question scope rule (item 28) belongs to Teacher/Student.** Contexts are matched before it is applied, and it applies only to a prompt that Teacher/Student responds to. A prompt taken by another context, such as Meta, Out of office or Salesperson/Customer, is never declined by it, just as "What can you talk about?" is answered with general prompts off (item 52) *(default)*. Turning a context on is how the administrator allows those prompts, so a context whose criteria are too broad lets more through; the Debug line (item 82) shows which context took a prompt.
79. **The two built-in contexts.** Today's behaviour becomes two contexts, with the same replies as before:
   - **Teacher/Student** (primary): answering questions from the content (items 27 and 28), the topic hints (item 53), Teach me, Quiz me (item 54) and the assessment (item 55). Their settings (Teach me, Quiz me and Assessment on or off) become this context's options.
   - **Meta** (supplementary): "What can you talk about?" (item 52); repeating a question, explaining what it means, a hint, "I don't know", checking a guess and questions about the quiz or assessment itself (items 54 and 55); giving examples; and a lesson's Next, Say it more simply and Stop.
80. **Choosing the contexts.** The administrator decides which contexts are available and which one is primary, on a Contexts page. Administrator sign-on (item 30) is built first, so it is in the host view, which only the administrator gets (item 51) *(default)*. The page lists the contexts in order of priority, and when two available supplementary contexts match a prompt, the higher one responds. Meta comes first, then the sample contexts (item 83), then added ones in the order they were added; the administrator can move any of them up or down *(default)*. A context turned off is never taken: with Meta off, "What's the question?" in a quiz is judged as an answer.
81. **Changing and adding contexts.** The administrator can change any context's guidelines and criteria, and set them back to how they shipped. In the built-in contexts, the guidelines change only the replies the LLM writes: answers, lesson parts, quiz and assessment questions and judgements, explanations of a question, hints and examples. Replies made by the code stay as they are whatever the guidelines say: the topics list, a question repeated, "How many are left?", a lesson's Next and Stop, and the scores and evaluation *(default)*. So editing Teacher/Student's guidelines changes how it teaches and answers, and editing Meta's changes how it explains, hints and gives examples. Criteria can be changed for both. They can add a new context from a name, primary or supplementary, guidelines and criteria. A new context's logic is the same for all of them: its guidelines are given to the chosen LLM (item 29) as instructions, with what the content has on the prompt (item 27). The administrator writes no code *(default)*, so code-based logic is only in the built-in contexts. Criteria are example statements or questions, matched like "What can you talk about?" (item 52), or a description in words, judged by the chosen LLM.
82. **Which context responded.** With Debug on in the settings, each reply shows which contexts were taken (the primary and any supplementary one), what the context did (for example "repeat the question") and why: which criterion matched, or that none did and the primary context responded. The same is in the log for every reply, and in the copied chat.
83. **Sample contexts.** Salesperson/Customer, Support Staff/Customer and Person Away/Person Contacting ship as examples, off by default, each with guidelines and criteria the administrator can change, to show how a context is specified *(default)*.

### How this changes earlier items

Noted here and applied when the PRs for these items are built.

- **Items 49 to 51 and 54 to 55 (settings):** the Teach me, Quiz me and Assessment switches move onto the Teacher/Student context on the Contexts page; the Debug setting also shows which context responded.
- **Item 30 (Administrator sign-on):** only the administrator reaches the Contexts page.
- **Item 66 (Each site is separate):** each site has its own contexts.

## Identity and guidelines

Added by Larry on 2026-10-18, to build right after contexts (items 77 to 83). The **identity** says who the AI is, so it can answer questions about itself, and the **guidelines** customize how it behaves, with goals and rules for the contexts it supports. Defaults are generated, the user changes them in the browser under **Customization**, and every change is kept.

84. **Identity.** Details of who the AI is: its name, who it is speaking as, its purpose, who it is for and what it can help with. It is given to the LLM with every prompt, so replies stay in keeping with it, and questions about the AI itself, such as "Who are you?" or "What is your purpose?", are answered from it. Those questions are a Meta action, so they are answered even with general prompts off (item 78) *(default)*.
85. **Guidelines.** Customizations of how the AI behaves: its goals (for example "Help participants understand the course well enough to pass the exam") and rules for each supported context, which are that context's guidelines (item 81). Goals apply to every reply, as the identity does. The identity, the goals and every context's guidelines are kept together in one place, which is the only copy; the Contexts page keeps each context's name, kind, criteria, availability and priority, and links to its guidelines, which are edited under Customization *(default)*.
86. **Generated defaults.** The first time the identity is needed, a default identity and guidelines are generated by the chosen LLM from what the app already knows: the person's name and role if given (item 57), the topics in the content (item 52) and the available contexts. Generation drafts the identity, the goals, and the guidelines of each context whose guidelines are still as shipped, tailored to that person and content; guidelines the administrator has changed, and those of an added context (written by the administrator when it is added, item 81), are never replaced *(default)*. Nothing waits for it: until it finishes, the shipped default identity and goals are used, so the first reply is never slowed. It has a time limit of 2 minutes *(default)*; if it times out or fails, the shipped defaults stay and the log says why. If the user saves a change while it is running, its result is dropped so the change is kept. A **Generate again** button makes a new draft from what the app knows then, which the user can save or discard.
87. **Customization.** A **Customization** page, with that heading, shows the identity and guidelines and lets the user edit and save them in the browser. Administrator sign-on (item 30) is built first, so only the administrator reaches it, in the host view (item 51) *(default)*. A change takes effect from the next prompt.
88. **Change history.** A version is the identity, the goals and every context's guidelines as they were at one moment. The shipped defaults are the first version. Every save, the automatic first generation, and every go-back keeps a new version, with when it was made and what made it; a generated draft becomes a version only when it is saved. All versions are kept *(default)*. The user can compare the latest version with the one before it, or with any earlier one, with the differences marked; go back to an earlier version, which becomes the latest as a new version so going back can itself be undone; and edit the latest version and save the edit as a new version. Going back changes only the identity, goals and guidelines, never which contexts are available, their priority or criteria. A context deleted since the earlier version is left out; a context added since keeps its current guidelines.

## Handling disputes

Added by Larry on 2026-10-21, to build last, after every other item. Someone may dispute a photo or a voice that a site uses without the right to it. This adds a way to dispute a custom photo or voice, which turns it off at once and falls back to a default person; simple messages with a clear notification; a way to dispute the dispute, offline, with the service's admin; and a third role, the admin, distinct from the host.

89. **Three roles: admin, host and participant.** Disputes are handled by an **admin**, who runs the service as a whole and is distinct from the host (Larry, 2026-10-21):
   - **Admin:** the service's own staff. Receives disputes and messages, sends messages to hosts and participants, and decides disputed disputes (item 94). Not tied to one site.
   - **Host:** the customer who manages one site (items 30 and 61), as today.
   - **Participant:** a signed-in participant of one site (item 32). An anonymous visitor (item 31) is not a role but can still dispute (item 91) and contact the admin (item 90).

   Elsewhere in this file "administrator" means a site's host (items 30, 51, 80, 87); the admin of this item is a different role.
90. **Messages and notifications.** The admin can send simple text messages to a host or a signed-in participant, and they can reply. When there is an unread message, it is clear: a notification mark with the number unread shows on every page until it is read *(default)*. Messages are kept on the site in an inbox *(default)*.
   - **Contact the admin.** Any host or participant can, at any time, send the admin a message about any issue, from a **Contact admin** link. An anonymous visitor can too, with an email address or phone number for the reply *(default)*.
91. **Disputing a photo or a voice.** A participant or visitor sees a clear **Dispute this image or voice** link wherever the person is shown. It opens a form that asks:
   - what is disputed: the image, the voice, or both;
   - an explanation of why they feel the host does not have the right to it;
   - an email address and a phone number, or for each one that is missing, a reason it is not available.

   Only a custom image or voice, one the host uploaded or recorded (items 1 and 59), can be disputed; a default person's picture is of a made-up person and its voice a licensed preset (items 57 and 58). On a default person, the link says so and offers **Contact admin** instead *(default)*. A dispute goes through only when every field is filled in, nothing in it is nonsense (for example an explanation of random letters, or an email or phone number that can't be real), what is disputed is custom, and the disputer has verified their email or phone (item 92). Then it sends a message to the admin, and one to the host of the site that uses that custom image or voice (item 90), and the image or voice is turned off (item 93).
92. **Verifying the disputer.** Before a dispute is allowed, the disputer confirms either their email address or their phone number, with a code sent to it, so that their identity is confirmed. Until then the dispute is held and nothing is turned off. The form says plainly that if this process doesn't work for them (for example they have neither, or no code arrives), they can message the admin directly with the full details (item 90) and must then wait for the admin to get back to them.
93. **What a dispute does.** As soon as a dispute goes through, the disputed image or voice, or both, is turned off on that site, and the site falls back to a default avatar: a disputed image is replaced by a default person's picture, and a disputed voice by a ready-made voice (item 58) *(default)*. The host's own files are kept, not deleted, until the dispute is decided *(default)*. Which default avatar is used is still to be picked (see the roadmap's decisions).
94. **Disputing the dispute.** The host, told of the dispute by a message (item 90), can dispute it. This happens offline: the host messages the admin, and the admin decides. The admin can then turn the image or voice back on, or keep it off, and tells the host and the disputer by message *(default)*.
95. **Cancelling a dispute.** The disputer can cancel their dispute:
   - **Signed in:** a participant who disputed while signed in (sign-in may be required by the host, item 33) must sign in to cancel it.
   - **Anonymous:** a visitor must enter the same phone number and email address again, or "NA" for whichever was not included in the dispute.

   Cancelling turns the image or voice back on at once, unless the admin has decided otherwise, and tells the admin and the host by message *(default)*.

### How this changes earlier items

Noted here and applied when the PRs for these items are built.

- **Items 30, 51, 80 and 87 (administrator):** the "administrator" there is the site's host, not this admin. Whether to rename them to host is open.
- **Item 66 (Each site is separate):** the admin is the one role that reaches every site, for disputes and messages only.
- **Item 67 (Support staff):** whether the admin is the same as the support staff, or a separate account, is open.

## iOS and Android

Added by Larry on 2026-10-22, after handling disputes: the app on iPhones and Android phones. The phone is a client of the hosted service *(default)*: the LLM, the voice and the video stay on the server, as they are today, and the phone sends prompts, uploads and plays the clips.

96. **Phones in the browser.** The hosted app works in Safari on an iPhone and Chrome on an Android phone, held upright: setup, the chat with its video and sound, settings and the host's pages. Photos can be taken with the phone's camera and recordings made with its microphone. The site can be added to the home screen and opens full screen.
97. **iOS and Android apps.** An app for each, built from the same web code as the site *(default)*, that connects to a site on me0.ai. It needs a connection; nothing is rendered on the phone.
98. **Signing in from an app.** The first time, the user enters their site and signs in as its host or a participant, and stays signed in until they sign out.
99. **Microphone, camera and speech.** The app asks for each only when first used, with a plain reason, and keeps working without it if refused. Hold to talk uses the phone's speech recognition.
100. **Behaving like a phone app.** Replies play aloud even with the silent switch on *(default)*, the screen stays on while the person speaks, and a reply stops when the app is left or a call comes in.
101. **In the stores.** The apps are free in the App Store and Google Play, with the privacy details each store asks for and, in the app, deleting data and the account, disputes and Contact admin. Memberships (item 64) are bought on the website, not in the app *(default)*.

## Safe photos

Added by Larry on 2026-10-24, to build right after the identity and guidelines (items 84 to 88). A photo that shows nudity or sexual content, or that isn't a photograph of one real person's face, is never stored or used. The checks run on the server's own CPU with on-device models, with no cloud service, so photos never leave the server and there is no per-use cost *(default)*.

102. **No nudity or sexual content.** Every image is checked as it is uploaded, before it is converted, stored or shown. One found unsafe, or near the limit *(default)*, is deleted at once, never kept or shown, and refused with a plain message: "This photo can't be used. Please choose a head-and-shoulders photo of the person." If the check can't run, the photo is refused, not let through.
103. **Only a real person's face.** Beyond item 2's exactly one face, the picture must be a photograph of a real person, not a drawing, cartoon, painting, statue, doll, mask, animal or photo of a screen *(default)*, and the face must be the main subject of the picture.
104. **Head and shoulders only.** The picture the video engine animates is cropped to the head and shoulders, so nothing below the shoulders can appear in any video.
105. **Every way a photo comes in.** The checks apply to Setup, changing photos in Settings (item 8), each customer's site (item 66) and photos taken on a phone (item 96). Photos stored before the checks existed are checked once and removed if they fail. The default people (item 57) are checked once when packed.

## UI simplification

Added by Larry on 2026-10-25, to build right after safe photos (items 102 to 105). The pages were built to be complete, which helped with debugging; for release they show only what their user needs, with a clean, professional look.

115. **Details hidden or removed.** The details that were there for debugging, such as timing metrics, step lists, scores, ids, file names, sizes, model names and counts, are not shown unless one **Show details** setting turns them on, off by default *(default)*. It takes in the timing metrics setting (item 49) and Debug. A detail no user needs is removed from the page; the log keeps it.
116. **One main thing per page.** Each page leads with the one thing its user came to do: chat, set up, pick an avatar, manage the PDFs, read the wiki or change a setting. Everything else is smaller, in a menu or closed until opened, and a step or choice already done is shown as one line. Nothing a host still needs is lost: it moves, not away.
117. **A clean, professional look.** Every page uses the same spacing, headings, buttons and messages, with short, plain words, so the app looks like one finished product (item 48).
118. **Measurably simpler.** Each page's visible words, buttons and links, and sections are counted before the redesign and after, in both views, and each page ends with fewer.
