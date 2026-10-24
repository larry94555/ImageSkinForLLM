# R99: a reply asked while the wiki is built (cloud session, 2026-10-23)

`reply_during_wiki.py` against llama-server (built from source, Gemma 3 4B Q4_K_M,
`--ctx-size 4096 --threads 2 --threads-batch 4 --swa-full`, 4 slots sharing one context) on a
4-core cloud session. The prompt "What is a prime number?" was asked with the LLM idle, then 20 s
into the sample PDF's first wiki part. Times in ms from the prompt being sent.

| Run | First token | First sentence | Last token | Prompt read (ms) | Wiki's first part done |
|---|---|---|---|---|---|
| Before, LLM idle | 1,497 | 6,281 | 11,580 | 1,472 | - |
| Before, during the wiki | 15,009 | 19,581 | 24,046 | 10,751 | 174.2 s |
| After (R99), LLM idle | 1,181 | 6,221 | 10,881 | 260 | - |
| After (R99), during the wiki | 441 | 5,164 | 9,886 | 227 | 167.7 s |

Before, the reply's single new prompt token waited 10.8 s behind the wiki's part being read in
another slot, and its first sentence came 13.3 s later than with the LLM idle. With replies
first, the wiki's request was cut off the moment the reply started and asked again once it was
written, so the reply's first sentence came as soon as with the LLM idle. The wiki's first part
didn't finish later: llama-server kept what it had read of the cut-off request, so asking again
read little of it again.

The log of the R99 run:

```
   33173 ms Wiki request cut off for a reply
   33174 ms Cutting off an LLM request
   33175 ms Wiki request paused for a reply; it is asked again after it
   43059 ms Wiki waited for a reply
  180919 ms Wiki part done
```
