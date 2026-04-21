---
description: Draft an implementation plan (approval-ready, no code written).
---

# /plan

Produce an approval-ready implementation plan for the user's goal.

## What goes in a plan

1. **Goal** — one sentence.
2. **Context** — what's already in the codebase; which bible section applies.
3. **Non-goals** — what we're explicitly not doing in this PR.
4. **Proposed change** — file list with purpose for each.
5. **Sequence** — numbered steps, each independently commitable.
6. **Risks** — what could go wrong; rollback plan.
7. **Tests** — what gets added; which tier (unit/integration/node).
8. **Docs** — what gets updated in `docs/`; whether the bible needs a revision-log entry.
9. **Acceptance** — the single command or check that proves we're done.

## Rules

- No code written. This is a plan, not an implementation.
- Cite file paths with `path:line` where specific.
- If a chosen approach conflicts with the bible, say so and propose a bible amendment in the same plan.
- If the plan is larger than one PR, split it into phases and deliver the phase plan only.

## Output

Markdown, sections as above, target 400–800 words.
