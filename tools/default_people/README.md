# The default people (R24b)

`make_default_people.py` makes, checks and packs the 36 ready-made people that **Start now with
a default person** offers (features.md items 56 to 58): one for each gender, realism
(photoreal or animated) and role. Who they are is in `src/imageskin/default_people.py`
(`people()`), so the app and this script share one list; the prompts are here (`prompt`).

## What it does, for each person

1. **Makes the picture** with [Segmind SSD-1B](https://huggingface.co/segmind/SSD-1B) (Apache
   2.0, picked in R24a), 25 steps at 1024 by 1024, at the revision R24a pinned. Every prompt asks
   for one made-up person facing the camera with a closed mouth, and names no real person or
   public figure (item 57).
2. **Runs the app's photo checks** (item 2). If one fails, it makes the picture again with the
   next seed, up to 3 seeds; a person who fails all 3 is reported and not packed.
3. **Prepares the picture** with the photoreal engine (R4c), as the app's Prepare step does.
4. **Checks it talks and idles:** it speaks a short line in the person's American voice and
   renders it, writes the idle loop as a video, and measures how much the mouth changes from
   frame to frame in each. Talking must move the mouth at least 1.5 times as much as idling.
5. **Packs it** as `packs/<name>.zip`: the picture and its prepared frames, at most 50 MB so it
   downloads in 20 seconds at 25 Mbit/s (item 57). A bigger pack fails the person.

Then it writes `results.json`, `contact-sheet.png` with all 36 pictures, and `index.html` with
the report. The exit code is 0 only if all 36 passed.

## The looks

Larry asked for a range of people (2026-10-17). `LOOKS` in `default_people.py` holds nine skin
tones, heritages and hair; within each gender and realism the nine roles take the nine looks,
each group starting two further on, so each role's four people all look different and every
look appears in every gender and realism. The app never shows or names them; they only go
into the prompts. The person comes first in each prompt, since SSD-1B reads only 77 tokens of
it and drops the rest; every prompt fits (the longest is 74).

## The pack

A prepared library is about 165 MB, mostly the 200 frames of the idle loop. The model renders
only every 4th of those frames and prepare fills in the rest along the optical flow, so a pack
holds only the 50 rendered frames, and the mouth and eye shapes, as PNGs, with the library's
other arrays compressed: about 28 MB. `default_people.unpack` fills in the other frames the same
way prepare does, so the unpacked library is identical, bit for bit, to the one prepared here
(checked on the first person), and it takes about 3 seconds.

**Where the packs are hosted:** as assets of a GitHub release of this repository (planned name
`default-people-1`). Downloading them needs no sign-in and costs nothing, a release asset may
be up to 2 GB, and they are kept out of the repository's history. R24c uploads them and
downloads one when it is chosen.

## Run it

Uses the app's own virtual environment with the `voice`, `photoreal` and `faces` extras, plus
the picture model's packages from `experiments/default_person/requirements.txt` (installed as
its README says), Python 3.11 or 3.12, and ffmpeg. On Linux without a desktop, MediaPipe needs
`libegl1`.

macOS / Linux:
```
source .venv/bin/activate
cd tools/default_people
python make_default_people.py -o ../../default-people
```

Windows 11, Command Prompt:
```
.venv\Scripts\activate.bat
cd tools\default_people
python make_default_people.py -o ..\..\default-people
```

Windows 11, PowerShell:
```
.venv\Scripts\Activate.ps1
cd tools\default_people
python make_default_people.py -o ..\..\default-people
```

It takes about 15 minutes a person on a 4-core CPU (about 10 to make the picture and 4 to 5 to
prepare it), so about 9 hours for all 36: every picture first, then the picture model is freed
before preparing, since both at once ran out of 16 GB of memory in R24a. A run picks up where an
earlier one stopped: packed people are kept, and pictures already made with the same prompt are
checked rather than made again. `--again` starts over; `--only <name> ...` runs some people.
