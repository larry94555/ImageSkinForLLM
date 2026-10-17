# Default people (R24a test pictures)

Eight made-up people from the R24a default person test (`experiments/default_person/`), one for
each gender and realism in four roles. Each was made by
[Segmind SSD-1B](https://huggingface.co/segmind/SSD-1B) (Apache 2.0, revision
`60987f37e94cd59c36b1cba832b9f97b57395a10`) from the prompt that
`default_person.py` builds for it (`prompt`), with seed 1, 25 steps, at 1024 by 1024. None is
based on a real person or a public figure, and no prompt names one. All eight pass the app's
photo checks and animate with the photoreal engine.

The file name is `<realism>_<gender>_<role>.png`. R24b makes all 36 people and packs them for
download; these are kept as the first reviewed set.
