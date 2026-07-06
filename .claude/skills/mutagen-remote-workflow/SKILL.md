---
name: mutagen-remote-workflow
description: Set up or use the `r`/`rexec` Kubernetes GPU pod workflow with Mutagen sync, SSH over kubectl port-forward, and local-only credentials. Use when the user mentions rexec, r, mutagen, remote builds, GPU dev pods, kubectl exec, or syncing files to a Kubernetes pod.
---

# Mutagen Remote Workflow Setup

Use this skill when working with the dotfiles `r`/`rexec` workflow.

The current workflow targets Kubernetes GPU dev pods, not Coder workspaces.
Do not put private SSH keys, GitHub tokens, or kubeconfig files on the pod.

## Architecture

```text
                         Kubernetes API
                  kubectl exec / port-forward
                +---------------------------+
                |                           |
+---------------v---------------+     +-----v---------------------------+
| Local MacBook                 |     | Kubernetes GPU dev pod          |
|                               |     |                                 |
| Editor, Git, GitHub auth      |     | Docker, GPUs, build/test tools   |
| kubeconfig                    |     | sshd on localhost-only tunnel    |
| SSH private key               |     | authorized_keys has public key   |
| Mutagen daemon                |     | synced working tree              |
+---------------+---------------+     +----------------+----------------+
                |                                      ^
                | SSH to 127.0.0.1:<local port>        |
                +--------------------------------------+
                       kubectl port-forward to pod
```

Execution flow:

```text
local edit -> r -> rexec --flush -> Mutagen one-way sync -> ssh command in pod
```

## Source Of Truth

The comprehensive user-facing documentation is:

```text
docs/rexec-kubernetes-pod.md
```

Read that file before changing the workflow. Keep it updated when changing
`bin/rexec`, `bin/r`, install behavior, config keys, or security assumptions.

## Key Files

| File | Purpose |
| --- | --- |
| `bin/rexec` | Python CLI for pod setup, Mutagen sync, and remote execution. |
| `bin/r` | Wrapper that runs `rexec --flush`, streams output, and writes logs locally. |
| `docs/rexec-kubernetes-pod.md` | Full architecture, setup, security, and troubleshooting docs. |
| `~/.config/rexec/pods.yaml` | Global pod registry: pod key → k8s pod name, ssh alias, tunnel port, cluster defaults (ADR 0002). |
| `.rexec.yaml` at the worktree root | Untracked worktree sync config: `remote_workdir` + `ignore` only, pod-agnostic. |
| `~/.config/rexec/pod_ed25519` | Local throwaway private key for the pod SSH shim. |
| `~/.ssh/config` | Managed block with one Host entry per registry pod, derived from the registry. |

## Setup Checklist

1. Confirm the pod is running:

```bash
kubectl --kubeconfig <kubeconfig> get pod -n <namespace> <pod>
```

2. Add a registry entry in `~/.config/rexec/pods.yaml` (pod key → `pod`,
   `ssh_alias`, unique `ssh_local_port`). Create `.rexec.yaml` in the worktree
   with `remote_workdir` and `ignore` rules (`local_root` defaults to the
   file's directory).

3. Run setup from the local repo root, per pod:

```bash
rexec --setup -p <key>
```

4. Verify execution:

```bash
rexec --pods
r -p <key> nvidia-smi
rexec --quiet hostname
rexec --shell 'pwd && ls'
```

## Config Shape

Pod registry `~/.config/rexec/pods.yaml`:

```yaml
default: e7e4
kubeconfig: ~/.rcli/kubeconfig/vultr-us-sea-prod-1.yaml
namespace: baseten
pods:
  e7e4:
    pod: brendanduke-dev-pod-b200-0
    ssh_alias: baseten-dev-pod
    ssh_local_port: 22222
  21ca:
    pod: brendanduke-tp8-dev-pod-b200-0
    ssh_alias: baseten-tp8-pod
    ssh_local_port: 22223
```

Worktree `.rexec.yaml` (sync facts only; pod-reachability keys here are a
legacy config and fail loud with migration instructions):

```yaml
remote_workdir: /workspace/fresh_glm5.2/baseten-dspark
ignore:
  - /.git
  - "**/__pycache__"
  - "**/.venv"
  - .DS_Store
```

Mutagen session names are always derived: `<worktree-dirname>-<podkey>`
(e.g. `baseten-dspark-21ca`); sessions auto-create on first flush.

Pod selection precedence: `-p/--pod <key>` flag, then `$REXEC_POD`, then the
registry `default:`. Worktree config discovery: `--config`, `REXEC_CONFIG`,
nearest `.rexec.yaml`, then `~/.config/rexec/config.yaml`.

| Environment variable | Meaning |
| --- | --- |
| `REXEC_CONFIG` | Worktree config file path |
| `REXEC_POD` | Pod key (registry selection, NOT a raw k8s pod name) |
| `REXEC_KUBECONFIG` | `kubeconfig` |
| `REXEC_NAMESPACE` | `namespace` |
| `REXEC_LOCAL_ROOT` | `local_root` |
| `REXEC_WORKDIR` | `remote_workdir` |

## Daily Commands

```bash
r nvidia-smi                              # registry default pod
r -p 21ca docker logs -f docker-worker-1  # explicit pod key
export REXEC_POD=21ca                     # point this shell at 21ca
r docker ps
r ./scripts/smoke-test.sh
rexec --pods                              # list the registry
rexec hostname
rexec --quiet hostname
rexec --shell 'ls -la | head'
rexec --tty bash
rexec --flush ./scripts/test.sh
```

For multi-line remote commands, use a quoted heredoc so local variables do not
expand unexpectedly:

```bash
rexec --flush --shell "$(cat <<'EOF'
set -euo pipefail
pwd
nvidia-smi
EOF
)"
```

## Security Rules

- Do not copy private SSH keys to the pod.
- Do not copy GitHub tokens or kubeconfig files to the pod.
- Do not add `.git` to Mutagen sync.
- Do not expose SSH with a Kubernetes `Service`; use local `kubectl port-forward`.
- Prefer short-lived environment variables or BuildKit secrets for one-off secrets.
- Keep `.rexec.yaml` and `~/.config/rexec/pods.yaml` untracked.

## Troubleshooting

If zsh runs the builtin history command instead of `r`, reload `.zshrc`:

```bash
source ~/.zshrc
```

If the port-forward fails, inspect the selected pod's log:

```bash
cat ~/.config/rexec/port-forward-<key>.log
```

If sync is stale, flush or recreate the Mutagen session (derived name
`<worktree-dirname>-<podkey>`):

```bash
mutagen sync flush <worktree>-<key>
mutagen sync terminate <worktree>-<key>
rexec --setup -p <key>
```

If the pod restarts, run:

```bash
rexec --setup -p <key>
```

If the pod moved to a node with a fresh disk (e.g. `b10-gpu move`), Mutagen
halts the session with `Halted due to one-sided root emptying`; `rexec --setup`,
`rexec --flush`, and `r` auto-reset it when the local side is populated and the
remote side is empty. `rexec --setup --flush` blocks until the re-push
completes. Sessions with an empty *local* side are never auto-reset — inspect
those with `mutagen sync list <mutagen_session>`.

## When Editing The Workflow

Update all relevant places together:

- `bin/rexec`
- `bin/r`
- `install.sh`
- `README.md`
- `docs/rexec-kubernetes-pod.md`
- `.claude/skills/mutagen-remote-workflow/SKILL.md`

Run at least:

```bash
python3 -m py_compile bin/rexec
bash -n bin/r install.sh
```

If a pod is available, verify:

```bash
rexec --setup
r nvidia-smi
```
