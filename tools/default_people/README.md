# The default people (R24b and R24b2)

`make_default_people.py` makes, checks and packs the 60 ready-made people that **Start now with
a default person** offers (features.md items 56 to 58 and 60): one for each gender, realism
(photoreal or animated) and role, and a second face for 24 of them (R24b2). Who they are is in `src/imageskin/default_people.py`
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

Then it writes `results.json`, `contact-sheet.png` with all 60 pictures (a row for each gender
and realism), a 128 by 128 JPEG thumbnail of each in `thumbnails/` for picking a face (R24c2),
and `index.html` with the report. The exit code is 0 only if all 60 passed.

## The looks

Larry asked for a range of people (2026-10-17). `LOOKS` in `default_people.py` holds nine skin
tones, heritages and hair; within each gender and realism the nine roles take the nine looks,
each group starting two further on, so each role's four people all look different and every
look appears in every gender and realism. The app never shows or names them; they only go
into the prompts. The person comes first in each prompt, since SSD-1B reads only 77 tokens of
it and drops the rest; every prompt fits (the longest is 74).

## The second faces (R24b2)

Larry asked for more people to find someone who looks like them (2026-10-17): across the 15
people of each gender and realism, all eight heritages, red and blond hair, at least three with
glasses, at least three in their 60s or 70s (not as Teenager, Student or Teaching Assistant) and
at least two with a visible disability. The first 36 already have red and blond hair and seven of
the heritages in every group, so `SECOND_FACES` in `default_people.py` gives each group the same
six: three older people (one with glasses, one in a wheelchair, one Indigenous), a young person
in a wheelchair and two more with glasses, over different roles and heritages. Glasses are taken
out of the negative prompt for the people who wear them; tinted glasses and glare stay in it, so
the photo checks can see the eyes.

SSD-1B drew no hearing aid, cochlear implant or white cane in any try, and leaves a wheelchair
out of a head-and-shoulders picture, so both visible disabilities are wheelchairs: the look
starts with "sitting in a modern wheelchair, its backrest, push handles and wheels clearly
visible", and these people drop the head-and-shoulders framing, which makes a waist-up picture
with a smaller face that still passes the photo checks.

SSD-1B can leave part of a prompt out, so the counts go by what the pictures show, not what was
asked: `looks_shown.json` records, for each of the 60, the heritage, red or blond hair, glasses,
age and disability seen by looking at the picture, and the report's table counts them for each
group. A unit test fails if any group falls short.

## The pack

A prepared library is about 165 MB, mostly the 200 frames of the idle loop. The model renders
only every 4th of those frames and prepare fills in the rest along the optical flow, so a pack
holds only the 50 rendered frames, and the mouth and eye shapes, as PNGs, with the library's
other arrays compressed: about 28 MB. `default_people.unpack` fills in the other frames the same
way prepare does, so the unpacked library is identical, bit for bit, to the one prepared here
(checked on the first person), and it takes about 3 seconds.

## Results (4-core cloud CPU, 2026-10-17)

All 36 passed on the first seed: photo check scores 79 to 92, the mouth moved 2.9 to 5.5 times
as much talking as idling, and the packs are 22.3 to 32.2 MB (0.97 GB for all 36). Each picture
took 9 to 10.5 minutes and each prepare 4 to 5.6, 8.5 hours in all.

**R24b2 (4-core cloud CPU, 2026-10-18):** all 24 second faces passed the photo checks (scores
77 to 91), the mouth moved 2.7 to 5.1 times as much talking as idling, and the packs are 22.5 to
31.4 MB (0.63 GB for the 24, 1.6 GB for all 60). Each picture took 10 to 17 minutes and each
prepare 4.5 to 5.8. Five pictures use another seed: two failed a photo check on seed 1 and the
script moved on by itself, and for three wheelchair people quick drafts of other seeds were
looked at first, since seed 1 left the wheelchair out or drew the face too small; their seed is
set in `SECOND_FACES`. Every one of the 60 pictures was looked at and `looks_shown.json` records what it
shows; every group of 15 meets every count. The 60 thumbnails are 456 KB in all and ship in
`web/public/default-people/`.

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
prepare it), so about 15 hours for all 60: every picture first, then the picture model is freed
before preparing, since both at once ran out of 16 GB of memory in R24a. A run picks up where an
earlier one stopped: packed people are kept, and pictures already made with the same prompt are
checked rather than made again. `--again` starts over; `--only <name> ...` runs some people.
