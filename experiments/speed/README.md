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
