# A quicker video of the person listening (R96e)

On Larry's hosted machine the idle loop, the video of the person listening between replies,
took 38 of Prepare's 52 minutes (R96b): LivePortrait rendered 50 of its 200 frames, every 4th,
at about 45 s each, and the frames between were filled in along the optical flow.

[options.py](options.py) renders loop frames one by one with LivePortrait as a reference, then
fills in the frames between every 4th, 8th or 12th one and scores them against the reference
(PSNR; above about 40 dB the difference can't be seen in a moving picture). "Mirrored" is the
motion R96e uses: every part of the head's drift is a cosine, so the loop's second half goes
back the way the first came and only frames 0 to 100 are rendered.

```
python experiments/idle_loop/options.py photo.png out_dir
```

## Cloud session, 2026-10-23

[results-cloud-2026-10-23.json](results-cloud-2026-10-23.json). A 4-core cloud CPU, the
default person `photoreal_male_professor.png`, 6.7 s a frame.

| Motion | Every | Frames rendered | Lowest PSNR | Mean PSNR |
|---|---|---|---|---|
| Before | 4 | 50 | 44.6 dB | 52.1 dB |
| Before | 8 | 25 | 41.1 dB | 48.6 dB |
| Before | 12 | 17 | 39.8 dB | 46.4 dB |
| Mirrored | 4 | 26 | 42.0 dB | 48.1 dB |
| **Mirrored** | **8** | **14** | **39.4 dB** | **44.8 dB** |
| Mirrored | 12 | 10 | 38.6 dB | 43.0 dB |

R96e uses the mirrored loop with every 8th frame and the middle one: 14 frames instead of 50.
Every 12th saves 4 more frames but its worst frames drop further, so 8 was kept.

`imageskin prepare` on the same photo, before and after:

| | Loop frames rendered | Loop step | Whole photo (shapes, loop, align) |
|---|---|---|---|
| Before | 50 | 256 s | 349 s |
| R96e | 14 | 74 s | 168 s |

On the hosted machine, at R96b's 45 s a frame, the loop step should drop from 38 minutes to
about 11, and Prepare from 52 minutes to about 25. The two loops side by side, each played three
times, are in the project files as `r96e-listening-video/listening_before_after.mp4`.

A default person's pack still holds every 4th frame of its loop as it was made, so the packs
already hosted keep working unchanged.
