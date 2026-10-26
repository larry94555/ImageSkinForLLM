# Where the pauses come from in a long reply (cloud-kokoro)

Times in milliseconds from the prompt being sent, rates in words a minute. A gap is playback waiting for the clip; the pause heard is the silence at the end of the clip before, the gap and the silence at the start of this one.

| Reply | Words | First word heard | Heard for (s) | Rate heard | Rate in clips | Speech rate | Own rate | LLM writes | Make/play | Gaps > 300 ms | Gap total (s) | Gap causes | Pauses heard > 300 ms | Of them mid-sentence | Cut together | Silence at joins (s) | Clip ends | Start/end silence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 152 | 4826 | 66.6 | 137 | 137 | 195 | 181 | 203 | 0.7 | 0 | 0 | - | 23 | 16 | 10 | 18.1 | none 9, sentence 8, clause 7 | 325/460 |
| 2 | 220 | 4597 | 85.8 | 154 | 154 | 227 | 217 | 216 | 0.75 | 0 | 0 | - | 33 | 22 | 13 | 25.4 | none 15, clause 7, sentence 12 | 320/445 |
| 3 | 261 | 4171 | 104.1 | 150 | 151 | 219 | 210 | 208 | 0.74 | 0 | 0 | - | 39 | 22 | 12 | 30 | none 15, clause 7, sentence 18 | 320/448 |

## Reply 1: Tell me about the history of the bicycle.

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | none | 3535 | 0 | 1171 | 730 | 4826 | 4826 | 2.52 | 2.5 | 320/455 | - | - | - | - | The bicycle has a surprisingly |
| 2 | 4 | sentence | 4868 | 568 | 1014 | 616 | 6570 | 7349 | 2.36 | 2.325 | 335/490 | 776 | 0 | 790 | - | long and interesting history. |
| 3 | 3 | clause | 7093 | 0 | 721 | 423 | 7932 | 9711 | 1.6 | 1.575 | 350/465 | 1777 | 0 | 840 | - | The first one, |
| 4 | 4 | clause | 7093 | 1145 | 769 | 531 | 9123 | 11314 | 1.88 | 1.85 | 305/435 | 2188 | 0 | 770 | - | called the running machine, |
| 5 | 9 | sentence | 9318 | 220 | 1807 | 1198 | 11546 | 13197 | 4.2 | 4.175 | 315/505 | 1648 | 0 | 750 | - | was built by Karl Drais in Germany in 1817. |
| 6 | 4 | none | 12654 | 0 | 876 | 558 | 13653 | 17400 | 1.84 | 1.8 | 360/430 | 3744 | 0 | 865 | - | It had two wheels |
| 7 | 4 | clause | 12655 | 1434 | 833 | 542 | 15038 | 19242 | 1.79 | 1.75 | 345/465 | 4202 | 0 | 775 | - | and a wooden frame, |
| 8 | 3 | clause | 12655 | 2809 | 809 | 453 | 16389 | 21035 | 1.72 | 1.675 | 355/450 | 4643 | 0 | 820 | - | but no pedals, |
| 9 | 8 | sentence | 15101 | 1624 | 1431 | 800 | 18279 | 22753 | 3 | 2.975 | 295/455 | 4476 | 0 | 745 | - | so riders pushed themselves along with their feet. |
| 10 | 3 | clause | 19105 | 0 | 931 | 574 | 20155 | 25755 | 2.07 | 2.025 | 330/430 | 5598 | 0 | 785 | - | In the 1860s, |
| 11 | 4 | none | 19105 | 1505 | 1130 | 667 | 21861 | 27823 | 2.32 | 2.275 | 315/415 | 5964 | 0 | 745 | - | French makers added pedals |
| 12 | 4 | clause | 19106 | 3303 | 869 | 484 | 23400 | 30141 | 1.79 | 1.75 | 350/470 | 6743 | 0 | 765 | - | to the front wheel, |
| 13 | 17 | sentence | 23778 | 0 | 3360 | 1745 | 27276 | 31933 | 6.48 | 6.45 | 320/515 | 4655 | 0 | 790 | - | and the result was nicknamed the boneshaker, because its iro… |
| 14 | 5 | none | 28897 | 0 | 922 | 596 | 29935 | 38416 | 2.16 | 2.125 | 295/470 | 8478 | 0 | 810 | - | Soon after came the penny |
| 15 | 5 | none | 28897 | 1518 | 922 | 566 | 31454 | 40579 | 2.08 | 2.05 | 295/405 | 9122 | 0 | 765 | - | farthing, with a huge front |
| 16 | 5 | none | 28897 | 3007 | 958 | 574 | 32979 | 42662 | 2.12 | 2.075 | 320/455 | 9680 | 0 | 725 | - | wheel that let riders go |
| 17 | 9 | sentence | 30461 | 2975 | 1574 | 931 | 35138 | 44779 | 3.52 | 3.475 | 325/445 | 9644 | 0 | 780 | - | faster, although falling off it could be quite dangerous. |
| 18 | 14 | sentence | 34462 | 1479 | 2247 | 1606 | 38326 | 48297 | 5.99 | 5.95 | 325/505 | 9973 | 0 | 770 | - | The real change came in 1885, when John Kemp Starley built t… |
| 19 | 4 | none | 39803 | 1 | 755 | 534 | 40677 | 54290 | 1.84 | 1.8 | 360/430 | 13610 | 0 | 865 | - | It had two wheels |
| 20 | 4 | none | 39803 | 1289 | 845 | 524 | 42056 | 56132 | 1.8 | 1.775 | 375/465 | 14074 | 0 | 805 | - | of the same size |
| 21 | 5 | none | 39803 | 2658 | 869 | 547 | 43446 | 57935 | 1.92 | 1.875 | 330/420 | 14486 | 0 | 795 | - | and a chain that drove |
| 22 | 3 | clause | 39803 | 4074 | 746 | 448 | 44740 | 59853 | 1.64 | 1.6 | 370/495 | 15115 | 0 | 790 | - | the back wheel, |
| 23 | 8 | sentence | 40692 | 4379 | 1082 | 726 | 46275 | 61496 | 2.6 | 2.575 | 320/480 | 15218 | 0 | 815 | - | which is still the design we use today. |
| 24 | 18 | sentence | 46476 | 404 | 1991 | 1681 | 49018 | 64098 | 7.32 | 7.275 | 305/485 | 15078 | 0 | 785 | - | With air-filled tyres added a few years later, cycling becam… |

## Reply 2: How do bees make honey?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | none | 3310 | 0 | 1167 | 619 | 4597 | 4597 | 1.92 | 1.875 | 365/455 | - | - | - | - | Bees make honey through |
| 2 | 5 | none | 5313 | 0 | 1169 | 651 | 6607 | 6607 | 2.28 | 2.25 | 300/420 | -90 | 93 | 848 | text late | a careful process that turns |
| 3 | 5 | clause | 7316 | 0 | 1001 | 643 | 8442 | 8890 | 2.2 | 2.175 | 295/445 | 445 | 0 | 715 | - | flower nectar into a thick, |
| 4 | 5 | none | 7316 | 1644 | 924 | 606 | 10004 | 11093 | 2.04 | 2 | 285/445 | 1086 | 0 | 730 | - | sweet food they can store |
| 5 | 3 | sentence | 7983 | 2508 | 743 | 441 | 11351 | 13136 | 1.59 | 1.55 | 330/485 | 1782 | 0 | 775 | - | for the winter. |
| 6 | 6 | sentence | 9764 | 1911 | 1050 | 656 | 12855 | 14728 | 2.27 | 2.225 | 305/420 | 1871 | 0 | 790 | - | It starts with the forager bees. |
| 7 | 4 | none | 13769 | 0 | 827 | 595 | 14771 | 16996 | 1.87 | 1.825 | 350/430 | 2227 | 0 | 770 | - | They fly from flower |
| 8 | 5 | none | 13769 | 1422 | 1311 | 903 | 16725 | 18864 | 2.96 | 2.925 | 310/415 | 2141 | 0 | 740 | - | to flower, sometimes visiting hundreds |
| 9 | 13 | sentence | 16438 | 968 | 1728 | 1045 | 19262 | 21826 | 3.96 | 3.925 | 330/450 | 2562 | 0 | 745 | - | in a single trip, and suck up the nectar with their long ton… |
| 10 | 4 | none | 20442 | 0 | 824 | 495 | 21386 | 25789 | 1.8 | 1.775 | 335/420 | 4400 | 0 | 785 | - | The nectar is kept |
| 11 | 5 | clause | 20442 | 1319 | 976 | 644 | 22862 | 27592 | 2.16 | 2.125 | 325/450 | 4727 | 0 | 745 | - | in a special honey stomach, |
| 12 | 10 | sentence | 21777 | 1605 | 1486 | 936 | 24992 | 29754 | 3.48 | 3.45 | 285/480 | 4760 | 0 | 735 | - | separate from the stomach they use for their own food. |
| 13 | 14 | sentence | 25781 | 23 | 1761 | 1165 | 27697 | 33237 | 4.4 | 4.375 | 320/490 | 5537 | 0 | 800 | - | While it is there, enzymes begin to break down the sugars in… |
| 14 | 4 | none | 29118 | 0 | 922 | 610 | 30160 | 37640 | 1.99 | 1.95 | 315/410 | 7477 | 0 | 805 | - | When a forager returns |
| 15 | 3 | clause | 29119 | 1532 | 754 | 493 | 31531 | 39633 | 1.59 | 1.55 | 375/455 | 8099 | 0 | 785 | - | to the hive, |
| 16 | 11 | sentence | 30898 | 1000 | 1706 | 1050 | 33745 | 41225 | 3.67 | 3.625 | 295/455 | 7478 | 0 | 750 | - | she passes the nectar to a house bee, mouth to mouth. |
| 17 | 5 | none | 34904 | 0 | 908 | 527 | 35930 | 44893 | 1.88 | 1.85 | 345/405 | 8965 | 0 | 800 | - | The house bee chews it |
| 18 | 3 | clause | 34905 | 1436 | 728 | 445 | 37186 | 46776 | 1.47 | 1.425 | 350/485 | 9587 | 0 | 755 | - | for a while, |
| 19 | 3 | clause | 34905 | 2609 | 927 | 577 | 38560 | 48243 | 1.92 | 1.875 | 355/445 | 9686 | 0 | 840 | - | adding more enzymes, |
| 20 | 6 | sentence | 35794 | 3224 | 880 | 632 | 40018 | 50161 | 2.16 | 2.125 | 310/460 | 10145 | 0 | 755 | - | and then passes it on again. |
| 21 | 16 | sentence | 40687 | 0 | 2863 | 1712 | 43692 | 52324 | 5.84 | 5.8 | 320/535 | 8629 | 0 | 780 | - | This is repeated several times, until the nectar has changed… |
| 22 | 13 | sentence | 44247 | 1017 | 2344 | 1291 | 47734 | 58166 | 4.34 | 4.3 | 320/510 | 10430 | 0 | 855 | - | Next, the bees spread the liquid into the wax cells of the h… |
| 23 | 4 | none | 48924 | 0 | 770 | 518 | 49812 | 62509 | 1.59 | 1.55 | 355/405 | 12694 | 0 | 865 | - | At this point it |
| 24 | 4 | clause | 48924 | 1289 | 857 | 597 | 51192 | 64102 | 1.99 | 1.95 | 305/470 | 12907 | 0 | 710 | - | is still very watery, |
| 25 | 5 | none | 48924 | 2743 | 1042 | 520 | 52826 | 66094 | 1.76 | 1.725 | 320/390 | 13266 | 0 | 790 | - | so the bees fan it |
| 26 | 5 | none | 48924 | 4305 | 945 | 600 | 54345 | 67857 | 1.94 | 1.9 | 320/405 | 13509 | 0 | 710 | - | with their wings to help |
| 27 | 3 | sentence | 49368 | 5407 | 930 | 599 | 55822 | 69800 | 1.94 | 1.9 | 335/420 | 13975 | 0 | 740 | - | the water evaporate. |
| 28 | 23 | sentence | 55379 | 925 | 3207 | 2026 | 59706 | 71743 | 6.96 | 6.925 | 315/445 | 12034 | 0 | 735 | - | When the honey is thick enough, with less than about twenty … |
| 29 | 5 | none | 61609 | 1 | 1056 | 572 | 62789 | 78705 | 1.96 | 1.925 | 305/425 | 15914 | 0 | 750 | - | A single bee makes only |
| 30 | 3 | none | 61609 | 1629 | 663 | 418 | 64025 | 80668 | 1.68 | 1.65 | 370/445 | 16640 | 0 | 795 | - | about a twelfth |
| 31 | 5 | none | 61610 | 2710 | 684 | 491 | 65124 | 82351 | 1.96 | 1.925 | 315/455 | 17224 | 0 | 760 | - | of a teaspoon of honey |
| 32 | 4 | clause | 61610 | 3885 | 734 | 458 | 66346 | 84313 | 1.8 | 1.775 | 375/440 | 17965 | 0 | 830 | - | in her whole life, |
| 33 | 5 | none | 61610 | 5077 | 735 | 440 | 67541 | 86116 | 1.76 | 1.725 | 320/470 | 18572 | 0 | 760 | - | so a jar of honey |
| 34 | 7 | sentence | 62720 | 5142 | 813 | 575 | 68795 | 87879 | 2.52 | 2.5 | 325/445 | 19081 | 0 | 795 | - | is the work of thousands of bees. |

## Reply 3: What should I know before I start running?

| Clip | Words | Ends at | Text came | Waited | Voice | Video | First byte | Plays | Seconds | Speech s | Start/end silence | Ready before end | Gap | Pause heard | Cause | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | none | 3093 | 0 | 961 | 522 | 4171 | 4171 | 1.76 | 1.725 | 340/485 | - | - | - | - | Starting to run |
| 2 | 4 | none | 4649 | 0 | 1221 | 503 | 5987 | 5987 | 1.79 | 1.75 | 370/455 | -56 | 54 | 909 | text late | is a great choice |
| 3 | 3 | clause | 4649 | 1724 | 843 | 453 | 7333 | 7780 | 1.56 | 1.525 | 345/440 | 444 | 0 | 800 | - | for your health, |
| 4 | 10 | sentence | 7542 | 128 | 1694 | 1024 | 9490 | 9490 | 3.76 | 3.725 | 335/480 | -150 | 147 | 922 | queued | and a little preparation will make it much more enjoyable. |
| 5 | 5 | none | 10446 | 0 | 922 | 564 | 11486 | 13252 | 2 | 1.975 | 280/390 | 1764 | 0 | 760 | - | Here are the most important |
| 6 | 6 | sentence | 10891 | 1042 | 1036 | 674 | 13088 | 15255 | 2.44 | 2.4 | 335/470 | 2164 | 0 | 725 | - | things to know before you begin. |
| 7 | 8 | sentence | 13337 | 305 | 1124 | 784 | 14890 | 17698 | 2.79 | 2.75 | 320/450 | 2805 | 0 | 790 | - | First, get a good pair of running shoes. |
| 8 | 5 | none | 15563 | 0 | 1011 | 541 | 16692 | 20491 | 1.87 | 1.825 | 335/450 | 3796 | 0 | 785 | - | Your shoes are the only |
| 9 | 4 | clause | 15563 | 1552 | 937 | 563 | 18170 | 22358 | 1.99 | 1.95 | 310/430 | 4191 | 0 | 760 | - | real equipment you need, |
| 10 | 5 | none | 18677 | 0 | 941 | 597 | 19737 | 24351 | 2 | 1.975 | 290/420 | 4611 | 0 | 720 | - | so it is worth visiting |
| 11 | 3 | clause | 18677 | 1538 | 837 | 472 | 21170 | 26354 | 1.72 | 1.7 | 375/490 | 5181 | 0 | 795 | - | a running store, |
| 12 | 5 | none | 21569 | 0 | 907 | 550 | 22593 | 28076 | 1.94 | 1.9 | 320/400 | 5481 | 0 | 810 | - | where the staff can watch |
| 13 | 4 | none | 21569 | 1457 | 931 | 575 | 24076 | 30019 | 1.96 | 1.925 | 360/440 | 5940 | 0 | 760 | - | you run and suggest |
| 14 | 4 | none | 21570 | 2964 | 709 | 473 | 25359 | 31982 | 1.72 | 1.7 | 355/430 | 6620 | 0 | 795 | - | a pair that suits |
| 15 | 5 | sentence | 22459 | 3257 | 879 | 577 | 26711 | 33704 | 2 | 1.975 | 305/430 | 6991 | 0 | 735 | - | your feet and your stride. |
| 16 | 3 | sentence | 23570 | 3601 | 876 | 548 | 28169 | 35707 | 1.99 | 1.95 | 290/450 | 7535 | 0 | 720 | - | Second, start slowly. |
| 17 | 18 | sentence | 28465 | 131 | 2549 | 1581 | 31280 | 37700 | 5.59 | 5.55 | 320/485 | 6417 | 0 | 770 | - | Many beginners try to do too much in the first few weeks, an… |
| 18 | 3 | none | 32914 | 0 | 861 | 454 | 33890 | 43293 | 1.68 | 1.65 | 375/490 | 9400 | 0 | 860 | - | A good plan |
| 19 | 4 | none | 32914 | 1315 | 809 | 507 | 35156 | 44975 | 1.72 | 1.675 | 345/430 | 9817 | 0 | 835 | - | is to mix running |
| 20 | 5 | none | 32914 | 2631 | 1048 | 649 | 36711 | 46693 | 2.39 | 2.35 | 305/435 | 9984 | 0 | 735 | - | and walking, for example one |
| 21 | 14 | sentence | 36694 | 548 | 2475 | 1472 | 39851 | 49086 | 5.44 | 5.4 | 325/450 | 9232 | 0 | 760 | - | minute of running followed by two minutes of walking, repeat… |
| 22 | 12 | sentence | 40032 | 1157 | 1774 | 1035 | 43091 | 54528 | 3.99 | 3.95 | 320/445 | 11435 | 0 | 770 | - | Over several weeks, you can run for longer and walk for less… |
| 23 | 6 | sentence | 41589 | 2410 | 1371 | 630 | 45489 | 58521 | 2.36 | 2.325 | 290/460 | 13029 | 0 | 735 | - | Third, warm up and cool down. |
| 24 | 5 | none | 46483 | 1 | 1015 | 609 | 47668 | 60884 | 2.27 | 2.225 | 300/390 | 13213 | 0 | 760 | - | Walk briskly for five minutes |
| 25 | 3 | clause | 46483 | 1625 | 704 | 489 | 48928 | 63151 | 1.68 | 1.65 | 375/475 | 14226 | 0 | 765 | - | before you run, |
| 26 | 3 | none | 46483 | 2817 | 777 | 477 | 50192 | 64834 | 1.48 | 1.45 | 370/380 | 14639 | 0 | 845 | - | and walk again |
| 27 | 5 | clause | 46483 | 4071 | 1011 | 654 | 51692 | 66317 | 2.12 | 2.075 | 300/415 | 14622 | 0 | 680 | - | for a few minutes afterwards, |
| 28 | 7 | sentence | 48265 | 3955 | 1238 | 717 | 53577 | 68435 | 2.52 | 2.5 | 290/475 | 14860 | 0 | 705 | - | so your heart rate comes down gently. |
| 29 | 6 | clause | 49599 | 4575 | 898 | 528 | 55190 | 70957 | 1.92 | 1.875 | 300/395 | 15765 | 0 | 775 | - | Here are a few more tips: |
| 30 | 11 | sentence | 52714 | 2886 | 1655 | 996 | 57380 | 72875 | 3.6 | 3.575 | 315/485 | 15497 | 0 | 710 | - | Run at a pace where you can still hold a conversation. |
| 31 | 11 | sentence | 55828 | 2423 | 2051 | 1274 | 60480 | 76478 | 4.36 | 4.325 | 330/455 | 15995 | 0 | 815 | - | Drink water before and after your run, especially on hot day… |
| 32 | 14 | sentence | 59832 | 1744 | 2170 | 1365 | 63878 | 80840 | 4.94 | 4.9 | 325/515 | 16960 | 0 | 780 | - | Rest at least one day between runs at first, so your body ca… |
| 33 | 9 | sentence | 62724 | 2389 | 1493 | 965 | 66733 | 85783 | 3.24 | 3.2 | 310/430 | 19047 | 0 | 825 | - | Listen to your body, and stop if something hurts. |
| 34 | 5 | sentence | 64503 | 3068 | 1103 | 697 | 68799 | 89026 | 2.52 | 2.5 | 300/435 | 20224 | 0 | 730 | - | Finally, be patient with yourself. |
| 35 | 9 | sentence | 67842 | 1529 | 1740 | 1115 | 71303 | 91549 | 4.27 | 4.225 | 300/490 | 20243 | 0 | 735 | - | Progress in running comes gradually, and everyone starts som… |
| 36 | 4 | none | 72291 | 0 | 779 | 532 | 73188 | 95816 | 1.76 | 1.725 | 365/430 | 22631 | 0 | 855 | - | If you keep going |
| 37 | 5 | clause | 72291 | 1312 | 834 | 505 | 74562 | 97579 | 1.76 | 1.725 | 290/395 | 23014 | 0 | 720 | - | for a couple of months, |
| 38 | 5 | none | 72291 | 2651 | 1122 | 644 | 76187 | 99342 | 2.24 | 2.2 | 325/380 | 23152 | 0 | 720 | - | you will probably be surprised |
| 39 | 13 | sentence | 75183 | 1526 | 1566 | 1093 | 78398 | 101584 | 3.99 | 3.95 | 320/505 | 23184 | 0 | 700 | - | by how much easier it feels and how much further you can go. |
| 40 | 7 | sentence | 76741 | 2626 | 957 | 757 | 80450 | 105577 | 2.74 | 2.7 | 330/450 | 25124 | 0 | 835 | - | Good luck, and enjoy your first runs! |
