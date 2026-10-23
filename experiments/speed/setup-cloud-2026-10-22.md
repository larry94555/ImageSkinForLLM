# Where the time goes: setup

## Photos (Larry's timing 8)

Milliseconds, from the upload's Server-Timing: `receive` the file arriving, `convert` HEIC to JPG, `wait` for another photo's checks, `read` the photo, `faces` and `covered` the face checks (R8), `quality` the light and sharpness (R9), `total` the server's whole request.

| File | Until checked | receive | convert | wait | read | faces | covered | quality | total | Problems | Error |
|---|---|---|---|---|---|---|---|---|---|---|---|
| photoreal_male_professor.png | 959 | 1 | 1 | 0 | 44 | 318 | 466 | 106 | 946 | 0 |  |
| photoreal_male_professor_2.png | 1180 | 1 | 1 | 0 | 31 | 523 | 601 | 3 | 1169 | 0 |  |

## Recordings (Larry's timing 9)

`convert` to WAV (R2), `sound` the sound checks (R10), `speakers` the one-speaker check (R11), `voice-sample` joining the recordings that passed.

| File | Until checked | receive | convert | sound | speakers | voice-sample | total | Problems | Error |
|---|---|---|---|---|---|---|---|---|---|
| setup-recording.wav | 1048 | 1 | 90 | 82 | 855 | 2 | 1032 | 0 |  |
| setup-recording.wav | 908 | 1 | 99 | 8 | 780 | 3 | 894 | 0 |  |
| setup-recording.wav | 691 | 1 | 113 | 9 | 551 | 7 | 682 | 0 |  |

## Prepare (Larry's timing 6)

Milliseconds from Prepare (or the change) to done, then to the sample's first bytes; Prepare's own steps in seconds. The page asks every 1000 ms, so it can show each step up to that much later.

| What | Done | Sample plays | voice (s) | models (s) | shapes (s) | loop (s) | align (s) | clips (s) | Error |
|---|---|---|---|---|---|---|---|---|---|
| Prepare | 373613 | 373624 | 8.6 | 2.4 | 69.1 | 252.0 | 12.1 | 25.0 |  |
| Prepare again, another photo | 362889 | 362899 | 0.5 | 2.7 | 75.5 | 245.0 | 11.7 | 23.4 |  |

## Start now

Milliseconds from Start now to each state first seen (asked every 50 ms; the page asks every 500 ms), then the first prompt after it.

| What | Person | States | Chat open | Warm-up wait | First word heard | Error |
|---|---|---|---|---|---|---|
| Start now | - | downloading 2, failed 2653 | - | - | - | The person couldn't be downloaded. Check the internet connection and click Try again. |
| Switch person | - | downloading 3, failed 2585 | - | - | - | The person couldn't be downloaded. Check the internet connection and click Try again. |
