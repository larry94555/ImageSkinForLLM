# llama-server settings compared

Replies: the three prompts of a conversation, after the warm-up. Times in milliseconds from the request; reading and writing in tokens a second, the replies' averaged.

| Setting | Model | Slots | Reused after warm-up | First token | First sentence | Read tokens/s | Written tokens/s |
|---|---|---|---|---|---|---|---|
| before: 4B Q4_K_M, 2 threads | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 5132.9 / 2929.1 / 3720.6 | 7374.3 / 4398.0 / 4912.3 | 17.6 | 4.6 |
| one slot | gemma-3-4b-it-Q4_K_M.gguf | 1 | 1 | 4421.1 / 2574.8 / 3106.5 | 6400.4 / 3921.7 / 4439.4 | 19.9 | 4.7 |
| 3 threads | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 3191.4 / 2201.4 / 2601.5 | 4819.0 / 3351.7 / 3546.3 | 25.9 | 6.3 |
| 4 threads | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 2409.1 / 1848.6 / 2145.9 | 3560.8 / 2766.6 / 2947.8 | 32.5 | 7.9 |
| 2 threads, 4 reading | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 2642.2 / 1764.9 / 2050.9 | 4975.1 / 3329.9 / 3377.6 | 32.0 | 4.6 |
| flash attention on | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 4316.4 / 3003.6 / 3074.6 | 6600.3 / 4602.1 / 4407.2 | 19.8 | 4.4 |
| flash attention off | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 4605.1 / 3105.4 / 2866.6 | 6899.2 / 4540.6 / 4305.2 | 19.0 | 4.4 |
| batch 128 | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 4508.8 / 2829.7 / 3403.9 | 6608.2 / 4069.4 / 4654.1 | 18.7 | 4.7 |
| batch 1024 | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 4368.6 / 2767.7 / 3102.2 | 6497.4 / 4077.0 / 4367.9 | 19.6 | 4.6 |
| context 8192 | gemma-3-4b-it-Q4_K_M.gguf | 4 | 1 | 4804.3 / 3530.1 / 3183.0 | 6875.1 / 5033.8 / 4481.5 | 18.0 | 4.8 |
| 4B Q4_0 | gemma-3-4b-it-Q4_0.gguf | 4 | 1 | 4202.2 / 2670.6 / 3166.7 | 6240.5 / 3930.9 / 5030.4 | 19.8 | 4.8 |
| 4B Q8_0 | gemma-3-4b-it-Q8_0.gguf | 4 | 1 | 6235.5 / 4061.8 / 4676.1 | 9528.0 / 6010.9 / 7532.0 | 13.7 | 3.0 |
| 1B Q4_K_M | gemma-3-1b-it-Q4_K_M.gguf | 4 | 1 | 1440.2 / 845.1 / 798.0 | 1684.3 / 1305.2 / 1582.6 | 60.7 | 12.3 |
| full SWA cache | gemma-3-4b-it-Q4_K_M.gguf | 4 | 97 | 944.5 / 1236.0 / 1502.0 | 3177.4 / 2605.0 / 2830.7 | 15.4 | 4.6 |
| chosen: 2 threads, 4 reading, full SWA cache | gemma-3-4b-it-Q4_K_M.gguf | 4 | 97 | 348.6 / 677.4 / 737.5 | 2374.1 / 1946.4 / 2723.7 | 32.5 | 4.8 |

The wiki: the sample PDF's first part (cut for a 4096-token window), and the whole sample PDF's wiki estimated from its speeds and R96a's tokens (24064 read, 12521 written).

| Setting | Tokens read | Read tokens/s | Tokens written | Written tokens/s | Part took | Sample PDF's wiki | Topics |
|---|---|---|---|---|---|---|---|
| before: 4B Q4_K_M, 2 threads | 2827 | 23.6 | 600 | 3.7 | 283887.6 | 73.4 min | 6 |
| one slot | 2826 | 23.4 | 606 | 3.8 | 279556.1 | 72.0 min | 6 |
| 3 threads | 2827 | 32.6 | 523 | 4.8 | 196285.6 | 55.8 min | 6 |
| 4 threads | 2827 | 44.2 | 508 | 6.2 | 146855.1 | 42.7 min | 6 |
| 2 threads, 4 reading | 2827 | 43.5 | 545 | 3.6 | 217502.4 | 67.2 min | 6 |
| flash attention on | 2827 | 24.5 | 581 | 3.7 | 272528.0 | 72.8 min | 6 |
| flash attention off | 2827 | 23.2 | 509 | 3.8 | 256204.6 | 72.2 min | 6 |
| batch 128 | 2827 | 23.8 | 558 | 3.7 | 271417.5 | 73.2 min | 6 |
| batch 1024 | 2827 | 24.5 | 507 | 3.9 | 246745.6 | 69.9 min | 6 |
| context 8192 | 2827 | 25.5 | 527 | 3.9 | 248100.7 | 69.2 min | 6 |
| 4B Q4_0 | 2827 | 23.1 | 540 | 3.9 | 261114.4 | 70.9 min | 6 |
| 4B Q8_0 | 2827 | 17.4 | 510 | 2.6 | 355786.1 | 103.3 min | 6 |
| 1B Q4_K_M | 2827 | 67.4 | 460 | 11.4 | 82238.0 | 24.2 min | 6 |
| full SWA cache | 2827 | 23.6 | 585 | 3.7 | 276926.8 | 73.4 min | 6 |
| chosen: 2 threads, 4 reading, full SWA cache | 2827 | 43.6 | 595 | 3.8 | 219354.3 | 64.1 min | 6 |

The topics each setting found in the first part:

- **before: 4B Q4_K_M, 2 threads:** Prime Numbers; Building Numbers with Primes; Infinite Primes; The Sieve of Eratosthenes; Counting Primes; Prime Number Theorem
- **one slot:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; Prime Number Theorem
- **3 threads:** Prime Numbers; The Fundamental Theorem of Arithmetic; Infinite Primes; The Sieve of Eratosthenes; Counting Primes; The Zeta Function and Euler's Contribution
- **4 threads:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; The Prime Number Theorem
- **2 threads, 4 reading:** Prime Numbers; The Fundamental Theorem of Arithmetic; Infinite Primes; Sieving for Primes; Distribution of Primes; The Prime Number Theorem
- **flash attention on:** Prime Numbers; Unique Prime Factorization; Infinite Primes; Sieve of Eratosthenes; Prime Number Distribution; Prime Number Theorem
- **flash attention off:** Prime Numbers; The Fundamental Theorem of Arithmetic; Infinite Primes; The Sieve of Eratosthenes; Counting Primes; The Zeta Function
- **batch 128:** Prime Numbers; The Fundamental Theorem of Arithmetic; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; The Prime Number Theorem
- **batch 1024:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; Euler and the Zeta Function
- **context 8192:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; The Prime Number Theorem
- **4B Q4_0:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Counting Primes; Prime Number Theorem
- **4B Q8_0:** Prime Numbers; Building Numbers with Primes; Infinitely Many Primes; The Sieve of Eratosthenes; Distribution of Primes; Prime Number Theorem
- **1B Q4_K_M:** Prime Numbers and the Zeta Function; 1. What a prime number is; 2. Building every number from primes; 3. There are infinitely many primes; 4. Finding primes: the sieve of Eratosthenes; 5. How many primes there are
- **full SWA cache:** Prime Numbers; Building Numbers with Primes; Infinite Primes; Sieving for Primes; Counting Primes; The Prime Number Theorem
- **chosen: 2 threads, 4 reading, full SWA cache:** Prime Numbers; The Fundamental Theorem of Arithmetic; Infinite Primes; The Sieve of Eratosthenes; Counting Primes (pi(x)); The Prime Number Theorem
