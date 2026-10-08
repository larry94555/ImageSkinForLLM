# Expressive face from the voice (experiment)

Larry, after the R25 sample in his cloned voice (2026-10-08): the voice rises, falls and gets
louder, but the face moves the same way for every word. This experiment drives the face from
the loudness and pitch already in the WAV, with no model run, on top of today's photoreal
engine (R4c), which is unchanged:

- **Jaw:** louder syllables open wider (up to 12 px in the 512 px face crop), quieter ones a
  little less, scaled by how open the mouth shape already is, so m, b, p, f and v still close.
- **Brows:** lift on high or stressed words (up to 8 px).
- **Head:** nods on stressed beats (up to 6 px), tilts (up to 2 degrees) and lifts as the
  pitch rises.

The extra motion is drawn as small smooth warps that fade out before the edge of the face crop,
so the paste into the photo stays seamless. Measuring the voice takes about 50 ms for 26 s of
speech; rendering is about 10% slower than today's engine (8.8 s against 8.0 s for 26 s of
speech on a 4-core CPU).

## Run it

```
imageskin say --voice-sample voice-sample.wav -o mine.wav "Wow, that's great news!"
python experiments/expressive/expressive.py ~/.imageskin/photoreal/<key> mine.wav after.mp4
```

`<key>` is the photo's library folder (the newest one in `~/.imageskin/photoreal`). The
strengths are in `prosody.Gains`. `after.motion.npz` next to the video holds the motion per
frame (jaw, brow, nod, tilt), for tuning.
