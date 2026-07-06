# Dotfiles — remote GPU dev workflow

Local-first tooling (Zellij, rexec, shell) for developing against remote GPU
dev pods on Kubernetes. The local machine holds credentials and editors; pods
hold GPUs, Docker, and synced working trees.

## Language

**Pod**:
A Kubernetes GPU dev pod reachable through rexec's ssh shim. One pod runs on
one node; a person may own several pods on different nodes.
_Avoid_: server, machine, box

**Pod key**:
The short handle naming one pod-registry entry (e.g. `21ca`). By convention it
echoes the node while pods run one-per-node; nothing enforces this, and future
entries (e.g. production deployments) may deviate. Every rexec/r invocation
resolves to exactly one pod key.
_Avoid_: pod name (that's the Kubernetes object name)

**Pod registry**:
The single global declaration of how to reach every pod: pod key → Kubernetes
pod name, ssh alias, tunnel port, plus cluster-level defaults. Sync plumbing
shared by all worktrees — not an authority on which pods exist or who owns
them (Kubernetes is; see ADR 0001).
_Avoid_: pod list, fleet inventory, pod config

**Worktree sync config**:
A worktree's `.rexec.yaml`, describing how that tree syncs (remote workdir,
ignore rules). Pod-agnostic: the same worktree can sync to any number of pods,
one derived session per (worktree, pod key) pair.
_Avoid_: pod config (obsolete: the pre-registry files that mixed pod
reachability with sync facts)

**Fleet**:
The pods you own, as reported by Kubernetes: pods in the dev namespace of the
rcli-selected context whose name carries your user prefix. Kubernetes is the
authority; local files never define the fleet. One member during single-node
work, several during multi-node (e.g. disaggregated) work.
_Avoid_: cluster (that's the Kubernetes cluster), node list

**Ownership**:
The pod-name prefix convention (`<user>-…`) established by the dev-env deploy
tooling. There are no ownership labels; the name is the record.

**Fleet layer**:
The Zellij floating-pane layer holding one GPU monitor pane per fleet member.
Summoned idempotently with one keybinding; shown/hidden as a unit with the
floating-panes toggle.

**Adaptive layout**:
The fleet layer's placement rule: full-size for one pane, side-by-side tiles
for two or three, overlapping full-size cascade (cycle to inspect) beyond
three — because a GPU monitor needs ~80 columns to stay readable.
