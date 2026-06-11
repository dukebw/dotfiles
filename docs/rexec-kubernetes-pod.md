# rexec Kubernetes Pod Workflow

`rexec` runs commands in a Kubernetes GPU dev pod while keeping editing, Git,
SSH private keys, GitHub credentials, and kubeconfig on the local laptop.

The workflow is optimized for this loop:

```bash
# Edit locally, run remotely after a one-way sync.
r nvidia-smi
r ./scripts/smoke-test.sh
rexec --shell 'docker ps | grep sglang'
rexec --tty bash
```

## Mental Model

Local files are authoritative. The pod is disposable compute.

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

`rexec` makes a Kubernetes pod look like a normal SSH host by creating an SSH
shim. Mutagen then uses that SSH transport for incremental file sync.

## Data Flow

```text
Local edit
  |
  | 1. r invokes rexec --flush
  v
Mutagen flush
  |
  | 2. one-way-replica sync
  v
/workspace/<repo> in pod
  |
  | 3. ssh command through kubectl port-forward
  v
Remote command executes in configured workdir
  |
  | 4. stdout/stderr stream back locally
  v
~/.config/rexec/logs/r/latest.log
```

## Security Model

The pod must not contain long-lived credentials.

What stays local:

- SSH private key: `~/.config/rexec/pod_ed25519`
- kubeconfig: configured by `~/.config/rexec/config.yaml`
- GitHub credentials and `gh auth`
- Git working tree metadata, including `.git`

What goes into the pod:

- Only the SSH public key in `/root/.ssh/authorized_keys`
- The synced working tree contents, excluding ignored paths
- Build artifacts created by remote commands

SSH is not exposed as a Kubernetes `Service`. It is reachable only through a
local `kubectl port-forward` process owned by the laptop session.

## Components

| Component | Location | Purpose |
| --- | --- | --- |
| `rexec` | `bin/rexec` | Python CLI that sets up the SSH shim, creates the Mutagen session, and executes commands. |
| `r` | `bin/r` | Bash wrapper that always flushes before execution and captures logs. |
| Config | `~/.config/rexec/config.yaml` | Local, untracked pod/workdir/sync configuration. |
| State | `~/.config/rexec/` | SSH key, port-forward PID/log, run logs. |
| SSH alias | `~/.ssh/config` | Managed block named by `ssh_alias`, usually `baseten-dev-pod`. |
| Mutagen session | `mutagen sync list` | One-way local-to-pod sync session. |

## Required Local Tools

Install these on the laptop:

```bash
brew install kubectl mutagen-io/mutagen/mutagen
python3 -m pip install --user pyyaml
```

The dotfiles `Brewfile` includes the expected CLI tools for normal setup.

## Required Pod Capabilities

The dev pod must support:

- `kubectl exec`
- `apt-get`, used by `rexec --setup` to install `openssh-server` if missing
- root or enough permissions to write `/root/.ssh/authorized_keys`
- a stable filesystem path for the remote workdir, usually under `/workspace`

The current Baseten GPU dev pod runbooks create privileged pods that satisfy
these requirements.

## Config File

Create `~/.config/rexec/config.yaml`. This file is intentionally local and not
tracked in dotfiles because it contains machine-specific paths and pod names.

Example:

```yaml
kubeconfig: /path/to/kubeconfig.yaml
namespace: baseten
pod: brendanduke-dev-pod-b200-0

local_root: /Users/brendenduke/work/baseten-ideogram4-smoke
remote_workdir: /workspace/baseten-ideogram4-smoke

ssh_alias: baseten-dev-pod
ssh_host: 127.0.0.1
ssh_local_port: 22222
ssh_remote_port: 2222
ssh_user: root
ssh_key: /Users/brendenduke/.config/rexec/pod_ed25519

mutagen_session: baseten-ideogram4-smoke

ignore:
  - /.git
  - /.derived
  - /bazel-*
  - /external
  - /node_modules
  - /frontend/node_modules
  - "**/__pycache__"
  - "**/.pytest_cache"
  - "**/.mypy_cache"
  - "**/*.pyc"
  - "**/.venv"
  - "**/*.venv"
  - .DS_Store
```

Environment overrides are available for one-off runs:

```bash
REXEC_POD=other-pod-0 r nvidia-smi
REXEC_WORKDIR=/workspace/other-worktree rexec --shell 'pwd'
```

Supported overrides:

| Environment variable | Config key |
| --- | --- |
| `REXEC_KUBECONFIG` | `kubeconfig` |
| `REXEC_NAMESPACE` | `namespace` |
| `REXEC_POD` | `pod` |
| `REXEC_LOCAL_ROOT` | `local_root` |
| `REXEC_WORKDIR` | `remote_workdir` |

## First-Time Setup

Run setup from the local repo you want synced:

```bash
rexec --setup
```

Setup performs these actions:

```text
1. Read ~/.config/rexec/config.yaml
2. Create ~/.config/rexec/pod_ed25519 if it does not exist
3. kubectl exec into the pod
4. Install/start openssh-server in the pod if needed
5. Append only the local public key to /root/.ssh/authorized_keys
6. Write/update the managed Host block in ~/.ssh/config
7. Start kubectl port-forward localhost:<ssh_local_port> -> pod:<ssh_remote_port>
8. Create the remote workdir
9. Create the Mutagen one-way-replica sync session
```

The managed SSH block looks like this:

```sshconfig
# BEGIN rexec managed pod SSH shim
Host baseten-dev-pod
    HostName 127.0.0.1
    Port 22222
    User root
    IdentityFile ~/.config/rexec/pod_ed25519
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
    ForwardX11 no
    ForwardX11Trusted no
# END rexec managed pod SSH shim
```

`rexec` owns only this block. It preserves other SSH config content.

## Daily Commands

Use `r` for the normal edit-run loop:

```bash
r nvidia-smi
r docker ps
r ./bin/run-smoke-test
```

Use `rexec` directly when you do not want an automatic sync:

```bash
rexec hostname
rexec --quiet hostname
rexec --shell 'ls -la | head'
rexec --tty bash
rexec --flush ./scripts/test.sh
```

Use a heredoc for readable multi-line remote commands:

```bash
rexec --flush --shell "$(cat <<'EOF'
set -euo pipefail
pwd
nvidia-smi
EOF
)"
```

`r` writes logs to:

```text
~/.config/rexec/logs/r/latest.log
~/.config/rexec/logs/r/history/<timestamp>-<pid>.log
```

## Lifecycle

```text
+----------------------+      rexec --setup       +----------------------+
| Config exists        +-------------------------->+ SSH shim ready       |
+----------------------+                           +----------+-----------+
                                                              |
                                                              | mutagen session
                                                              v
+----------------------+      r <command>         +----------------------+
| Local worktree       +-------------------------->+ Pod worktree synced  |
+----------------------+                           +----------+-----------+
                                                              |
                                                              | ssh command
                                                              v
                                                   +----------------------+
                                                   | Remote command runs  |
                                                   +----------------------+
```

If the pod restarts, run `rexec --setup` again. The private key remains local;
the pod only gets the public key again.

If the port-forward dies, the next `rexec`/`r` invocation starts it again.

## Mutagen Operations

Inspect the sync session:

```bash
mutagen sync list
mutagen sync list <mutagen_session>
```

Force a flush without running a command:

```bash
mutagen sync flush <mutagen_session>
```

Recreate a session after changing ignore rules:

```bash
mutagen sync terminate <mutagen_session>
rexec --setup
```

## Troubleshooting

### `r: event not found` or `fc: event not found`

Zsh has a builtin `r` history command. The dotfiles `.zshrc` defines an `r()`
function that dispatches to `~/.local/bin/r`. Reload the shell:

```bash
source ~/.zshrc
```

### `Missing rexec config`

Create `~/.config/rexec/config.yaml`; see the config example above.

### `Pod ... is not Running`

Check the configured namespace and pod:

```bash
kubectl --kubeconfig <kubeconfig> get pod -n <namespace> <pod>
```

### `kubectl port-forward exited early`

Read the log:

```bash
cat ~/.config/rexec/port-forward.log
```

Common causes are stale pod names, an unreachable kubeconfig, or the local port
already being used by another process.

### Mutagen sync is stale

Run:

```bash
rexec --setup
mutagen sync flush <mutagen_session>
```

If that does not help, terminate and recreate the session:

```bash
mutagen sync terminate <mutagen_session>
rexec --setup
```

### SSH works but command runs in the wrong directory

Check `remote_workdir` in `~/.config/rexec/config.yaml`. `rexec` always runs:

```bash
cd <remote_workdir> && <command>
```

### Need to pass a short-lived secret for one command

Pipe secrets over stdin or environment for that command only. Do not write
tokens into the config file or pod filesystem.

Example pattern:

```bash
gh auth token | ssh baseten-dev-pod 'read -r GITHUB_TOKEN; export GITHUB_TOKEN; your-command'
```

Prefer BuildKit secrets for Docker builds:

```bash
DOCKER_BUILDKIT=1 docker build --secret id=github_token,env=GITHUB_TOKEN .
```

## Design Decisions

| Decision | Reason |
| --- | --- |
| SSH shim instead of direct `kubectl exec` for every file operation | Mutagen supports SSH endpoints and gives incremental sync. |
| `kubectl port-forward` instead of a Kubernetes `Service` | SSH is reachable only from the local laptop session. |
| One-way local-to-remote sync | Local worktree is authoritative; remote build artifacts do not pollute local Git. |
| Public key in pod, private key local | Satisfies the dev environment constraint not to put private keys on the pod. |
| `.git` ignored | Avoids copying local Git metadata and credentials into the pod. |
| `r` wraps `rexec --flush` | The common command does the safe thing by default. |
