# Where the pauses come from in a long reply (cloud-main)

Times in milliseconds from the prompt being sent, rates in words a minute. A gap is playback waiting for the clip; the pause heard is the silence at the end of the clip before, the gap and the silence at the start of this one.

| Reply | Words | First word heard | Heard for (s) | Rate heard | Rate in clips | Speech rate | Own rate | LLM writes | Make/play | Gaps > 300 ms | Gap total (s) | Gap causes | Pauses heard > 300 ms | Of them mid-sentence | Cut together | Silence at joins (s) | Clip ends | Start/end silence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 152 | 15513 | 81.9 | 111 | 136 | 143 | - | 203 | 1.13 | 5 | 14.9 | queued 5 | 8 | 1 | 0 | 2.5 | none 1, sentence 8 | 50/300 |
| 2 | 220 | 20344 | 83.2 | 159 | 159 | 168 | - | 216 | 1.07 | 1 | 0.4 | queued 1 | 9 | 0 | 0 | 3.4 | none 1, clause 1, sentence 10 | 50/300 |
| 3 | 261 | 20109 | 101.5 | 154 | 154 | 164 | - | 208 | 1.03 | 0 | 0 | - | 12 | 0 | 0 | 4.8 | none 1, clause 3, sentence 13 | 50/300 |

## Reply 1: Tell me about the history of the bicycle.

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | none | 12790 | 0 | 2542 | 1036 | 15513 | 15513 | 2.5 | 2.46 | 50/0 | - | - | - | - | The bicycle has a surprisingly |
| 2 | 4 | sentence | 14124 | 2244 | 2009 | 1005 | 18511 | 18511 | 2.36 | 2.325 | 50/300 | -498 | 495 | 545 | queued | long and interesting history. |
| 3 | 16 | sentence | 18574 | 809 | 5911 | 3022 | 25510 | 25510 | 7.48 | 7.445 | 50/300 | -4639 | 4637 | 4987 | queued | The first one, called the running machine, was built by Karl… |
| 4 | 19 | sentence | 24361 | 3956 | 5720 | 3047 | 34256 | 34256 | 7.47 | 7.425 | 50/300 | -1266 | 1263 | 1613 | queued | It had two wheels and a wooden frame, but no pedals, so ride… |
| 5 | 28 | sentence | 33047 | 4039 | 12222 | 6040 | 49638 | 49638 | 13.4 | 13.355 | 50/300 | -7912 | 7914 | 8264 | queued | In the 1860s, French makers added pedals to the front wheel,… |
| 6 | 24 | sentence | 39728 | 15620 | 8037 | 4071 | 63611 | 63611 | 9.96 | 9.915 | 50/300 | -573 | 576 | 926 | queued | Soon after came the penny farthing, with a huge front wheel … |
| 7 | 14 | sentence | 43733 | 23724 | 3552 | 2477 | 71223 | 73569 | 7.04 | 7.01 | 50/300 | 2348 | 0 | 350 | - | The real change came in 1885, when John Kemp Starley built t… |
| 8 | 24 | sentence | 49966 | 23522 | 4015 | 3138 | 77736 | 80611 | 8.16 | 8.12 | 50/300 | 2873 | 0 | 350 | - | It had two wheels of the same size and a chain that drove th… |
| 9 | 18 | sentence | 55754 | 24888 | 4437 | 3251 | 85364 | 88774 | 8.67 | 8.625 | 50/300 | 3407 | 0 | 350 | - | With air-filled tyres added a few years later, cycling becam… |

## Reply 2: How do bees make honey?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | none | 3339 | 0 | 1808 | 672 | 20344 | 20344 | 1.52 | 1.495 | 50/0 | - | - | - | - | Bees make honey through |
| 2 | 10 | clause | 6009 | 0 | 3308 | 1683 | 20345 | 21867 | 3.95 | 3.91 | 50/120 | 1519 | 0 | 50 | - | a careful process that turns flower nectar into a thick, |
| 3 | 14 | sentence | 8011 | 2989 | 4008 | 2182 | 20344 | 25820 | 5.24 | 5.22 | 50/300 | 5473 | 0 | 170 | - | sweet food they can store for the winter. It starts with the… |
| 4 | 22 | sentence | 16467 | 724 | 6924 | 3876 | 24343 | 31062 | 9.28 | 9.255 | 50/300 | 6717 | 0 | 350 | - | They fly from flower to flower, sometimes visiting hundreds … |
| 5 | 19 | sentence | 21808 | 6184 | 4898 | 2907 | 33113 | 40345 | 7.14 | 7.1 | 50/300 | 7229 | 0 | 350 | - | The nectar is kept in a special honey stomach, separate from… |
| 6 | 14 | sentence | 25821 | 9977 | 3496 | 2035 | 39473 | 47488 | 5.02 | 4.98 | 50/305 | 8012 | 0 | 350 | - | While it is there, enzymes begin to break down the sugars in… |
| 7 | 18 | sentence | 30939 | 10391 | 4763 | 2781 | 46364 | 52511 | 6.52 | 6.495 | 50/300 | 6144 | 0 | 355 | - | When a forager returns to the hive, she passes the nectar to… |
| 8 | 17 | sentence | 35834 | 13042 | 4439 | 2564 | 53520 | 59033 | 6.35 | 6.305 | 50/300 | 5511 | 0 | 350 | - | The house bee chews it for a while, adding more enzymes, and… |
| 9 | 29 | sentence | 40730 | 15150 | 9522 | 4958 | 65737 | 65737 | 12.2 | 12.175 | 50/300 | -354 | 356 | 706 | queued | This is repeated several times, until the nectar has changed… |
| 10 | 21 | sentence | 49418 | 20942 | 3427 | 2655 | 74012 | 77940 | 7.39 | 7.35 | 50/300 | 3925 | 0 | 350 | - | At this point it is still very watery, so the bees fan it wi… |
| 11 | 23 | sentence | 55426 | 21016 | 4162 | 2841 | 80825 | 85332 | 8.16 | 8.135 | 50/300 | 4505 | 0 | 350 | - | When the honey is thick enough, with less than about twenty … |
| 12 | 29 | sentence | 62771 | 20675 | 4695 | 3713 | 88410 | 93495 | 10.08 | 10.045 | 50/300 | 5082 | 0 | 350 | - | A single bee makes only about a twelfth of a teaspoon of hon… |

## Reply 3: What should I know before I start running?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | none | 3116 | 0 | 1933 | 547 | 20109 | 20109 | 1.2 | 1.155 | 50/0 | - | - | - | - | Starting to run |
| 2 | 7 | clause | 6008 | 0 | 1873 | 855 | 20111 | 21307 | 2.03 | 1.99 | 50/120 | 1198 | 0 | 50 | - | is a great choice for your health, |
| 3 | 10 | sentence | 7566 | 1171 | 2978 | 1711 | 20110 | 23340 | 4.07 | 4.03 | 50/300 | 3227 | 0 | 170 | - | and a little preparation will make it much more enjoyable. |
| 4 | 19 | sentence | 10903 | 2523 | 4816 | 2947 | 20108 | 27412 | 7.31 | 7.265 | 50/300 | 7302 | 0 | 350 | - | Here are the most important things to know before you begin.… |
| 5 | 9 | clause | 21367 | 0 | 2326 | 1206 | 23824 | 34720 | 3.16 | 3.14 | 50/120 | 10898 | 0 | 350 | - | Your shoes are the only real equipment you need, |
| 6 | 29 | sentence | 22479 | 2421 | 7714 | 4328 | 32835 | 37883 | 11.28 | 11.25 | 50/300 | 5045 | 0 | 170 | - | so it is worth visiting a running store, where the staff can… |
| 7 | 18 | sentence | 28489 | 8454 | 4134 | 2757 | 41285 | 49165 | 6.32 | 6.28 | 50/300 | 7878 | 0 | 350 | - | Many beginners try to do too much in the first few weeks, an… |
| 8 | 26 | sentence | 36722 | 7112 | 7096 | 4493 | 51146 | 55488 | 10.51 | 10.47 | 50/300 | 4339 | 0 | 350 | - | A good plan is to mix running and walking, for example one m… |
| 9 | 18 | sentence | 40059 | 15364 | 4736 | 2933 | 60373 | 66001 | 6.96 | 6.935 | 50/300 | 5625 | 0 | 350 | - | Over several weeks, you can run for longer and walk for less… |
| 10 | 29 | clause | 48293 | 14800 | 7818 | 4753 | 71181 | 72964 | 11.08 | 11.055 | 50/120 | 1780 | 0 | 350 | - | Walk briskly for five minutes before you run, and walk again… |
| 11 | 11 | sentence | 52744 | 22920 | 2931 | 1531 | 78804 | 84046 | 3.75 | 3.705 | 50/300 | 5240 | 0 | 170 | - | Run at a pace where you can still hold a conversation. |
| 12 | 11 | sentence | 55864 | 24263 | 2365 | 1929 | 82655 | 87794 | 4.84 | 4.81 | 50/300 | 5141 | 0 | 350 | - | Drink water before and after your run, especially on hot day… |
| 13 | 14 | sentence | 59869 | 24552 | 2945 | 2038 | 87581 | 92637 | 5.59 | 5.545 | 50/300 | 5053 | 0 | 350 | - | Rest at least one day between runs at first, so your body ca… |
| 14 | 9 | sentence | 62761 | 26643 | 1842 | 1164 | 91406 | 98224 | 3.52 | 3.48 | 50/300 | 6821 | 0 | 350 | - | Listen to your body, and stop if something hurts. |
| 15 | 14 | sentence | 64570 | 27841 | 3550 | 2632 | 96177 | 101747 | 7.68 | 7.635 | 50/300 | 5567 | 0 | 350 | - | Finally, be patient with yourself. Progress in running comes… |
| 16 | 27 | sentence | 75255 | 23338 | 3938 | 3264 | 102749 | 109425 | 9.39 | 9.35 | 50/300 | 6678 | 0 | 350 | - | If you keep going for a couple of months, you will probably … |
| 17 | 7 | sentence | 76813 | 28984 | 1592 | 900 | 107568 | 118817 | 2.76 | 2.735 | 50/300 | 11247 | 0 | 350 | - | Good luck, and enjoy your first runs! |
