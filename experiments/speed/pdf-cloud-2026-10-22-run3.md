# Where the time goes: the wiki and answers from it (Local (llama.cpp))

## The PDF: sample.pdf

19 pages read as text (366 paragraphs); 3 wiki parts, 17 wiki topics. All times in milliseconds from the upload.

| Upload | Reading | Wiki | Total | Wiki build (server) |
|---|---|---|---|---|
| 6 | 701 | 3631470 | 3632177 | 3631500 |

| Stage | Steps | Took | Prompt tokens read | Reused | Tokens written |
|---|---|---|---|---|---|
| Topics | 3 | 647570 | 7982 | 0 | 1674 |
| Outline | 33 | 2983925 | 16954 | 872 | 10847 |

| Stage | Step | Took | Ended | Requests | Prompt tokens read | Reused from cache | Read tokens/s | Tokens written | Written tokens/s |
|---|---|---|---|---|---|---|---|---|---|
| Topics | 1 | 253158 | 253158 | 1 | 2827 | 0 | 42.0 | 660 | 3.6 |
| Topics | 2 | 202913 | 456071 | 1 | 2870 | 0 | 42.3 | 485 | 3.6 |
| Topics | 3 | 191499 | 647570 | 1 | 2285 | 0 | 46.2 | 529 | 3.8 |
| Outline | 1 | 66676 | 714246 | 1 | 527 | 0 | 53.0 | 238 | 4.3 |
| Outline | 2 | 119504 | 833749 | 1 | 819 | 10 | 50.3 | 424 | 4.1 |
| Outline | 3 | 55640 | 889389 | 1 | 278 | 10 | 50.3 | 207 | 4.2 |
| Outline | 4 | 132080 | 1021469 | 1 | 849 | 9 | 46.3 | 468 | 4.1 |
| Outline | 5 | 70461 | 1091931 | 1 | 377 | 9 | 44.2 | 254 | 4.2 |
| Outline | 6 | 55365 | 1147296 | 1 | 330 | 8 | 48.6 | 206 | 4.3 |
| Outline | 7 | 115826 | 1263121 | 1 | 844 | 7 | 48.5 | 410 | 4.2 |
| Outline | 8 | 42142 | 1305263 | 1 | 235 | 7 | 46.1 | 161 | 4.4 |
| Outline | 9 | 48452 | 1353716 | 1 | 275 | 6 | 51.2 | 193 | 4.5 |
| Outline | 10 | 128385 | 1482101 | 1 | 923 | 5 | 47.2 | 433 | 4.0 |
| Outline | 11 | 46790 | 1528890 | 1 | 257 | 6 | 45.2 | 163 | 4.0 |
| Outline | 12 | 62988 | 1591878 | 1 | 274 | 5 | 42.5 | 229 | 4.1 |
| Outline | 13 | 187447 | 1779325 | 1 | 1290 | 4 | 44.0 | 600 | 3.8 |
| Outline | 14 | 87669 | 1866994 | 1 | 493 | 4 | 49.9 | 321 | 4.1 |
| Outline | 15 | 140406 | 2007400 | 1 | 822 | 3 | 50.5 | 509 | 4.1 |
| Outline | 16 | 61032 | 2068432 | 1 | 299 | 3 | 49.0 | 235 | 4.3 |
| Outline | 17 | 47124 | 2115556 | 1 | 258 | 2 | 49.0 | 184 | 4.4 |
| Outline | 18 | 79913 | 2195469 | 1 | 473 | 1 | 54.5 | 301 | 4.2 |
| Outline | 19 | 128220 | 2323689 | 1 | 842 | 1 | 47.6 | 438 | 4.0 |
| Outline | 20 | 48067 | 2371756 | 1 | 285 | 1 | 45.5 | 179 | 4.3 |
| Outline | 21 | 61653 | 2433409 | 1 | 418 | 1 | 47.0 | 236 | 4.5 |
| Outline | 22 | 132211 | 2565620 | 1 | 846 | 1 | 51.7 | 481 | 4.2 |
| Outline | 23 | 40283 | 2605903 | 1 | 234 | 5 | 50.7 | 159 | 4.5 |
| Outline | 24 | 71375 | 2677278 | 1 | 376 | 4 | 53.0 | 277 | 4.3 |
| Outline | 25 | 78660 | 2755938 | 1 | 436 | 3 | 50.4 | 294 | 4.2 |
| Outline | 26 | 82986 | 2838924 | 1 | 521 | 2 | 45.6 | 292 | 4.1 |
| Outline | 27 | 64204 | 2903128 | 1 | 275 | 6 | 43.9 | 228 | 3.9 |
| Outline | 28 | 85655 | 2988783 | 1 | 482 | 5 | 40.7 | 300 | 4.1 |
| Outline | 29 | 92964 | 3081747 | 1 | 476 | 4 | 45.8 | 341 | 4.1 |
| Outline | 30 | 74634 | 3156381 | 1 | 462 | 1 | 50.1 | 282 | 4.3 |
| Outline | 31 | 81647 | 3238028 | 1 | 453 | 5 | 50.6 | 306 | 4.2 |
| Outline | 32 | 86398 | 3324426 | 1 | 485 | 4 | 42.1 | 298 | 4.0 |
| Outline | 33 | 307068 | 3631495 | 2 | 740 | 730 | 45.2 | 1200 | 4.1 |

## Answers from the wiki

All times in milliseconds from the prompt being sent.

| Reply | Prompt | Warm-up wait | Turn wait | History tokens | Looked up | Asked tokens | Reached LLM | Prompt tokens read | Reused from cache | Read tokens/s | First token | First sentence | Last token | Tokens written | Written tokens/s | First sentence to heard | First word heard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | typed | 0.0 | 0.2 | 374 | 36.2 | 380 | 86 | 811 | 0 | 39.3 | 20954 | 22205 | 25331 | 20 | 4.3 | 1056 | 23261 |
| 2 | spoken | 0.0 | 0.1 | 415 | 19.8 | 391 | 4156 | 856 | 1 | 45.4 | 23035 | 24709 | 31080 | 33 | 4.0 | 1445 | 26154 |
| 3 | typed | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 4 | typed | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 5 | typed | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 6 | typed | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 7 | typed | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 8 | typed | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 9 | typed | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |

### Reply 1: What is a prime number?

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 22205 | 1 | 836 | 643 | 23042 | 23052 | 23261 | 23717 | 1.64 | 23261 | - |  |
| 2 | 25332 | 0 | 2230 | 1557 | 27562 | 27579 | 27709 | 29132 | 5.24 | 27709 | 2805 | yes |

### Reply 2: What did Euler find about the primes and the zeta function?

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 24709 | 0 | 1210 | 777 | 25919 | 25944 | 26154 | 26717 | 2.0 | 26154 | - |  |
| 2 | 25550 | 1146 | 1050 | 754 | 27746 | 27762 | 27924 | 28536 | 2.16 | 28157 | 0 |  |
| 3 | 31081 | 1 | 4126 | 2191 | 35208 | 35230 | 35520 | 37405 | 7.28 | 35520 | 5201 | yes |

### Reply 3: How many primes are there below one million?

Error: Remote end closed connection without response

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

### Reply 4: What does the Riemann hypothesis say?

Error: Could not reach the app for the clips (<urlopen error [Errno 111] Connection refused>).

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

### Reply 5: How is the zeta function used in physics?

Error: Could not reach the app for the clips (<urlopen error [Errno 111] Connection refused>).

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

### Reply 6: What can you talk about?

Error: Could not reach the app for the clips (<urlopen error [Errno 111] Connection refused>).

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

### Reply 7: Teach me about Prime Numbers

Error: Could not reach the app for the clips (<urlopen error [Errno 111] Connection refused>).

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

### Reply 8: Quiz me on Prime Numbers

Error: Could not reach the app for the clips (<urlopen error [Errno 111] Connection refused>).

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

### Reply 9: Assess me

Error: Could not reach the app for the clips (<urlopen error [Errno 111] Connection refused>).

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
