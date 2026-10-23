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
