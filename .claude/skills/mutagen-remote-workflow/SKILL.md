---
name: mutagen-remote-workflow
description: Set up local editing + remote build workflow using Mutagen file sync with Coder workspaces. Includes the `rexec` helper script for running commands on remote machines. Use when the user mentions rexec, mutagen, remote builds, Coder workspaces, or syncing files to a remote GPU server.
---

# Mutagen Remote Workflow Setup

Set up a local editing + remote build/execution workflow using Mutagen file sync. This enables:
- **Local neovim editing** (no SSH latency on keystrokes)
- **Remote build execution** (bazel, GPU tests on Coder workspaces)
- **Automatic file sync** between local and remote

## Architecture

```
┌─────────────────────┐         Mutagen Sync         ┌─────────────────────┐
│   Local MacBook     │ ◄───────────────────────────►│  Coder Workspace    │
│                     │      (one-way-replica)       │                     │
│ ~/work/modular      │                              │ ~/work/modular      │
│ - neovim (local)    │                              │ - ./bazelw build    │
│ - AI agent (local)  │                              │ - GPU execution     │
│ - git (local)       │                              │ - nvitop monitoring │
└─────────────────────┘                              └─────────────────────┘
```

## Quick Start (TL;DR)

```bash
# In ~/work/modular
mutagen project start          # Start sync from mutagen.yml
r ./bazelw build //path:target  # Run command remotely (flushes first)
rexec hostname                 # Run command remotely (no flush)
```

## Key Files

| File | Purpose |
|------|---------|
| `~/work/modular/mutagen.yml` | Declarative Mutagen sync config |
| `~/.local/bin/rexec` | Remote execution helper (Python) |
| `~/.local/bin/r` | Wrapper: flush + rexec |
| `~/.ssh/config` | SSH multiplexing config |

## Prerequisites

- macOS with Homebrew
- Coder CLI configured (`coder config-ssh` already run)
- SSH access to Coder workspace (e.g., `ssh <workspace>.coder` works)
- Local clone of the repository

## Setup Steps

### 1. Install Mutagen

```bash
brew install mutagen-io/mutagen/mutagen
mutagen version  # Verify: should show 0.18.x or higher
```

### 2. SSH Multiplexing (speeds up repeated commands)

Add to `~/.ssh/config`:

```sshconfig
Host *.coder coder.*
    # Speed: connection multiplexing
    ControlMaster auto
    ControlPath ~/.ssh/cm/%C
    ControlPersist 10m

    # Reliability
    ServerAliveInterval 60
    ServerAliveCountMax 10
    TCPKeepAlive yes

    # Don't pay X11 tax for every short command
    ForwardX11 no
    ForwardX11Trusted no

    StrictHostKeyChecking no
    ConnectTimeout 0
```

Create socket directory:
```bash
mkdir -p ~/.ssh/cm
```

Test (second command should be <0.5s):
```bash
time ssh b200-hydra.coder hostname  # ~2s first time
time ssh b200-hydra.coder hostname  # <0.5s with multiplexing
```

### 3. Mutagen Project Config

Create `~/work/modular/mutagen.yml` (gitignored):

```yaml
sync:
  defaults:
    mode: one-way-replica
    flushOnCreate: true

    symlink:
      mode: posix-raw

    permissions:
      defaultFileMode: "0644"
      defaultDirectoryMode: "0755"

    ignore:
      vcs: true
      paths:
        - "/.derived"
        - "/bazel-*"
        - "/external"
        - "**/__pycache__"
        - "**/.pytest_cache"
        - "**/.mypy_cache"
        - "**/*.pyc"
        - "**/.venv"
        - "**/*.venv"
        - ".DS_Store"

  modular:
    alpha: "/Users/bduke/work/modular"
    beta: "b200-hydra.coder:/home/ubuntu/work/modular"
```

Start the sync:
```bash
cd ~/work/modular
mutagen project start    # Start from yml
mutagen project list     # Verify running
```

### 4. rexec - Remote Execution Tool

`~/.local/bin/rexec` is a Python script that:
- Prints a clear header to stderr (pipeline-safe)
- Auto-detects remote host from current worktree
- Supports `--shell` for pipes/redirects
- Supports `--flush` to sync Mutagen before executing
- Supports `--tty` for interactive commands
- Supports `-q` for quiet mode (no header)

**Usage:**
```bash
rexec hostname                          # Basic command
rexec -q hostname                       # Quiet (no header)
rexec --shell "ls -la | head -5"        # Shell mode (pipes work)
rexec --flush ./bazelw test //...       # Flush Mutagen first
rexec --tty htop                        # Interactive (allocate TTY)
rexec -r gcore-h100 hostname            # Explicit remote override
```

### 5. r Wrapper (Recommended)

`~/.local/bin/r` is a simple wrapper that flushes Mutagen before running rexec:

```bash
r ./bazelw build //path:target  # Flushes + executes remotely
```

This is the recommended way to run remote commands - ensures your local changes are synced before the command runs.

## Daily Commands Reference

### Mutagen Project Mode

```bash
cd ~/work/modular
mutagen project start    # Start sync session
mutagen project list     # Show session status
mutagen project flush    # Force immediate sync
mutagen project pause    # Pause before large git ops
mutagen project resume   # Resume after workspace restart
mutagen project terminate # Stop session (keeps files)
```

### Remote Execution

```bash
r ./bazelw build //path:target       # Flush + exec (recommended)
rexec ./bazelw test //path:target    # Exec without flush
rexec --flush ./bazelw run //...     # Explicit flush + exec
rexec -q hostname | cat              # Pipeline-safe (no header)
rexec --tty python                   # Interactive REPL
```

### Zellij

- `Ctrl+a 1/2/...` - Switch tabs
- `Ctrl+a f` or `Alt+f` - Toggle floating panes
- `Ctrl+a d` - Detach session

## Troubleshooting

### "Scanning files" takes forever
Large repos (10-50GB) take several minutes on first scan. This is normal.

### Workspace auto-stopped
After Coder workspace restarts:
```bash
cd ~/work/modular
mutagen project resume
```

### Need to change ignores
Edit `mutagen.yml`, then:
```bash
mutagen project terminate
mutagen project start
```

### SSH multiplexing not working
Check socket exists:
```bash
ls ~/.ssh/cm/
```

### Sync seems stale
Force a flush before execution:
```bash
r ./bazelw build //...  # Wrapper auto-flushes
# or
rexec --flush ./bazelw build //...
```

## Advanced: Multi-Workspace with Git Worktrees

For working on multiple branches simultaneously, each synced to a different remote GPU:

### Architecture

```
Local (git worktrees)                    Remotes (Coder workspaces)
─────────────────────                    ─────────────────────────
~/work/modular/                    ───►  b200-hydra.coder
  (branch: main)                         ~/work/modular

~/work/modular-feature-x/          ───►  gcore-h100.coder
  (branch: feature-x)                    ~/work/modular
```

### Setup Steps

**1. Create local git worktree:**
```bash
cd ~/work/modular
git worktree add ../modular-feature-x feature-x
```

**2. Create mutagen.yml in the worktree** with the new remote:
```yaml
sync:
  modular:
    alpha: "/Users/bduke/work/modular-feature-x"
    beta: "gcore-h100.coder:/home/ubuntu/work/modular"
```

**3. Update rexec worktree mappings** in `~/.local/bin/rexec`:
```python
WORKTREE_MAPPINGS = {
    Path.home() / "work" / "modular": "b200-hydra.coder",
    Path.home() / "work" / "modular-feature-x": "gcore-h100.coder",
}
```

**4. Work in any worktree:**
```bash
cd ~/work/modular-feature-x
r ./bazelw build //path:target  # Auto-routes to gcore-h100.coder
```

## Key Design Decisions

1. **Declarative config**: `mutagen.yml` in repo root makes setup reproducible

2. **SSH multiplexing in ~/.ssh/config**: Faster repeated commands, not managed by rexec

3. **Header to stderr**: `rexec` output is pipeline-safe (`rexec -q cmd | grep foo`)

4. **r wrapper**: One obvious command in PATH for "run this remotely"

5. **one-way-replica**: Local is authoritative. Prevents remote build artifacts from syncing back.

6. **posix-raw symlinks**: Both macOS and Linux are POSIX. Default "portable" mode breaks some symlinks.

7. **Ignore build outputs**: Bazel outputs can be 10-50GB. Syncing them defeats the purpose.
