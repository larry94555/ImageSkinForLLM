# Default people (R24a test pictures)

Eight made-up people from the R24a default person test (`experiments/default_person/`), one for
each gender and realism in four roles. Each was made by
[Segmind SSD-1B](https://huggingface.co/segmind/SSD-1B) (Apache 2.0, revision
`60987f37e94cd59c36b1cba832b9f97b57395a10`) from the prompt that
`default_person.py` builds for it (`prompt`), with seed 1, 25 steps, at 1024 by 1024. None is
based on a real person or a public figure, and no prompt names one. All eight pass the app's
photo checks and animate with the photoreal engine.

The eight files ending in `_2` are R24a2's second faces (`default_person.py --varied`), one for each of the first eight, each of a different heritage, made the same way from `VARIED_PEOPLE`. All eight also pass the photo checks and animate. `contact-sheet.png` shows the first faces above the second faces. The four Teenager pictures (`*_teenager*.png`) were taken out on 2026-10-24, since every default person is an adult (Larry, R24b4), so six of each are left.

The file name is `<realism>_<gender>_<role>.png`, with `_2` for a second face; the name never says the look. R24b makes all 36 people and packs them for
download; these are kept as the first reviewed set.
