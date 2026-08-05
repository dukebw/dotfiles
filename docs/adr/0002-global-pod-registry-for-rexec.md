# Pod reachability lives in one global registry; worktree configs only sync

rexec resolves every invocation against two files with disjoint concerns: a
global pod registry (`~/.config/rexec/pods.yaml`) declaring how to reach each
pod (pod key → Kubernetes pod name, ssh alias, tunnel port, cluster defaults),
and a per-worktree `.rexec.yaml` declaring only how that tree syncs
(`remote_workdir`, `ignore`). Selection is `-p/--pod <key>` >
`$REXEC_POD` > the registry's `default:`; mutagen sessions are always derived
as `<root-basename>-<8-char-root-hash>-<podkey>` and auto-created on first
flush. The full-root hash distinguishes nested repositories with the same
basename across worktrees.

The forcing observation: pod facts were duplicated per worktree (two worktrees
× two pods = four files differing in exactly four keys), and the facts that
must be globally consistent — local tunnel ports, ssh aliases, the managed
`~/.ssh/config` block — were declared in per-worktree files, so two worktrees
could silently disagree about the same pod's port, and each pod's `--setup`
clobbered the other's managed ssh block. Deriving the ssh block and the
port-forward state files from the registry makes those conflicts impossible
by construction, and multi-pod work (disaggregated serving: one worktree
synced to N pods) needs zero new config lines per pod pair.

This does not amend ADR 0001: Kubernetes remains the authority on which pods
exist and who owns them. The registry is sync plumbing — ports and aliases are
local resources Kubernetes knows nothing about. Pod keys echo node names by
convention (one pod per node on the dev cluster today); nothing enforces it.

Consequences accepted: `$REXEC_POD` changed meaning from "raw Kubernetes pod
name override" to "registry key" (grep showed zero usage of the old meaning
outside rexec's own docs); legacy worktree configs containing pod keys
hard-error with migration instructions rather than being honored (no
dual-schema code path); existing ad-hoc mutagen session names were terminated
and recreated under collision-resistant derived names (a rescan, not a
retransfer).

## Considered Options

- Filename-suffix selection (`-p tp8` → nearest `.rexec-tp8.yaml`; rejected:
  keeps all duplication and the port-conflict hazard, scales worst under
  disagg — every new pod means a new file in every worktree).
- Per-worktree `pods:` map inside `.rexec.yaml` (rejected: DRYs within a
  worktree but pod facts stay copied across worktrees, and globally-scoped
  resources remain declared in locally-scoped files).
- Maximal derivation (aliases `rexec-<key>`, positional port allocation;
  rejected: renames aliases that scripts and muscle memory depend on, and
  positional ports silently re-wire when entries are added or removed).
- Honoring legacy flat configs alongside the registry (rejected: two schemas
  forever, and `-p` against an inline single-pod config has no coherent
  meaning).
