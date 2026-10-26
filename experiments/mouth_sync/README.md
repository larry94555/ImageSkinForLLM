# Where the mouth runs ahead of the voice (R127)

Larry saw the default people's mouths open before their voices start (roadmap item 106). This
experiment measures, before any change, how far ahead the mouth is and where each part of that
comes from: the sound timings, turning them into frames, the MP4, and the browser. Its result
decides R128's fix.

## How to run it

```
python experiments/mouth_sync/mouth_lead.py                          # Kokoro af_heart
python experiments/mouth_sync/mouth_lead.py --voice am_michael
python experiments/mouth_sync/mouth_lead.py --voice bf_emma --lang b
python experiments/mouth_sync/mouth_lead.py --clone <voice-sample.wav>     # Chatterbox Turbo
python experiments/mouth_sync/mouth_lead.py --clone <voice-sample.wav> --pocket   # Pocket TTS
```

It needs the `voice` extra (and the cloned voice's install from `clone-requirements.txt` for
`--clone`) and ffmpeg, but no prepared face: the mouth is measured from the weights the photoreal
engine draws each frame from. The tables are written to `mouth-lead/mouth-lead-<voice>.md` and
`.json`, and the log has `Mouth lead experiment started`, `Measured clip` for each clip with its
lead at the start and the time it took, and `Mouth lead experiment done`.

On the hosted machine the app and everything it needs are in its Docker image, not on the
machine itself, and the image leaves `experiments/` out. So run it in a one-off app container
with this folder mounted, from `deploy/`, writing the tables to the data volume:

```
docker compose run --rm --no-deps -v "$PWD/../experiments/mouth_sync:/exp:ro" app \
    python /exp/mouth_lead.py --voice af_heart -o /data/mouth-lead
docker compose run --rm --no-deps app cat /data/mouth-lead/mouth-lead-af_heart.md
```

The person's own voice there is `--clone /data/uploads/voice-sample.wav`.

For the browser it needs Node and Playwright, which the app doesn't install; on Windows, in
PowerShell, it can go in a folder of its own:

```
npm install --prefix $env:TEMP\pw playwright
$env:NODE_PATH = "$env:TEMP\pw\node_modules"
python experiments/mouth_sync/mouth_lead.py --media sync-media
node experiments/mouth_sync/browser_sync.js sync-media chrome     # the installed Chrome
node experiments/mouth_sync/browser_sync.js sync-media            # or Playwright's own Chromium
python experiments/mouth_sync/mouth_lead.py --browser sync-media  # the table, in sync-media/browser.md
```

## What it measures

Six clips are made as the app makes them: three reply sentences, "Goodbye.", "Welcome back." and
the sample video's script. Each is spoken by the app's voice engine and written with
`write_speech`, and the mouth's weights per frame come from `frame_weights` on the JSON's
shapes, as `PhotorealEngine.render` does. Then at the start of each clip, and at each word
after a pause of at least 150 ms:

| Column | What it is |
|---|---|
| Heard | the voice is first heard: the first 5 ms no more than 35 dB below the clip's loud level, the silence level `expression.loudness` uses |
| Opens | the mouth opens: the start of the first frame after the pause whose openness (`expression.openness`, 0 closed to 1 the widest shape) reaches 0.1. "–" when the mouth doesn't close in the pause before (or is open from the clip's first frame) |
| Lead | Heard minus Opens: how long the mouth is open before the voice is heard. Negative is after |
| Timings | the part of the lead from the sound timings: Heard minus the start of the first sound in the JSON |
| Frames | the part from turning the timings into frames: that sound's start minus Opens. `frame_weights` moves the lips 30 ms ahead of the sound, blends shapes over a 60 ms Gaussian (so the mouth starts opening before the sound), and samples each frame at its middle while it shows from its start |
| MP4 | how much later the sound is than the picture in the file: the MP4's audio decoded and lined up against the WAV, less how much the frames moved |

For Kokoro it also runs the forced aligner the cloned voice uses (R25) on Kokoro's own audio and
compares its word starts with Kokoro's.

In the browser, `browser_sync.js` plays MP4s written with `write_mp4` as the app writes its
clips, each with a white frame and a beep on its first frame and at 0.6, 1.6 and 2.6 s, the way
the chat's ClipPlayer plays a reply: the muted idle video underneath; the first clip, progressive
as reply clips are, faded in over it with the chat's 0.25 s opacity transition once it plays;
then two more progressive clips and a whole one (as the sample and fixed lines are), each loaded
in a hidden second player that is shown, then played, when the clip before ends. At each switch
it compares the clip's first picture on screen (its first frame after it plays, or its player
being shown, whichever is first) and the moment it is half faded in with its first sound; and at
each white frame, when it is shown with when its beep is played.

## Results: cloud session, 2026-10-25

A 4-core cloud machine with no graphics card or sound card. Kokoro's three most used default
voices and Chatterbox Turbo cloned from a donor voice sample. Larry's own photo and voice are not
in the cloud session, so they are for the manual test in the PR. Pocket TTS's cloning weights
need a Hugging Face sign-in, so it wasn't run here; it gets its timings from the same aligner as
Chatterbox. Full tables: [results/](results/).

| Voice | Starts and words after a pause | Lead in the file | Over 80 ms | Timings part (median) | Frames part where the mouth opens first (median) |
|---|---|---|---|---|---|
| af_heart | 17 | -235 to +55 ms | 0 | -85 to -20 ms (-50) | +70 to +115 ms (+90) |
| am_michael | 16 | -230 to +60 ms | 0 | -190 to -30 ms (-65) | +75 to +120 ms (+90) |
| bf_emma | 14 | -265 to +75 ms | 0 | -115 to -10 ms (-55) | +85 to +100 ms (+85) |
| Cloned (Chatterbox) | 23 | -120 to +160 ms | 5 | -168 to +71 ms (-27) | +57 to +110 ms (+81) |

- **The MP4 adds nothing after its first frame.** ffmpeg's AAC encoder starts the sound 43 ms
  (1024 samples) late in a progressive MP4, and every frame but the first moves by the same
  43 ms, so they stay together; a whole MP4 moves neither. Measured 0 ms in every clip of every
  voice. The progressive MP4's first frame stays at 0, so it shows 43 ms before the sound (for
  83 ms). Every clip starts with 0.1 to 0.4 s of silence, so that frame always has the mouth at
  rest: it puts no open mouth before the voice.
- **The browser adds about 35 ms within a clip.** In headless Chromium 153, over five runs
  ([browser-cloud-2026-10-25.md](results/browser-cloud-2026-10-25.md)), each white frame after
  a clip's first showed 24 to 49 ms (once 13 ms) before its beep, the same in every clip and in
  whole and progressive MP4s. Chromium shows frames on its screen's beat (about 33 ms here), so
  that is about the accuracy. The sound goes through Web Audio to be measured, and its own 42 ms
  output delay is left out, as the chat page doesn't use Web Audio.
- **The switch from the idle video adds nothing.** The first clip of a reply is out of sight
  until it plays and then fades in: its first frame came -9 to +7 ms from its first sound, and
  it was half faded in -10 to +1 ms from it, so the sound comes with the picture.
- **The switch between clips shows the next clip's first frame early, at rest.** The loaded next
  player shows its first frame as soon as it takes over, and it played 85 to 91 ms before its
  first sound for a progressive clip (the browser's ~40 ms and the progressive MP4's 43 ms first
  frame) and 42 to 45 ms for a whole one. That first frame has the mouth at rest (each clip
  starts with silence), so it is not a mouth lead; the frames after it are back to the
  browser's ~35 ms.
- **The frames open the mouth 60 to 120 ms before the first sound.** Wherever the mouth opens first,
  the Frames part is 57 to 120 ms, with a median of 81 to 90 ms in each voice: `frame_weights`' 30 ms lead, the 60 ms blend starting the
  opening early (a tenth open is reached about 50 ms before the sound), and frames sampled at
  their middle (up to 20 ms more).
- **Kokoro's timings hide it; the aligner's don't.** Kokoro's sound timings start 10 to 190 ms
  (median 55 ms) after its voice is first heard (its first sound, often a breath or an "h", is
  quiet), which takes back most of the frames' lead: with Kokoro the mouth opens at most 75 ms
  before the voice in the file. The forced aligner puts the cloned voice's sounds close to the
  audio (median 27 ms after it, and up to 71 ms before it), so the frames' lead shows in full:
  up to 160 ms.
- **The aligner is about 75 ms behind Kokoro's own word starts** (107 words: +39 to +192 ms,
  median +73 ms for af_heart; the same for am_michael). Against the audio it is the closer of
  the two at the start of a word after a pause, as above.
- **Openings after the voice** (negative leads, down to -265 ms) are words starting with m, b or
  p, where the lips close first and openness counts them closed, and short pauses where the
  timings run a quiet "s" or "z" on into the pause, so the mouth only half closes and opens
  again late. They are not leads and are for R128 to keep in mind, not to fix.

### Each lead over 80 ms

In the file, all five are the cloned voice's:

| Clip | Word | Lead | Timings | Frames | Cause |
|---|---|---|---|---|---|
| reply 1 | Hello (start) | 95 ms | +14 ms | +81 ms | the frames' early opening |
| goodbye | Goodbye (start) | 90 ms | +5 ms | +85 ms | the frames' early opening |
| sample | two | 90 ms | +22 ms | +68 ms | the frames' early opening, the aligner a little early |
| sample | three | 160 ms | +71 ms | +89 ms | the aligner 71 ms early ("th" is quiet), and the frames |
| sample | did | 110 ms | +18 ms | +92 ms | the frames' early opening |

In the browser, add about 35 ms to every lead within a clip: that puts Kokoro's largest leads
over 80 ms too (bf_emma's sample at 75 ms becomes about 110 ms, am_michael's at 60 ms about
95 ms, af_heart's 50 to 55 ms leads about 85 to 90 ms).

## What R128 should change

1. **The frames, for every voice:** open the mouth from rest no earlier than the first sound
   (drop the 30 ms lead and the blend's early start where the mouth opens from rest, and
   sample each frame where it starts to show), keeping the blend between sounds as it is. This
   takes 60 to 120 ms off every opening.
2. **The browser's ~35 ms:** small, the same in every clip, and about a frame's accuracy here;
   measure it on Larry's laptop and the hosted machine with real sound (below) before allowing
   for it.
3. **The cloned voice's timings:** after the first change, the aligner's early starts (up to
   71 ms) are within the 80 ms limit; if they still show, start the first sound after a pause
   where the audio's voice starts, as Heard measures it.
4. **Kokoro:** once the frames don't open early, Kokoro's late timings (median 55 ms) would make
   the mouth open after the voice. Starting the first sound after a pause where the voice is
   first heard (as in 3) fixes both voices the same way.

## After R128

R128 made changes 1, 3 and 4 above (`visemes.frame_weights` and `imageskin/mouth_sync.py`), and
`mouth_lead.py` now measures the mouth as the app draws it. Measured again in the cloud session
the same day ([results/](results/), `*-after-r128-*`):

| Voice | Starts and words after a pause | Lead in the file, before R128 | After R128 | Over 80 ms |
|---|---|---|---|---|
| af_heart | 17 | -235 to +55 ms | -80 to -10 ms | 0 |
| am_michael | 16 | -230 to +60 ms | -155 to -5 ms | 0 |
| bf_emma | 14 | -265 to +75 ms | -105 to 0 ms | 0 |
| Cloned (Chatterbox) | 21 (23 before) | -120 to +160 ms | -40 to 0 ms | 0 |

Since Codex's review of R128 the mouth also closes in every pause heard in the audio, even
where the sound timings run a sound on into it, and a mouth that stays open through a pause
counts as leading by the whole pause rather than being left out (the "–" rows before). Every
start and word after a pause now has a measured opening.

The mouth now opens on the first frame that starts with the voice, or up to a frame (33 ms)
after it; the browser's ~30 ms (change 2) puts the picture back about level with the sound.
Leads well below zero are, as before, words starting with m, b or p and short pauses the mouth
doesn't close in. Chatterbox speaks a little differently each time, so its clips aren't the
same takes as before.

To watch it rather than read it, `side_by_side.py` renders lines on a prepared face twice, as
before R128 on the left and as now on the right, with the voice, at normal and half speed:

```
python experiments/mouth_sync/side_by_side.py                          # the face prepared last, af_heart
python experiments/mouth_sync/side_by_side.py --clone <voice-sample.wav>
python experiments/mouth_sync/side_by_side.py --library <home>/photoreal/<folder>
```

The videos go to `side-by-side/`, and it prints each line's lead before and after.

## Still to measure

- Larry's own photo and voice (cloned with Chatterbox, or Pocket TTS on the hosted machine):
  `mouth_lead.py --clone` with his voice sample, as in the PR's manual test.
- The browser with real sound: `browser_sync.js sync-media chrome` on Larry's laptop (with and
  without Bluetooth headphones, whose delay the browser may not know) and against the hosted
  machine. A sound card or headphones that report less delay than they have make the picture
  run ahead by the difference; that can't be measured in a cloud session.
