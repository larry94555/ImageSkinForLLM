# llama-server settings compared

Replies: the three prompts of a conversation, after the warm-up. Times in milliseconds from the request; reading and writing in tokens a second, the replies' averaged.

| Setting | Model | Slots | Reused after warm-up | First token | First sentence | Read tokens/s | Written tokens/s |
|---|---|---|---|---|---|---|---|
| hosted, R97 settings | gemma-3-4b-it-Q4_K_M.gguf | 4 | 97 | 418.2 / 903.6 / 876.5 | 2230.8 / 2177.6 / 1973.8 | 26.1 | 5.4 |
| before: 4B Q4_K_M, 2 threads | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 7119.1 / 3480.9 / 3778.9 | 8942.9 / 4582.0 / 4894.4 | 14.2 | 5.4 |
| one slot | gemma-3-4b-it-Q4_K_M.gguf | 1 | 1 | 7086.8 / 3720.4 / 3997.6 | 8886.8 / 4986.6 / 5636.3 | 14.4 | 5.5 |
| full SWA cache | gemma-3-4b-it-Q4_K_M.gguf | 4 | 97 | 800.6 / 1764.6 / 1739.8 | 2615.5 / 3048.0 / 2856.7 | 13.3 | 5.4 |
| 3 threads | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 4770.8 / 2336.1 / 2722.6 | 6018.6 / 3088.5 / 3487.8 | 21.1 | 7.9 |
| 4 threads | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 3579.0 / 1769.5 / 1914.9 | 4580.6 / 2355.2 / 2504.2 | 28.2 | 10.1 |
| 2 threads, 4 reading | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 3594.8 / 1836.6 / 2052.4 | 5383.3 / 2919.8 / 3512.0 | 27.7 | 5.5 |
| flash attention on | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 7087.3 / 3448.1 / 3720.0 | 8881.6 / 4534.6 / 4814.9 | 14.4 | 5.5 |
| flash attention off | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 7168.7 / 3479.2 / 4013.5 | 9010.2 / 4585.1 / 5119.5 | 14.2 | 5.4 |
| batch 128 | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 7112.3 / 3463.2 / 3764.0 | 8903.2 / 4569.6 / 4853.4 | 14.3 | 5.5 |
| batch 1024 | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 7082.2 / 3464.0 / 3723.3 | 8882.9 / 4567.7 / 4834.2 | 14.4 | 5.5 |
| context 8192 | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 7079.3 / 3449.7 / 3999.5 | 8871.6 / 4534.4 / 5088.3 | 14.3 | 5.5 |
| 4B Q4_0 | gemma-3-4b-it-Q4_0.gguf | 4 | 1 | 4039.4 / 2065.3 / 2195.7 | 5513.3 / 2964.2 / 3547.1 | 24.3 | 6.7 |
| 4B Q8_0 | gemma-3-4b-it-Q8_0.gguf | 4 | 1 | 4438.7 / 2400.3 / 2781.6 | 6286.4 / 3550.4 / 4483.8 | 21.5 | 5.3 |
| 1B Q4_K_M | gemma-3-1b-it-Q4_K_M.gguf | 4 | 1 | 3336.2 / 1262.7 / 1628.9 | 3519.1 / 1627.8 / 2356.9 | 30.9 | 16.4 |
| chosen: 2 threads, 4 reading, full SWA cache | gemma-3-4b-it-Q4_K_M.gguf | 4 | 97 | 423.1 / 904.6 / 869.1 | 2234.7 / 2006.8 / 1980.0 | 26.1 | 5.4 |

The wiki: the sample PDF's first part (cut for a 4096-token window), and the whole sample PDF's wiki estimated from its speeds and R96a's tokens (24064 read, 12521 written).

| Setting | Tokens read | Read tokens/s | Tokens written | Written tokens/s | Part took | Sample PDF's wiki | Topics |
|---|---|---|---|---|---|---|---|
| hosted, R97 settings | 2827 | 27.5 | 529 | 4.3 | 224413.3 | 63.1 min | 6 |
| before: 4B Q4_K_M, 2 threads | 2827 | 13.8 | 581 | 4.3 | 337864.5 | 77.6 min | 6 |
| one slot | 2826 | 13.9 | 509 | 4.6 | 313142.8 | 74.2 min | 6 |
| full SWA cache | 2827 | 14.0 | 564 | 4.3 | 331431.4 | 77.2 min | 6 |
| 3 threads | 2827 | 20.3 | 583 | 6.0 | 236710.2 | 54.5 min | 6 |
| 4 threads | 2827 | 27.4 | 516 | 7.8 | 169513.2 | 41.4 min | 6 |
| 2 threads, 4 reading | 2827 | 27.5 | 552 | 4.3 | 229859.4 | 63.1 min | 6 |
| flash attention on | 2827 | 13.9 | 563 | 4.3 | 333299.6 | 77.4 min | 6 |
| flash attention off | 2827 | 13.5 | 616 | 4.4 | 349413.7 | 77.1 min | 6 |
| batch 128 | 2827 | 13.9 | 531 | 4.3 | 326139.2 | 77.4 min | 6 |
| batch 1024 | 2827 | 13.2 | 576 | 3.9 | 361279.8 | 83.9 min | 6 |
| context 8192 | 2827 | 13.9 | 585 | 4.4 | 337778.6 | 76.3 min | 6 |
| 4B Q4_0 | 2827 | 23.2 | 538 | 5.0 | 228483.6 | 59.0 min | 6 |
| 4B Q8_0 | 2827 | 21.3 | 504 | 4.3 | 250962.1 | 67.4 min | 6 |
| 1B Q4_K_M | 2827 | 30.5 | 388 | 15.5 | 117690.7 | 26.6 min | 6 |
| chosen: 2 threads, 4 reading, full SWA cache | 2827 | 27.6 | 573 | 4.3 | 234348.3 | 63.1 min | 6 |

The topics each setting found in the first part:

- **hosted, R97 settings:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes (Pi(x)); The Prime Number Theorem
- **before: 4B Q4_K_M, 2 threads:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; Prime Number Theorem
- **one slot:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; The Prime Number Theorem
- **full SWA cache:** Prime Numbers; The Fundamental Theorem of Arithmetic; Infinite Primes; The Sieve of Eratosthenes; Counting Primes; The Prime Number Theorem
- **3 threads:** Prime Numbers; Unique Prime Factorization; Infinite Primes; Sieving Primes; Prime Number Distribution; The Prime Number Theorem
- **4 threads:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; The Prime Number Theorem
- **2 threads, 4 reading:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; Prime Number Theorem
- **flash attention on:** Prime Numbers; The Fundamental Theorem of Arithmetic; Infinite Primes; The Sieve of Eratosthenes; Counting Primes (pi(x)); Prime Number Theorem
- **flash attention off:** Prime Numbers; Building Numbers with Primes; Infinite Primes; The Sieve of Eratosthenes; Counting Primes; The Zeta Function and Euler
- **batch 128:** Prime Numbers; Factorization of Numbers; Infinite Primes; The Sieve of Eratosthenes; Counting Primes; The Prime Number Theorem
- **batch 1024:** Prime Numbers; The Fundamental Theorem of Arithmetic; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes (Pi(x)); The Prime Number Theorem
- **context 8192:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; The Prime Number Theorem
- **4B Q4_0:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; Sieve of Eratosthenes; Distribution of Primes; Prime Number Theorem
- **4B Q8_0:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Distribution of Primes; The Prime Number Theorem
- **1B Q4_K_M:** Prime Numbers and the Zeta Function; 1. What a prime number is; 2. Building every number from primes; 3. There are infinitely many primes; 4. Finding primes: the sieve of Eratosthenes; 5. How many primes there are
- **chosen: 2 threads, 4 reading, full SWA cache:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; The Prime Number Theorem
