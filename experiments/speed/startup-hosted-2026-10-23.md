# Where the time goes: start-up and the first load

## Start-up (Larry's timings 7 and 10)

Milliseconds from the app's process starting.

| Part | Began | Ended | Took | Error |
|---|---|---|---|---|
| app made | 1870.0 | 2132.8 | 262.8 | - |
| face models | 1894.6 | 3505.8 | 1611.2 | - |
| speaker model | 1900.6 | 2859.7 | 959.1 | - |
| reply warm-up | 2122.5 | 14728.5 | 12606.0 | - |
| LLM warm-up | 2124.1 | 2158.7 | 34.6 | - |
| voice and video warm-up | 2126.5 | 14728.4 | 12601.9 | - |
| server listening | 2598.4 | 2598.4 | 0.0 | - |
| ready | 14728.8 | 14728.8 | 0.0 | - |
| time-startup began | 25588 | 25588 | 0 | - |

## The first prompt and the next

Milliseconds from each prompt being sent. The first after the start against the next shows whether the warm-up left the LLM at its usual speed.

| Reply | Prompt | Warm-up wait | Turn wait | History tokens | Looked up | Asked tokens | Reached LLM | Prompt tokens read | Reused from cache | Read tokens/s | First token | First sentence | Last token | Tokens written | Written tokens/s | First sentence to heard | First word heard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | typed | 0.0 | 0.1 | 924 | 0.4 | 14 | 38 | 953 | 0 | 14.5 | 65604 | 67415 | 69640 | 20 | 4.7 | 2892 | 70308 |
| 2 | typed | 0.0 | 0.1 | 965 | 0.3 | 17 | 9 | 43 | 948 | 10.8 | 4004 | 4611 | 8582 | 23 | 4.8 | 2354 | 6965 |

### Reply 1: Hello! Who are you?

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 67416 | 0 | 2766 | 912 | 70182 | 70192 | 70308 | 71126 | 2.47 | 70308 | - |  |
| 2 | 69640 | 1454 | 2925 | 1217 | 74019 | 74029 | 74159 | 75279 | 3.72 | 74159 | 1384 | yes |

### Reply 2: What is the tallest mountain in the world?

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4611 | 0 | 2231 | 742 | 6842 | 6856 | 6965 | 7631 | 1.59 | 6965 | - |  |
| 2 | 7761 | 0 | 1790 | 613 | 9551 | 9557 | 9671 | 10181 | 1.76 | 9671 | 1113 | yes |
| 3 | 8582 | 1582 | 3295 | 1257 | 13459 | 13470 | 13603 | 14718 | 4.27 | 13603 | 2169 | yes |

## The browser's first load

Each group fetched at once over 6 connections, compressed, as a browser does; one group after the other.

| What | Files | Bytes | Took (ms) | Failed |
|---|---|---|---|---|
| page | 1 | 446 | 8 | - |
| scripts and styles | 3 | 74025 | 27 | - |
| fonts | 2 | 122772 | 6 | - |
| face pictures | 68 | 318909 | 161 | - |
| all | 74 | 516152 | 202 | - |

## Opening the chat after a restart

| Request | Status | First byte | Took (ms) |
|---|---|---|---|
| api/consent | 200 | 10 | 10 |
| api/settings | 200 | 8 | 8 |
| api/review | 200 | 15 | 15 |
| api/start-now | 200 | 10 | 10 |
| api/chat | 200 | 12 | 12 |
| api/chat/hints | 200 | 14 | 14 |
| api/chat/photo | 200 | 38 | 38 |
| api/chat/idle | 200 | 10 | 12 |

All at once: 47 ms.

Welcome back's video: first byte in 4 ms, 71242 bytes in 4 ms (status 200).

## Changing the LLM in Settings

Saved in 3 ms; the next prompt, in ms from being sent:

| Reply | Prompt | Warm-up wait | Turn wait | History tokens | Looked up | Asked tokens | Reached LLM | Prompt tokens read | Reused from cache | Read tokens/s | First token | First sentence | Last token | Tokens written | Written tokens/s | First sentence to heard | First word heard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | typed | 0.0 | 0.1 | 1012 | 0.3 | 17 | 37 | 46 | 986 | 4.2 | 11255 | 12509 | 15769 | 20 | 4.2 | 2920 | 15430 |

### Reply 1: What is the tallest mountain in the world?

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 12510 | 0 | 2740 | 881 | 15250 | 15269 | 15430 | 16138 | 2.16 | 15430 | - |  |
| 2 | 15769 | 362 | 3482 | 1319 | 19613 | 19619 | 19759 | 20979 | 4.44 | 19759 | 2167 | yes |
