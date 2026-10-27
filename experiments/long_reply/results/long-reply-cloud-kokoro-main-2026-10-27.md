# Where the pauses come from in a long reply (cloud-kokoro-main)

Times in milliseconds from the prompt being sent, rates in words a minute. A gap is playback waiting for the clip; the pause heard is the silence at the end of the clip before, the gap and the silence at the start of this one.

| Reply | Words | First word heard | Heard for (s) | Rate heard | Rate in clips | Speech rate | Own rate | LLM writes | Make/play | Gaps > 300 ms | Gap total (s) | Gap causes | Pauses heard > 300 ms | Of them mid-sentence | Cut together | Silence at joins (s) | Clip ends | Start/end silence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 152 | 16464 | 65.3 | 140 | 145 | 189 | 143 | 203 | 0.88 | 1 | 2.2 | queued 1 | 17 | 10 | 7 | 13.2 | none 6, sentence 8, clause 4 | 320/470 |
| 2 | 220 | 4771 | 76 | 174 | 179 | 221 | 170 | 216 | 0.91 | 3 | 2.2 | text late 2, queued 1 | 16 | 5 | 2 | 12.6 | none 4, sentence 12, clause 1 | 315/460 |
| 3 | 261 | 4454 | 97.6 | 160 | 166 | 215 | 166 | 208 | 0.9 | 4 | 3.2 | text late 1, queued 3 | 25 | 8 | 4 | 19.7 | none 4, clause 4, sentence 18 | 318/458 |

## Reply 1: Tell me about the history of the bicycle.

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | none | 14706 | 0 | 1576 | 901 | 16464 | 16464 | 2.52 | 2.5 | 320/460 | - | - | - | - | The bicycle has a surprisingly |
| 2 | 4 | sentence | 16040 | 1143 | 1443 | 805 | 18744 | 18987 | 2.36 | 2.325 | 335/490 | 240 | 0 | 795 | - | long and interesting history. |
| 3 | 3 | clause | 19600 | 0 | 990 | 575 | 20711 | 21350 | 1.6 | 1.575 | 350/470 | 636 | 0 | 840 | - | The first one, |
| 4 | 4 | clause | 19600 | 1566 | 1192 | 712 | 22480 | 22953 | 1.88 | 1.85 | 305/435 | 470 | 0 | 775 | - | called the running machine, |
| 5 | 5 | none | 19600 | 3470 | 1376 | 745 | 24571 | 24835 | 2.12 | 2.075 | 320/400 | 262 | 0 | 755 | - | was built by Karl Drais |
| 6 | 4 | sentence | 20489 | 4701 | 1620 | 942 | 26938 | 26953 | 2.79 | 2.75 | 325/480 | 17 | 0 | 725 | - | in Germany in 1817. |
| 7 | 19 | sentence | 26274 | 1479 | 4031 | 2408 | 31987 | 31987 | 6.52 | 6.475 | 315/470 | -2244 | 2241 | 3036 | queued | It had two wheels and a wooden frame, but no pedals, so ride… |
| 8 | 3 | clause | 34291 | 1 | 1269 | 756 | 35741 | 38504 | 2.07 | 2.025 | 330/430 | 2766 | 0 | 800 | - | In the 1860s, |
| 9 | 4 | none | 34291 | 2026 | 1444 | 810 | 37892 | 40572 | 2.32 | 2.275 | 320/420 | 2682 | 0 | 750 | - | French makers added pedals |
| 10 | 4 | clause | 34291 | 4281 | 1148 | 687 | 39896 | 42890 | 1.79 | 1.75 | 350/480 | 2996 | 0 | 770 | - | to the front wheel, |
| 11 | 5 | none | 34291 | 6117 | 1279 | 713 | 41812 | 44682 | 2.12 | 2.075 | 305/430 | 2868 | 0 | 785 | - | and the result was nicknamed |
| 12 | 5 | none | 34291 | 8109 | 1218 | 710 | 43745 | 46800 | 2.12 | 2.075 | 320/355 | 3057 | 0 | 750 | - | the boneshaker, because its iron |
| 13 | 5 | none | 34291 | 10037 | 1314 | 800 | 45769 | 48918 | 2.32 | 2.275 | 305/390 | 3151 | 0 | 660 | - | tyres made every ride rough |
| 14 | 2 | sentence | 34958 | 11485 | 979 | 552 | 47543 | 51235 | 1.6 | 1.575 | 400/520 | 3695 | 0 | 790 | - | and noisy. |
| 15 | 24 | sentence | 41633 | 6341 | 4786 | 3063 | 52975 | 52975 | 8.34 | 8.3 | 290/470 | -140 | 137 | 947 | queued | Soon after came the penny farthing, with a huge front wheel … |
| 16 | 14 | sentence | 45640 | 10185 | 3135 | 2137 | 59139 | 61318 | 5.99 | 5.95 | 325/510 | 2176 | 0 | 795 | - | The real change came in 1885, when John Kemp Starley built t… |
| 17 | 24 | sentence | 51867 | 9229 | 2434 | 2104 | 63737 | 67311 | 7.14 | 7.1 | 315/495 | 3571 | 0 | 825 | - | It had two wheels of the same size and a chain that drove th… |
| 18 | 18 | sentence | 57653 | 7983 | 2414 | 2100 | 68239 | 74453 | 7.32 | 7.275 | 305/485 | 6212 | 0 | 800 | - | With air-filled tyres added a few years later, cycling becam… |

## Reply 2: How do bees make honey?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | none | 3332 | 0 | 1315 | 706 | 4771 | 4771 | 1.92 | 1.875 | 365/455 | - | - | - | - | Bees make honey through |
| 2 | 5 | none | 5555 | 0 | 1383 | 791 | 7071 | 7071 | 2.28 | 2.25 | 305/420 | -380 | 382 | 1142 | text late | a careful process that turns |
| 3 | 13 | sentence | 8003 | 0 | 2610 | 1702 | 10817 | 10817 | 4.67 | 4.625 | 315/490 | -1466 | 1463 | 2198 | text late | flower nectar into a thick, sweet food they can store for th… |
| 4 | 6 | sentence | 9782 | 2533 | 1416 | 754 | 13860 | 15485 | 2.27 | 2.225 | 305/425 | 1627 | 0 | 795 | - | It starts with the forager bees. |
| 5 | 4 | none | 14677 | 0 | 1166 | 652 | 15967 | 17752 | 1.87 | 1.825 | 350/440 | 1788 | 0 | 775 | - | They fly from flower |
| 6 | 5 | none | 14677 | 1819 | 1870 | 1081 | 18527 | 19620 | 2.96 | 2.925 | 310/415 | 1095 | 0 | 750 | - | to flower, sometimes visiting hundreds |
| 7 | 4 | clause | 14677 | 4770 | 1208 | 602 | 20827 | 22583 | 1.79 | 1.75 | 345/445 | 1753 | 0 | 760 | - | in a single trip, |
| 8 | 9 | sentence | 16456 | 4801 | 1662 | 955 | 23052 | 24375 | 2.79 | 2.75 | 315/460 | 1321 | 0 | 760 | - | and suck up the nectar with their long tongues. |
| 9 | 19 | sentence | 21797 | 2077 | 3441 | 2093 | 27475 | 27475 | 6 | 5.975 | 315/520 | -310 | 307 | 1082 | queued | The nectar is kept in a special honey stomach, separate from… |
| 10 | 14 | sentence | 25802 | 3608 | 2581 | 1485 | 32181 | 33478 | 4.4 | 4.375 | 325/495 | 1294 | 0 | 845 | - | While it is there, enzymes begin to break down the sugars in… |
| 11 | 18 | sentence | 30919 | 2558 | 2973 | 1862 | 36635 | 37881 | 5.64 | 5.6 | 315/450 | 1243 | 0 | 810 | - | When a forager returns to the hive, she passes the nectar to… |
| 12 | 17 | sentence | 35813 | 2499 | 3118 | 1992 | 41607 | 43523 | 5.4 | 5.375 | 300/490 | 1914 | 0 | 750 | - | The house bee chews it for a while, adding more enzymes, and… |
| 13 | 16 | sentence | 40707 | 2716 | 3307 | 2077 | 46888 | 48926 | 5.84 | 5.8 | 325/535 | 2035 | 0 | 815 | - | This is repeated several times, until the nectar has changed… |
| 14 | 13 | sentence | 44302 | 4505 | 2459 | 1450 | 51404 | 54769 | 4.34 | 4.3 | 320/510 | 3362 | 0 | 855 | - | Next, the bees spread the liquid into the wax cells of the h… |
| 15 | 21 | sentence | 49419 | 3296 | 3653 | 2242 | 56575 | 59112 | 6.28 | 6.25 | 315/465 | 2534 | 0 | 825 | - | At this point it is still very watery, so the bees fan it wi… |
| 16 | 23 | sentence | 55427 | 3184 | 4360 | 2451 | 63130 | 65394 | 6.96 | 6.925 | 315/450 | 2262 | 0 | 780 | - | When the honey is thick enough, with less than about twenty … |
| 17 | 29 | sentence | 62769 | 2654 | 2985 | 2613 | 68619 | 72357 | 8.39 | 8.35 | 310/480 | 3735 | 0 | 760 | - | A single bee makes only about a twelfth of a teaspoon of hon… |

## Reply 3: What should I know before I start running?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | none | 3117 | 0 | 1215 | 612 | 4454 | 4454 | 1.76 | 1.725 | 340/490 | - | - | - | - | Starting to run |
| 2 | 4 | none | 5341 | 0 | 1067 | 615 | 6583 | 6583 | 1.79 | 1.75 | 375/465 | -369 | 366 | 1231 | text late | is a great choice |
| 3 | 3 | clause | 5341 | 1683 | 1077 | 512 | 8222 | 8375 | 1.56 | 1.525 | 350/440 | 151 | 0 | 815 | - | for your health, |
| 4 | 10 | sentence | 7566 | 1047 | 2101 | 1266 | 10852 | 10852 | 3.76 | 3.725 | 335/495 | -917 | 914 | 1689 | queued | and a little preparation will make it much more enjoyable. |
| 5 | 11 | sentence | 10903 | 1077 | 2231 | 1262 | 14355 | 14615 | 3.6 | 3.575 | 300/510 | 257 | 0 | 795 | - | Here are the most important things to know before you begin. |
| 6 | 8 | sentence | 13350 | 2124 | 1855 | 1025 | 17451 | 18217 | 2.79 | 2.75 | 320/455 | 764 | 0 | 830 | - | First, get a good pair of running shoes. |
| 7 | 5 | none | 18468 | 1 | 1371 | 701 | 19968 | 21010 | 1.87 | 1.825 | 335/455 | 1039 | 0 | 790 | - | Your shoes are the only |
| 8 | 4 | clause | 18468 | 2072 | 1332 | 702 | 22037 | 22878 | 1.99 | 1.95 | 310/430 | 843 | 0 | 765 | - | real equipment you need, |
| 9 | 5 | none | 18468 | 4107 | 1335 | 745 | 24039 | 24870 | 2 | 1.975 | 290/420 | 829 | 0 | 720 | - | so it is worth visiting |
| 10 | 3 | clause | 18468 | 6187 | 1227 | 659 | 26012 | 26873 | 1.72 | 1.7 | 375/490 | 858 | 0 | 795 | - | a running store, |
| 11 | 18 | sentence | 22473 | 4069 | 2911 | 1848 | 29627 | 29627 | 5.2 | 5.175 | 315/520 | -1034 | 1031 | 1836 | queued | where the staff can watch you run and suggest a pair that su… |
| 12 | 3 | sentence | 23585 | 7716 | 1182 | 730 | 32610 | 34830 | 1.99 | 1.95 | 290/455 | 2217 | 0 | 810 | - | Second, start slowly. |
| 13 | 18 | sentence | 28484 | 4730 | 2998 | 1949 | 36444 | 36823 | 5.59 | 5.55 | 320/485 | 376 | 0 | 775 | - | Many beginners try to do too much in the first few weeks, an… |
| 14 | 26 | sentence | 36715 | 1446 | 4960 | 3078 | 43341 | 43341 | 8.84 | 8.8 | 305/450 | -928 | 926 | 1716 | queued | A good plan is to mix running and walking, for example one m… |
| 15 | 12 | sentence | 40050 | 6148 | 2254 | 1348 | 48643 | 52184 | 3.99 | 3.95 | 320/445 | 3538 | 0 | 770 | - | Over several weeks, you can run for longer and walk for less… |
| 16 | 6 | sentence | 41608 | 8194 | 1449 | 836 | 51380 | 56176 | 2.36 | 2.325 | 290/460 | 4794 | 0 | 735 | - | Third, warm up and cool down. |
| 17 | 23 | sentence | 48285 | 3802 | 4435 | 2740 | 56679 | 58539 | 7.96 | 7.925 | 315/520 | 1857 | 0 | 775 | - | Walk briskly for five minutes before you run, and walk again… |
| 18 | 6 | clause | 49619 | 9643 | 1210 | 720 | 60597 | 66502 | 1.92 | 1.875 | 300/395 | 5902 | 0 | 820 | - | Here are a few more tips: |
| 19 | 11 | sentence | 52735 | 8457 | 1976 | 1235 | 63353 | 68419 | 3.6 | 3.575 | 315/485 | 5069 | 0 | 710 | - | Run at a pace where you can still hold a conversation. |
| 20 | 11 | sentence | 55849 | 8554 | 2363 | 1569 | 66925 | 72022 | 4.36 | 4.325 | 330/455 | 5094 | 0 | 815 | - | Drink water before and after your run, especially on hot day… |
| 21 | 14 | sentence | 59855 | 8481 | 2852 | 1839 | 71349 | 76385 | 4.94 | 4.9 | 325/515 | 5033 | 0 | 780 | - | Rest at least one day between runs at first, so your body ca… |
| 22 | 9 | sentence | 62748 | 10280 | 2250 | 1166 | 75413 | 81328 | 3.24 | 3.2 | 310/430 | 5912 | 0 | 825 | - | Listen to your body, and stop if something hurts. |
| 23 | 5 | sentence | 64527 | 11918 | 1564 | 922 | 78138 | 84570 | 2.52 | 2.5 | 320/440 | 6430 | 0 | 750 | - | Finally, be patient with yourself. |
| 24 | 9 | sentence | 67864 | 11068 | 1473 | 1299 | 80563 | 87093 | 4.27 | 4.225 | 300/490 | 6527 | 0 | 740 | - | Progress in running comes gradually, and everyone starts som… |
| 25 | 27 | sentence | 75210 | 6494 | 2906 | 2497 | 84815 | 91361 | 7.96 | 7.925 | 315/505 | 6548 | 0 | 805 | - | If you keep going for a couple of months, you will probably … |
| 26 | 7 | sentence | 76769 | 10339 | 1054 | 796 | 88290 | 99323 | 2.74 | 2.7 | 330/455 | 11031 | 0 | 835 | - | Good luck, and enjoy your first runs! |
