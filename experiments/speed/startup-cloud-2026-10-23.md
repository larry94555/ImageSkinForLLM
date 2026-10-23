# Where the time goes: start-up and the first load

## Start-up (Larry's timings 7 and 10)

Milliseconds from the app's process starting.

| Part | Began | Ended | Took | Error |
|---|---|---|---|---|
| llama-server answering /health | - | 5508 | - | - |
| time-startup began | 409 | 409 | 0 | - |
| app made | 2510.0 | 2856.8 | 346.8 | - |
| face models | 2537.8 | 5467.4 | 2929.6 | - |
| speaker model | 2544.4 | 3668.5 | 1124.1 | - |
| reply warm-up | 2853.2 | 46580.8 | 43727.6 | - |
| LLM warm-up | 2911.5 | 2999.2 | 87.7 | - |
| voice and video warm-up | 2924.4 | 46580.7 | 43656.3 | - |
| server listening | 2958.0 | 2958.0 | 0.0 | - |
| ready | 46581.2 | 46581.2 | 0.0 | - |

## The first prompt and the next

Milliseconds from each prompt being sent. The first after the start against the next shows whether the warm-up left the LLM at its usual speed.

| Reply | Prompt | Warm-up wait | Turn wait | History tokens | Looked up | Asked tokens | Reached LLM | Prompt tokens read | Reused from cache | Read tokens/s | First token | First sentence | Last token | Tokens written | Written tokens/s | First sentence to heard | First word heard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | typed | 0.0 | 0.2 | 0 | 0.3 | 14 | 44 | 107 | 0 | 33.9 | 3202 | 5880 | 8012 | 19 | 3.7 | 10087 | 15967 |
| 2 | typed | 0.0 | 0.2 | 40 | 0.2 | 17 | 27 | 42 | 102 | 30.7 | 1400 | 2899 | 6096 | 20 | 4.0 | 6287 | 9185 |

### Reply 1: Hello! Who are you?

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5880 | 0 | 9898 | 803 | 15778 | 15807 | 15967 | 16583 | 2.8 | 15967 | - |  |
| 2 | 8013 | 8569 | 3862 | 397 | 20444 | 20456 | 20565 | 20870 | 1.48 | 20565 | 1795 | yes |

### Reply 2: What is the tallest mountain in the world?

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2899 | 0 | 6168 | 491 | 9067 | 9078 | 9185 | 9600 | 1.52 | 9185 | - |  |
| 2 | 3647 | 5912 | 3394 | 325 | 12953 | 12960 | 13068 | 13333 | 1.0 | 13068 | 2360 | yes |
| 3 | 6096 | 7182 | 6744 | 707 | 20023 | 20038 | 20148 | 20761 | 2.84 | 20148 | 6077 | yes |

## The browser's first load

Each group fetched at once over 6 connections, compressed, as a browser does; one group after the other.

| What | Files | Bytes | Took (ms) | Failed |
|---|---|---|---|---|
| page | 1 | 446 | 11 | - |
| scripts and styles | 3 | 74025 | 41 | - |
| fonts | 2 | 122772 | 7 | - |
| face pictures | 68 | 318909 | 235 | - |
| all | 74 | 516152 | 294 | - |

## Opening the chat after a restart

| Request | Status | First byte | Took (ms) |
|---|---|---|---|
| api/consent | 200 | 10 | 10 |
| api/settings | 200 | 13 | 13 |
| api/review | 200 | 31 | 31 |
| api/start-now | 200 | 12 | 12 |
| api/chat | 200 | 17 | 17 |
| api/chat/hints | 200 | 18 | 18 |
| api/chat/photo | 200 | 44 | 44 |
| api/chat/idle | 200 | 22 | 25 |

All at once: 54 ms.

Welcome back's video: first byte in 10 ms, 91857 bytes in 10 ms (status 200).

## Changing the LLM in Settings

Saved in 4 ms; the next prompt, in ms from being sent:

| Reply | Prompt | Warm-up wait | Turn wait | History tokens | Looked up | Asked tokens | Reached LLM | Prompt tokens read | Reused from cache | Read tokens/s | First token | First sentence | Last token | Tokens written | Written tokens/s | First sentence to heard | First word heard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | typed | 0.0 | 0.2 | 84 | 0.3 | 17 | 33 | 182 | 0 | 34.6 | 7734 | 9800 | 13073 | 21 | 3.7 | 7756 | 17556 |

### Reply 1: What is the tallest mountain in the world?

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 9801 | 0 | 7633 | 513 | 17434 | 17448 | 17556 | 17969 | 1.92 | 17556 | - |  |
| 2 | 10412 | 7536 | 4103 | 409 | 22051 | 22051 | 22216 | 22473 | 1.36 | 22216 | 2737 | yes |
| 3 | 13073 | 9386 | 4685 | 512 | 27145 | 27158 | 27270 | 27675 | 1.76 | 27270 | 3691 | yes |
