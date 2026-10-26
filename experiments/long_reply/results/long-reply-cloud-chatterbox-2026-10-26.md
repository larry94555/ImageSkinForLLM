# Where the pauses come from in a long reply (cloud-chatterbox)

Times in milliseconds from the prompt being sent, rates in words a minute. A gap is playback waiting for the clip; the pause heard is the silence at the end of the clip before, the gap and the silence at the start of this one.

| Reply | Words | First word heard | Heard for (s) | Rate heard | Rate in clips | Speech rate | Own rate | LLM writes | Make/play | Gaps > 300 ms | Gap total (s) | Gap causes | Pauses heard > 300 ms | Of them mid-sentence | Cut together | Silence at joins (s) | Clip ends | Start/end silence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 152 | 17056 | 184.5 | 49 | 183 | 198 | 200 | 203 | 3.9 | 8 | 134.7 | queued 8 | 8 | 1 | 0 | 3 | none 1, sentence 8 | 105/230 |
| 2 | 220 | 15337 | 258.4 | 51 | 203 | 220 | 224 | 216 | 4.08 | 12 | 193.4 | queued 12 | 12 | 1 | 0 | 4.1 | none 1, sentence 12 | 115/195 |
| 3 | 261 | 12657 | 327.4 | 48 | 195 | 219 | 223 | 208 | 4.18 | 19 | 247.1 | queued 19 | 19 | 2 | 0 | 7.6 | none 1, sentence 18, clause 1 | 125/250 |

## Reply 1: Tell me about the history of the bicycle.

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | none | 4162 | 0 | 12709 | 1182 | 17056 | 17056 | 2.48 | 2.44 | 35/360 | - | - | - | - | The bicycle has a surprisingly |
| 2 | 4 | sentence | 5496 | 12557 | 11502 | 1013 | 29741 | 29741 | 1.92 | 1.88 | 85/325 | -10205 | 10202 | 10647 | queued | long and interesting history. |
| 3 | 16 | sentence | 9948 | 20621 | 28377 | 2901 | 59154 | 59154 | 6.2 | 6.16 | 105/195 | -27493 | 27490 | 27920 | queued | The first one, called the running machine, was built by Karl… |
| 4 | 19 | sentence | 15733 | 46113 | 17053 | 2380 | 79175 | 79175 | 5.16 | 5.12 | 135/225 | -13821 | 13818 | 14148 | queued | It had two wheels and a wooden frame, but no pedals, so ride… |
| 5 | 28 | sentence | 24412 | 56868 | 25708 | 3621 | 107256 | 107256 | 8.6 | 8.56 | 180/295 | -22921 | 22918 | 23323 | queued | In the 1860s, French makers added pedals to the front wheel,… |
| 6 | 24 | sentence | 31088 | 79522 | 23660 | 3448 | 134483 | 134483 | 7.88 | 7.84 | 60/345 | -18627 | 18625 | 18980 | queued | Soon after came the penny farthing, with a huge front wheel … |
| 7 | 14 | sentence | 35094 | 102625 | 16691 | 2140 | 154675 | 154675 | 5.32 | 5.28 | 80/230 | -12312 | 12309 | 12734 | queued | The real change came in 1885, when John Kemp Starley built t… |
| 8 | 24 | sentence | 41325 | 115226 | 18280 | 2330 | 175038 | 175038 | 6.08 | 6.04 | 115/160 | -15043 | 15040 | 15385 | queued | It had two wheels of the same size and a chain that drove th… |
| 9 | 18 | sentence | 47110 | 130052 | 17999 | 3028 | 195410 | 195410 | 6.12 | 6.08 | 125/205 | -14292 | 14289 | 14574 | queued | With air-filled tyres added a few years later, cycling becam… |

## Reply 2: How do bees make honey?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | none | 3364 | 0 | 11792 | 1092 | 15337 | 15337 | 2.16 | 2.12 | 80/310 | - | - | - | - | Bees make honey through |
| 2 | 18 | sentence | 8041 | 8207 | 26207 | 2652 | 42692 | 42692 | 6.04 | 6 | 140/195 | -25195 | 25192 | 25642 | queued | a careful process that turns flower nectar into a thick, swe… |
| 3 | 6 | sentence | 9821 | 35287 | 12239 | 1053 | 57530 | 57530 | 2.4 | 2.36 | 115/320 | -8798 | 8795 | 9105 | queued | It starts with the forager bees. |
| 4 | 22 | sentence | 16498 | 41901 | 30663 | 3039 | 89285 | 89285 | 6.68 | 6.64 | 190/190 | -29355 | 29352 | 29862 | queued | They fly from flower to flower, sometimes visiting hundreds … |
| 5 | 19 | sentence | 21840 | 70263 | 16135 | 2349 | 108442 | 108442 | 5.16 | 5.12 | 60/180 | -12477 | 12475 | 12725 | queued | The nectar is kept in a special honey stomach, separate from… |
| 6 | 14 | sentence | 25845 | 84743 | 12042 | 1447 | 122815 | 122815 | 3.76 | 3.72 | 95/195 | -9213 | 9210 | 9485 | queued | While it is there, enzymes begin to break down the sugars in… |
| 7 | 18 | sentence | 30963 | 93114 | 16438 | 2022 | 140708 | 140708 | 5 | 4.96 | 90/175 | -14133 | 14130 | 14415 | queued | When a forager returns to the hive, she passes the nectar to… |
| 8 | 17 | sentence | 35858 | 106680 | 16582 | 2381 | 159359 | 159359 | 5.12 | 5.08 | 140/165 | -13651 | 13648 | 13963 | queued | The house bee chews it for a while, adding more enzymes, and… |
| 9 | 16 | sentence | 40753 | 120749 | 15392 | 1927 | 177085 | 177085 | 4.52 | 4.48 | 180/170 | -12606 | 12603 | 12948 | queued | This is repeated several times, until the nectar has changed… |
| 10 | 13 | sentence | 44313 | 134508 | 14248 | 1777 | 193271 | 193271 | 4.04 | 4 | 150/245 | -11666 | 11664 | 11984 | queued | Next, the bees spread the liquid into the wax cells of the h… |
| 11 | 21 | sentence | 49431 | 145416 | 21717 | 2576 | 216777 | 216777 | 6.08 | 6.04 | 65/220 | -19466 | 19464 | 19774 | queued | At this point it is still very watery, so the bees fan it wi… |
| 12 | 23 | sentence | 55442 | 163700 | 18361 | 2297 | 237696 | 237696 | 5.92 | 5.88 | 115/195 | -14839 | 14836 | 15171 | queued | When the honey is thick enough, with less than about twenty … |
| 13 | 29 | sentence | 62790 | 177013 | 25605 | 3332 | 265623 | 265623 | 8.12 | 8.08 | 155/300 | -22007 | 22004 | 22354 | queued | A single bee makes only about a twelfth of a teaspoon of hon… |

## Reply 3: What should I know before I start running?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | none | 3118 | 0 | 9356 | 726 | 12657 | 12657 | 1.36 | 1.32 | 65/355 | - | - | - | - | Starting to run |
| 2 | 17 | sentence | 7568 | 5631 | 22702 | 2148 | 36101 | 36101 | 4.56 | 4.52 | 180/190 | -22084 | 22081 | 22616 | queued | is a great choice for your health, and a little preparation … |
| 3 | 11 | sentence | 10906 | 27145 | 13935 | 1330 | 52229 | 52229 | 2.8 | 2.76 | 200/200 | -11568 | 11565 | 11955 | queued | Here are the most important things to know before you begin. |
| 4 | 8 | sentence | 13354 | 39963 | 12390 | 1210 | 65891 | 65891 | 2.6 | 2.56 | 180/265 | -10862 | 10859 | 11239 | queued | First, get a good pair of running shoes. |
| 5 | 35 | sentence | 22479 | 44438 | 44424 | 4185 | 111578 | 111578 | 9.72 | 9.68 | 185/205 | -43087 | 43084 | 43534 | queued | Your shoes are the only real equipment you need, so it is wo… |
| 6 | 3 | sentence | 23591 | 91935 | 8077 | 902 | 123767 | 123767 | 2.2 | 2.16 | 70/290 | -2469 | 2467 | 2742 | queued | Second, start slowly. |
| 7 | 18 | sentence | 28488 | 96018 | 16628 | 2380 | 141350 | 141350 | 5.24 | 5.2 | 110/240 | -15383 | 15380 | 15780 | queued | Many beginners try to do too much in the first few weeks, an… |
| 8 | 26 | sentence | 36720 | 106794 | 26249 | 3625 | 169991 | 169991 | 8.68 | 8.64 | 125/390 | -23401 | 23398 | 23763 | queued | A good plan is to mix running and walking, for example one m… |
| 9 | 12 | sentence | 40062 | 133327 | 12691 | 1764 | 186276 | 186276 | 4.04 | 4 | 105/250 | -7605 | 7602 | 8097 | queued | Over several weeks, you can run for longer and walk for less… |
| 10 | 6 | sentence | 41616 | 146228 | 7470 | 977 | 195493 | 195493 | 2.2 | 2.16 | 115/380 | -5177 | 5175 | 5540 | queued | Third, warm up and cool down. |
| 11 | 23 | sentence | 48292 | 148002 | 21536 | 2887 | 218043 | 218043 | 7.08 | 7.04 | 95/260 | -20350 | 20347 | 20822 | queued | Walk briskly for five minutes before you run, and walk again… |
| 12 | 6 | clause | 49627 | 171090 | 7284 | 685 | 228177 | 228177 | 1.84 | 1.8 | 125/330 | -3054 | 3052 | 3437 | queued | Here are a few more tips: |
| 13 | 11 | sentence | 52743 | 175943 | 9889 | 1229 | 238790 | 238790 | 2.8 | 2.76 | 180/195 | -8773 | 8770 | 9280 | queued | Run at a pace where you can still hold a conversation. |
| 14 | 11 | sentence | 55860 | 183947 | 11959 | 1426 | 251954 | 251954 | 3.36 | 3.32 | 150/205 | -10364 | 10361 | 10706 | queued | Drink water before and after your run, especially on hot day… |
| 15 | 14 | sentence | 59865 | 193327 | 12657 | 1619 | 266064 | 266064 | 3.64 | 3.6 | 130/245 | -10750 | 10748 | 11083 | queued | Rest at least one day between runs at first, so your body ca… |
| 16 | 9 | sentence | 62758 | 204710 | 10443 | 1313 | 278128 | 278128 | 2.8 | 2.76 | 95/200 | -8424 | 8420 | 8760 | queued | Listen to your body, and stop if something hurts. |
| 17 | 5 | sentence | 64538 | 214686 | 9036 | 1041 | 288444 | 288444 | 2.52 | 2.48 | 100/250 | -7516 | 7514 | 7814 | queued | Finally, be patient with yourself. |
| 18 | 9 | sentence | 67874 | 221427 | 12398 | 1512 | 301864 | 301864 | 3.44 | 3.4 | 130/200 | -10900 | 10897 | 11277 | queued | Progress in running comes gradually, and everyone starts som… |
| 19 | 27 | sentence | 75221 | 227991 | 22273 | 2659 | 325693 | 325693 | 6.88 | 6.84 | 120/375 | -20389 | 20386 | 20706 | queued | If you keep going for a couple of months, you will probably … |
| 20 | 7 | sentence | 76778 | 251365 | 9224 | 1070 | 337560 | 337560 | 2.52 | 2.48 | 160/340 | -4987 | 4985 | 5520 | queued | Good luck, and enjoy your first runs! |
