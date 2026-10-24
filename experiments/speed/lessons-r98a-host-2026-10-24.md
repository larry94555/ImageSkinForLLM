# R98a on the hosted machine: Teach me from the saved first part

Larry's run on app.me0.ai, 2026-10-24 (4 Ampere cores, Gemma 3 4B Q4_0), with the sample PDF's
wiki built and every topic's first lesson part saved (30 topics, about 17 s each to write, in
8 minutes after the wiki). `imageskin time-reply "Teach me about Prime Number Basics" "Teach me
about Riemann Zeta Function"`; the log had `Lesson from the saved part` for both.

| Reply | Prompt | Reached LLM | First word heard (ms) |
|---|---|---|---|
| 1 | Teach me about Prime Number Basics | no | 2841 |
| 2 | Teach me about Riemann Zeta Function | no | 5316 |

Against answers the LLM writes in the same run's `time-pdf` (after the summary): first word
heard after 14.3 to 15.8 s. All of the 2.8 to 5.3 s is the voice and video of the first clip:
reply 2's first sentence has no comma, so its first clip was 6.5 s of speech, voiced in 5.1 s.

The same run's `time-pdf` (before the fixes in PR #160's later commits) asked Teach me about the
first page's title, "Prime Numbers", which is not a lesson topic, and after the 87 s conversation
summary made after its questions; `time-pdf` now takes the outline's first topic and waits for
the summary.
