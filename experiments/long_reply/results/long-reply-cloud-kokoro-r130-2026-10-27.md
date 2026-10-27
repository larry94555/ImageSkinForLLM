# Where the pauses come from in a long reply (cloud-kokoro-r130)

Times in milliseconds from the prompt being sent, rates in words a minute. A gap is playback waiting for the clip; the pause heard is the silence at the end of the clip before, the gap and the silence at the start of this one.

| Reply | Words | First word heard | Heard for (s) | Rate heard | Rate in clips | Speech rate | Own rate | LLM writes | Make/play | Gaps > 300 ms | Gap total (s) | Gap causes | Pauses heard > 300 ms | Of them mid-sentence | Cut together | Silence at joins (s) | Clip ends | Start/end silence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 152 | 17654 | 74.9 | 122 | 136 | 143 | 143 | 203 | 0.88 | 2 | 7.7 | text late 2 | 7 | 0 | 0 | 2.5 | none 1, sentence 8 | 50/300 |
| 2 | 220 | 12543 | 83.2 | 159 | 160 | 169 | 170 | 216 | 0.94 | 1 | 0.7 | queued 1 | 9 | 0 | 0 | 3.5 | none 1, clause 2, sentence 10 | 50/300 |
| 3 | 261 | 12445 | 101 | 155 | 155 | 165 | 166 | 208 | 0.93 | 0 | 0 | - | 13 | 0 | 0 | 5.1 | none 1, clause 3, sentence 14 | 50/300 |

## Reply 1: Tell me about the history of the bicycle.

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | none | 15405 | 0 | 2117 | 919 | 17654 | 17654 | 2.51 | 2.465 | 55/0 | - | - | - | - | The bicycle has a surprisingly |
| 2 | 4 | sentence | 16739 | 1703 | 1794 | 803 | 20362 | 20362 | 2.36 | 2.325 | 50/300 | -198 | 201 | 251 | queued | long and interesting history. |
| 3 | 16 | sentence | 21188 | 0 | 4961 | 2548 | 26362 | 26362 | 7.48 | 7.445 | 50/300 | -3640 | 3637 | 3987 | text late | The first one, called the running machine, was built by Karl… |
| 4 | 19 | sentence | 26975 | 1723 | 4306 | 2716 | 33164 | 33845 | 7.47 | 7.425 | 50/300 | 678 | 0 | 350 | - | It had two wheels and a wooden frame, but no pedals, so ride… |
| 5 | 28 | sentence | 35654 | 67 | 9384 | 4594 | 45327 | 45327 | 13.4 | 13.355 | 50/300 | -4012 | 4014 | 4364 | text late | In the 1860s, French makers added pedals to the front wheel,… |
| 6 | 24 | sentence | 42327 | 7372 | 5936 | 3552 | 55861 | 58724 | 9.96 | 9.915 | 50/300 | 2866 | 0 | 350 | - | Soon after came the penny farthing, with a huge front wheel … |
| 7 | 14 | sentence | 46331 | 12856 | 2318 | 2191 | 61664 | 68682 | 7.04 | 7.015 | 50/300 | 7020 | 0 | 350 | - | The real change came in 1885, when John Kemp Starley built t… |
| 8 | 24 | sentence | 52561 | 11135 | 2787 | 2530 | 66758 | 75725 | 8.16 | 8.12 | 50/300 | 8964 | 0 | 350 | - | It had two wheels of the same size and a chain that drove th… |
| 9 | 18 | sentence | 58347 | 10666 | 2898 | 2714 | 72128 | 83887 | 8.67 | 8.625 | 50/300 | 11757 | 0 | 350 | - | With air-filled tyres added a few years later, cycling becam… |

## Reply 2: How do bees make honey?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | none | 3329 | 0 | 1528 | 541 | 12543 | 12543 | 1.52 | 1.495 | 50/0 | - | - | - | - | Bees make honey through |
| 2 | 10 | clause | 5998 | 1 | 2787 | 1489 | 12539 | 14066 | 3.95 | 3.91 | 50/120 | 1524 | 0 | 50 | - | a careful process that turns flower nectar into a thick, |
| 3 | 14 | sentence | 8001 | 2274 | 3273 | 1883 | 13749 | 18018 | 5.24 | 5.215 | 50/300 | 4267 | 0 | 170 | - | sweet food they can store for the winter. It starts with the… |
| 4 | 6 | clause | 15566 | 0 | 1698 | 763 | 17390 | 23261 | 2.19 | 2.145 | 50/120 | 5868 | 0 | 350 | - | They fly from flower to flower, |
| 5 | 16 | sentence | 16455 | 1571 | 4260 | 2480 | 22490 | 25449 | 6.68 | 6.635 | 50/300 | 2961 | 0 | 170 | - | sometimes visiting hundreds in a single trip, and suck up th… |
| 6 | 19 | sentence | 21796 | 2972 | 4448 | 2666 | 29422 | 32126 | 7.14 | 7.1 | 50/300 | 2707 | 0 | 350 | - | The nectar is kept in a special honey stomach, separate from… |
| 7 | 14 | sentence | 25801 | 6081 | 3291 | 1831 | 35342 | 39269 | 5.02 | 4.98 | 50/300 | 3924 | 0 | 350 | - | While it is there, enzymes begin to break down the sugars in… |
| 8 | 18 | sentence | 30919 | 6086 | 4238 | 2271 | 41402 | 44292 | 6.52 | 6.495 | 50/300 | 2887 | 0 | 350 | - | When a forager returns to the hive, she passes the nectar to… |
| 9 | 17 | sentence | 35813 | 7701 | 4121 | 2433 | 47820 | 50815 | 6.35 | 6.305 | 50/300 | 2992 | 0 | 350 | - | The house bee chews it for a while, adding more enzymes, and… |
| 10 | 29 | sentence | 40708 | 9361 | 7526 | 4351 | 57867 | 57867 | 12.2 | 12.175 | 50/300 | -702 | 705 | 1055 | queued | This is repeated several times, until the nectar has changed… |
| 11 | 21 | sentence | 49388 | 12559 | 4334 | 2639 | 66479 | 70070 | 7.39 | 7.35 | 50/300 | 3588 | 0 | 350 | - | At this point it is still very watery, so the bees fan it wi… |
| 12 | 23 | sentence | 55396 | 13525 | 2999 | 2638 | 72136 | 77462 | 8.16 | 8.135 | 50/300 | 5324 | 0 | 350 | - | When the honey is thick enough, with less than about twenty … |
| 13 | 29 | sentence | 62738 | 11820 | 3582 | 3018 | 78360 | 85625 | 10.08 | 10.045 | 50/300 | 7262 | 0 | 350 | - | A single bee makes only about a twelfth of a teaspoon of hon… |

## Reply 3: What should I know before I start running?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | none | 3112 | 0 | 1357 | 494 | 12445 | 12445 | 1.2 | 1.155 | 50/0 | - | - | - | - | Starting to run |
| 2 | 7 | clause | 5336 | 0 | 1669 | 765 | 12440 | 13643 | 2.03 | 1.99 | 50/120 | 1205 | 0 | 50 | - | is a great choice for your health, |
| 3 | 10 | sentence | 7562 | 208 | 2597 | 1559 | 12448 | 15676 | 4.07 | 4.03 | 50/300 | 3225 | 0 | 170 | - | and a little preparation will make it much more enjoyable. |
| 4 | 11 | sentence | 10899 | 1028 | 2596 | 1420 | 14659 | 19748 | 3.95 | 3.91 | 50/300 | 5087 | 0 | 350 | - | Here are the most important things to know before you begin. |
| 5 | 8 | sentence | 13349 | 2595 | 2093 | 1043 | 18169 | 23701 | 2.88 | 2.855 | 50/300 | 5529 | 0 | 350 | - | First, get a good pair of running shoes. |
| 6 | 9 | clause | 19136 | 0 | 2318 | 1088 | 21619 | 26584 | 3.16 | 3.14 | 50/120 | 4962 | 0 | 350 | - | Your shoes are the only real equipment you need, |
| 7 | 26 | sentence | 22474 | 69 | 5461 | 3467 | 28278 | 29746 | 9.24 | 9.2 | 50/300 | 1466 | 0 | 170 | - | so it is worth visiting a running store, where the staff can… |
| 8 | 21 | sentence | 23586 | 7886 | 5269 | 3038 | 36932 | 38989 | 8.36 | 8.34 | 50/300 | 2054 | 0 | 350 | - | Second, start slowly. Many beginners try to do too much in t… |
| 9 | 26 | sentence | 36723 | 3057 | 6512 | 3842 | 46517 | 47352 | 10.51 | 10.47 | 50/300 | 832 | 0 | 350 | - | A good plan is to mix running and walking, for example one m… |
| 10 | 18 | sentence | 40049 | 10085 | 4261 | 2539 | 54621 | 57865 | 6.96 | 6.935 | 50/300 | 3241 | 0 | 350 | - | Over several weeks, you can run for longer and walk for less… |
| 11 | 29 | clause | 48282 | 8654 | 7010 | 3835 | 64166 | 64827 | 11.08 | 11.055 | 50/120 | 659 | 0 | 350 | - | Walk briskly for five minutes before you run, and walk again… |
| 12 | 11 | sentence | 52733 | 15048 | 2453 | 1366 | 70398 | 75910 | 3.75 | 3.705 | 50/300 | 5509 | 0 | 170 | - | Run at a pace where you can still hold a conversation. |
| 13 | 11 | sentence | 55848 | 15752 | 3095 | 1806 | 74891 | 79658 | 4.84 | 4.81 | 50/300 | 4769 | 0 | 350 | - | Drink water before and after your run, especially on hot day… |
| 14 | 14 | sentence | 59853 | 16648 | 3602 | 1987 | 80250 | 84500 | 5.56 | 5.54 | 50/300 | 4248 | 0 | 350 | - | Rest at least one day between runs at first, so your body ca… |
| 15 | 9 | sentence | 62746 | 19346 | 1507 | 1054 | 83757 | 90063 | 3.52 | 3.485 | 50/305 | 6303 | 0 | 350 | - | Listen to your body, and stop if something hurts. |
| 16 | 14 | sentence | 64525 | 20128 | 2435 | 2447 | 87250 | 93586 | 7.68 | 7.635 | 50/300 | 6333 | 0 | 355 | - | Finally, be patient with yourself. Progress in running comes… |
| 17 | 27 | sentence | 75204 | 14331 | 3228 | 2905 | 92980 | 101264 | 9.39 | 9.35 | 50/300 | 8286 | 0 | 350 | - | If you keep going for a couple of months, you will probably … |
| 18 | 7 | sentence | 76763 | 18906 | 1220 | 869 | 97073 | 110656 | 2.76 | 2.735 | 50/300 | 13581 | 0 | 350 | - | Good luck, and enjoy your first runs! |
