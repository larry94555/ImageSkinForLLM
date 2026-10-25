# Picture against sound in the browser, cloud session, 2026-10-25

`node browser_sync.js` five times on the media `mouth_lead.py --media` writes, in headless Chromium 153 on a 4-core cloud machine with no sound card (Chromium's own stand-in for one). Clip 1 is a whole MP4 started over the muted idle video; clips 2 and 3 are progressive MP4s, each started by the hidden second player as the one before ends, as ClipPlayer does.

## Run 1

| Clip | Mark | Picture ahead of sound |
|---|---|---|
| 1 (marks-whole.mp4) | 0.6 s | 16 ms |
| 1 (marks-whole.mp4) | 1.6 s | 16 ms |
| 1 (marks-whole.mp4) | 2.6 s | 16 ms |
| 2 (marks-progressive.mp4) | 0.6 s | 32 ms |
| 2 (marks-progressive.mp4) | 1.6 s | 31 ms |
| 2 (marks-progressive.mp4) | 2.6 s | 31 ms |
| 3 (marks-progressive.mp4) | 0.6 s | 33 ms |
| 3 (marks-progressive.mp4) | 1.6 s | 33 ms |
| 3 (marks-progressive.mp4) | 2.6 s | 33 ms |

## Run 2

| Clip | Mark | Picture ahead of sound |
|---|---|---|
| 1 (marks-whole.mp4) | 0.6 s | 35 ms |
| 1 (marks-whole.mp4) | 1.6 s | 34 ms |
| 1 (marks-whole.mp4) | 2.6 s | 34 ms |
| 2 (marks-progressive.mp4) | 0.6 s | 31 ms |
| 2 (marks-progressive.mp4) | 1.6 s | 32 ms |
| 2 (marks-progressive.mp4) | 2.6 s | 31 ms |
| 3 (marks-progressive.mp4) | 0.6 s | 33 ms |
| 3 (marks-progressive.mp4) | 1.6 s | 33 ms |
| 3 (marks-progressive.mp4) | 2.6 s | 33 ms |

## Run 3

| Clip | Mark | Picture ahead of sound |
|---|---|---|
| 1 (marks-whole.mp4) | 0.6 s | 21 ms |
| 1 (marks-whole.mp4) | 1.6 s | 21 ms |
| 1 (marks-whole.mp4) | 2.6 s | 21 ms |
| 2 (marks-progressive.mp4) | 0.6 s | 31 ms |
| 2 (marks-progressive.mp4) | 1.6 s | 31 ms |
| 2 (marks-progressive.mp4) | 2.6 s | 31 ms |
| 3 (marks-progressive.mp4) | 0.6 s | 40 ms |
| 3 (marks-progressive.mp4) | 1.6 s | 40 ms |
| 3 (marks-progressive.mp4) | 2.6 s | 40 ms |

## Run 4

| Clip | Mark | Picture ahead of sound |
|---|---|---|
| 1 (marks-whole.mp4) | 0.6 s | 41 ms |
| 1 (marks-whole.mp4) | 1.6 s | 41 ms |
| 1 (marks-whole.mp4) | 2.6 s | 41 ms |
| 2 (marks-progressive.mp4) | 0.6 s | 29 ms |
| 2 (marks-progressive.mp4) | 1.6 s | 29 ms |
| 2 (marks-progressive.mp4) | 2.6 s | 29 ms |
| 3 (marks-progressive.mp4) | 0.6 s | 35 ms |
| 3 (marks-progressive.mp4) | 1.6 s | 35 ms |
| 3 (marks-progressive.mp4) | 2.6 s | 35 ms |

## Run 5

| Clip | Mark | Picture ahead of sound |
|---|---|---|
| 1 (marks-whole.mp4) | 0.6 s | 22 ms |
| 1 (marks-whole.mp4) | 1.6 s | 22 ms |
| 1 (marks-whole.mp4) | 2.6 s | 22 ms |
| 2 (marks-progressive.mp4) | 0.6 s | 40 ms |
| 2 (marks-progressive.mp4) | 1.6 s | 40 ms |
| 2 (marks-progressive.mp4) | 2.6 s | 40 ms |
| 3 (marks-progressive.mp4) | 0.6 s | 29 ms |
| 3 (marks-progressive.mp4) | 1.6 s | 29 ms |
| 3 (marks-progressive.mp4) | 2.6 s | 29 ms |

