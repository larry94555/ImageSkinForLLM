# ImageSkinForLLM: Features

A web app that puts a talking video of a real person on top of an LLM. The user types or speaks a prompt; the reply is shown as text and spoken by a video of the person, in their cloned voice, lip-synced to the text.

Items 1 to 16 match the original feature list. Items 17 to 23 were added after review. Items 24 onward add question and answer over PDF content (Larry, 2026-10-08), items 48 to 51 give it a professional look with a student and a teacher view (Larry, 2026-10-13), items 56 to 59 let a user start at once with a default person, and item 60 gives them a range of faces to choose from (Larry, 2026-10-16). Items 61 to 76 turn the app into a paid service for many teachers on me0.ai, with a support site and an AI that gathers feedback and contact information (Larry, 2026-10-17); they come after everything above. Items marked *(default)* are choices made pending Larry's confirmation.

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
25. **Kinds of PDF.** Each PDF holds text, slides or data tables, and each kind is processed so its content can be used for answers. Scanned PDFs (pictures of pages, which would need OCR) are not read for now; their pages are shown as having no text *(default)*.
26. **Knowledge wiki.** Because the PDFs can be large, processing builds a wiki that represents the knowledge in them. The wiki makes it easy for the administrator to review what was processed and to correct it. Adding, removing or replacing a PDF updates the wiki; a page the administrator corrected is not silently overwritten when its PDF is processed again *(default)*. The wiki reads as an outline (Larry, 2026-10-12): each PDF has a table of contents whose entries are either summarized in a few sentences, when simple enough, or summarized briefly with a link to a detail page of their own, which follows the same pattern for its parts.
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
35. **My history, and deleting from the record.** A signed-in student sees their own history. Changed by Larry on 2026-10-17 (before, a student's clear only hid their history from them and kept it for the administrator):
   - **The teacher (administrator, or the host in a business) can delete** any question, with its answer, from the chat history, on the user history page (item 36).
   - **The student can delete** any of their own questions, with its answer, from their history, so a statement they don't want on their record is not kept, but only when the setting below allows it.
   - **Student deleting setting.** A setting chooses whether students can delete parts of their chat history. A business would usually turn it off, so the record stays complete; a school may need it on. Off by default *(default)*.

   A deleted question is removed from the record for everyone, the administrator included: it is no longer in the history, search, topics, ratings, statistics, summaries or profile (items 36 to 47). The log notes only that a question was deleted and by whom, never its words *(default)*. Deleting one question needs no save first (item 37). The delete is permanent: the app keeps a list of deleted turn ids, without their words, so a file saved before the delete can't load the turn back (item 37), and any summary of older turns sent to the LLM (item 15) that included it is rebuilt without it.
36. **User history page.** The administrator has a page with every prompt and every answer not deleted (item 35), organized by date and time, by signed-in user, or as anonymous, to review everything that has happened.
37. **Save before clear, and load.** Larry, 2026-10-08:
   - **Save.** The conversation can be saved to a file.
   - **Clear only what was saved.** Clearing a conversation (item 8's "Clear conversation") needs the conversation to be saved first. Only the parts that were saved successfully can be cleared; anything not saved successfully cannot be cleared and stays.
   - **Load.** A saved file can be loaded back into the conversation history. Loading adds to the existing history and never replaces it, and it is idempotent: loading the same file again, or a file whose turns are already in the history, adds nothing twice. A turn deleted since the file was saved (item 35) is skipped, never added back.

### How this changes earlier items

These are noted here and applied when the PRs for these items are built; the earlier items keep their wording until then.

- **Item 8 (Settings):** the Settings link shows only to the signed-in administrator, not on every screen. Its "Clear conversation" follows item 37: save first, and only saved turns are cleared.
- **Deployment ("single user"):** the hosted app now has one administrator, student accounts and anonymous visitors.
- **Items 9 to 15 (Chat):** the chat becomes the question and answer screen; conversation history is kept per visitor.
- **Item 16 (LLM interface):** item 29 adds Grok, OpenRouter and subscriptions to the Claude and OpenAI keys planned there.
- **Item 23 (Delete my data):** an administrator action, since only the administrator has the photos and recordings.

## Student insights

Added by Larry on 2026-10-09. These build on the history in items 34 to 37 and change none of the items above. They are for the administrator, except item 46, which students see.

### Topics and understanding

38. **Topics.** The topics are the knowledge wiki's topic pages (item 26), so they follow the content as PDFs are added, removed or replaced *(default)*.
39. **Topic of each question.** A question's topics are the wiki pages the lookup in item 27 found for it, kept with the question; there is no second classification. A question can have no topic (for example a general prompt allowed by item 28), one, or several. Questions already in the history when this is added, and history loaded later from a file (item 37), are tagged the same way. Tags are not rewritten when the wiki changes; a topic whose page was removed is shown as removed.
40. **Understanding shown by each question.** Every question from a signed-in student is rated for each of its topics, so one question can be strong for one topic and unrated or weak for another:
   - **strong:** the question itself shows correct use or connection of the topic's concepts.
   - **weak:** the question contains a clear misconception about the topic.
   - **unrated:** the question gives no clear evidence either way, including ordinary fact-seeking questions. A basic but reasonable question is unrated, not weak.

   Each rating keeps a one-line reason. The administrator can correct a rating; the correction is kept with it and is never silently overwritten. Ratings are seen only by the administrator, never by students *(default)*.
41. **Student profile.** For each student: each topic they asked about, with their strong, weak and unrated questions on it (item 40). There is no score: topics are broad and made of subtopics, so a student can be strong on some subtopics and weak on others, and a topic with both strong and weak questions shows both. The questions listed under the topic show which subtopics they were about. It is worked out from items 39 and 40 whenever it is needed, not kept separately, and shown on the student summary page (item 45).

### Search

42. **Search one student's history.** On the user history page (item 36), the administrator searches the conversation history of a chosen student, by words in the questions and answers, and can narrow by date and topic.
43. **Search all histories.** The same search on the same page across the conversation histories of all students. Anonymous questions are included and marked as anonymous *(default)*.

Search never finds a deleted question or its answer (item 35).

### Statistics and summaries

44. **Topic statistics page.** For each topic: how many questions were asked about it, which topics were not asked about at all, and how many strong, weak and unrated questions it drew (item 40), as counts by question type rather than a single score. Topic counts include anonymous questions; strong and weak come from signed-in students only.
45. **Student summary page.** One page per student showing their profile (item 41): each topic they asked about, with the counts of their strong, weak and unrated questions on it and the questions themselves.

### Deleting from history

46. **Heads-up before deleting.** When a student or the teacher deletes a question (item 35), a confirmation says: "Deleting removes this question and its answer from the record for everyone. This can't be undone." The delete goes ahead only after they confirm. Changed by Larry on 2026-10-17; before, it said a cleared conversation stays available to the administrator.

## Interests and personality

Added by Larry on 2026-10-09, after the student insights above. It builds on the history (items 34 to 37) and the student profile (item 41) and changes none of the items above.

47. **Interests and personality profile.** For each signed-in student, a short profile that tries to characterize their interests and personality from the questions they ask and how they respond to the answers:
   - **Interests:** what they keep coming back to, inside the content and outside it, and the kind of question they like to ask (for example real-world examples, the reasons behind something, or its history).
   - **How they respond to answers:** from their next message after each answer, such as asking follow-ups and how deep they go, asking for examples or a simpler explanation, questioning or pushing back on an answer, moving straight on, or showing frustration or enthusiasm.

   Each line of the profile gives its evidence in one line and links to the questions it came from, and it is worded as an impression from their questions, not a fact or a judgment of the student. Anonymous questions are not used, and a student with too few questions has no profile yet. The administrator can edit or remove a line, and the change is never silently overwritten. The profile is seen only by the administrator, never by students, and is shown on the student summary page (item 45) *(default)*.

## A professional look

Added by Larry on 2026-10-13. The chat must be clean and professional enough to use in a commercial setting: judged only on how it looks and on answering typed questions, the app is clearly of professional quality. The teacher view must be usable by a non-technical teacher and the student view by a non-technical student. These come before spoken prompts (item 9's microphone).

48. **Professional look and clean video.** The video plays cleanly, as one steady picture of the person, with no controls, empty frames, flicker or jumps. Every page has one consistent look, and every message is short and plain, with no technical words, ids or error codes; the detail goes to the log.
49. **Metrics setting.** The timing metrics (such as the timing readout under the video) are hidden unless a setting turns them on. Off by default *(default)*.
50. **Student view and teacher view.** A setting chooses the view:
   - **Student view:** the chat, and read-only use of the wiki and the existing PDFs. The options to manage content, edit the wiki or change the setup are hidden.
   - **Teacher view:** every page and option. Teacher by default *(default)*.
51. **Anyone can change these settings for now.** Items 49 and 50 can be changed at will by anyone. Later this is restricted, and the view follows who is using the app:
   - **Administrator** (signed on, item 30): the teacher view.
   - **Signed-in student** (item 32): the student view.
   - **Anonymous visitor** (item 31): question and answer only, with no wiki or PDFs.

## Knowing what to ask, teach me, quiz me and the assessment

Added by Larry on 2026-10-14. Today nothing tells a student which topics they can ask about and which ones they can't, and the app only answers questions. Larry added the assessment (item 55) later the same day: Teach me should prepare a student to score 100% on it. These come after the professional look (items 48 to 51) and before spoken prompts (item 9's microphone). They work in the student and teacher views. Once accounts exist (items 30 to 32), anonymous visitors, who are question and answer only (item 51), get items 52 and 53 but not Teach me, Quiz me or the assessment *(default)*.

52. **"What can you talk about?"** A question like "What topics can you talk about?" or "What do you know about?" is answered with the topics in the content: the wiki's main entries (item 26), each named in plain words, in a short spoken answer that ends by suggesting one to ask about. It is answered even when general prompts are off (item 28), and then also says that questions outside these topics can't be answered. Before any PDF is added it says it can talk about anything.
53. **Topic hints.** The chat shows what can be asked before the student asks anything: a short line under the prompt box naming a few of the topics, and a few example questions drawn from the wiki that send the question when clicked. When general prompts are off, the line says questions must be about these topics. A prompt declined by item 28 names a few topics it can answer instead. The hints follow the content as PDFs are added, removed or replaced *(default)*.
54. **Teach me and quiz me.** Two buttons by the prompt box, also started by typing "teach me about …" or "quiz me on …". When no topic is named, each asks the student to choose one from the list in item 52; Teach me's list also offers **Everything, from the start**, which teaches the topics in order. Both use only the content, as answers do (item 27), and are spoken like any reply.
   - **Teach me:** the person explains the topic in short parts, one at a time, from the wiki and PDFs, going from the main ideas into the detail. After each part the student can ask a question about it, say "next", or ask for it again more simply. It goes on for as long as the student wants: when a topic is finished it gives a one-line summary, offers a quick quiz, and moves on to the next topic, until the whole content has been taught. The aim is that a student who stays to the end is ready to score 100% on the assessment (item 55). A student who stops can pick up where they left off: on that browser until accounts exist, then for each signed-in student, so students sharing a device don't share progress *(default)*.
   - **Quiz me:** the person asks one question at a time about the topic, drawn from the wiki and PDFs. The student types an answer; the reply says whether it is right, partly right or wrong, in a friendly way, with the correct answer and a one-line reason from the content. A quiz has 5 questions *(default)*, the student can stop at any time, and it ends with how many they got right and the parts worth going over again.
55. **Assessment.** An **Assessment** button, also started by typing "assess me" or "test me on everything", evaluates the student's knowledge of all the content, not one topic. It asks a sample of questions rather than everything. Each question is about one main topic and at one level, and counts toward both:
   - **Breadth:** every main topic in the wiki gets at least one question, and no topic gets a second until every topic has one.
   - **Depth:** questions come at three levels: recalling a fact, explaining an idea in their own words, and applying or connecting ideas. Deeper questions come from the wiki's detail pages. The questions are split as evenly as possible across the three levels, so each level has at least a third of them, rounded down.

   Questions come one at a time and are judged as in quiz me, but the correct answer is shown only at the end, so the assessment isn't taught as it goes. It has 15 questions, or one per main topic when there are more than 15 topics, so every level has at least 5 *(default)*. It ends with an evaluation: the overall result, a breadth result (the topics answered well out of all the topics), a depth result for each level, and the topics and levels to go over again, with an offer to start Teach me on them.

## Starting with a default person

Added by Larry on 2026-10-16, for testing. A user can start chatting at once, without uploading a photo or recording their voice, by choosing a default person. The app makes a picture of that person and gives them a ready-made voice, and the user can replace either with their own later.

56. **Default person choices.** The first setup screen offers **Start now with a default person** beside the usual upload. The user picks:
   - **Gender:** male or female, for the picture and the voice.
   - **Accent:** British or American.
   - **Realism:** photorealistic or animated.
   - **Role:** Professor, Teaching Assistant, Student, Parent, Teenager, Boss (corporate executive, professional), Office Manager, High School Teacher, or Business Consultant.

   The roles don't carry a gender; the gender choice decides it. Where a role has a word for each gender, the list shows that word: Father or Mother for Parent, Son or Daughter for Teenager. Changing the gender after picking a role keeps the role and changes the person to match, so Mother becomes Father *(default)*.
57. **Generated picture.** The picture is made to fit the choices: the person's gender, an age, clothes and a setting that suit the role, photoreal or animated. Each of the 36 is checked before it ships: it passes the same checks as an uploaded photo (item 2), and a short line is rendered to show it talks and idles like one. That is why the sample video and review can be skipped (item 58). Every picture is of a made-up person: it is not based on a real person or a public figure, and the prompts used to make it name none. Since accent doesn't change the picture, there is one picture for each gender, realism and role: 36 in all, 24 of them with a second face (item 60). They are made and prepared ahead of time, so choosing one doesn't wait for the one-time prepare step (item 5) *(default)*.
   - **Getting the picture.** Only the chosen person's picture and prepared frames are downloaded, when they are first chosen, and kept for next time; the others are never fetched unless chosen *(default)*. Only the small thumbnails used to pick a face (item 60), under 1 MB for all of them, ship with the app. A person already downloaded starts at once. Otherwise the screen shows the download's progress and goes to the chat when it ends. If it fails, a plain message says so with **Try again**, and the usual upload is still offered.
   - **Start now means:** no uploads, recordings or prepare step. The only wait is that one person's download the first time they are chosen, which is at most 50 MB, so it takes 20 seconds or less at 25 Mbit/s.
58. **Default voice.** The voice is one of Kokoro's ready-made voices for the chosen gender and accent, which ship with the app under its license, not a clone, so there are no recordings to check. They are `af_heart` (American woman), `am_michael` (American man), `bf_emma` (British woman) and `bm_george` (British man), picked in R24a for their grades in Kokoro's voice list; Kokoro and its voices are Apache 2.0. The user isn't asked for consent (item 22): they supply no one's picture or voice, the picture is of a made-up person (item 57), and the voice is a licensed preset rather than a clone of someone the user brings. Setup goes straight to the chat; the sample video and review (items 6 and 7) are skipped, and the Goodbye and Welcome back lines are spoken in the default voice.
59. **Replace with your own.** At any time the user can replace the default picture with their own photos, or the default voice with their own recordings, or both. Each goes through the usual checks, prepare and review for what is replaced (items 1 to 7), and the part not replaced stays as it was. Consent (item 22) is asked for each real person brought in:
   - **Own photo, default voice:** the user confirms the person in the photos agreed to have their picture animated.
   - **Default picture, own voice:** the user confirms the person in the recordings agreed to have their voice cloned.
   - **Own photo and own voice:** as in item 22, the user confirms they are the same person and that this person agreed to be cloned. A photo of one real person with the voice of another is not allowed *(default)*. When one part is already the user's own and the other is replaced, the consent repeats that both are the same person.
60. **A range of faces.** 60 default people for now, at most (Larry, 2026-10-17): the 36 of item 57 and a second face for 24 of the choices, six for each gender and realism *(default)*. Across the 15 people of each gender and realism, every one of eight broad heritages appears with hair to suit, at least one has red hair and one blond hair, at least three wear glasses, at least three are in their 60s or 70s where the role suits it (not Teenager, Student or Teaching Assistant), and at least two have a visible disability, such as a wheelchair or a hearing aid (Larry, 2026-10-17), so more people can find a default person who looks like them. Each is checked, prepared and downloaded like the 36 (item 57). After the four choices, a choice with two faces shows both as small pictures and the user picks one. No face is labelled with a heritage, skin tone, ethnicity, age or disability anywhere the user sees: they are shown only as pictures (Larry, 2026-10-16).

## Many teachers on me0.ai

Added by Larry on 2026-10-17, to build after every item above. The app becomes a service for many teachers (content administrators), each with their own site at their own subdomain of me0.ai, a free trial and a monthly plan. Each site works like the whole app does today, for its own teacher, students and visitors.

61. **Teacher sign-up and the teacher's account.** A teacher signs up on me0.ai with their email address and a password, confirms the address from an email, and becomes the administrator (item 30) of their own new site. Any number of teachers can sign up. One teacher account owns exactly one site *(default)*; a teacher who wants a second site signs up again with another email address.
   - **Forgot password.** The sign-in page has **Forgot password**, which emails a link to set a new password. The link works once and for one hour *(default)*.
   - **Change email.** The teacher can change their email address in the site's settings; the change takes effect only after they confirm it from an email sent to the new address, and the old address is told of the change.
   - **Support staff** (item 67) recover their own access the same way, by email; if that fails, a command on the server resets a staff password *(default)*.
62. **Free trial.** A new site starts a free one-week trial with the Light plan's limits (item 63) *(default)*. No payment details are asked for to start it *(default)*, so there is one trial per email address, and the low limits keep the cost of repeated trials small *(default)*. The teacher can cancel the trial at any time and is never charged. The site shows the days left in the trial to its teacher, and when the trial ends without a plan, or is cancelled, the site pauses (item 64) until the teacher picks a plan.
63. **Plans and upgrades.** Three monthly plans, most likely priced:
   - **Light:** $1 a month, for light use.
   - **Moderate:** $10 a month, for moderate use.
   - **Power:** $50 a month, for power users.

   What each plan allows (for example how many questions a month, PDFs or students) is decided before the plans are built. Payment goes through a payment provider, so card details never reach our server *(default)*. A teacher can upgrade from Light to Moderate or Power, or from Moderate to Power, at any time, and the new plan starts at once *(default: the provider charges the difference for the rest of the month)*. When a site reaches its plan's limit, the teacher is told plainly and offered an upgrade; students and visitors see a short, friendly notice *(default)*.
64. **Cancel, and a paused site.** A teacher can cancel the trial or the subscription at any time from their site's settings. A cancelled subscription keeps the site working until the end of the billing period already paid for, then the site pauses; a cancelled trial pauses at once.
   - **A failed payment.** When a renewal charge fails, the site keeps working while the payment provider retries it, and the teacher sees a notice asking them to update their payment details; visitors and students see nothing *(default)*. If a retry or new card succeeds, the notice goes. If the provider finally gives up and ends the subscription, the site pauses as below, and the 30 days start then.
   - **While paused,** visitors and students see a short notice and nothing else. The teacher can still sign in, pick a plan to bring the site back as it was, save conversations and download their PDFs, or delete the site at once *(default)*.
   - **After 30 days paused,** the site is deleted *(default)*. Its subdomain stays reserved for it until then.
   - **Deleting a site.** The teacher can delete their site at any time from its settings, paused or not, after confirming. Deleting a site, by the teacher or after 30 days paused, removes everything it owns: the photo and voice and their prepared files, the content and wiki, the settings, the student accounts, visitor conversations and history, and the feedback, contacts and tickets (items 66 and 73 to 76), along with the teacher's account (item 61), and releases the subdomain. Any subscription is cancelled with the payment provider at once, so there is no further charge, with no refund for the current billing period *(default)*. Only billing records are kept (dates, plan and amounts, as the law requires), with none of the site's content *(default)*.
65. **Own subdomain.** At sign-up the teacher picks their site's name, which becomes its address, for example `smith-biology.me0.ai`. The name is checked as it is typed: it must be free, use only letters, numbers and hyphens, and not be a reserved name such as `support`, `www`, `api` or `admin`. The teacher can change it later to any free name; the old name is released at once and the old address stops working *(default)*.
66. **Each site is separate.** Each site has its own person (photo and voice, or a default person), its own content (PDFs and wiki), its own settings, and its own students, visitors and history (items 24 to 60). Nothing from one site is visible on another, and a teacher can reach only their own site. The student and visitor experience is saved per site: a student's account, history and Teach me progress belong to that site, and an anonymous visitor's conversation is remembered on that browser for that site *(default)*.

### How this changes earlier items

Noted here and applied when the PRs for these items are built.

- **Deployment:** the hosted app serves every site from one service on me0.ai, each at its own subdomain over HTTPS.
- **Item 23 (Delete my data) and item 30 (Administrator sign-on):** they apply to one site, for that site's teacher.
- **Item 29 (LLM choice):** chosen per site.

## Support at support.me0.ai

Added by Larry on 2026-10-17, to build after the teachers' sites (items 61 to 66). Help for teachers, students and visitors, at `support.me0.ai`, open to anyone without signing in.

67. **Support site.** `support.me0.ai` has five things, each one click from its first page: the support guide (item 68), the support person (item 69), asking the AI (item 70), tickets (item 71) and feedback (item 72). A support administrator (the service's own staff) signs in to manage the guide, tickets and feedback.
68. **Support guide.** A PDF that explains the service: signing up, the trial, plans, upgrading and cancelling, picking and changing the subdomain, and setting up the person, content, settings and students. Anyone can read or download it, and it is the content the support person and the AI answer from.
69. **Support person.** A video of a person who answers questions, made with the app itself: a talking person on the support site whose content is the support guide, answering spoken or typed questions as a teacher's site does (items 9 to 12 and 27).
70. **Ask the AI.** A question typed to the AI service is answered in text from the support guide, for those who would rather read than watch. When it can't answer, it says so and offers to open a ticket. Answers that also draw on the tickets come with item 76.
71. **Tickets.** Anyone can open a support ticket with a title and a description. Tickets are open: anyone can see the list, search it and read any ticket with its replies. Each ticket has a status: Open, In progress, Waiting for reply, Resolved or Closed *(default)*, changed by the support staff, who can also reply.
   - **Public by design, private where it must be.** Before a ticket is opened, a clear warning says its title and description will be public. Only the exact title and description the visitor approves become public; an email address or other contact detail is never shown. Support staff can hide or delete a ticket or a reply, for spam, abuse or personal information shared by mistake.
   - **Email updates.** Whoever opens a ticket, and anyone else interested in it, can give an email address to be told by email whenever its status changes. It is optional, updates start only after the address is confirmed from a first email, so no one can sign up someone else's address, and each email has a link to stop them.
72. **Feedback.** A short form for feedback on the service, with an optional email address for a reply. Feedback is seen only by the support staff, not shown publicly *(default)*.

## Gathering information from visitors and tickets

Added by Larry on 2026-10-17, as its own milestone after support (items 67 to 72). The AI can gather feedback and contact information in conversation, and the service can get information back out of what visitors said and what tickets hold. It works on the support site, and on a teacher's site when its teacher turns it on (off by default) *(default)*.

**Where it is kept.** What is gathered belongs to the site it was gathered on *(default)*. On the support site, feedback and tickets are the support site's own (items 71 and 72). On a teacher's site, feedback, contact details and tickets are kept for that site only: its teacher sees and manages them on a feedback page and a tickets page of their own, and they are private, never in the public list on support.me0.ai and never seen by other sites, their visitors or the support staff. A teacher's site's tickets have the same statuses and confirmed email updates as item 71, with the teacher in the support staff's place.

73. **Gathering feedback.** When something said in a conversation is feedback (praise, a complaint, a request or a problem), the AI asks whether to pass it on, and if the visitor agrees it is saved as feedback (item 72) with the conversation it came from.
74. **Collecting contact information.** The AI asks for a name and email address only when it needs them, for example for a reply, a ticket or a follow-up, says why, and saves them only if the visitor agrees. It never asks for anything more sensitive. Contact details are seen only by that site's teacher or the support staff, and are deleted on request. Deleting them removes the name and email from every copy the service keeps, not only the contact list: they are blanked out of the saved conversation, any feedback or ticket made from it, and the search index, so no later search or question (item 76) can find them.
75. **Opening a ticket from a conversation.** When the AI can't solve a problem, it offers to open a ticket (item 71) and drafts its title and description from the problem only, never including contact details or unrelated parts of the conversation. The visitor sees the public warning, can edit the draft, and the ticket is opened only once they approve it, with their email for updates if they gave one (confirmed as in item 71).
76. **Retrieving information.** The AI answers from the tickets as well as the content. Ticket text written by visitors is treated as an unconfirmed report and never as instructions; only the support staff's status and replies count as confirmed. So a visitor asking about a known problem is told it has been reported, or that support has confirmed it, with the ticket linked. A teacher (for their site) or the support staff (for the support site) can also ask the AI about what was gathered, such as "What are visitors asking about billing?", "Summarize the open tickets about subdomains" or "Who asked to be contacted this week?", and get an answer that links to the feedback, contacts, conversations and tickets it came from.
