# Picture against sound in the browser, cloud session, 2026-10-25

`browser_sync.js` five times on the media `mouth_lead.py --media` writes, then `mouth_lead.py --browser`, in headless Chromium 153 on a 4-core cloud machine with no sound card (Chromium's own stand-in for one). The page plays them as ClipPlayer plays a reply: the muted idle video underneath, clip 1 (progressive, as reply clips are) faded in over it with the chat's 0.25 s opacity transition once it plays, then clips 2 and 3 (progressive) and 4 (whole, as the sample and fixed lines are), each loaded in a hidden second player that is shown, then played, when the clip before ends. Every clip has a white frame and a beep on its first frame and at 0.6, 1.6 and 2.6 s.

## Run 1

| Clip | Switch | First picture vs first sound | Half faded in vs first sound | White frame at 0 s | White frame at 0.6 s | White frame at 1.6 s | White frame at 2.6 s |
|---|---|---|---|---|---|---|---|
| 1 (marks-progressive.mp4) | idle video to the reply | -6 ms | -6 ms | 70 ms | 27 ms | 37 ms | 37 ms |
| 2 (marks-progressive.mp4) | from the clip before | 87 ms | 86 ms | 79 ms | 36 ms | 36 ms | 36 ms |
| 3 (marks-progressive.mp4) | from the clip before | 85 ms | 81 ms | 85 ms | 42 ms | 42 ms | 42 ms |
| 4 (marks-whole.mp4) | from the clip before | 44 ms | 37 ms | 33 ms | 33 ms | 33 ms | 33 ms |

## Run 2

| Clip | Switch | First picture vs first sound | Half faded in vs first sound | White frame at 0 s | White frame at 0.6 s | White frame at 1.6 s | White frame at 2.6 s |
|---|---|---|---|---|---|---|---|
| 1 (marks-progressive.mp4) | idle video to the reply | -1 ms | -1 ms | 85 ms | 42 ms | 42 ms | 42 ms |
| 2 (marks-progressive.mp4) | from the clip before | 90 ms | 81 ms | 84 ms | 41 ms | 41 ms | 41 ms |
| 3 (marks-progressive.mp4) | from the clip before | 87 ms | 75 ms | 82 ms | 39 ms | 39 ms | 39 ms |
| 4 (marks-whole.mp4) | from the clip before | 42 ms | 27 ms | 24 ms | 24 ms | 24 ms | 24 ms |

## Run 3

| Clip | Switch | First picture vs first sound | Half faded in vs first sound | White frame at 0 s | White frame at 0.6 s | White frame at 1.6 s | White frame at 2.6 s |
|---|---|---|---|---|---|---|---|
| 1 (marks-progressive.mp4) | idle video to the reply | -9 ms | -9 ms | 81 ms | 36 ms | 36 ms | 36 ms |
| 2 (marks-progressive.mp4) | from the clip before | 87 ms | 84 ms | 86 ms | 44 ms | 44 ms | 44 ms |
| 3 (marks-progressive.mp4) | from the clip before | 85 ms | 78 ms | 56 ms | 13 ms | 43 ms | 43 ms |
| 4 (marks-whole.mp4) | from the clip before | 45 ms | 31 ms | 28 ms | 28 ms | 28 ms | 28 ms |

## Run 4

| Clip | Switch | First picture vs first sound | Half faded in vs first sound | White frame at 0 s | White frame at 0.6 s | White frame at 1.6 s | White frame at 2.6 s |
|---|---|---|---|---|---|---|---|
| 1 (marks-progressive.mp4) | idle video to the reply | 7 ms | -10 ms | 79 ms | 37 ms | 37 ms | 37 ms |
| 2 (marks-progressive.mp4) | from the clip before | 86 ms | 84 ms | 87 ms | 44 ms | 44 ms | 44 ms |
| 3 (marks-progressive.mp4) | from the clip before | 89 ms | 84 ms | 76 ms | 34 ms | 44 ms | 44 ms |
| 4 (marks-whole.mp4) | from the clip before | 43 ms | 28 ms | 48 ms | 48 ms | 48 ms | 48 ms |

## Run 5

| Clip | Switch | First picture vs first sound | Half faded in vs first sound | White frame at 0 s | White frame at 0.6 s | White frame at 1.6 s | White frame at 2.6 s |
|---|---|---|---|---|---|---|---|
| 1 (marks-progressive.mp4) | idle video to the reply | 1 ms | 1 ms | 87 ms | 44 ms | 44 ms | 44 ms |
| 2 (marks-progressive.mp4) | from the clip before | 88 ms | 83 ms | 76 ms | 33 ms | 33 ms | 33 ms |
| 3 (marks-progressive.mp4) | from the clip before | 91 ms | 83 ms | 86 ms | 49 ms | 43 ms | 43 ms |
| 4 (marks-whole.mp4) | from the clip before | 45 ms | 34 ms | 31 ms | 31 ms | 31 ms | 31 ms |

