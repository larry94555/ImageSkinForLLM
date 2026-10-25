# Mouth against voice after R128: af_heart

Lead is how long the mouth opens before the voice is heard (negative: after). Timings is the part from the sound timings, Frames the part from turning them into frames, and the MP4 columns how much later the sound is than the picture in the file.

## At the start of each clip

| Clip | Heard | Opens | Lead in the WAV | Timings | Frames | Sound later in whole MP4 | in progressive MP4 | Lead in the file |
|---|---|---|---|---|---|---|---|---|
| reply 1 | 0.300 s | 0.32 s | -20 ms | -50 ms | 30 ms | 0 ms | 0 ms | -20 ms |
| reply 2 | 0.320 s | 0.4 s | -80 ms | -55 ms | -25 ms | 0 ms | 0 ms | -80 ms |
| reply 3 | 0.325 s | 0.36 s | -35 ms | -25 ms | -10 ms | 0 ms | 0 ms | -35 ms |
| goodbye | 0.410 s | 0.44 s | -30 ms | -40 ms | 10 ms | 0 ms | 0 ms | -30 ms |
| welcome back | 0.380 s | 0.4 s | -20 ms | -70 ms | 50 ms | 0 ms | 0 ms | -20 ms |
| sample | 0.330 s | 0.36 s | -30 ms | -20 ms | -10 ms | 0 ms | 0 ms | -30 ms |

Lead in the file uses the progressive MP4 for reply clips and the whole one for the rest, as the app writes them.

## At each word after a pause

| Clip | Word | Heard | Opens | Lead | Timings | Frames |
|---|---|---|---|---|---|---|
| reply 2 | about | 3.415 s | 3.44 s | -25 ms | -60 ms | 35 ms |
| reply 3 | a | 1.525 s | 1.56 s | -35 ms | -50 ms | 15 ms |
| sample | How | 1.430 s | 1.44 s | -10 ms | -45 ms | 35 ms |
| sample | I'm | 2.505 s | 2.52 s | -15 ms | -70 ms | 55 ms |
| sample | Let | 6.325 s | 6.36 s | -35 ms | -50 ms | 15 ms |
| sample | Numbers | 7.885 s | 7.92 s | -35 ms | -65 ms | 30 ms |
| sample | question | 12.130 s | 12.16 s | -30 ms | -45 ms | 15 ms |
| sample | And | 14.280 s | 14.28 s | 0 ms | -70 ms | 70 ms |
| sample | wow | 15.385 s | – s | – ms | -65 ms | – ms |
| sample | She | 16.965 s | 17 s | -35 ms | -85 ms | 50 ms |
| sample | If | 19.250 s | 19.28 s | -30 ms | -50 ms | 20 ms |

## The aligner's word starts against Kokoro's own

107 words: the aligner's start is +75 ms from Kokoro's on average (median +73 ms, from +39 to +174 ms). Negative is earlier.

| Clip | Word | Aligner minus Kokoro |
|---|---|---|
| reply 1 | Hello | +46 ms |
| reply 1 | I'm | +62 ms |
| reply 1 | glad | +72 ms |
| reply 1 | you | +46 ms |
| reply 1 | asked | +155 ms |
| reply 2 | Mount | +61 ms |
| reply 2 | Everest | +129 ms |
| reply 2 | is | +96 ms |
| reply 2 | the | +74 ms |
| reply 2 | tallest | +77 ms |
| reply 2 | mountain | +86 ms |
| reply 2 | in | +60 ms |
| reply 2 | the | +66 ms |
| reply 2 | world | +78 ms |
| reply 2 | at | +89 ms |
| reply 2 | about | +89 ms |
| reply 2 | 8,849 | +84 ms |
| reply 2 | meters | +72 ms |
| reply 3 | Once | +125 ms |
| reply 3 | upon | +69 ms |
| reply 3 | a | +83 ms |
| reply 3 | time | +81 ms |
| reply 3 | a | +87 ms |
| reply 3 | cat | +55 ms |
| reply 3 | named | +59 ms |
| reply 3 | Milo | +85 ms |
| reply 3 | was | +68 ms |
| reply 3 | afraid | +78 ms |
| reply 3 | of | +52 ms |
| reply 3 | water | +84 ms |
| goodbye | Goodbye | +46 ms |
| welcome back | Welcome | +48 ms |
| welcome back | back | +70 ms |
| sample | This | +45 ms |
| sample | is | +70 ms |
| sample | a | +78 ms |
| sample | test | +58 ms |
| sample | How | +66 ms |
| sample | do | +49 ms |
| sample | I | +88 ms |
| sample | sound | +59 ms |
| sample | I'm | +77 ms |
| sample | speaking | +62 ms |
| sample | in | +64 ms |
| sample | my | +69 ms |
| sample | own | +127 ms |
| sample | voice | +57 ms |
| sample | or | +73 ms |
| sample | as | +81 ms |
| sample | close | +63 ms |
| sample | to | +63 ms |
| sample | it | +73 ms |
| sample | as | +68 ms |
| sample | a | +76 ms |
| sample | computer | +73 ms |
| sample | can | +44 ms |
| sample | get | +74 ms |
| sample | Let | +81 ms |
| sample | me | +72 ms |
| sample | try | +79 ms |
| sample | a | +69 ms |
| sample | few | +75 ms |
| sample | things | +50 ms |
| sample | Numbers | +87 ms |
| sample | one | +174 ms |
| sample | two | +39 ms |
| sample | three | +53 ms |
| sample | forty-five | +56 ms |
| sample | and | +72 ms |
| sample | nine | +67 ms |
| sample | hundred | +82 ms |
| sample | ninety-nine | +77 ms |
| sample | A | +106 ms |
| sample | question | +93 ms |
| sample | did | +63 ms |
| sample | you | +65 ms |
| sample | see | +61 ms |
| sample | that | +54 ms |
| sample | coming | +74 ms |
| sample | And | +89 ms |
| sample | a | +66 ms |
| sample | little | +65 ms |
| sample | excitement | +100 ms |
| sample | wow | +80 ms |
| sample | that's | +55 ms |
| sample | great | +76 ms |
| sample | news | +86 ms |
| sample | She | +73 ms |
| sample | sells | +78 ms |
| sample | seashells | +78 ms |
| sample | by | +77 ms |
| sample | the | +62 ms |
| sample | seashore | +82 ms |
| sample | If | +118 ms |
| sample | anything | +103 ms |
| sample | looks | +68 ms |
| sample | or | +83 ms |
| sample | sounds | +81 ms |
| sample | wrong | +79 ms |
| sample | tell | +59 ms |
| sample | me | +82 ms |
| sample | now | +62 ms |
| sample | so | +79 ms |
| sample | we | +64 ms |
| sample | can | +59 ms |
| sample | fix | +69 ms |
| sample | it | +87 ms |

Leads over 80 ms in the file: 0 of 17.
