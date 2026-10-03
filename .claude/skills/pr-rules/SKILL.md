---
name: "pr-rules"
description: "Use for every change in ImageSkinForLLM: branch, size, tests, proof, logging and PR description rules that must be met before a change counts as done."
---

# PR rules

Apply these rules to every change. Sections 4, 5 and 6 apply only to code changes. A change is done only when a PR that meets them is open and its link has been given to the user.

## 1. Branches and merging
- Never commit or push directly to `main`.
- Commit and push only to a non-main branch, then open a PR.
- Never merge a PR into `main`. Only a human merges.

## 2. Size
Before opening the PR, rate how long a competent engineer needs to review it:

| Size | Review time |
|---|---|
| Simple | 10 minutes or less |
| Medium | 10 to 20 minutes |
| Large | 20 to 30 minutes |
| Very large | More than 30 minutes |

- Aim for Simple or Medium.
- Use Large only when the change truly cannot be split. Say why in the PR.
- Never open a Very large PR. Split the work into smaller PRs first.
- State the size rating in the PR description.

## 3. Simplicity
- Keep the design, the change and the data structures as simple as possible.
- Prefer the smallest change that solves the problem. Do not add scope.

## 4. Tests and coverage (code changes only)
- All new or changed code has unit tests.
- Aim for 80% test coverage or more, and report the coverage number.
- Add functional tests when unit tests alone cannot show the code works.

## 5. Logging (code changes only)
New or changed code logs:
- errors, with enough context to act on them
- the time taken for meaningful actions
- evidence that the code ran, such as a clear info line at the start or end of the action

## 6. Proof that it works (code changes only)
A PR that changes code must include proof:
- **UI changes:** a screenshot of the running app showing the change.
- **Non-UI changes:** a screenshot of the unit test run. It must show the summary line with how many tests ran, passed, failed and were skipped.
- **When unit tests are not enough:** functional test output as well.

A PR that only changes docs, markdown, skills or other non-code files skips proof and says "No code changes."

## 7. PR description
Keep it as short as possible while staying clear. Use this layout:

```
## Intent
What this change is for, in one or two sentences.

## Problem solved / feature added
What was wrong or missing, and what now works.

## Size
Simple | Medium | Large (with the reason if Large)

## Proof
Code changes: screenshot(s) and the test summary line: ran / passed / failed / skipped. Coverage: NN%.
No code changes: "No code changes."

## How to test manually (omit when there are no code changes)
1. How to start the app.
2. Steps to exercise the change.
3. What you should see in the UI or in the logs to confirm the code ran.
```

## 8. Checklist before reporting done
- [ ] On a non-main branch, pushed, PR open
- [ ] Size rated, and not Very large
- [ ] Code changes: unit tests added, coverage reported, ideally 80% or more
- [ ] Code changes: logging added for errors, timing and evidence of running
- [ ] Code changes: proof screenshot(s) attached, with the test summary line
- [ ] Code changes: manual test steps include what to look for in the UI or logs
- [ ] PR link given to the user