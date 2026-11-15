---
name: pr-sweep
description: Sweep Brendan's open pull requests toward merge - rebase conflicted or base-stale PRs, fix or re-run red CI, tick the B200 GPU suite, enable auto-merge on approved PRs, and close stale ones. Use when a scheduled wake or the user asks to sweep, babysit, shepherd, or check on "my PRs" / "my open PRs", asks what is blocking them, or asks to change, pause, or recreate the PR sweep schedule.
---

# PR sweep

One sweep moves every open PR of mine in `basetenlabs/baseten` one step closer to merged, then reports. It usually runs
from a schedule with nobody watching, so it must finish on its own: decide, act, record, report. Never use the question
tool; when a PR needs a decision you can't make, record it as needs-you (below) and move on.

`S=~/.claude/skills/pr-sweep/scripts/pr_sweep.py` decides what is due and keeps the ledger. Trust its `actions`: they
encode the limits that keep an unattended loop from pushing, re-running, or burning GPU time forever.

A request for a dry run, or for "what's blocking my PRs", means step 1 and the report only, with the "Did" column
saying what a sweep would do.

## 1. Snapshot

```bash
python3 $S snapshot
```

One JSON line per open PR. The fields that drive the sweep:

- `actions` — what to do now, in order. Empty means leave the PR alone.
- `blocked` — actions a previous sweep gave up on for this head commit, with the reason. Don't retry them.
- `waiting` — what the PR is waiting on that is not yours to do (review, approvals, CI running, a draft, its parent).
- `ci` — `green`, `pending`, `red` (a required check failed), `stale-base` (mp-status wants a rebase), or `needs-b200`.
- `failing` — every failed check. When `ci` is not `red` these are not required for merge: mention them in the report
  and leave them.
- `parent` / `children` — stack neighbours. A stack is one unit: one worktree, one rebase, one export.

Do each PR's listed actions once and stop. A push restarts CI and changes what is due (a rebased PR becomes eligible for
auto-merge, a child's red check may clear), so follow-on steps belong to the next wake, not to a wait inside this one.

PRs in other repositories are listed but never acted on. Drafts are only ever closed for staleness, since a draft is
parked on purpose.

## 2. Act

Work stack by stack. Stacks are independent, so when several need a rebase or a CI fix, hand each to its own `general`
subagent, telling it to load this skill and do that one action for that stack, and do the one-command actions yourself.

Get the stack's worktree before any git work:

```bash
python3 $S worktree <pr>     # {"path": ..., "stack": [bottom..top], "commits_below_stack": n}
```

It reuses a clean worktree of mine that already sits exactly on the PR head, and otherwise creates
`~/work/baseten-sweep-pr<N>` from the remote head. Work only in the path it prints. If it fails (dirty worktree,
unexpected stack shape), that is a needs-you for the action.

Pushing is always `stack-pr view`, then `stack-pr export` (load the `stack-pr` skill). Export only when the plan shows
`update` for exactly the PRs in `stack` and creates nothing: an unexpected `create` means the worktree holds commits
that are not these PRs, and exporting would open PRs I never asked for.

### rebase

```bash
git fetch origin master && git rebase origin/master
```

- `commits_below_stack > 0` means a parent PR already merged; the rebase should drop those commits as already applied.
- Resolve a conflict only when the right result is clear from both sides (both changes kept, a renamed symbol, a moved
  hunk). If it needs a judgment about behaviour, `git rebase --abort` and record needs-you.
- If the rebase leaves a PR's commit empty or drops it, the change already landed: `python3 $S close <pr> --note superseded`.
- After exporting: `python3 $S log rebase <pr>` once per stack (any PR in it).

### fix-ci

Find what failed (`failing` names the checks): `gh pr checks <pr> --repo basetenlabs/baseten` prints each check's URL,
whose `/actions/runs/<run-id>/` part feeds `gh run view <run-id> --repo basetenlabs/baseten --log-failed`. `mp-status`
saying "CPU checks have not passed" points at the failing `mp-cpu-checks / …` job. Then pick one:

- **Flake or infrastructure** (lost runner, network error, timeout in a step the diff can't affect, cancelled job):
  `gh run rerun <run-id> --repo basetenlabs/baseten --failed`, then `python3 $S log rerun <pr>`. Only when
  `reruns_for_head` is absent; a second failure on the same commit is not a flake.
- **Caused by the PR**: make the smallest fix in the worktree and check it with the narrowest test you can run locally
  (some project environments don't install on macOS; say so rather than skipping silently). Fold the fix into the PR's
  own commit (`git commit --amend`, or `--fixup` plus `git rebase --autosquash origin/master` for a lower commit in a
  stack), keep the `stack-pr-branch` trailer, and update the commit's Testing section if the fix made it untrue. Export,
  then `python3 $S log fix <pr>`.
- **Anything else** (also failing on master, needs a design decision, or you can't tell): needs-you. Don't weaken or
  skip a test to get green.

### tick-b200

```bash
python3 $S tick <pr>
```

Starts the B200 GPU suite for the head commit by ticking the box in the MPCI bot's comment. The suite is shared
hardware: the script proposes one tick per commit. Tick a second time only for a run that was cancelled or timed out.

### enable-automerge

```bash
python3 $S automerge <pr>
```

Squash auto-merge; GitHub merges once the required checks pass. Offered only for approved PRs based on master with no
unresolved review threads from people. It is fine to enable while the "Approval checks" status still wants another
team's approval: that status is required, so GitHub waits for it. Stacked children wait: GitHub retargets them to master
when the parent merges.

### close

```bash
python3 $S close <pr> --note stale
```

Offered after 30 days without a person touching the PR, unless it is approved or has children. The branch is kept, so
reopening restores it.

### needs-you

```bash
python3 $S log needs-you <pr> --blocks <action> --note "<one line: what is wrong and what decision is needed>"
```

This stops later sweeps from retrying that action until the PR's head changes. For a stack-wide failure, log it for each
PR in the stack that listed the action.

### Notifications

Every script command that changes something (`tick`, `automerge`, `close`, `log …`) posts a desktop notification that
opens the PR, so don't skip the `log` after a rebase, fix, or re-run: those notifications are the only way I hear what
the sweep did without opening this session. macOS shows about two lines, so a `--note` should lead with the decision
needed or the thing that changed.

## 3. Finish

Run `python3 $S gc` to remove sweep worktrees of PRs that merged or closed (not in a dry run), then report in this
shape, one row per PR and counting PRs:

```markdown
**PR sweep** — <n> open, <n> acted on, <n> need you

| PR | State | Did | Waiting on |
| --- | --- | --- | --- |
| #41464 Gate FlashInfer autotune caches | approved, B200 running | ticked B200 | GPU suite, then auto-merge |

**Needs you**
- #40784: <reason>
  https://github.com/basetenlabs/baseten/pull/40784
```

Leave out "Needs you" when it is empty. Put each URL on its own line, not in a markdown link. Mention approved, green
PRs in other repositories under "Needs you", since nothing will merge them.

## Limits

These hold whatever a PR's state suggests, because each one is either visible to other people or hard to undo:

- No comments, reviews, replies, reactions, reviewer requests, or resolving of review threads. Review feedback is mine
  to answer; report it under "Waiting on".
- No labels (above all `skip-gpu-tests` and `skip-mpci`), no draft or ready toggles, no retitling outside a commit
  amend, no `--admin` or direct merges. A PR merges through auto-merge or not at all.
- No pushes except `stack-pr export`, and no git work in `~/work/baseten` or in a worktree the script didn't print.
- Only my PRs.

## Schedule

The sweep runs in a dedicated session titled `[run] pr-sweep` in `~/work/baseten` (the `[run]` prefix makes my notify
plugin skip its turn-finished pings, leaving only the notifications above), woken by an OpenCode schedule (needs
`experimental.schedules` in `~/.config/opencode/opencode.json`): hourly, Monday to Friday, 07:00-20:00 Eastern. The
schedule's check is `python3 $S gate`, which prints one `#<pr> …` line per PR with work due and nothing otherwise, so
the session wakes only when there is work and quiet hours cost nothing. The check always exits 0, because the scheduler
pauses a schedule whose check fails; it also notifies me when a PR merges, when the same work stays due for three checks,
and when the check itself cannot reach GitHub. To recreate the schedule from that session:

```text
Schedule a wake with cron "0 7-20 * * 1-5" in America/New_York, gated by
if: { run: "python3 ~/.claude/skills/pr-sweep/scripts/pr_sweep.py gate", matches: "^#" },
with the prompt "Load the pr-sweep skill and run one sweep of my open PRs."
```

If a wake ever arrives with an error from the check, or the schedule shows as paused, don't just report it: nobody reads
this session. Run `python3 $S gate` to see the failure, resume the schedule if the check now exits 0, and otherwise
post one notification with `terminal-notifier -title "PR sweep: schedule is paused" -message "<why>"`.

Pause, resume, or delete it with the schedule tools in that session. Thresholds (30-day staleness, 2 fix pushes per
week, 2 B200 ticks per commit) are constants at the top of the script. History is in
`~/.local/state/pr-sweep/ledger.jsonl`.
