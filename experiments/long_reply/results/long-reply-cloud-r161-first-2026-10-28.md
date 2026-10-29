# Where the pauses come from in a long reply (cloud-r161-first)

Times in milliseconds from the prompt being sent, rates in words a minute. A gap is playback waiting for the clip; the pause heard is the silence at the end of the clip before, the gap and the silence at the start of this one.

| Reply | Words | First word heard | Heard for (s) | Rate heard | Rate in clips | Speech rate | Own rate | LLM writes | Make/play | Gaps > 300 ms | Gap total (s) | Gap causes | Pauses heard > 300 ms | Of them mid-sentence | Cut together | Silence at joins (s) | Clip ends | Start/end silence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 152 | 23896 | 67.1 | 136 | 136 | 143 | - | 203 | 1.11 | 0 | 0 | - | 7 | 0 | 0 | 2.5 | none 1, sentence 8 | 50/300 |
| 2 | 220 | 21898 | 84.7 | 156 | 159 | 168 | - | 216 | 1.15 | 1 | 1.8 | queued 1 | 9 | 0 | 0 | 3.4 | none 1, clause 1, sentence 10 | 50/300 |
| 3 | 261 | 22529 | 101.4 | 154 | 154 | 164 | - | 208 | 1.03 | 0 | 0 | - | 12 | 0 | 0 | 4.8 | none 1, clause 3, sentence 13 | 50/300 |

## Reply 1: Tell me about the history of the bicycle.

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | none | 3593 | 0 | 3425 | 1124 | 23896 | 23896 | 2.51 | 2.465 | 55/0 | - | - | - | - | The bicycle has a surprisingly |
| 2 | 4 | sentence | 4927 | 3216 | 2856 | 1153 | 23905 | 26404 | 2.36 | 2.325 | 50/300 | 2501 | 0 | 50 | - | long and interesting history. |
| 3 | 16 | sentence | 9378 | 2775 | 6680 | 3301 | 23922 | 28767 | 7.48 | 7.445 | 50/300 | 4842 | 0 | 350 | - | The first one, called the running machine, was built by Karl… |
| 4 | 19 | sentence | 15166 | 6968 | 6636 | 3162 | 29045 | 36250 | 7.47 | 7.425 | 50/300 | 7202 | 0 | 350 | - | It had two wheels and a wooden frame, but no pedals, so ride… |
| 5 | 28 | sentence | 23847 | 8085 | 10851 | 5336 | 43060 | 43717 | 13.4 | 13.355 | 50/300 | 660 | 0 | 350 | - | In the 1860s, French makers added pedals to the front wheel,… |
| 6 | 24 | sentence | 30524 | 17596 | 4112 | 3748 | 52459 | 57115 | 9.96 | 9.915 | 50/300 | 4658 | 0 | 350 | - | Soon after came the penny farthing, with a huge front wheel … |
| 7 | 14 | sentence | 34533 | 21447 | 3098 | 2625 | 59290 | 67073 | 7.04 | 7.015 | 50/305 | 7785 | 0 | 350 | - | The real change came in 1885, when John Kemp Starley built t… |
| 8 | 24 | sentence | 40764 | 20941 | 4669 | 3122 | 66648 | 74115 | 8.16 | 8.12 | 50/300 | 7465 | 0 | 355 | - | It had two wheels of the same size and a chain that drove th… |
| 9 | 18 | sentence | 46548 | 22948 | 5150 | 3198 | 74935 | 82278 | 8.67 | 8.625 | 50/300 | 7340 | 0 | 350 | - | With air-filled tyres added a few years later, cycling becam… |

## Reply 2: How do bees make honey?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | none | 3351 | 0 | 1786 | 659 | 21898 | 21898 | 1.52 | 1.495 | 50/0 | - | - | - | - | Bees make honey through |
| 2 | 10 | clause | 6021 | 0 | 2934 | 1722 | 21900 | 23421 | 3.95 | 3.91 | 50/120 | 1518 | 0 | 50 | - | a careful process that turns flower nectar into a thick, |
| 3 | 14 | sentence | 8024 | 2654 | 4485 | 2515 | 21915 | 27373 | 5.24 | 5.22 | 50/300 | 5456 | 0 | 170 | - | sweet food they can store for the winter. It starts with the… |
| 4 | 22 | sentence | 16481 | 1198 | 8355 | 4807 | 26324 | 32616 | 9.28 | 9.255 | 50/300 | 6289 | 0 | 350 | - | They fly from flower to flower, sometimes visiting hundreds … |
| 5 | 19 | sentence | 21822 | 9020 | 5198 | 3393 | 36315 | 41899 | 7.12 | 7.095 | 50/300 | 5581 | 0 | 350 | - | The nectar is kept in a special honey stomach, separate from… |
| 6 | 14 | sentence | 25829 | 13605 | 3500 | 2084 | 43145 | 49022 | 5.02 | 4.98 | 50/300 | 5874 | 0 | 350 | - | While it is there, enzymes begin to break down the sugars in… |
| 7 | 18 | sentence | 30958 | 14059 | 4805 | 2646 | 50037 | 54044 | 6.52 | 6.495 | 50/300 | 4005 | 0 | 350 | - | When a forager returns to the hive, she passes the nectar to… |
| 8 | 17 | sentence | 35854 | 16615 | 4380 | 2758 | 57080 | 60567 | 6.35 | 6.305 | 50/300 | 3484 | 0 | 350 | - | The house bee chews it for a while, adding more enzymes, and… |
| 9 | 29 | sentence | 40754 | 18855 | 8872 | 4969 | 68719 | 68719 | 12.2 | 12.175 | 50/300 | -1802 | 1804 | 2154 | queued | This is repeated several times, until the nectar has changed… |
| 10 | 21 | sentence | 49437 | 24013 | 2987 | 3116 | 76711 | 80921 | 7.39 | 7.35 | 50/300 | 4208 | 0 | 350 | - | At this point it is still very watery, so the bees fan it wi… |
| 11 | 23 | sentence | 55453 | 24100 | 5761 | 3331 | 85559 | 88314 | 8.16 | 8.135 | 50/300 | 2752 | 0 | 350 | - | When the honey is thick enough, with less than about twenty … |
| 12 | 29 | sentence | 62798 | 25848 | 5969 | 4264 | 94955 | 96477 | 10.08 | 10.045 | 50/300 | 1519 | 0 | 350 | - | A single bee makes only about a twelfth of a teaspoon of hon… |

## Reply 3: What should I know before I start running?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | none | 3122 | 0 | 1744 | 518 | 22529 | 22529 | 1.2 | 1.155 | 50/0 | - | - | - | - | Starting to run |
| 2 | 7 | clause | 6014 | 0 | 1882 | 854 | 22530 | 23727 | 2.03 | 1.99 | 50/120 | 1199 | 0 | 50 | - | is a great choice for your health, |
| 3 | 10 | sentence | 7572 | 1180 | 2958 | 1708 | 22530 | 25760 | 4.07 | 4.03 | 50/300 | 3227 | 0 | 170 | - | and a little preparation will make it much more enjoyable. |
| 4 | 19 | sentence | 10912 | 2506 | 4882 | 2947 | 22546 | 29832 | 7.31 | 7.265 | 50/300 | 7284 | 0 | 350 | - | Here are the most important things to know before you begin.… |
| 5 | 9 | clause | 21380 | 0 | 2739 | 1477 | 24304 | 37140 | 3.16 | 3.14 | 50/120 | 12838 | 0 | 350 | - | Your shoes are the only real equipment you need, |
| 6 | 29 | sentence | 22492 | 3105 | 8606 | 4790 | 34487 | 40303 | 11.28 | 11.25 | 50/300 | 5813 | 0 | 170 | - | so it is worth visiting a running store, where the staff can… |
| 7 | 18 | sentence | 28507 | 10487 | 4320 | 2504 | 43528 | 51586 | 6.32 | 6.28 | 50/300 | 8055 | 0 | 350 | - | Many beginners try to do too much in the first few weeks, an… |
| 8 | 26 | sentence | 36746 | 9072 | 6936 | 4115 | 52980 | 57908 | 10.51 | 10.47 | 50/300 | 4926 | 0 | 350 | - | A good plan is to mix running and walking, for example one m… |
| 9 | 18 | sentence | 40084 | 16786 | 4710 | 2817 | 61761 | 68421 | 6.96 | 6.935 | 50/300 | 6657 | 0 | 350 | - | Over several weeks, you can run for longer and walk for less… |
| 10 | 29 | clause | 48318 | 16080 | 7860 | 4843 | 72560 | 75384 | 11.08 | 11.055 | 50/120 | 2821 | 0 | 350 | - | Walk briskly for five minutes before you run, and walk again… |
| 11 | 11 | sentence | 52780 | 24321 | 2148 | 1463 | 79445 | 86466 | 3.75 | 3.705 | 50/300 | 7019 | 0 | 170 | - | Run at a pace where you can still hold a conversation. |
| 12 | 11 | sentence | 55887 | 24826 | 2471 | 1768 | 83403 | 90214 | 4.84 | 4.81 | 50/300 | 6813 | 0 | 350 | - | Drink water before and after your run, especially on hot day… |
| 13 | 14 | sentence | 59891 | 25062 | 2809 | 2144 | 88037 | 95057 | 5.56 | 5.54 | 50/300 | 7017 | 0 | 350 | - | Rest at least one day between runs at first, so your body ca… |
| 14 | 9 | sentence | 62784 | 27123 | 1756 | 1255 | 91849 | 100620 | 3.52 | 3.48 | 50/300 | 8768 | 0 | 350 | - | Listen to your body, and stop if something hurts. |
| 15 | 14 | sentence | 64563 | 28355 | 2960 | 2749 | 96129 | 104142 | 7.68 | 7.635 | 50/300 | 8011 | 0 | 350 | - | Finally, be patient with yourself. Progress in running comes… |
| 16 | 27 | sentence | 75245 | 23383 | 3915 | 3413 | 102770 | 111820 | 9.39 | 9.35 | 50/300 | 9052 | 0 | 350 | - | If you keep going for a couple of months, you will probably … |
| 17 | 7 | sentence | 76804 | 29152 | 1429 | 994 | 107518 | 121213 | 2.76 | 2.735 | 50/300 | 13692 | 0 | 350 | - | Good luck, and enjoy your first runs! |
