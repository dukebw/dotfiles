## Execution context

Resolve working paths from the active workspace. A model or topic name does not select a checkout or branch.

Apply cloud-host, devcontainer, and GPU-pod instructions only in that actual execution environment. A
missing executable does not establish the environment or authorize starting a VM or installing a toolchain.

Treat resource names, reservations, paths, and running-job statements from earlier work as historical observations.
Recheck live state before acting; preserve recorded version pins when reproducing an old result rather than treating
them as current defaults.

## Baseten admin access

For Baseten admin API, deployment, and log investigations, use `B10_ADMIN_API_KEY` from `~/.env` when the normal Truss
remotes cannot resolve the target. Never print the key, include it in model-visible tool output, or commit it. If an MCP
tool requires a Truss remote, create or reuse the local `b10-admin` remote using that environment variable.

## Billip access

Never access Billip autonomously. Do not call `baseten_billip_*` tools, use or sync a Billip browser session, or inspect
Billip session credentials unless Brendan explicitly approves Billip access for the current task. If Billip could
unblock an investigation, explain what specific data is needed and ask first; prefer non-Billip APIs or owner-provided
configuration when available.

## Baseten deployment naming

For Brendan's Kubernetes or Helm deployments on Baseten, include `-debugging-brendanduke` in the short base name.
Check every generated pod name; rename and recreate if truncation drops `debugging` or `brendanduke`.
For management-API model deployments, use the segment in the display name only.

## Git workspace policy

Work in `~/work/baseten/` unless I name another checkout. Create another clone or Git worktree only when a task needs
one, and put it under `~/work/`, not in a temporary directory.

Keep inference-engine and runtime forks (SGLang, vLLM, TRT-LLM, Dynamo) inside the active Baseten checkout at the
default location.

Do not push, create remote branches, or open pull requests unless I explicitly request that remote operation. Local
commits are allowed.

Pull requests follow the stack-pr workflow: one commit is one PR. Put a new change up for review as a new commit on the
current stack, not on a new branch; stack-pr creates the PR branches. Keep each commit's `stack-pr-branch` trailer when
amending, and load the `stack-pr` skill before viewing or exporting the stack.

When addressing PR review comments, load the `address-pr-review-comments` skill.

For commits in Baseten repositories, including forks, use the `What`, `How`, and `Testing` sections from
`~/work/baseten/.github/pull_request_template.md` as the commit body. Omit the `Release requirements` section.

## Code changes

Prefer a surgical edit over rewriting a file when the result is the same.

If you find a pre-existing bug, performance concern, or behavior the task doesn't mention, don't fix, optimize, or
extend it in this change unless the requested behavior cannot work without it; report it as a follow-up. Keep scratch
checks and verification scripts out of the repository. Commit tests only where the task asks for them or the repository
already keeps tests for this kind of change, sized like the neighboring test files.

## Nsight Systems

For any `nsys` work (capturing or analyzing `.nsys-rep` reports, report SQL, recipes, CLI syntax), first read
`/Applications/NVIDIA Nsight Systems.app/Contents/skills/nsight-systems/SKILL.md` and follow it, including its
platform bootstrap. Its scripts run on this Mac; on a GPU pod, use the `nsys` installed there.

## Terminal output

Paste URLs verbatim on their own line, never as markdown links; markdown links are not clickable in my terminal.

## Visuals

Make generated visuals such as HTML pages, diagrams and charts dark mode by default. An explicit request for another
scheme, or matching an existing document's or product's styling, takes precedence.
