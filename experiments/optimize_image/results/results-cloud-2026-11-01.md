# R233 optimize image results

## The default people's framing

| Picture | Margin above hair | Face share | Chin to bottom | Centre offset |
|---|---|---|---|---|
| animated_female_professor | 0.08 | 0.429 | 0.76 | +0.13 |
| animated_female_professor_2 | 0.04 | 0.463 | 0.60 | +0.07 |
| animated_male_boss | 0.03 | 0.486 | 0.66 | +0.01 |
| animated_male_boss_2 | 0.04 | 0.462 | 0.60 | -0.01 |
| animated_male_parent | 0.04 | 0.430 | 0.71 | -0.00 |
| animated_male_parent_2 | 0.08 | 0.466 | 0.60 | -0.01 |
| photoreal_female_boss | 0.00 | 0.501 | 0.50 | +0.18 |
| photoreal_female_boss_2 | 0.08 | 0.477 | 0.57 | +0.12 |
| photoreal_female_parent | 0.00 | 0.488 | 0.54 | +0.13 |
| photoreal_female_parent_2 | 0.00 | 0.439 | 0.69 | +0.14 |
| photoreal_male_professor | 0.04 | 0.498 | 0.49 | +0.03 |
| photoreal_male_professor_2 | 0.03 | 0.506 | 0.53 | +0.02 |
| **Median (the target)** | 0.04 | 0.471 | 0.60 | +0.05 |

## Framing each photo

| Photo | Size | Face px | Hair cut (landmarks / segments) | Neck cut (landmarks / segments) | Filled (landmarks / segments) | Face share after (landmarks / segments) |
|---|---|---|---|---|---|---|
| full_length.png | 832x1216 | 89 | 0.4% / 0.0% | 0.0% / 0.0% | 0% / 0% | 0.480 / 0.470 |
| high_collar.png | 1024x1024 | 464 | 0.0% / 0.0% | 0.0% / 0.0% | 1% / 2% | 0.470 / 0.474 |
| larry.jpg | 1920x1080 | 312 | 0.0% / 0.0% | 0.0% / 0.0% | 13% / 13% | 0.468 / 0.465 |
| long_hair.png | 1024x1024 | 297 | 0.1% / 0.0% | 0.0% / 0.0% | 0% / 0% | 0.468 / 0.456 |
| near_edge.png | 615x902 | 188 | 0.0% / 0.0% | 0.0% / 0.0% | 13% / 12% | 0.483 / 0.481 |
| turned.png | 1024x1024 | 381 | 0.0% / 0.0% | 0.0% / 0.0% | 0% / 0% | 0.470 / 0.471 |
| waist_up.png | 1024x1024 | 188 | 0.0% / 0.0% | 0.0% / 0.0% | 0% / 0% | 0.484 / 0.475 |
| default_photoreal_male_professor.png | 1024x1024 | 510 | 0.0% / 0.0% | 0.0% / 0.0% | 10% / 10% | 0.473 / 0.468 |
| default_photoreal_female_parent_2.png | 1024x1024 | 449 | 0.7% / 0.0% | 0.0% / 0.0% | 0% / 6% | 0.471 / 0.445 |

## Photo checks on each result (segments framing)

| Photo | lanczos | fsrcnn | espcn | realesrgan |
|---|---|---|---|---|
| full_length.png | fails: The photo is blurry | fails: The photo is blurry | fails: The photo is blurry | passes, score 92 (5024 ms) |
| high_collar.png | passes, score 96 (7 ms) | passes, score 94 (1086 ms) | passes, score 94 (584 ms) | passes, score 92 (7741 ms) |
| larry.jpg | passes, score 89 (5 ms) | passes, score 87 (526 ms) | passes, score 87 (310 ms) | passes, score 85 (3180 ms) |
| long_hair.png | passes, score 84 (5 ms) | passes, score 83 (413 ms) | passes, score 83 (260 ms) | passes, score 85 (2774 ms) |
| near_edge.png | passes, score 87 (4 ms) | passes, score 85 (827 ms) | passes, score 84 (481 ms) | passes, score 88 (1108 ms) |
| turned.png | passes, score 90 (4 ms) | passes, score 89 (634 ms) | passes, score 89 (393 ms) | passes, score 91 (5220 ms) |
| waist_up.png | passes, score 86 (4 ms) | passes, score 84 (727 ms) | passes, score 84 (548 ms) | passes, score 89 (1876 ms) |
| default_photoreal_male_professor.png | passes, score 82 (5 ms) | passes, score 82 (3 ms) | passes, score 82 (3 ms) | passes, score 82 (3 ms) |
| default_photoreal_female_parent_2.png | passes, score 85 (6 ms) | passes, score 84 (1082 ms) | passes, score 84 (1085 ms) | passes, score 85 (8815 ms) |

## Small faces: enlarged back and compared with the original

PSNR in dB on the face at the video's size (higher is closer to the original), then R9's sharpness (the check needs 0.05).

| Face px | lanczos | fsrcnn | espcn | realesrgan |
|---|---|---|---|---|
| 60 | 32.89 dB, 0.018 | 33.24 dB, 0.023 | 32.81 dB, 0.020 | 27.12 dB, 0.086 |
| 80 | 35.13 dB, 0.025 | 35.37 dB, 0.028 | 34.86 dB, 0.026 | 28.05 dB, 0.111 |
| 100 | 37.05 dB, 0.032 | 37.12 dB, 0.034 | 36.45 dB, 0.031 | 29.38 dB, 0.121 |
| 130 | 39.38 dB, 0.041 | 39.16 dB, 0.040 | 38.63 dB, 0.038 | 33.75 dB, 0.089 |
| 160 | 41.28 dB, 0.048 | 40.79 dB, 0.046 | 40.14 dB, 0.044 | 35.10 dB, 0.092 |
| 200 | 43.53 dB, 0.056 | 42.58 dB, 0.053 | 41.67 dB, 0.051 | 36.70 dB, 0.090 |

## Speed and size of each method

| Method | Model file | Load ms | Memory added (MB) | 256 px to 1024 px, ms |
|---|---|---|---|---|
| lanczos | 0 KB | 0 | 2 | 4 |
| fsrcnn | 38 KB | 2 | 276 | 258 |
| espcn | 84 KB | 1 | 111 | 176 |
| realesrgan | 4752 KB | 40 | 75 | 416 |
