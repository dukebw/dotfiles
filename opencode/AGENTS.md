## Subagent policy

Default to completing work in the current agent.

Do not use the Task tool merely to search the repository, inspect a small
number of files, or perform work that is sequential.

Use a subagent only when:
- I explicitly request delegation, or
- there are at least two independent, bounded workstreams that can proceed
  in parallel and delegation is likely to materially reduce wall-clock time.

Prefer the narrow read-only explore or scout agent over general.
When uncertain, do not delegate.

## Baseten admin access

For Baseten admin API, deployment, and log investigations, use
`B10_ADMIN_API_KEY` from `~/.env` when the normal Truss remotes cannot resolve
the target. Never print the key, include it in model-visible tool output, or
commit it. If an MCP tool requires a Truss remote, create or reuse the local
`b10-admin` remote using that environment variable.

## Git workspace policy

Create repository clones and Git worktrees under `~/work/`, not temporary
directories.

Do not push, create remote branches, or open pull requests unless I explicitly
request that remote operation. Local commits are allowed.

For commits in Baseten repositories, including forks, use the `What`, `How`,
and `Testing` sections from `~/work/baseten/.github/pull_request_template.md`
as the commit body. Omit the `Release requirements` section.
