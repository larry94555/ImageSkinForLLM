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
browser's developer tools show them too: `receive`, `convert` (HEIC to JPG, or a recording to
WAV), `wait` (for another photo's checks), `read`, `faces` and `covered` (the face checks, R8),
`quality` (light and sharpness, R9), `sound` (R10), `speakers` (the one-speaker check, R11),
`voice-sample` (joining the recordings that passed) and `total`. Prepare's steps come from its
own status, as the Prepare page shows them.

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

Start now, the switch to another person and the avatar in your own voice still need a run on
Larry's hosted machine, which can download the people, and the accent change one with the
person's own voice (Pocket TTS or Chatterbox).
