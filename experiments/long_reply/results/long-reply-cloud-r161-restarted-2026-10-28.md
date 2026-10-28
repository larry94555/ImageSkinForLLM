# Where the pauses come from in a long reply (cloud-r161-restarted)

Times in milliseconds from the prompt being sent, rates in words a minute. A gap is playback waiting for the clip; the pause heard is the silence at the end of the clip before, the gap and the silence at the start of this one.

| Reply | Words | First word heard | Heard for (s) | Rate heard | Rate in clips | Speech rate | Own rate | LLM writes | Make/play | Gaps > 300 ms | Gap total (s) | Gap causes | Pauses heard > 300 ms | Of them mid-sentence | Cut together | Silence at joins (s) | Clip ends | Start/end silence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 152 | 37389 | 67 | 136 | 136 | 143 | - | 203 | 1.05 | 0 | 0 | - | 7 | 0 | 0 | 2.5 | none 1, sentence 8 | 50/300 |
| 2 | 220 | 21860 | 82.9 | 159 | 159 | 168 | - | 216 | 1.03 | 0 | 0 | - | 9 | 0 | 0 | 3.4 | none 1, clause 1, sentence 10 | 50/300 |
| 3 | 261 | 22737 | 102.2 | 153 | 154 | 164 | - | 208 | 1.09 | 1 | 0.7 | queued 1 | 12 | 0 | 0 | 4.8 | none 1, clause 3, sentence 13 | 50/300 |

## Reply 1: Tell me about the history of the bicycle.

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | none | 17106 | 0 | 2233 | 957 | 37389 | 37389 | 2.5 | 2.46 | 50/0 | - | - | - | - | The bicycle has a surprisingly |
| 2 | 4 | sentence | 18441 | 1857 | 2081 | 962 | 37394 | 39892 | 2.36 | 2.325 | 50/300 | 2495 | 0 | 50 | - | long and interesting history. |
| 3 | 16 | sentence | 22891 | 450 | 5206 | 2820 | 37393 | 42255 | 7.48 | 7.445 | 50/300 | 4859 | 0 | 350 | - | The first one, called the running machine, was built by Karl… |
| 4 | 19 | sentence | 28677 | 2690 | 5493 | 2943 | 37388 | 49737 | 7.47 | 7.425 | 50/300 | 12347 | 0 | 350 | - | It had two wheels and a wooden frame, but no pedals, so ride… |
| 5 | 28 | sentence | 37357 | 2447 | 10690 | 5040 | 50764 | 57205 | 13.4 | 13.355 | 50/300 | 6443 | 0 | 350 | - | In the 1860s, French makers added pedals to the front wheel,… |
| 6 | 24 | sentence | 44035 | 11499 | 6942 | 3917 | 62698 | 70603 | 9.96 | 9.915 | 50/300 | 7907 | 0 | 350 | - | Soon after came the penny farthing, with a huge front wheel … |
| 7 | 14 | sentence | 48043 | 18351 | 3629 | 2656 | 70230 | 80560 | 7.04 | 7.015 | 50/300 | 10333 | 0 | 350 | - | The real change came in 1885, when John Kemp Starley built t… |
| 8 | 24 | sentence | 54274 | 18405 | 3917 | 3102 | 76819 | 87603 | 8.16 | 8.12 | 50/300 | 10781 | 0 | 350 | - | It had two wheels of the same size and a chain that drove th… |
| 9 | 18 | sentence | 60060 | 19640 | 3767 | 3739 | 83740 | 95766 | 8.67 | 8.625 | 50/300 | 12023 | 0 | 350 | - | With air-filled tyres added a few years later, cycling becam… |

## Reply 2: How do bees make honey?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | none | 3340 | 0 | 1715 | 619 | 21860 | 21860 | 1.52 | 1.495 | 50/0 | - | - | - | - | Bees make honey through |
| 2 | 10 | clause | 6009 | 0 | 2970 | 1558 | 21863 | 23383 | 3.95 | 3.91 | 50/120 | 1517 | 0 | 50 | - | a careful process that turns flower nectar into a thick, |
| 3 | 14 | sentence | 8012 | 2525 | 3770 | 2236 | 21863 | 27335 | 5.24 | 5.22 | 50/300 | 5470 | 0 | 170 | - | sweet food they can store for the winter. It starts with the… |
| 4 | 22 | sentence | 16468 | 75 | 6885 | 3905 | 23765 | 32578 | 9.28 | 9.255 | 50/300 | 8810 | 0 | 350 | - | They fly from flower to flower, sometimes visiting hundreds … |
| 5 | 19 | sentence | 21809 | 5526 | 4592 | 2864 | 32154 | 41861 | 7.14 | 7.1 | 50/305 | 9704 | 0 | 350 | - | The nectar is kept in a special honey stomach, separate from… |
| 6 | 14 | sentence | 25814 | 8977 | 3508 | 1911 | 38471 | 49004 | 5.02 | 4.98 | 50/300 | 10530 | 0 | 355 | - | While it is there, enzymes begin to break down the sugars in… |
| 7 | 18 | sentence | 30933 | 9278 | 4355 | 2811 | 44767 | 54026 | 6.52 | 6.495 | 50/300 | 9257 | 0 | 350 | - | When a forager returns to the hive, she passes the nectar to… |
| 8 | 17 | sentence | 35829 | 11549 | 5114 | 2692 | 52724 | 60549 | 6.35 | 6.305 | 50/300 | 7822 | 0 | 350 | - | The house bee chews it for a while, adding more enzymes, and… |
| 9 | 29 | sentence | 40725 | 14459 | 8537 | 4981 | 64053 | 66897 | 12.2 | 12.175 | 50/300 | 2846 | 0 | 350 | - | This is repeated several times, until the nectar has changed… |
| 10 | 21 | sentence | 49408 | 19297 | 3776 | 2679 | 72694 | 79099 | 7.39 | 7.35 | 50/300 | 6403 | 0 | 350 | - | At this point it is still very watery, so the bees fan it wi… |
| 11 | 23 | sentence | 55426 | 19734 | 3478 | 2778 | 78864 | 86492 | 8.16 | 8.135 | 50/300 | 7625 | 0 | 350 | - | When the honey is thick enough, with less than about twenty … |
| 12 | 29 | sentence | 62769 | 18648 | 4375 | 3572 | 86018 | 94655 | 10.08 | 10.045 | 50/300 | 8634 | 0 | 350 | - | A single bee makes only about a twelfth of a teaspoon of hon… |

## Reply 3: What should I know before I start running?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | none | 3116 | 0 | 1535 | 496 | 22737 | 22737 | 1.2 | 1.155 | 50/0 | - | - | - | - | Starting to run |
| 2 | 7 | clause | 5340 | 0 | 2394 | 806 | 22731 | 23935 | 2.03 | 1.99 | 50/120 | 1206 | 0 | 50 | - | is a great choice for your health, |
| 3 | 10 | sentence | 7565 | 978 | 3035 | 1971 | 22731 | 25968 | 4.07 | 4.03 | 50/300 | 3234 | 0 | 170 | - | and a little preparation will make it much more enjoyable. |
| 4 | 19 | sentence | 10902 | 2646 | 5224 | 2932 | 22748 | 30040 | 7.31 | 7.265 | 50/300 | 7290 | 0 | 350 | - | Here are the most important things to know before you begin.… |
| 5 | 9 | clause | 21820 | 0 | 2793 | 1332 | 24804 | 37348 | 3.16 | 3.14 | 50/120 | 12546 | 0 | 350 | - | Your shoes are the only real equipment you need, |
| 6 | 29 | sentence | 22486 | 3460 | 9505 | 4425 | 35729 | 40511 | 11.28 | 11.25 | 50/300 | 4779 | 0 | 170 | - | so it is worth visiting a running store, where the staff can… |
| 7 | 18 | sentence | 28494 | 11383 | 4813 | 2393 | 44844 | 51794 | 6.32 | 6.28 | 50/300 | 6947 | 0 | 350 | - | Many beginners try to do too much in the first few weeks, an… |
| 8 | 26 | sentence | 36728 | 10355 | 8722 | 4086 | 56038 | 58116 | 10.51 | 10.47 | 50/300 | 2076 | 0 | 350 | - | A good plan is to mix running and walking, for example one m… |
| 9 | 18 | sentence | 40066 | 19826 | 4856 | 2911 | 64962 | 68629 | 6.96 | 6.935 | 50/300 | 3664 | 0 | 350 | - | Over several weeks, you can run for longer and walk for less… |
| 10 | 29 | clause | 48303 | 19358 | 8392 | 4508 | 76279 | 76279 | 11.08 | 11.055 | 50/120 | -690 | 687 | 1037 | queued | Walk briskly for five minutes before you run, and walk again… |
| 11 | 11 | sentence | 52753 | 27808 | 2213 | 1385 | 82993 | 87362 | 3.75 | 3.705 | 50/300 | 4366 | 0 | 170 | - | Run at a pace where you can still hold a conversation. |
| 12 | 11 | sentence | 55899 | 28260 | 2307 | 1845 | 86702 | 91110 | 4.84 | 4.81 | 50/300 | 4410 | 0 | 350 | - | Drink water before and after your run, especially on hot day… |
| 13 | 14 | sentence | 59876 | 28436 | 2796 | 2246 | 91306 | 95952 | 5.59 | 5.545 | 50/300 | 4644 | 0 | 350 | - | Rest at least one day between runs at first, so your body ca… |
| 14 | 9 | sentence | 62769 | 30585 | 2205 | 1343 | 95747 | 101540 | 3.52 | 3.475 | 50/300 | 5795 | 0 | 350 | - | Listen to your body, and stop if something hurts. |
| 15 | 14 | sentence | 64548 | 32355 | 3252 | 2688 | 100355 | 105058 | 7.68 | 7.635 | 50/300 | 4705 | 0 | 350 | - | Finally, be patient with yourself. Progress in running comes… |
| 16 | 27 | sentence | 75228 | 27616 | 5361 | 3410 | 108420 | 112735 | 9.39 | 9.35 | 50/300 | 4318 | 0 | 350 | - | If you keep going for a couple of months, you will probably … |
| 17 | 7 | sentence | 76786 | 34830 | 1587 | 1068 | 113392 | 122128 | 2.76 | 2.735 | 50/300 | 8733 | 0 | 350 | - | Good luck, and enjoy your first runs! |
