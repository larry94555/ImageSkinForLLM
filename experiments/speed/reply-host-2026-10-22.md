# Where the time goes: a reply (Local (llama.cpp))

Larry's hosted machine (app.me0.ai: 4 Ampere cores, llama-server with Gemma 3 4B on 2 threads),
2026-10-22, `docker compose exec app imageskin time-reply --spoken 3 --stop`, as Larry pasted it.

All times in milliseconds from the prompt being sent.

| Reply | Prompt | Warm-up wait | Turn wait | History tokens | Prompt tokens read | Reused from cache | Read tokens/s | First token | First sentence | Last token | Tokens written | Written tokens/s | First sentence to heard | First word heard |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | typed | 0.0 | 0.1 | 0 | 106 | 1 | 14.9 | 7139 | 8956 | 10489 | 19 | 5.4 | 3529 | 12485 |
| 2 | typed | 0.0 | 0.1 | 40 | 48 | 102 | 14.0 | 3467 | 4563 | 8267 | 26 | 5.2 | 3860 | 8424 |
| 3 | spoken | 0.0 | 0.1 | 96 | 53 | 145 | 14.1 | 36235 | 37354 | 51351 | 75 | 4.9 | 3913 | 41267 |
| 4 | typed | - | - | - | - | - | - | - | - | - | - | - | - | - |

## Reply 1: Hello! Who are you?

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 8957 | 0 | 3092 | 1022 | 12049 | 12054 | 12485 | 13094 | 3.16 | 12485 | - |  |
| 2 | 10489 | 2582 | 1731 | 626 | 14802 | 14807 | 15229 | 15432 | 2.08 | 15648 | 0 |  |

## Reply 2: What is the tallest mountain in the world, and how high is it?

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4564 | 0 | 3322 | 922 | 7886 | 7905 | 8424 | 8834 | 2.52 | 8424 | - |  |
| 2 | 5311 | 3496 | 1892 | 671 | 10700 | 10710 | 11125 | 11380 | 2.2 | 11125 | 179 | yes |
| 3 | 8268 | 3103 | 3612 | 1329 | 14983 | 14993 | 15430 | 16343 | 4.64 | 15430 | 2102 | yes |

## Reply 3: Tell me a short story about a cat who learns to swim.

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 37356 | 0 | 3317 | 1079 | 40673 | 40673 | 41267 | 41787 | 2.59 | 41267 | - |  |
| 2 | 38505 | 3247 | 3295 | 1078 | 45046 | 45054 | 45633 | 46146 | 2.56 | 45633 | 1773 | yes |
| 3 | 39865 | 6259 | 3389 | 1070 | 49513 | 49537 | 50055 | 50625 | 2.74 | 50055 | 1859 | yes |
| 4 | 42891 | 7692 | 3902 | 1448 | 54485 | 54496 | 54934 | 55949 | 4.56 | 54934 | 2137 | yes |
| 5 | 44465 | 11467 | 1852 | 664 | 57785 | 57785 | 58368 | 58475 | 2.2 | 59497 | 0 |  |
| 6 | 47627 | 10822 | 4203 | 1531 | 62652 | 62657 | 63107 | 64223 | 5.39 | 63107 | 1408 | yes |
| 7 | 51352 | 12832 | 3682 | 1356 | 67865 | 67876 | 68320 | 69233 | 4.72 | 68500 | 0 |  |

## Reply 4: Tell me a short story about a cat who learns to swim.

Stop answered in 33 ms; the next prompt could be taken 997 ms after Stop.

| Clip | Sentence | Waited | Voice | Video | Listed | Seen | First byte | Downloaded | Seconds | Plays | Gap | Late |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 8826 | 0 | 3342 | - | 12169 | 12169 | - | - | - | - | - |  |
