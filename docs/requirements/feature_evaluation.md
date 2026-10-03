# ImageSkinForLLM: Evaluation of features.md (second review)

**Verdict:** features.md is now complete enough to start building. Every issue and gap from the first review is addressed. What remains are a few small inconsistencies, some vague thresholds, and confirming the *(default)* choices. Numbers refer to features.md.

## Fixed since the first review

| First-review finding | Where it's fixed |
|---|---|
| Settings said "three options" but listed nine | 8 |
| WAV-only uploads; .m4a from the guide rejected | 1 |
| No expected file count | 1 (5 photos, 3 or 4 recordings) |
| Sample script about 3 seconds, not 30 | 6 (~75-word script) |
| No progress shown during slow renders | 5, 6 |
| "Reject voice" forced a re-upload for accent | 7 (Change accent) |
| Settings changes didn't require a new sample | 8 |
| "Restart the LLM" unclear | 14 (Start again, history kept) |
| No latency target | 12 (2 seconds) |
| No speech to text | 9 |
| No streaming plan | 12 |
| No idle video, stop, saved setup, error handling, volume | 17 to 21 |
| Validation checks undefined | 2, 3 |
| Replies not safe to voice; text/speech sync unclear | 10, 11 |
| History could overflow the context window | 15 |
| Hosted gaps: consent, privacy, HTTPS, compute, API keys | Deployment, 16, 22, 23 |
| "Goodbye" and "Welcome back" not pre-rendered | 5 |

## Remaining issues

| # | Issue | Suggested fix |
|---|---|---|
| 3 | "Long enough" has no number. | At least 30 seconds of usable speech in total; 1 to 2 minutes recommended. |
| 1 | Unclear whether fewer than 5 photos is allowed. Only one good photo is needed. | Require at least 1 valid photo; recommend 5. |
| 5, 8 | Pre-rendered "Goodbye" and "Welcome back" go stale when images, voice or accent change. | Re-render them whenever a new sample is accepted. |
| 8, 23 | "Delete my data" isn't reachable from Settings. | Add it to the Settings list. |
| 15, 19 | Saved setup survives a return visit, but it's unclear whether chat history does. | Save history with the setup, cleared by "Clear conversation" or "Delete my data." |
| 12 | Sentence-by-sentence clips can show a visible jump where one clip ends and the next starts. | Return to the idle pose between clips (17) and crossfade the joins. |
| 11 | Word highlighting needs word timings from the voice engine. | Make word timings a requirement when choosing the voice engine. |
| Deployment | Supporting both local and hosted video engines up front doubles the work. | Build one first, behind the pluggable interface, and add the other later. |

## Risks still open

- **The 2-second target vs. local video.** Per the planning notes, the best single-photo models take minutes per sentence. Meeting item 12 locally likely means MuseTalk-style lip sync on a pre-made idle loop, or a hosted streaming avatar. This choice should be made before building.
- **Americanize may cost likeness.** The sample test (6, 7) is where the user judges that trade-off. No change needed.
- **Language.** The app assumes English replies. The guide's optional 4th recording (first language) isn't used anywhere yet. Fine for now.

## Defaults to confirm with Larry

1. Single user on the hosted site.
2. Support both local and hosted video engines (this review suggests building one first).
3. Push-to-talk for the microphone.
4. 2-second latency target.
5. History kept after "Start again."
