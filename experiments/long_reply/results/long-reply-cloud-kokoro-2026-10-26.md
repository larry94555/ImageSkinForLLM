# Where the pauses come from in a long reply (cloud-kokoro)

Times in milliseconds from the prompt being sent, rates in words a minute. A gap is playback waiting for the clip; the pause heard is the silence at the end of the clip before, the gap and the silence at the start of this one.

| Reply | Words | First word heard | Heard for (s) | Rate heard | Rate in clips | Speech rate | Own rate | LLM writes | Make/play | Gaps > 300 ms | Gap total (s) | Gap causes | Pauses heard > 300 ms | Of them mid-sentence | Cut together | Silence at joins (s) | Clip ends | Start/end silence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 152 | 7567 | 72.9 | 125 | 158 | 182 | 181 | 203 | 1.22 | 5 | 15.2 | queued 5 | 8 | 1 | 0 | 6.4 | none 1, sentence 8 | 315/495 |
| 2 | 220 | 5164 | 88.2 | 150 | 182 | 219 | 217 | 216 | 1.17 | 10 | 15.5 | text late 1, queued 9 | 14 | 3 | 1 | 11 | none 2, clause 1, sentence 12 | 315/465 |
| 3 | 261 | 4716 | 111.1 | 141 | 162 | 214 | 210 | 208 | 1.05 | 9 | 12.9 | text late 2, queued 7 | 28 | 11 | 7 | 21.9 | none 7, clause 4, sentence 18 | 320/455 |

## Reply 1: Tell me about the history of the bicycle.

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | none | 3600 | 0 | 3769 | 1369 | 7567 | 7567 | 2.52 | 2.5 | 320/460 | - | - | - | - | The bicycle has a surprisingly |
| 2 | 4 | sentence | 4933 | 3805 | 2309 | 1079 | 11226 | 11226 | 2.36 | 2.325 | 335/495 | -1139 | 1136 | 1931 | queued | long and interesting history. |
| 3 | 16 | sentence | 9390 | 2738 | 6357 | 2966 | 18710 | 18710 | 6.47 | 6.425 | 300/515 | -5124 | 5121 | 5916 | queued | The first one, called the running machine, was built by Karl… |
| 4 | 19 | sentence | 15175 | 6276 | 4884 | 3260 | 26594 | 26594 | 6.52 | 6.475 | 315/470 | -1414 | 1416 | 2246 | queued | It had two wheels and a wooden frame, but no pedals, so ride… |
| 5 | 28 | sentence | 23854 | 5741 | 9722 | 5688 | 39697 | 39697 | 11.07 | 11.025 | 310/535 | -6583 | 6586 | 7366 | queued | In the 1860s, French makers added pedals to the front wheel,… |
| 6 | 24 | sentence | 30534 | 14472 | 6470 | 4109 | 51691 | 51691 | 8.34 | 8.3 | 290/470 | -924 | 926 | 1751 | queued | Soon after came the penny farthing, with a huge front wheel … |
| 7 | 14 | sentence | 34540 | 21046 | 2926 | 2545 | 58718 | 60033 | 5.99 | 5.95 | 325/510 | 1313 | 0 | 795 | - | The real change came in 1885, when John Kemp Starley built t… |
| 8 | 24 | sentence | 40773 | 20285 | 3406 | 3021 | 64722 | 66026 | 7.14 | 7.1 | 315/495 | 1301 | 0 | 825 | - | It had two wheels of the same size and a chain that drove th… |
| 9 | 18 | sentence | 46559 | 20925 | 3674 | 2977 | 71370 | 73169 | 7.32 | 7.275 | 305/485 | 1796 | 0 | 800 | - | With air-filled tyres added a few years later, cycling becam… |

## Reply 2: How do bees make honey?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | none | 3340 | 0 | 1545 | 1077 | 5164 | 5164 | 1.92 | 1.875 | 365/455 | - | - | - | - | Bees make honey through |
| 2 | 5 | none | 6010 | 0 | 2196 | 1149 | 8438 | 8438 | 2.28 | 2.25 | 300/420 | -1354 | 1357 | 2112 | text late | a careful process that turns |
| 3 | 5 | clause | 6010 | 3346 | 1775 | 1150 | 11319 | 11319 | 2.2 | 2.175 | 295/455 | -601 | 598 | 1313 | queued | flower nectar into a thick, |
| 4 | 8 | sentence | 8012 | 4268 | 2277 | 1378 | 14748 | 14748 | 2.74 | 2.7 | 290/490 | -1229 | 1226 | 1971 | queued | sweet food they can store for the winter. |
| 5 | 6 | sentence | 9793 | 6144 | 1684 | 1091 | 17805 | 17805 | 2.27 | 2.225 | 305/425 | -317 | 314 | 1109 | queued | It starts with the forager bees. |
| 6 | 22 | sentence | 16470 | 2242 | 6601 | 3573 | 25646 | 25646 | 7.84 | 7.8 | 330/460 | -5571 | 5573 | 6328 | queued | They fly from flower to flower, sometimes visiting hundreds … |
| 7 | 19 | sentence | 21810 | 7076 | 4063 | 2788 | 33162 | 33489 | 6 | 5.975 | 315/520 | 324 | 0 | 775 | - | The nectar is kept in a special honey stomach, separate from… |
| 8 | 14 | sentence | 25816 | 9923 | 2607 | 1996 | 38509 | 39492 | 4.4 | 4.375 | 325/495 | 980 | 0 | 845 | - | While it is there, enzymes begin to break down the sugars in… |
| 9 | 18 | sentence | 30936 | 9406 | 4873 | 2623 | 45450 | 45450 | 5.64 | 5.6 | 315/450 | -1558 | 1555 | 2365 | queued | When a forager returns to the hive, she passes the nectar to… |
| 10 | 17 | sentence | 35831 | 12007 | 4488 | 2606 | 52595 | 52595 | 5.4 | 5.375 | 300/490 | -1505 | 1503 | 2253 | queued | The house bee chews it for a while, adding more enzymes, and… |
| 11 | 16 | sentence | 40728 | 14205 | 4785 | 2813 | 59977 | 59977 | 5.84 | 5.8 | 325/535 | -1982 | 1979 | 2794 | queued | This is repeated several times, until the nectar has changed… |
| 12 | 13 | sentence | 44289 | 18242 | 3177 | 2120 | 65906 | 65906 | 4.34 | 4.3 | 320/510 | -89 | 87 | 942 | queued | Next, the bees spread the liquid into the wax cells of the h… |
| 13 | 21 | sentence | 49415 | 18413 | 2948 | 2859 | 71033 | 71033 | 6.28 | 6.25 | 315/465 | -787 | 784 | 1609 | queued | At this point it is still very watery, so the bees fan it wi… |
| 14 | 23 | sentence | 55426 | 18210 | 3473 | 3162 | 77432 | 77432 | 6.96 | 6.925 | 315/450 | -119 | 117 | 897 | queued | When the honey is thick enough, with less than about twenty … |
| 15 | 29 | sentence | 62773 | 17499 | 4419 | 3511 | 84968 | 84968 | 8.39 | 8.35 | 310/480 | -576 | 573 | 1333 | queued | A single bee makes only about a twelfth of a teaspoon of hon… |

## Reply 3: What should I know before I start running?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | none | 3114 | 0 | 1420 | 935 | 4716 | 4716 | 1.76 | 1.725 | 340/490 | - | - | - | - | Starting to run |
| 2 | 4 | none | 6005 | 0 | 1269 | 801 | 7457 | 7457 | 1.79 | 1.75 | 375/465 | -981 | 979 | 1844 | text late | is a great choice |
| 3 | 3 | clause | 6005 | 2071 | 1042 | 744 | 9292 | 9292 | 1.56 | 1.525 | 345/440 | -45 | 42 | 852 | queued | for your health, |
| 4 | 10 | sentence | 7563 | 2301 | 2397 | 1945 | 12497 | 12497 | 3.76 | 3.725 | 335/495 | -1645 | 1642 | 2417 | queued | and a little preparation will make it much more enjoyable. |
| 5 | 11 | sentence | 10901 | 3305 | 2408 | 1725 | 16811 | 16811 | 3.6 | 3.575 | 300/510 | -554 | 552 | 1347 | queued | Here are the most important things to know before you begin. |
| 6 | 8 | sentence | 13349 | 4990 | 2044 | 1439 | 20625 | 20625 | 2.79 | 2.75 | 320/455 | -214 | 211 | 1041 | queued | First, get a good pair of running shoes. |
| 7 | 5 | none | 22041 | 1 | 1569 | 917 | 23788 | 23788 | 1.87 | 1.825 | 335/455 | -373 | 370 | 1160 | text late | Your shoes are the only |
| 8 | 4 | clause | 22041 | 2487 | 1423 | 965 | 26135 | 26135 | 1.99 | 1.95 | 310/430 | -477 | 479 | 1244 | queued | real equipment you need, |
| 9 | 5 | none | 22041 | 4875 | 1319 | 854 | 28416 | 28416 | 2 | 1.975 | 290/420 | -291 | 288 | 1008 | queued | so it is worth visiting |
| 10 | 3 | clause | 22041 | 7048 | 1208 | 803 | 30474 | 30474 | 1.72 | 1.7 | 375/490 | -58 | 56 | 851 | queued | a running store, |
| 11 | 5 | none | 22042 | 9059 | 1340 | 922 | 32617 | 32617 | 1.94 | 1.9 | 320/400 | -423 | 420 | 1230 | queued | where the staff can watch |
| 12 | 4 | none | 22042 | 11320 | 1339 | 933 | 34836 | 34836 | 1.96 | 1.925 | 360/440 | -279 | 276 | 1036 | queued | you run and suggest |
| 13 | 4 | none | 22042 | 13593 | 1155 | 760 | 36962 | 36962 | 1.72 | 1.7 | 355/430 | -166 | 164 | 959 | queued | a pair that suits |
| 14 | 5 | sentence | 22513 | 15035 | 1171 | 997 | 38948 | 38948 | 2 | 1.975 | 305/440 | -266 | 263 | 998 | queued | your feet and your stride. |
| 15 | 3 | sentence | 23636 | 16080 | 1231 | 942 | 41130 | 41130 | 1.99 | 1.95 | 290/455 | -182 | 178 | 908 | queued | Second, start slowly. |
| 16 | 18 | sentence | 28525 | 13364 | 3754 | 2729 | 45859 | 45859 | 5.59 | 5.55 | 320/485 | -2739 | 2736 | 3511 | queued | Many beginners try to do too much in the first few weeks, an… |
| 17 | 26 | sentence | 36767 | 11606 | 6541 | 3977 | 55137 | 55137 | 8.84 | 8.8 | 305/450 | -3688 | 3686 | 4476 | queued | A good plan is to mix running and walking, for example one m… |
| 18 | 12 | sentence | 40105 | 18787 | 2560 | 1937 | 61645 | 63980 | 3.99 | 3.95 | 320/445 | 2332 | 0 | 770 | - | Over several weeks, you can run for longer and walk for less… |
| 19 | 6 | sentence | 41670 | 21720 | 1607 | 1118 | 65171 | 67973 | 2.36 | 2.325 | 290/460 | 2799 | 0 | 735 | - | Third, warm up and cool down. |
| 20 | 23 | sentence | 48348 | 17768 | 6001 | 3629 | 72335 | 72335 | 7.96 | 7.925 | 315/520 | -2002 | 1999 | 2774 | queued | Walk briskly for five minutes before you run, and walk again… |
| 21 | 6 | clause | 49684 | 26061 | 1288 | 989 | 77211 | 80298 | 1.92 | 1.875 | 300/395 | 3084 | 0 | 820 | - | Here are a few more tips: |
| 22 | 11 | sentence | 52800 | 25222 | 1394 | 1440 | 79629 | 82215 | 3.6 | 3.575 | 315/485 | 2589 | 0 | 710 | - | Run at a pace where you can still hold a conversation. |
| 23 | 11 | sentence | 55916 | 24941 | 1740 | 1633 | 82761 | 85818 | 4.36 | 4.325 | 330/455 | 3054 | 0 | 815 | - | Drink water before and after your run, especially on hot day… |
| 24 | 14 | sentence | 59923 | 24308 | 1898 | 1908 | 86342 | 90181 | 4.94 | 4.9 | 325/515 | 3836 | 0 | 780 | - | Rest at least one day between runs at first, so your body ca… |
| 25 | 9 | sentence | 62816 | 25221 | 1341 | 1159 | 89561 | 95123 | 3.24 | 3.2 | 310/430 | 5560 | 0 | 825 | - | Listen to your body, and stop if something hurts. |
| 26 | 5 | sentence | 64597 | 25941 | 1154 | 918 | 91866 | 98366 | 2.52 | 2.5 | 320/440 | 6497 | 0 | 750 | - | Finally, be patient with yourself. |
| 27 | 9 | sentence | 67933 | 24676 | 1611 | 1767 | 94431 | 100889 | 4.27 | 4.225 | 300/490 | 6455 | 0 | 740 | - | Progress in running comes gradually, and everyone starts som… |
| 28 | 27 | sentence | 75281 | 20708 | 3929 | 3264 | 100130 | 105157 | 7.96 | 7.925 | 315/505 | 5029 | 0 | 805 | - | If you keep going for a couple of months, you will probably … |
| 29 | 7 | sentence | 76839 | 26343 | 1278 | 1185 | 104649 | 113119 | 2.74 | 2.7 | 330/455 | 8468 | 0 | 835 | - | Good luck, and enjoy your first runs! |
