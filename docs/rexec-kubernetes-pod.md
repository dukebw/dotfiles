# rexec Kubernetes Pod Workflow

`rexec` runs commands in Kubernetes dev and tooling pods while keeping editing,
Git, SSH private keys, GitHub credentials, and kubeconfig on the local laptop.

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
| Local MacBook                 |     | Kubernetes dev/tooling pod      |
|                               |     |                                 |
| Editor, Git, GitHub auth      |     | Compiler/build/test tools        |
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
- kubeconfig: configured by `~/.config/rexec/pods.yaml`
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
| `rexec-docker-pull` | `bin/rexec-docker-pull` | Pulls Docker images on the pod with temporary Docker credentials only when needed. |
| Pod registry | `~/.config/rexec/pods.yaml` | Global: how to reach every pod (pod key → k8s pod name, ssh alias, tunnel port, cluster defaults). ADR 0002. |
| Worktree sync config | `.rexec.yaml` at the worktree root | How this tree syncs (`remote_workdir`, `ignore`). Pod-agnostic and untracked. |
| State | `~/.config/rexec/` | SSH key, per-pod port-forward PID/log (`port-forward-<key>.*`), run logs. |
| SSH aliases | `~/.ssh/config` | One managed block containing a Host entry for every registry pod. |
| Mutagen sessions | `mutagen sync list` | One-way local-to-pod sync, one session per (worktree, pod key); new sessions are named `<root-basename>-<8-char-root-hash>-<podkey>`. |

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

GPU dev pods satisfy these requirements through the existing runbooks. The
CPU-only remote clangd pod is defined in
`kubernetes/remote-clangd-statefulset.yaml`.

## Configuration

Two files with disjoint concerns (ADR 0002):

- **Pod registry** `~/.config/rexec/pods.yaml` — global, declares how to reach
  every pod. Ports and aliases are local machine-wide resources (one tunnel
  daemon, one `~/.ssh/config`), so they are declared exactly once here.
- **Worktree sync config** `.rexec.yaml` at each worktree root — declares how
  that tree syncs. Pod-agnostic: the same worktree can sync to any number of
  pods. Keep it untracked via the global Git ignore.

Pod registry:

```yaml
default: e7e4
kubeconfig: ~/.rcli/kubeconfig/vultr-us-sea-prod-1.yaml
namespace: baseten

pods:
  e7e4:
    pod: brendanduke-dev-pod-b200-0
    ssh_alias: baseten-dev-pod
    ssh_local_port: 22222
  clangd:
    pod: remote-clangd-debugging-brendanduke-0
    ssh_alias: baseten-remote-clangd-pod
    ssh_local_port: 22230
  21ca:
    pod: brendanduke-tp8-dev-pod-b200-0
    ssh_alias: baseten-tp8-pod
    ssh_local_port: 22223
    # kubeconfig/namespace/ssh_* may be overridden per entry
    # (e.g. a pod on a different cluster).
```

Pod keys (`e7e4`, `clangd`, `21ca`) are free-form handles. GPU pod keys may echo
their node; purpose-specific tooling pods use descriptive keys. Registry loading
validates unique ports and unique aliases and fails loud on conflicts.

Worktree sync config:

```yaml
remote_workdir: /workspace/fresh_glm5.2/baseten-dspark
# local_root defaults to the directory containing this file.

ignore:
  - /.git
  - "**/__pycache__"
  - "**/.venv"
  - .DS_Store
```

### Selecting a pod

Every invocation resolves to exactly one pod key:

1. `-p/--pod <key>` flag
2. `$REXEC_POD` (export once per terminal to point a whole tab at one pod)
3. The registry's `default:`

```bash
r -p 21ca docker logs -f docker-worker-1
export REXEC_POD=21ca && r docker ps
rexec --pods            # list the registry
```

An unknown key fails loud with the known keys listed.

### Worktree config resolution

1. `--config <path>`
2. `REXEC_CONFIG=<path>`
3. The nearest `.rexec.yaml` found by walking upward from the current directory
4. A config-free invocation when both `REXEC_LOCAL_ROOT` and `REXEC_WORKDIR`
   are set
5. `~/.config/rexec/config.yaml`

The paired root variables are a complete ephemeral worktree config, used by
remote editor tooling and one-off setup. They deliberately bypass the global
fallback so an unrelated or stale worktree config cannot break that invocation.
Setting only one remains an override on a resolved config and does not enable
config-free operation.

Supported environment overrides:

| Environment variable | Meaning |
| --- | --- |
| `REXEC_CONFIG` | Worktree config file path |
| `REXEC_POD` | Pod key (registry selection, not a raw k8s pod name) |
| `REXEC_KUBECONFIG` | `kubeconfig` |
| `REXEC_NAMESPACE` | `namespace` |
| `REXEC_LOCAL_ROOT` | `local_root` |
| `REXEC_WORKDIR` | `remote_workdir` |

### Migrating to the pod registry

Pre-registry configs mixed pod reachability into `.rexec.yaml` (and per-pod
variants like `.rexec-tp8.yaml`). Loading one now fails loud. To migrate:

1. Move `pod`/`ssh_alias`/`ssh_local_port` (plus `kubeconfig`/`namespace`)
   into a `pods.yaml` entry; pick a pod key.
2. Strip the worktree config down to `remote_workdir` + `ignore`; delete
   per-pod variant files.
3. Terminate old ad-hoc-named mutagen sessions
   (`mutagen sync terminate <old>`); `rexec --setup --flush -p <key>`
   recreates them under derived names — a rescan, not a retransfer, when the
   trees already match.
4. Delete any hand-written `~/.ssh/config` entries for pods now covered by the
   managed block (they shadow it: ssh first-match wins).

## First-Time Setup

Run setup from the local repo you want synced, once per pod you'll use:

```bash
rexec --setup -p e7e4
rexec --setup -p 21ca
```

Setup performs these actions:

```text
1. Resolve the worktree config and the selected registry entry
2. Create ~/.config/rexec/pod_ed25519 if it does not exist
3. Regenerate the managed ~/.ssh/config block from the WHOLE registry
4. kubectl exec into the selected pod
5. Install/start openssh-server in the pod if needed
6. Append only the local public key to /root/.ssh/authorized_keys
7. Start kubectl port-forward localhost:<ssh_local_port> -> pod:<ssh_remote_port>
   (state in ~/.config/rexec/port-forward-<key>.{pid,log}, one pair per pod)
8. Create the remote workdir
9. Create the Mutagen one-way-replica session <root-basename>-<8-char-root-hash>-<podkey>
```

Sessions also auto-create lazily: the first `r -p <key> ...` in a worktree
creates that (worktree, pod) session on the spot.

If a pre-hash `<root-basename>-<podkey>` session already points at the exact
local and remote roots, rexec reuses it. A legacy session pointing at another
same-named nested repository is not reused; rexec creates the hashed session,
which prevents worktrees containing repeated names such as `trt-llm` from
colliding.

The managed SSH block holds one Host entry per registry pod:

```sshconfig
# BEGIN rexec managed pod SSH shim
Host baseten-dev-pod
    HostName 127.0.0.1
    Port 22222
    ...
Host baseten-tp8-pod
    HostName 127.0.0.1
    Port 22223
    ...
# END rexec managed pod SSH shim
```

`rexec` owns only this block and derives it from the registry, so no pod's
setup can clobber another's entry. Other SSH config content is preserved.

## Daily Commands

Use `r` for the normal edit-run loop:

```bash
r nvidia-smi                              # registry default pod
r -p 21ca docker logs -f docker-worker-1  # explicit pod key
export REXEC_POD=21ca                     # point this tab at 21ca
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

## Docker Image Pulls

Do not run plain `docker login` on the pod for long-lived use: Docker writes
credentials to `/root/.docker/config.json` by default. Use `rexec-docker-pull`
for private images so credentials live only in a unique temporary
`DOCKER_CONFIG` under `/tmp`.

```bash
rexec-docker-pull \
  baseten/dynamo-cache-aware-routing:trtllm-dyn12-gpu-67d0025e9b-1612f9093-5641f85404 \
  baseten/bitnami-etcd:latest \
  nats:latest
```

Behavior:

```text
1. Skip images already present on the pod.
2. Try unauthenticated `docker pull` for missing images.
3. If a pull fails with an auth-looking error, run `docker login` once through `rexec --tty` using a temp `DOCKER_CONFIG`.
4. Retry only the auth-failed images with that temp config.
5. Always delete the temp config, even on failure.
```

Use `--config` from outside the worktree:

```bash
rexec-docker-pull --config /path/to/.rexec.yaml baseten/private-image:tag
```

Force login first when the pull error is not recognized as auth-related:

```bash
rexec-docker-pull --login baseten/private-image:tag
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

If the pod came back with a fresh disk (for example after `b10-gpu move` to
another node), Mutagen sees the previously populated remote root reappear empty
and safety-halts the session (`Halted due to one-sided root emptying`).
`rexec --setup`, `rexec --flush`, and `r` detect this signature — session
halted, local side populated, remote side empty — and automatically run
`mutagen sync reset` to re-push from local. Use `rexec --setup --flush` to
block until the re-push completes. Sessions whose *local* side is empty are
never auto-reset, because one-way-replica mode would wipe the pod-side copy.

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

Recreate a session after changing ignore rules. Get the collision-resistant
derived name from `mutagen sync list`:

```bash
mutagen sync terminate baseten-dspark-1a2b3c4d-21ca
rexec --setup -p 21ca
```

## Troubleshooting

### `r: event not found` or `fc: event not found`

Zsh has a builtin `r` history command. The dotfiles `.zshrc` defines an `r()`
function that dispatches to `~/.local/bin/r`. Reload the shell:

```bash
source ~/.zshrc
```

### `Missing rexec worktree config` / `Missing pod registry`

Create `.rexec.yaml` in the worktree root (sync facts) and/or
`~/.config/rexec/pods.yaml` (pod entries); see the configuration section above.

### `... contains pod-reachability keys`

The worktree config predates the registry model; follow
[Migrating to the pod registry](#migrating-to-the-pod-registry).

### `Pod ... is not Running`

Check the configured namespace and pod:

```bash
kubectl --kubeconfig <kubeconfig> get pod -n <namespace> <pod>
```

### `kubectl port-forward exited early`

Read the selected pod's log:

```bash
cat ~/.config/rexec/port-forward-<key>.log
```

Common causes are stale pod names, an unreachable kubeconfig, or the local port
already being used by another process.

### `session is not currently able to synchronize`

The session is halted. After a pod move/restart onto a fresh disk, the next
`rexec --setup`, `rexec --flush`, or `r` invocation auto-resets it (see the
pod-restart note above) — rerun the command if an older rexec printed this.
If rexec reports the session does not match the recreated-remote signature,
inspect it before touching anything:

```bash
mutagen sync list <mutagen_session>
```

A halt with the *local* (alpha) side empty usually means the local worktree was
deleted; terminate the session instead of resetting it.

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

Check `remote_workdir` in the resolved rexec config. `rexec` always runs:

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
| Global pod registry, sync-only worktree configs | Ports/aliases are machine-global resources; declaring them per worktree allowed silent conflicts and ssh-block clobbering. See ADR 0002. |
| Derived mutagen session names | One session per (worktree, pod) with zero config lines; scales to one worktree synced to N pods (disaggregated serving). |
