# A spoken question checked sooner (R101)

Larry's hosted run of R96 (2026-10-22) found a spoken question reached the LLM 32.4 s after it
was sent, against 26 to 33 ms for a typed one: before it is answered, the LLM was asked to put
back misheard names with all 100 of the content's words (about 400 tokens), read at 14 tokens a
second there.

Now only the content's words spelled like a word heard (at most 8) are named, and the LLM
answers with just the changes ("Oiler -> Euler", or NONE), about 100 tokens in and 3 to 6 out.

Measured in a cloud session (4-core Xeon, llama-server with Gemma 3 4B Q4_K_M on 2 threads,
which reads about 44 tokens a second), with 100 content words, by `spoken_correction.py` here
(its docstring says how to run it):

| Question as heard | Before: result, time | After: result, time |
|---|---|---|
| What did Oiler multiply over? | unchanged, 9.8 s | "Euler", 3.6 s |
| Tell me about the boiler product | "Euler", 9.2 s | unchanged, 3.2 s |
| How long does prepare take? | unchanged, 11.0 s | unchanged, 3.4 s |
| Who are you? | unchanged, 9.0 s | unchanged, 2.4 s |

llama-server read 400 to 404 prompt tokens per check before, and 95 to 105 after. At the hosted
machine's 14 tokens a second that is about 7 s instead of about 29 s, plus about 1 s for the
answer. The LLM's answers vary a little (temperature 0.3): over three more tries each, "Oiler"
was put back 3 times, "boiler" 2, and "Rie man" as "Riemann" 2; nothing was ever changed to a
word that doesn't sound like the one heard, as the existing check (`kept`) refuses that.

llama-server reused none of the fixed instruction from its cache, though it is the same at the
start of every check: Gemma 3's sliding-window attention keeps llama-server from reusing a
prompt's start once the rest differs, unless it is started with `--swa-full`. That, also seen
in R96's first reply (1 token reused after the warm-up), is for R97; with it, a check would read
only its last 25 tokens or so.
