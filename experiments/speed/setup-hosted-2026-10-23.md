# Where the time goes: setup

## Photos (Larry's timing 8)

Milliseconds, from the upload's Server-Timing: `receive` the file arriving, `convert` HEIC to JPG, `wait` for another photo's checks, `read` the photo, `faces` and `covered` the face checks (R8), `quality` the light and sharpness (R9), `total` the server's whole request.

| File | Until checked | receive | convert | wait | read | faces | covered | quality | total | Problems | Error |
|---|---|---|---|---|---|---|---|---|---|---|---|
| photoreal_male_professor.jpg | 603 | 0 | 0 | 0 | 11 | 152 | 390 | 37 | 599 | 0 |  |
| photoreal_male_professor_2.jpg | 711 | 0 | 0 | 0 | 6 | 152 | 538 | 3 | 707 | 0 |  |

## Recordings (Larry's timing 9)

`convert` to WAV (R2), `sound` the sound checks (R10), `speakers` the one-speaker check (R11), `voice-sample` joining the recordings that passed.

| File | Until checked | receive | convert | sound | speakers | voice-sample | total | Problems | Error |
|---|---|---|---|---|---|---|---|---|---|
| recording.m4a | 1390 | 0 | 98 | 8 | 1275 | 2 | 1385 | 0 |  |
| recording.m4a | 1387 | 0 | 97 | 6 | 1275 | 4 | 1383 | 0 |  |
| recording.m4a | 1353 | 0 | 96 | 6 | 1238 | 6 | 1349 | 0 |  |

## Prepare (Larry's timing 6)

Milliseconds from Prepare (or the change) to done, then to the sample's first bytes; Prepare's own steps in seconds. The page asks every 1000 ms, so it can show each step up to that much later.

| What | Done | Sample plays | voice (s) | models (s) | shapes (s) | loop (s) | align (s) | clips (s) | Error |
|---|---|---|---|---|---|---|---|---|---|
| Prepare | 3104489 | 3104497 | 50.6 | 7.5 | 639.4 | 2271.8 | 16.1 | 113.1 |  |
| Prepare again, another photo | 3147850 | 3147858 | 1.9 | 5.1 | 652.5 | 2338.3 | 16.5 | 127.5 |  |
| Prepare again, another accent | 155387 | 155395 | 89.6 | - | - | - | - | 65.5 |  |
| Prepare, avatar in your own voice | 152217 | 152225 | 88.1 | - | - | - | - | 63.6 |  |

## Start now

Milliseconds from Start now to each state first seen (asked every 250 ms; the page asks every 500 ms), then the first prompt after it.

| What | Person | States | Chat open | Warm-up wait | First word heard | Error |
|---|---|---|---|---|---|---|
| Start now | photoreal_male_professor | downloading 1, unpacking 254, getting-ready 6061, ready 14613, chat open 22040 | 22044 | 0.0 | 5937 |  |
| Switch person | animated_female_boss | downloading 3, unpacking 256, getting-ready 3312, ready 11398, chat open 18321 | 18325 | 0.0 | 8222 |  |
