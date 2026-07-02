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
| `.rexec.yaml` or `~/.config/rexec/config.yaml` | Local untracked pod/workdir config. |
| `~/.config/rexec/pod_ed25519` | Local throwaway private key for the pod SSH shim. |
| `~/.ssh/config` | Contains a managed `rexec` Host block. |

## Setup Checklist

1. Confirm the pod is running:

```bash
kubectl --kubeconfig <kubeconfig> get pod -n <namespace> <pod>
```

2. Create `.rexec.yaml` in the worktree or `~/.config/rexec/config.yaml` with the kubeconfig, namespace, pod,
   local root, remote workdir, SSH alias, local port, remote port, key path,
   Mutagen session name, and ignore rules.

3. Run setup from the local repo root:

```bash
rexec --setup
```

4. Verify execution:

```bash
r nvidia-smi
rexec --quiet hostname
rexec --shell 'pwd && ls'
```

## Config Shape

Example config:

```yaml
kubeconfig: /path/to/kubeconfig.yaml
namespace: baseten
pod: brendanduke-dev-pod-b200-0

local_root: /Users/brendanduke/work/baseten-ideogram4-smoke
remote_workdir: /workspace/baseten-ideogram4-smoke

ssh_alias: baseten-dev-pod
ssh_host: 127.0.0.1
ssh_local_port: 22222
ssh_remote_port: 2222
ssh_user: root
ssh_key: /Users/brendanduke/.config/rexec/pod_ed25519

mutagen_session: baseten-ideogram4-smoke

ignore:
  - /.git
  - /node_modules
  - "**/__pycache__"
  - "**/.venv"
  - .DS_Store
```

Supported environment overrides:

Config discovery order: `--config`, `REXEC_CONFIG`, nearest `.rexec.yaml`, then
`~/.config/rexec/config.yaml`.

| Environment variable | Config key |
| --- | --- |
| `REXEC_CONFIG` | Config file path |
| `REXEC_KUBECONFIG` | `kubeconfig` |
| `REXEC_NAMESPACE` | `namespace` |
| `REXEC_POD` | `pod` |
| `REXEC_LOCAL_ROOT` | `local_root` |
| `REXEC_WORKDIR` | `remote_workdir` |

## Daily Commands

```bash
r nvidia-smi
r docker ps
r ./scripts/smoke-test.sh
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
- Keep `.rexec.yaml` and `~/.config/rexec/config.yaml` untracked.

## Troubleshooting

If zsh runs the builtin history command instead of `r`, reload `.zshrc`:

```bash
source ~/.zshrc
```

If the port-forward fails, inspect:

```bash
cat ~/.config/rexec/port-forward.log
```

If sync is stale, flush or recreate the Mutagen session:

```bash
mutagen sync flush <mutagen_session>
mutagen sync terminate <mutagen_session>
rexec --setup
```

If the pod restarts, run:

```bash
rexec --setup
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
