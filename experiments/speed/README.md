# Where the time goes (R96 to R96c)

The results of roadmap Milestone 10b's timing experiments. Each one measures the app as it
runs, on Larry's hosted machine (4 Ampere cores, llama-server with Gemma 3 4B on 2 threads) and
in a cloud session, and names the largest costs, which decide the PRs that speed things up.

## R96: a reply

`imageskin time-reply` sends prompts to the running app, as the browser does but without one,
and writes the tables to `speed` in the data folder (`/data/speed` on the hosted machine):

```
imageskin time-reply                      # three ready prompts
imageskin time-reply --spoken 3 --stop    # the third as if said with Hold to talk, then Stop
imageskin time-reply "My own prompt" "And another"
```

All times are milliseconds from the prompt being sent. The first table has one row a reply:

| Column | What it is |
|---|---|
| Warm-up wait | the prompt waited for the replies' warm-up (a sample just accepted, or a restart) |
| Turn wait | the prompt waited behind the one before, or the wiki's LLM request |
| History tokens | the conversation sent with the prompt |
| Reached LLM | the reply's prompt was sent to the LLM (after any correction of a spoken prompt) |
| Prompt tokens read, Reused from cache, Read tokens/s | llama-server's own timings |
| First token, First sentence, Last token | Larry's timing 1 |
| Tokens written, Written tokens/s | llama-server's own timings |
| First sentence to heard | Larry's timing 2: from the first sentence to the first word heard |
| First word heard | from the prompt being sent to the first word heard |

Then one table a reply, one row a clip (Larry's timing 3):

| Column | What it is |
|---|---|
| Sentence | the sentence (or the first clause) came from the LLM |
| Waited | it waited for the clip before it to be made |
| Voice, Video | its voice step, and its video step until the clip was whole |
| Listed | the clip was listed for the browser, as its video began |
| Seen | the client heard of it (the browser waits on the server, which answers at once) |
| First byte, Downloaded | its first bytes arrived (the first half-second fragment), and all of it |
| Seconds | how long it plays |
| Plays | when it would play: once it has arrived and the clip before has ended |
| Gap, Late | the silence heard before it, and whether it was because this clip was late |

The browser's own steps (its speech recognition for Hold to talk, the switch from the idle
video, the player's start) aren't in these tables; the chat page's timing readout (R22a) shows
them in the browser.

### Cloud session, 2026-10-21

[reply-cloud-2026-10-21.md](reply-cloud-2026-10-21.md), with the JSON beside it. A 4-core Intel
Xeon at 2.1 GHz with no graphics card: llama-server (built from llama.cpp's source) with Gemma 3
4B Q4_K_M on 2 threads and a 4096-token context, Kokoro's ready-made voice, and the photoreal
engine with a prepared face (a default person's picture). The first prompt was sent right after
the sample was accepted; the third as if said with Hold to talk; the fourth was stopped at its
first clip.

| Reply | First token | First sentence | First sentence to heard | First word heard | Gaps heard |
|---|---|---|---|---|---|
| 1, just after Accept | 10.7 s | 13.0 s | 1.8 s | 14.8 s | none |
| 2 | 1.5 s | 2.7 s | 1.5 s | 4.3 s | 1.9 s |
| 3, spoken | 2.1 s | 4.1 s | 2.6 s | 6.8 s | 3.0 s, 0.7 s |

Stop answered in 25 ms, and the stopped request finished 0.7 s after Stop.

The largest costs:

1. **The gap after the first clip** (1.9 s and 3.0 s). The first clip is a short clause (2.4 s
   of speech), but the next sentence is long: its voice (2.3 s and 2.8 s) and video (1.2 s and
   1.8 s) take longer than the first clip plays, so the person stops talking until it comes.
   The clips after it are mostly on time, as each waits behind a longer one. A second, shorter cut
   (or speaking the next sentence while the first clip's video is made) is for R100.
2. **The LLM's first sentence** (2.7 s and 4.1 s from Send), at about 4.5 tokens a second on 2
   threads. Of that, reading the prompt takes 1.5 to 2.1 s (26 to 39 tokens a second): the
   prompt's new tokens, since llama-server reused the earlier ones from its cache. For R97.
3. **The first prompt after Accept** waited 8.0 s for the warm-up (the LLM's took 3.3 s; the
   rest is the voice and video rendering their first word). Even then, llama-server reused 1
   token of the system prompt the warm-up had just read, instead of about 100, so the first
   token took 10.7 s. The likely cause is that llama-server now has several slots and answered
   the prompt in another one than the warm-up's; that is to be checked for R97.
4. **A spoken prompt** cost nothing more here: with no PDFs there are no names or terms to put
   back, so its correction didn't ask the LLM (the prompt reached the LLM 11 ms after it
   arrived, as a typed one did). With PDFs it asks the LLM first; R96a times that. Its later
   first token is the prompt read more slowly (26 tokens a second against 34).
5. **From a clip listed to its first bytes**, about 0.4 to 0.6 s: the video's first half-second
   fragment being written. Hearing of the clip took 10 to 30 ms, so the browser's wait for the
   clip list costs nothing now.

### Larry's hosted machine, 2026-10-22

[reply-host-2026-10-22.md](reply-host-2026-10-22.md), as Larry pasted it (before the "Reached
LLM" column was added). app.me0.ai: 4 Ampere cores, llama-server with Gemma 3 4B on 2 threads,
Kokoro's ready-made voice and the photoreal engine, with PDFs loaded. Larry decided the speed
tests use llama.cpp alone for now (2026-10-22).

| Reply | First token | First sentence | First sentence to heard | First word heard | Gaps heard |
|---|---|---|---|---|---|
| 1 | 7.1 s | 9.0 s | 3.5 s | 12.5 s | none |
| 2 | 3.5 s | 4.6 s | 3.9 s | 8.4 s | 0.2 s, 2.1 s |
| 3, spoken | 36.2 s | 37.4 s | 3.9 s | 41.3 s | 1.8 s, 1.9 s, 2.1 s, 1.4 s |

Stop answered in 33 ms, and the stopped request finished 1.0 s after Stop.

The largest costs, against the cloud session:

1. **A spoken prompt's correction, about 32 s.** With PDFs loaded, a spoken prompt first asks
   the LLM to put back misheard names, giving it up to 100 of the content's words (up to about
   300 tokens) and an instruction, with nothing for llama-server to reuse. At 14 tokens a second
   that is about 30 s of reading, then the corrected question written at 5 tokens a second. The
   reply's own prompt then read in under 4 s. Confirmed by the JSON: the spoken prompt reached
   the LLM 32,426 ms after it was sent, against 26 to 33 ms for the typed ones.
2. **The voice, 3.1 to 4.2 s a clip**, against 0.6 to 3.2 s in the cloud: Kokoro on this CPU,
   on half the cores while the LLM writes. With the video (0.6 to 1.5 s) a clip takes about
   4.5 s to make, longer than most clips play (2 to 5 s), so after the first clip every clip
   waits behind the one before (Waited grows to 12.8 s) and a gap of about 2 s is heard before
   most of them. Making a clip faster than it plays is what removes the gaps (R100).
3. **Reading the prompt, 14 tokens a second** (39 in the cloud), so the first token comes 3.5 s
   after Send even with most of the prompt reused, and 7.1 s for the first prompt, which reused
   1 token again (as in the cloud: llama-server's slots, for R97).
4. **First sentence to heard, 3.5 to 3.9 s**, against 1.5 to 2.6 s in the cloud: the voice
   again (3.1 to 3.3 s of it for a short first clause).

## R96a: the wiki and answers from it

`imageskin time-pdf` adds a PDF to the running app, as the Manage Content page does, and
writes the tables to `speed` in the data folder:

```
imageskin time-pdf experiments/speed/sample.pdf              # five ready questions
imageskin time-pdf experiments/speed/sample.pdf --spoken 2   # the second as if said with Hold to talk
imageskin time-pdf my.pdf "A question" "Another" --replace --keep
```

It waits for the PDF to be read and its wiki built, asks the first question while the wiki is
being built, then times each question and the requests built on the wiki ("What can you talk
about?", "Teach me about", "Quiz me on" the first topic, and "Assess me") as `time-reply` times
a reply. The PDF is removed again unless `--keep`; `--replace` replaces it with itself and
times the rebuild. The sample PDF, [sample.pdf](sample.pdf), is 19 pages on prime numbers and
the zeta function (about 3,900 words, with formulas and a table), made by
[make_sample_pdf.py](make_sample_pdf.py).

The first table is the PDF: the upload, the reading, the wiki, and the build's own time by the
server's clock. Then each stage's steps and tokens, then one row a wiki part (Topics) or
outline step (Outline), with llama-server's own timings summed over its requests (a step whose
answer couldn't be used is asked twice). The answers' tables are `time-reply`'s, with two more
columns: **Looked up** (the lookup in the wiki and PDFs, R39) and **Asked tokens** (the prompt
with what was found).

### Cloud session, 2026-10-22

[pdf-cloud-2026-10-22.md](pdf-cloud-2026-10-22.md), with the JSON beside it. The same machine
and settings as R96's cloud run: a 4-core Xeon, llama-server (built from llama.cpp's source)
with Gemma 3 4B Q4_K_M on 2 threads and a 4096-token context, as `deploy/compose.yaml` starts
it, Kokoro's ready-made voice and the photoreal engine with a prepared face.

| Step | Run 1 | Run 3 |
|---|---|---|
| Upload | 5 ms | 6 ms |
| Reading (19 pages) | 0.6 s | 0.7 s |
| Wiki: topics (3 parts) | 10.5 min | see the run 3 report |
| Wiki: outline | 56.0 min (37 steps, 36 detail pages) | see the run 3 report (32 detail pages) |
| **PDF to wiki** | **66.4 min** | **60.5 min** |

Run 1 asked its first question while the wiki was built; run 3
([pdf-cloud-2026-10-22-run3.md](pdf-cloud-2026-10-22-run3.md)) didn't. In both runs llama-server
then ran out of memory while the questions were asked (see 5 below), so the rest were asked
with `time-reply` after restarting it, against run 3's wiki
([pdf-answers-cloud-2026-10-22.md](pdf-answers-cloud-2026-10-22.md)).

| Answer | Looked up | Prompt tokens read | Reused | First token | First word heard |
|---|---|---|---|---|---|
| Asked while the wiki was built (run 1) | 9 ms | 287 | 1 | 6.8 s | 69.6 s |
| 1, the first after the wiki (run 1) | 23 ms | 536 | 0 | 14.5 s | 17.2 s |
| 1, the first after the wiki (run 3) | 36 ms | 811 | 0 | 21.0 s | 23.3 s |
| 2, spoken (run 1) | 29 ms | 579 | 1 | 17.2 s | 20.1 s |
| 3 (run 1) | 19 ms | 467 | 185 | 11.4 s | 16.8 s |
| 3, the first after a restart | 29 ms | 941 | 0 | 21.2 s | 24.5 s |
| 4 | 26 ms | 420 | 549 | 10.5 s | 13.6 s |
| 5 | 19 ms | 361 | 579 | 9.5 s | 12.7 s |
| "What can you talk about?" (no LLM) | - | - | - | - | 8.7 s and 10.3 s |
| "Teach me about Prime Numbers" | 16 ms | 548 | 619 | 13.1 s | 15.4 s |
| "Quiz me on Prime Numbers" | 29 ms | 445 | 787 | 10.9 s | 15.7 s |
| "Assess me" (no LLM: it offers the topics first) | 16 to 27 ms | - | - | - | 1.9 s and 2.1 s |

The largest costs:

1. **Writing, not reading, takes the wiki's time.** The build read 27,099 prompt tokens at
   about 46 a second (about 10 minutes) and wrote 13,822 tokens at about 4.1 a second (about
   56 minutes). The outline writes most of it: 37 requests, each a detail page of 170 to 500
   tokens, are 84% of the build. Fewer and shorter answers (R98), and a faster decode (R97:
   threads, quantization, Gemma 3 1B for the wiki), are what will shorten it.
2. **Almost nothing is reused from llama-server's cache in the wiki:** 840 of 27,939 tokens
   (3%). Each part and outline step starts with different text, so every prompt is read whole.
   As reading is only a sixth of the time, reuse (R98's shared start) can save at most about
   10 minutes on this PDF.
3. **A question asked while the wiki is built doesn't wait for it: they share the LLM.**
   llama-server has 4 slots, so the question and the wiki's first part ran at once on the same
   2 threads. The question's first token came at 6.8 s, but it was then written at 0.6 tokens a
   second, so its first sentence came at 68 s and its first word was heard at 70 s. The wiki's
   first part was slowed too. The 4 slots also share one 4096-token context (`kv_unified`), so
   requests running at once take room from each other: in two later runs, other requests sent
   to the same llama-server at the same time (by the test suite, by mistake) left the wiki's
   first part without room, llama-server refused it with "Context size has been exceeded"
   (500), and the build failed with "The AI couldn't build a wiki from this PDF". A reply
   during a build could do the same. R99 decides how replies and the wiki share the LLM, and
   R97 the slots and the context.
4. **An answer from the wiki is heard 13 to 24 s after Send.** Its prompt has about 390
   tokens of the question and what was found, and llama-server reads 360 to 940 tokens of it
   again at 38 to 46 a second, so the first token comes 9.5 to 21 s after Send, against 1.5 s
   for a reply without content in R96. The first question after the wiki or a restart reuses
   nothing: the passages found change the prompt from the first message on, and the system prompt the warm-up read wasn't reused (the slots again, as in
   R96; for R97). The lookup itself takes 19 to 29 ms, and a spoken question's correction
   (R96d) 4.5 s.
5. **llama-server's memory grows to about 10.5 GB**, and it was killed twice when the
   session's memory ran out (once the app with it). Logged in the second and third runs: 5.5 GB
   once the model was loaded (2.5 GB of it the model, mapped from its file), 6.8 GB ten minutes
   into the wiki, and 10.4 GB at the end. That is llama-server's prompt cache in memory, which
   it keeps for up to 8 GB unless `--cache-ram` says otherwise (`--help`: "default: 8192"). The
   hosted machine gives it 6 GB (`mem_limit` in `deploy/compose.yaml`), so a wiki build will get
   it killed and restarted there, and every request after a restart reads its whole prompt
   again. R97 sets `--cache-ram` to fit.
6. **"What can you talk about?" is heard 8.7 to 10.3 s after Send** without the LLM: its first
   sentence, the list of topics, is 14 to 17 s of speech, and its voice takes 8.4 to 10 s. A long first
   sentence isn't cut as the LLM's first clause is (R22b, R22e); for R100.

### Larry's hosted machine, 2026-10-22

[pdf-host-2026-10-22.md](pdf-host-2026-10-22.md), with the JSON beside it, run by Larry on
app.me0.ai (4 Ampere cores, llama-server from `ghcr.io/ggml-org/llama.cpp:server` with Gemma 3
4B on 2 threads, as `deploy/compose.yaml` starts it) with the same sample PDF and
`--spoken 2`. Nothing failed and llama-server wasn't killed.

| | Cloud (run 1) | Hosted machine |
|---|---|---|
| Reading (19 pages) | 0.6 s | 0.8 s |
| Wiki parts, topics | 3, 18 | 11, 47 |
| Outline steps | 37 | 96 |
| Prompt tokens read | 27,099, at 46 a second (10 min) | 54,910, at 14.7 a second (62 min) |
| Tokens written | 13,822, at 4.1 a second (56 min) | 35,525, at 5.1 a second (117 min) |
| **PDF to wiki** | **66.4 min** | **180.3 min** |

| Answer | Prompt tokens read | Reused | Reached LLM | First token | First word heard |
|---|---|---|---|---|---|
| Asked while the wiki was built | 213 | 405 | 16 ms | 69.3 s | 73.8 s |
| 1, the first after the wiki | 664 | 0 | 0.4 s | 52.1 s | 55.7 s |
| 2, spoken | 690 | 1 | 10.0 s | 57.0 s | 61.2 s |
| 3 | 204 | 512 | 52 ms | 14.9 s | 18.9 s |
| 4 | 203 | 557 | 52 ms | 14.8 s | 18.4 s |
| 5 | 477 | 0 | 48.7 s | 81.4 s | 85.5 s |
| "What can you talk about?" (no LLM) | - | - | - | - | 11.9 s |
| "Teach me about Prime Number Definition" | 296 | 305 | 52 ms | 20.4 s | 24.0 s |
| "Quiz me on Prime Number Definition" | 206 | 432 | 52 ms | 14.7 s | 18.6 s |
| "Assess me" | 47 | 469 | 51 ms | 3.8 s | 7.5 s |

The largest costs, against the cloud session:

1. **The app split the PDF into parts a third of the size, so the wiki did 2.7 times the
   work.** Each part was 770 to 990 tokens with its instructions, against 2,300 to 2,900 in the
   cloud, from the same PDF and the same 4096-token window. That is what the app does when it
   counts tokens by bytes (about 4 bytes a token in English) instead of asking llama-server:
   the asked tokens and the history are about twice the cloud's for the same prompts too (654
   to 686 asked tokens, against 195 to 394). llama-server answers `/tokenize` with 503
   ("Loading model") while it loads the model, and the app takes any answer that isn't a
   success as "this server can't count" and estimates from then on, until it is restarted
   (`LlmClient.count` in `src/imageskin/chat.py`). On the hosted machine the app starts with
   llama-server, so its first count is likely asked while the model is loading. Checked in the
   cloud: a starting llama-server answered `/tokenize` with 503 for its first seconds. More
   parts gave more topics (47) and so more outline pages (96 steps), so the build read twice
   the tokens and wrote 2.6 times as many. Counting again once the model is loaded would
   likely bring the build to about an hour, as in the cloud.
2. **Reading is 3 times slower than in the cloud (14.7 tokens a second against 46)**, so on
   this machine reading is a third of the build (62 min), not a sixth, and a prompt's reuse
   from llama-server's cache matters more here: answers 3 and 4 reused 512 and 557 tokens and
   were heard after 18 to 19 s; 1, 2 and 5 reused none and were heard after 56 to 86 s.
   Writing is a little faster than in the cloud (5.1 against 4.1).
3. **Answer 5 waited 48.7 s before reaching the LLM**: the conversation's older turns were
   summarized first (its history went from 1,914 to 1,049 tokens), as the history may take
   half the window. With tokens counted by bytes the history fills that half about twice as
   soon, so this too comes from 1.
4. **A spoken question's correction took 9.9 s** (answer 2 reached the LLM after 10.0 s),
   against 32 s in R96's hosted run and 4.5 s in the cloud.
5. **The question asked while the wiki was built read its prompt at 3.1 tokens a second**, as
   it shared the 2 threads with the wiki, and was heard after 74 s, as in the cloud (70 s).

## R96b: setup

`imageskin time-setup` goes through setup on the running app, as a new user would in the
browser, and writes the tables to `speed` in the data folder. It changes the app's setup, so it
runs only on an app with nothing set up yet: start the app with an empty data folder for it (on
the hosted machine, a second container with its own `/data`, or `--anyway` on a copy).

```
IMAGESKIN_HOME=/tmp/setup-test imageskin serve      # a fresh data folder
imageskin time-setup                                # a ready photo and recording
imageskin time-setup --photo me.jpg --photo me2.jpg --recording a.m4a --recording b.m4a
```

In turn it: uploads a photo and three recordings (Larry's timings 8 and 9), prepares the video
and voice (timing 6), uploads a second photo, chooses it and prepares again, changes the accent
and prepares again (only with a voice engine that has accents), picks a default person with
Start now and then another, each to the chat opening and its first prompt's first word heard,
and prepares the avatar in your own voice (R24d).

Each upload's answer now carries a `Server-Timing` header with its steps in milliseconds, so the
browser's developer tools show them too: `save` (copying the parsed file into the uploads
folder), `convert` (HEIC to JPG, or a recording to WAV), `wait` (for another photo's checks),
`read`, `faces` and `covered` (the face checks, R8), `quality` (light and sharpness, R9),
`sound` (R10), `speakers` (the one-speaker check, R11), `voice-sample` (joining the recordings
that passed) and `endpoint` (the whole endpoint). FastAPI receives and parses the upload before
the endpoint runs, so none of these include that; the time until checked, seen by
`time-setup`, does, and `Before endpoint` is that part of it. The two results files below were
made when `save` was called `receive` and `endpoint` was called `total`, with the same
meanings. Prepare's steps come from its own status, as the Prepare page shows them.

### Cloud session, 2026-10-22

[setup-cloud-2026-10-22.md](setup-cloud-2026-10-22.md), with the JSON beside it. The same 4-core
Xeon as R96, with llama-server (Gemma 3 4B Q4_K_M, 2 threads) running, Kokoro's ready-made voice
(Chatterbox and Pocket TTS aren't installed, so there is no accent to change) and the photoreal
engine, with the models already downloaded (their download is start-up's, R96c).

| Step | Time |
|---|---|
| A photo, until checked | 0.96 s and 1.18 s |
| A recording (40 s), until checked | 0.69 s to 1.05 s |
| Prepare, until the sample can be watched | 373.6 s (6.2 min) |
| Prepare again after another photo | 362.9 s (6.0 min) |
| Start now | not timed: the session can't reach app.me0.ai to download the person |

Prepare's steps, the first time and after another photo:

| Step | First | Again |
|---|---|---|
| Get the voice ready | 8.6 s | 0.5 s |
| Get ready to animate the face | 2.4 s | 2.7 s |
| Make the mouth shapes and the blinking eyes | 69.1 s | 75.5 s |
| Make the video of the person listening | 252.0 s | 245.0 s |
| Line up the mouth with the head | 12.1 s | 11.7 s |
| Make the sample video and the greetings | 25.0 s | 23.4 s |

The largest costs:

1. **The video of the person listening, about 250 s**, two thirds of Prepare. It is the idle
   video shown between replies (R23), made frame by frame by the photoreal engine like any
   other video, though nothing in it speaks. A shorter loop, fewer frames played back and forth,
   or making it after the sample is shown, are for the PRs that speed up setup.
2. **The mouth shapes and blinking eyes, about 70 s**, a fifth of Prepare.
3. **Prepare again after another photo redoes everything but the voice**: a new face needs new
   shapes and a new listening video, so it is as slow as the first time.
4. **The photo and recording checks are already quick**, about a second each. In a photo the
   face checks take most of it (`faces` 0.3 to 0.5 s and `covered` 0.5 to 0.6 s), as each
   photo opens and closes both MediaPipe models; in a recording the one-speaker check does
   (0.55 to 0.86 s).
5. **The browser's polling** adds up to 1 s to Prepare (every 1 s) and up to 0.5 s to Start
   now (every 500 ms), small against the steps themselves. The sample could be fetched 10 ms
   after Prepare finished.

### Larry's hosted machine, 2026-10-23

[setup-hosted-2026-10-23.md](setup-hosted-2026-10-23.md), with the JSON beside it. app.me0.ai:
4 Ampere cores (the app container gets 3), llama-server with Gemma 3 4B on 2 threads,
Chatterbox Turbo speaking in the person's own voice, and the photoreal engine, run against a
second copy of the app with an empty data folder and the real one's models. Every step passed;
the whole run took about 1 h 50 min, started in the background (`docker compose exec -d`) and
followed with `setup-progress.txt`.

| Step | Time |
|---|---|
| A photo, until checked | 0.60 s and 0.71 s |
| A recording (40 s), until checked | 1.35 s to 1.39 s |
| Prepare, until the sample can be watched | 3104 s (51.7 min) |
| Prepare again after another photo | 3148 s (52.5 min) |
| Prepare again after another accent | 155 s (2.6 min) |
| Prepare the avatar in your own voice | 152 s (2.5 min) |
| Start now, to the chat opening | 22.0 s, then 5.9 s to the first prompt's first word heard |
| Switch person, to the chat opening | 18.3 s, then 8.2 s to the first word heard |

Prepare's steps, in seconds, and how many times as long as in the cloud:

| Step | First | Another photo | Another accent | Own voice | First, against the cloud |
|---|---|---|---|---|---|
| Get the voice ready | 50.6 | 1.9 | 89.6 | 88.1 | 5.9 times (Chatterbox here, Kokoro there) |
| Get ready to animate the face | 7.5 | 5.1 | - | - | 3.1 times |
| Make the mouth shapes and the blinking eyes | 639.4 | 652.5 | - | - | 9.3 times |
| Make the video of the person listening | 2271.8 | 2338.3 | - | - | 9.0 times |
| Line up the mouth with the head | 16.1 | 16.5 | - | - | 1.3 times |
| Make the sample video and the greetings | 113.1 | 127.5 | 65.5 | 63.6 | 4.5 times |

Start now's states, in seconds from the click: downloading at once, unpacking at 0.25 s, getting
ready at 6.1 s (3.3 s for the second person), ready at 14.6 s (11.4 s) and the chat open at
22.0 s (18.3 s).

The largest costs on the hosted machine:

1. **The video of the person listening, about 38 minutes**, 73% of Prepare, and 9 times as long
   as in the cloud, as the photoreal engine's frames are on 3 Ampere cores instead of 4 Xeon
   ones. It is the largest cost in all of setup by far, and the first thing for the PRs that
   speed up setup: a shorter loop, fewer frames played back and forth, or making it after the
   sample is shown.
2. **The mouth shapes and blinking eyes, about 11 minutes**, 21% of Prepare, also 9 times the
   cloud's.
3. **Another photo costs a whole Prepare again, 52 minutes**: everything but the voice is redone
   for a new face. The voice is kept (1.9 s).
4. **Another accent or the avatar in your own voice costs about 2.5 minutes**, the voice made
   again (about 90 s, the Chatterbox clone loading and the accent's sample) and the clips spoken
   again (about 65 s). The face is kept.
5. **Start now opens the chat in 18 to 22 s**, most of it after the download: 8 s getting the
   person ready and 7 s from ready to the chat opening (the replies' warm-up, R96c), after
   which the first reply waited for nothing (warm-up wait 0) and its first word was heard in
   6 to 8 s.
6. **The photo and recording checks stay quick**: 0.6 to 0.7 s for a photo, with `covered` (the
   segmenter) the largest part at 0.39 to 0.54 s; 1.4 s for a recording, 92% of it the
   one-speaker check (1.24 to 1.28 s).

## R96c: start-up and the first load

`imageskin time-startup` is run right after the app is started or restarted, and writes the
tables to `speed` in the data folder:

```
imageskin time-startup                                      # llm_url from the config
imageskin time-startup --llm-url http://llama:8080/v1       # llama-server elsewhere
```

It waits for the ready line, and for llama-server's `/health` to answer 200 (it answers 503
while it loads its model). The app now keeps when each part of its start began and ended, in
ms from its process starting, and serves them at `/api/startup`; the log has `Start-up part
finished` for each. The parts are:

| Part | What it is |
|---|---|
| app made | `create_app`: the settings, the stores, the jobs carried on from before |
| face models, speaker model | the MediaPipe models and the one-speaker check's model, loaded in the background |
| reply warm-up | the replies' warm-up (R22a), once a sample is accepted |
| LLM warm-up | llama-server reading the system prompt, inside the reply warm-up |
| voice and video warm-up | the voice and video engines loaded and a word rendered, and the idle video made if it isn't there |
| server listening | uvicorn taking requests |
| ready | the ready line, "Loading has completed. The application is ready for use." |

Before "app made" begins is Python and the app's modules loading (torch among them). Then it
times the first prompt and the next, so the first can be compared with the usual speed
(Larry's timing 10); the browser's first load, each group fetched at once over 6 connections,
compressed (the page, its scripts and styles, the fonts they name, and the face pictures of the
avatar page; timing 7); the requests the chat makes when it is opened again after a restart,
with Welcome back's video (which plays after Exit and Start again); and saving the local LLM
again in Settings, to its next prompt's first word.

### Cloud session, 2026-10-23

[startup-cloud-2026-10-23.md](startup-cloud-2026-10-23.md), with the JSON beside it. The same
4-core Xeon at 2.1 GHz: llama-server (built from llama.cpp's source) with Gemma 3 4B Q4_K_M on
2 threads and a 4096-token context, Chatterbox Turbo speaking in the person's own voice, and
the photoreal engine, with a person prepared and accepted. llama-server and the app were
started together, as after a reboot, with the models already downloaded; time-startup began
0.4 s after the app's process.

| Part | From the process starting |
|---|---|
| Python and the app's modules loaded | 0 to 2.5 s |
| App made | 2.5 to 2.9 s |
| Server listening | 3.0 s |
| Speaker model, face models | done at 3.7 s and 5.5 s |
| LLM warm-up | 2.9 to 3.0 s, refused: llama-server was still loading |
| llama-server answering /health | 5.5 s (5.3 s to load the model, from a disk cache) |
| Voice and video warm-up | 2.9 to 46.6 s (43.7 s) |
| Ready line | 46.6 s |

The largest costs and what they mean:

1. **The voice and video warm-up, 44 s**, almost all of the start. It loads Chatterbox and the
   photoreal engine and renders a word; the ready line waits for it. The LLM is ready 41 s
   before it.
2. **The LLM's warm-up is wasted after a restart.** It runs as soon as the app is made, while
   llama-server is still loading its model, so llama-server answers 503 (`Could not warm up
   the LLM`) and nothing tries again. The first prompt then read the system prompt again (107
   tokens, none reused) and its first token came after 3.2 s, against 1.4 s for the next
   prompt, which reused 102. On the hosted machine llama-server took 164 s to load (PR #148),
   so the warm-up is always refused there. Warming it up once llama-server answers `/health`
   would make the first prompt as quick as the next.
3. **Saving the LLM again in Settings** made the next prompt reuse nothing either (182 tokens
   read, first token 7.7 s): the warm-up the save starts and the prompt reach llama-server
   together.
4. **The browser's first load is small**: 74 files and 0.5 MB (the face pictures 0.3 MB of
   it), 0.3 s on this machine. Over the internet through Caddy it will be longer, but it is
   not where start-up's time goes.
5. **Opening the chat again after a restart is quick**: its 8 requests take 54 ms together,
   and Welcome back's video (92 KB) arrives in 10 ms.

### Larry's hosted machine, 2026-10-23

[startup-hosted-2026-10-23.md](startup-hosted-2026-10-23.md), with the JSON beside it.
app.me0.ai after `docker compose restart app llama`, with Larry's person and a 924-token
conversation saved; time-startup began 25.6 s after the app's process, after the ready line.

| Part | From the process starting |
|---|---|
| App made | 1.9 to 2.1 s |
| Server listening | 2.6 s |
| Face models, speaker model | done at 3.5 s and 2.9 s |
| LLM warm-up | 2.1 to 2.2 s: refused, as llama-server was still loading |
| Voice and video warm-up | 2.1 to 14.7 s (12.6 s) |
| Ready line | 14.7 s |
| llama-server answering /health | not timed: the watch ended without a time (fixed since) |

1. **The first reply after the restart took 65.6 s to its first token**, against 4.0 s for the
   next. It read all 953 prompt tokens again at 14.5 a second, reusing none. Two causes: the
   warm-up was refused while llama-server loaded its model, and even a warm-up that ran only
   reads the system prompt, while the saved conversation adds 924 tokens of history to the
   first prompt. The second reply reused 948. This is start-up's largest cost by far.
2. **The voice and video warm-up took 12.6 s**, much less than in the cloud (44 s), as the
   models were already in the disk cache.
3. **The browser's first load (0.2 s) and opening the chat again (47 ms)** are small, measured
   inside the container; through Caddy and the internet they will be longer.
4. **Saving the LLM again in Settings** cost the next prompt little here (first token 11.3 s,
   986 tokens reused): the history was already in llama-server's cache.

The fix for the first: warm the LLM up once llama-server answers `/health`, with the saved
conversation's prompt rather than the system prompt alone, so the first reply after a restart
reuses what the next one does.

## R100: the pause after the first clip

The gaps after the first clip in the cloud run of 2026-10-21 (1.9 s and 3.0 s) were the LLM, not
the voice: the voice had made the first clip and sat waiting (Waited 0) while the LLM wrote the
rest of a long first sentence, which was only handed over at its full stop. Since R100, while
every clip so far is made and the LLM is still writing a sentence, that sentence is handed over
at its next clause (`cut_for_waiting_voice` in the log's `Reply sentence ready`).

On Larry's hosted machine, and in this cloud session of 2026-10-22 (a 4-core Xeon at 2.8 GHz,
the same setup as above, [reply-cloud-2026-10-22-r100.md](reply-cloud-2026-10-22-r100.md)), the
voice is never waiting: each clip waits 2 to 9 s for the one before, so no sentence was cut for
it and the replies are as before. There, a clip takes longer to make than to play while the LLM
writes (the voice alone takes 1.1 to 1.3 s a second of speech), so the gaps come from the CPU.

Speaking the next sentence while the clip before is rendered doesn't help either, as R22b
found: [voice_video_overlap.py](voice_video_overlap.py), with the LLM writing on 2 threads,
took 5.3 s for the video of a 3-second clause and then the voice of the next sentence, one after
the other, and 6.0 to 7.4 s for both at once (1 or 2 threads each).

## R97: llama-server's settings

`imageskin time-llm` asks a running llama-server what the app asks it, without the app: the
replies' warm-up and three prompts of a conversation, streamed, then the sample PDF's first
wiki part (cut for a 4096-token window, so every setting gets the same request). Each run adds
a row, under its name, to `llm-settings.md` and `.json` in the results folder, and the whole
sample PDF's wiki is estimated from the part's reading and writing speeds and R96a's tokens.
[llama_settings.sh](llama_settings.sh) starts llama-server with each setting in turn and runs it:

```
bash ../experiments/speed/llama_settings.sh docker             # on the hosted machine, from deploy
LLAMA_SERVER=llama-server MODELS=~/models bash experiments/speed/llama_settings.sh local
bash ../experiments/speed/llama_settings.sh docker threads     # only the settings named so
```

### Cloud session, 2026-10-23

[llm-settings-cloud-2026-10-23.md](llm-settings-cloud-2026-10-23.md), with the JSON beside it.
A 4-core Intel Xeon at 2.8 GHz, llama-server built from llama.cpp's source that day, nothing
else running. Each setting changes one thing from what the app ran with (Gemma 3 4B Q4_K_M,
2 threads, 4096 tokens):

| Setting | First token, 3 replies | First sentence, 3 replies | Sample PDF's wiki |
|---|---|---|---|
| Before: 2 threads | 5.1 / 2.9 / 3.7 s | 7.4 / 4.4 / 4.9 s | 73 min |
| `--swa-full` | 0.9 / 1.2 / 1.5 s | 3.2 / 2.6 / 2.8 s | 73 min |
| `--threads-batch 4` (reading on 4) | 2.6 / 1.8 / 2.1 s | 5.0 / 3.3 / 3.4 s | 67 min |
| **Both, now in compose.yaml** | **0.35 / 0.7 / 0.7 s** | **2.4 / 1.9 / 2.7 s** | **64 min** |
| 3 threads | 3.2 / 2.2 / 2.6 s | 4.8 / 3.4 / 3.5 s | 56 min |
| 4 threads | 2.4 / 1.8 / 2.1 s | 3.6 / 2.8 / 2.9 s | 43 min |
| Gemma 3 1B Q4_K_M | 1.4 / 0.8 / 0.8 s | 1.7 / 1.3 / 1.6 s | 24 min |
| 4B Q8_0 | 6.2 / 4.1 / 4.7 s | 9.5 / 6.0 / 7.5 s | 103 min |
| 4B Q4_0, one slot, flash attention on or off, batch 128 or 1024, context 8192 | within 15% of before | within 15% | 69 to 73 min |

What it found:

1. **llama-server read every prompt again from its first token.** Gemma 3 keeps a
   sliding-window cache, which llama-server can't cut back to the start two prompts share, so
   the replies' warm-up (R22a) was never reused ("Reused after warm-up" 1 token, with 4 slots or
   one) and each reply read the whole conversation again. This was the 1 token reused that R96
   found, and it wasn't the slots. `--swa-full` keeps the whole cache (about 0.35 GB more for 4096
   tokens), and the warm-up's 97 tokens are reused: the first token came 5.1 s sooner. It is also
   what lets R96d's and R98's shared prompt starts be reused.
2. **Reading on 4 threads** (`--threads-batch 4`) reads a prompt as fast as 4 threads do (44
   tokens a second against 24) while writing stays on 2, so the voice and video keep their half
   of the cores while the LLM writes. Reading is over before the reply's voice starts. With
   `--swa-full`, a reply reads only its new tokens, so this mostly speeds up the wiki (73 to 64
   minutes) and a question with content quoted before it.
3. **Writing scales with threads** (3.7, 4.8 and 6.2 tokens a second on 2, 3 and 4), and most
   of the wiki is writing. But 4 threads for the LLM would take the voice's cores during a
   reply, which R22a measured as both crawling, so it stays at 2. A wiki written on every core
   while nobody chats is for R99.
4. **Gemma 3 1B is 3 times as fast** (24 minutes for the wiki), but its topics are the PDF's
   numbered headings copied ("1. What a prime number is") with the PDF's title as a topic, where
   4B found its own titles, and the README already notes it ignores the conversation. It isn't
   used for now.
5. **Nothing else helped here:** Q8_0 is a third slower, and Q4_0, one slot, flash attention,
   the batch sizes and an 8192-token context are within the run-to-run noise. On the hosted
   machine's Ampere cores Q4_0 may be faster, as llama.cpp repacks it for ARM, so the hosted run
   decides it.

### Larry's hosted machine, 2026-10-23

[llm-settings-hosted-2026-10-23.md](llm-settings-hosted-2026-10-23.md), as Larry pasted it.
app.me0.ai: 4 Ampere cores, each setting in its own llama-server container with as many cores
as its threads, the app idle. The first sentence of the three replies, and the sample PDF's wiki
estimated as above:

| Setting | First sentence, 3 replies | Sample PDF's wiki |
|---|---|---|
| Before: 4B Q4_K_M, 2 threads | 8.9 / 4.6 / 4.9 s | 78 min |
| Both flags, 4B Q4_K_M (also the app's own llama-server, PR step 4) | 2.2 / 2.0 / 2.0 s | 63 min |
| `--swa-full` | 2.6 / 3.0 / 2.9 s | 77 min |
| `--threads-batch 4` (reading on 4) | 5.4 / 2.9 / 3.5 s | 63 min |
| 3 threads | 6.0 / 3.1 / 3.5 s | 55 min |
| 4 threads | 4.6 / 2.4 / 2.5 s | 41 min |
| **4B Q4_0** | **5.5 / 3.0 / 3.5 s** | **59 min** |
| 4B Q8_0 | 6.3 / 3.6 / 4.5 s | 67 min |
| Gemma 3 1B Q4_K_M | 3.5 / 1.6 / 2.4 s | 27 min |
| One slot, flash attention on or off, batch 128 or 1024, context 8192 | within 10% of before | 74 to 84 min |

The same as in the cloud: with both flags the warm-up's 97 tokens were reused (1 before), and
the first token came after 0.4 s instead of 7.1 s. One difference: **Q4_0 is a quarter faster here** (59 minutes
against 78, and the first sentence sooner), where in the cloud it was no faster, as llama.cpp
repacks Q4_0 for ARM's instructions; even Q8_0 beat Q4_K_M here. So `deploy/compose.yaml` runs
Q4_0 (`unsloth/gemma-3-4b-it-GGUF:Q4_0`, about 2.4 GB) with `--threads-batch 4 --swa-full`;
its topics for the first part were the same as Q4_K_M's in the cloud. The laptop's README line
keeps Q4_K_M, which was as fast on the cloud's Intel cores. The last setting of
[llama_settings.sh](llama_settings.sh), "hosted", is that combination, to confirm it.

## R99: replies don't wait behind the wiki

R96a found a question asked while the wiki was built ran beside the wiki's request in another of
llama-server's 4 slots, on the same threads, and was heard after 70 s in the cloud and 74 s on
the hosted machine. Since R99, a reply cuts off the wiki's request in progress (as removing its
PDF does) and the wiki waits until the reply is written, then asks again
(`src/imageskin/replies_first.py`; the log has `Wiki request cut off for a reply` and
`Wiki waited for a reply` with its `duration_ms`). Only with the local LLM: a provider answers
both at once elsewhere.

[reply_during_wiki.py](reply_during_wiki.py) asks a reply 20 s into the sample PDF's first
wiki part, with and without it. In a cloud session (2026-10-23,
[reply-during-wiki-cloud-2026-10-23.md](reply-during-wiki-cloud-2026-10-23.md)) the reply's
first sentence came after 19.6 s before and 5.2 s after, against 6.2 to 6.3 s with the LLM
idle, and the wiki's first part was done no later (167.7 s against 174.2 s), as llama-server
kept what it had read of the cut-off request.

R97's other idea, the wiki writing on 4 threads while nobody chats and 2 during a reply, needs
llama-server restarted to change its threads, which would lose its cache each time, so it isn't
done.
