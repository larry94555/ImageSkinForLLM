# The default people (R24b, R24b2 and R24b3)

`make_default_people.py` makes, checks and packs the 68 ready-made people that **Start now with
a default person** offers (features.md items 56 to 58 and 60): one for each binary gender, realism
(photoreal or animated) and role, a second face for 24 of them (R24b2), and 8 nonbinary people (R24b3). Who they are is in `src/imageskin/default_people.py`
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
glasses, at least three in their 60s or 70s (not as Young Adult, Student or Teaching Assistant) and
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

## The nonbinary people (R24b3)

Larry asked for nonbinary people of a range of heritages (2026-10-21), 6 to 8 of them:
`NONBINARY_PEOPLE` in `default_people.py` has 8, four for each realism, each of the eight
heritages once, and in each realism one older person and one with glasses (no wheelchair, which
Larry said isn't needed). The prompt asks for an "androgynous person" and keeps feminine,
masculine, makeup, lipstick, earrings, jewelry, beard and moustache out (`GENDERED`); quick drafts
at 640 by 640 and 12 steps tried four wordings first, since the first full picture read as a
woman. Their voice is an even blend of the accent's woman's and man's Kokoro voice (`VOICES`).
`looks_shown.json` counts them as one group, `nonbinary`, over both realisms.

## Only adults (R24b4)

Larry asked that every default person be 18 or over (2026-10-24). The Teenager role, asked for
as "aged sixteen" in a hoodie, became Young Adult, and four more people who looked sixteen or
seventeen at their role's age are listed in `LOOKED_YOUNG` (in `default_people.py`) and asked for
older. All 14 are asked for as an "adult" woman, man or androgynous person in their late
twenties; quick drafts of "young" or "mid twenties", or in a hoodie, still looked like
teenagers. The animated style, and an androgynous face, make a face look younger still: the
first full pictures of these looked about eighteen. So the animated women and men are asked for
in their early thirties, the photoreal nonbinary people in their late thirties and the animated
nonbinary person in their early forties, all with "child, teenager, childlike face" in the
negative prompt (`CHILDLIKE`). As an adult in an apartment, the animated woman in a wheelchair
was drawn full length with her face too small on three seeds; her look now asks for waist-up,
with fewer words to stay within 77 tokens, and passed on seed 2. Every one of the 14 was looked
at to check that they read as an adult. The young adults keep the younger voices the teenagers
had.

## The voices (R24e)

Larry found the voices didn't fit the faces (2026-10-22): a voice was picked only by gender and
accent, so a teenager, a Student and a woman in her seventies all spoke in `af_heart`.
Each person now has a voice of their own for each accent (`VOICE_CHOICES` and `person_voices()`
in `default_people.py`): the young adults take a younger voice, the people `looks_shown.json` marks
as in their sixties or seventies an older one, and the adults take turns over several. The turns
go in the avatar page's order within each look, so no face has the same voice as either of the
two faces before it, which are a different gender or the same role's other face.

Kokoro has no young or older voices, so the choice is by measured median pitch (the voice's
pitch while saying one line, by autocorrelation, in `hear_voices.py`), with blends of two voices
where no single voice is high or low enough, and Kokoro's own grades in its VOICES.md to avoid
its weakest voices (`af_nicole` whispers, `am_santa` and `am_adam` are graded lowest). No speed
change was needed. Pitches in Hz, saying "Hello, it's good to meet you. Ask me anything you like
about the course." on 2026-10-22:

| Voices | Younger | Adult | Older |
|---|---|---|---|
| American woman | `af_bella` 200, `af_bella,af_jessica` 205 | `af_heart` 203, `af_sarah` 202, `af_aoede` 185, `af_nova` 168, `af_sky` 168 | `af_kore` 160, `af_kore,af_alloy` 156 |
| American man | `am_fenrir` 154, `am_fenrir,am_eric` 159 | `am_michael` 124, `am_puck` 121, `am_liam` 133, `am_echo` 115 | `am_onyx,am_michael` 105, `am_onyx,am_echo` 100 |
| American nonbinary | `af_bella,am_fenrir` 181 | `af_heart,am_michael` 167, `af_sarah,am_puck` 158 | `af_kore,am_michael` 148 |
| British woman | `bf_alice` 235, `bf_alice,bf_isabella` 233 | `bf_emma` 189, `bf_isabella` 209, `bf_lily` 200 | `bf_emma,af_kore` 175, `bf_emma,af_alloy` 175 |
| British man | `bm_george,am_fenrir` 153, `bm_fable,am_fenrir` 139 | `bm_george` 149, `bm_fable` 128, `bm_daniel` 131 | `bm_lewis` 103, `bm_lewis,bm_daniel` 120 |
| British nonbinary | `bf_alice,bm_george` 191 | `bf_emma,bm_george` 171, `bf_isabella,bm_fable` 174 | `bf_emma,bm_lewis` 154 |

Kokoro has only four British women's and four British men's voices, so the British older women
blend `bf_emma` with an American woman's lower voice, and the British young men blend a
British man's voice with `am_fenrir`, the highest well-graded man's voice; the accent is the
British pronunciation, which the language code sets, not the voice. The first adult voice of each
kind is R24a's or R24b3's, so a ready-made voice saved before R24e is still offered. Pitch only
suggests age; these were not picked by listening, so `hear_voices.py` makes a page to listen to
every face in both accents:

```
python tools/default_people/hear_voices.py -o default-people/voices
```

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
`web/public/faces/` (not under `/default-people/`, which the hosted site keeps for the packs).

**Where the packs are hosted:** on the hosted site (R32a), at `https://<site>/default-people/<name>.zip`,
served by Caddy without the site's password, since they are made-up people and Start now on any
computer downloads them. The app's default address is `https://app.me0.ai/default-people`
(`HOSTED_URL` in `src/imageskin/start_now.py`); `IMAGESKIN_DEFAULT_PEOPLE_URL` changes it. They
were first planned as assets of a GitHub release, which a cloud session can't make.

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

## Uploading the packs to the hosted site (R32a)

The app downloads each person's pack from the hosted site and checks it against its size and
SHA-256 in `src/imageskin/default_people_packs.json`. Caddy serves the `.zip` files in
`deploy/default-people` on the server (`deploy/compose.yaml`); the folder isn't in git. After
making packs again, update that file, then copy all 60 packs there again.

1. On the server (connected as in `deploy/README.md`, step 4), make the folder, and update the
   site so Caddy serves it:

   ```
   cd ~/ImageSkinForLLM/deploy
   git pull
   mkdir -p default-people
   sudo chown ubuntu:ubuntu default-people
   docker compose up -d --build
   ```

2. On your laptop, from the folder that holds the 60 packs, copy them over (replace
   `129.146.1.2` with your machine's IP, as in step 4 of `deploy/README.md`). About 1.5 GB.

   macOS / Linux:
   ```
   scp -i ~/.ssh/oracle.key *.zip ubuntu@129.146.1.2:ImageSkinForLLM/deploy/default-people/
   ```

   Windows 11, Command Prompt:
   ```
   for %f in (*.zip) do scp -i "%USERPROFILE%\.ssh\oracle.key" "%f" ubuntu@129.146.1.2:ImageSkinForLLM/deploy/default-people/
   ```

   Windows 11, PowerShell:
   ```
   scp -i "$env:USERPROFILE\.ssh\oracle.key" (Get-ChildItem *.zip).Name ubuntu@129.146.1.2:ImageSkinForLLM/deploy/default-people/
   ```

3. Check every pack from the real address, on your laptop with the app installed. Leave out
   `--url` when the site is `app.me0.ai`; otherwise give your `SITE_ADDRESS`. The command is the
   same on every platform:

   ```
   imageskin check-packs --url https://129-146-1-2.sslip.io/default-people
   ```

   It prints a line for each pack and ends with `60 of 60 packs match`. A pack that is missing
   or differs is printed as `WRONG <name>: ...` and the command exits with 1; copy that pack
   again. The packs need no password: `https://<site>/default-people/animated_female_boss.zip`
   downloads in a browser, while the rest of the site still asks for it.

The hosted app gets the packs from Caddy inside Docker (`http://caddy:8090`), so Start now on the
hosted site works without reaching its own public address.

### Trying Start now before the packs are uploaded

Serve a folder holding one or more packs, and point the app at it with
`IMAGESKIN_DEFAULT_PEOPLE_URL`. In one terminal, from the folder with the packs:

```
python -m http.server 9100 --bind 127.0.0.1
```

In another, start the app with the variable set (macOS / Linux, Command Prompt, PowerShell):

```
export IMAGESKIN_DEFAULT_PEOPLE_URL=http://127.0.0.1:9100
set IMAGESKIN_DEFAULT_PEOPLE_URL=http://127.0.0.1:9100
$env:IMAGESKIN_DEFAULT_PEOPLE_URL = "http://127.0.0.1:9100"
```

The log line `Downloading default person` shows the address each pack comes from. A person whose
pack isn't in the folder gets "This person isn't available to download yet."
