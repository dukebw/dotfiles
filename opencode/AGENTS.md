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

## Billip access

Never access Billip autonomously. Do not call `baseten_billip_*` tools, use or
sync a Billip browser session, or inspect Billip session credentials unless
Brendan explicitly approves Billip access for the current task. If Billip could
unblock an investigation, explain what specific data is needed and ask first;
prefer non-Billip APIs or owner-provided configuration when available.

## Baseten cluster access

Before concluding that a workload-plane kubeconfig is unavailable, run
`rcli sync --provider rancher` and use `rcli select --provider rancher` to
select the cluster. `rcli select` chooses from the kubeconfigs synced under
`~/.rcli/kubeconfig/`; access still depends on Kubernetes RBAC. Verify the
required operation with `kubectl auth can-i` before treating access as a
blocker.

## Baseten deployment naming

Every Kubernetes or Helm deployment created for Brendan on a Baseten cluster
must use a short base name containing the exact contiguous segment
`-debugging-brendanduke` before any controller-generated suffixes. After
creation, verify that every generated pod name contains both `debugging` and
`brendanduke`; if Grove or Kubernetes truncation removes either token, rename
and recreate the deployment before proceeding.

## Git workspace policy

Create repository clones and Git worktrees under `~/work/`, not temporary
directories.

For `feat/k3` work, use `~/work/baseten-k3/` for monorepo changes and
`~/work/baseten-k3/mp/baseten_dynamo/cache_aware_routing_trtllm/baseten_trtllm/trt-llm/`
for TensorRT-LLM changes unless Brendan explicitly specifies another checkout.

Do not push, create remote branches, or open pull requests unless I explicitly
request that remote operation. Local commits are allowed.

For commits in Baseten repositories, including forks, use the `What`, `How`,
and `Testing` sections from `~/work/baseten/.github/pull_request_template.md`
as the commit body. Omit the `Release requirements` section.
