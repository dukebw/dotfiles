---
name: stack-pr
version: 1.0.0
description: Use stack-pr to view/export stacked PRs and preserve stack-info.
displayName: "Stack PR Workflow"
author: "Modular"
license: "Apache-2.0"
---

# Stack PR Workflow

Use this skill when managing stacked PRs with `stack-pr`.

References:
- Claude skills docs: https://code.claude.com/docs/en/skills

## Commands

- `stack-pr view`
  - Verify the stack shows the expected commit(s).
  - Confirm the PR number and branch mapping in the output.

- `stack-pr export`
  - Use only after `stack-pr view` confirms the stack is correct.
  - If needed, push a specific range:
    - `stack-pr export -B <base> -H <head>`

## Commit Message Guidance

- Preserve the existing `stack-info` line when amending commits.
- Keep `stack-info` outside `BEGIN_PUBLIC`/`END_PUBLIC` blocks.

Example commit message tail:

```
stack-info: PR: https://github.com/modularml/modular/pull/76987, branch: dukebw/stack/353
```

## Safety Checklist

1. Run `stack-pr view`.
2. Confirm a single commit (or expected stack) and the correct PR number.
3. Export with `stack-pr export`.
