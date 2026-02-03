---
name: mutagen-remote-workflow
description: Set up local editing + remote build workflow using Mutagen file sync with Coder workspaces. Includes the `hydra` helper script for running commands on remote machines. Use when the user mentions hydra, mutagen, remote builds, Coder workspaces, or syncing files to a remote GPU server.
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

### 2. Align Git State

Before creating Mutagen session, ensure both sides are on the same commit:

```bash
# Check local
cd ~/work/<repo>
git status && git log -1 --oneline

# Check remote
ssh <workspace>.coder "cd ~/work/<repo> && git status && git log -1 --oneline"
```

If they differ:
- Commit/push remote changes first
- Then `git fetch && git reset --hard origin/<branch>` locally

### 3. Create Mutagen Sync Session

**Key flags explained:**
- `--sync-mode=one-way-replica`: Local is source of truth, remote mirrors it
- `--symlink-mode=posix-raw`: Preserves symlinks between macOS ↔ Linux
- `--ignore`: Exclude build artifacts to avoid syncing gigabytes of churn

```bash
mutagen sync create \
  --name=<session-name> \
  --sync-mode=one-way-replica \
  --symlink-mode=posix-raw \
  --default-file-mode=0644 \
  --default-directory-mode=0755 \
  --ignore="/.derived" \
  --ignore="/bazel-*" \
  --ignore="**/__pycache__" \
  --ignore="**/.pytest_cache" \
  --ignore="**/.mypy_cache" \
  --ignore="/external" \
  --ignore="**/*.pyc" \
  --ignore="/.git" \
  --ignore="**/.venv" \
  --ignore="**/*.venv" \
  ~/work/<repo> \
  <workspace>.coder:/home/ubuntu/work/<repo>
```

**Common ignores for Bazel repos:**
| Pattern | Purpose |
|---------|---------|
| `/.derived` | Bazel build outputs |
| `/bazel-*` | Bazel symlinks (bazel-bin, bazel-out, etc.) |
| `/external` | Bazel external dependencies |
| `**/__pycache__` | Python bytecode |
| `**/*.venv` | Python venvs (including `.foo+bar.venv` patterns) |
| `/.git` | Git dir (each side manages its own) |

### 4. Verify Sync

```bash
mutagen sync list                           # List all sessions
mutagen sync monitor <session-name>         # Real-time monitoring
mutagen sync list --long <session-name>     # Check for conflicts
```

Healthy state shows: `Status: Watching for changes`

### 5. Handle Conflicts

Conflicts occur when remote has files not on local (typically build artifacts):

```bash
# Option 1: Reset (rescans both sides)
mutagen sync reset <session-name>

# Option 2: Clean remote manually, then flush
ssh <workspace>.coder "rm -rf /path/to/conflict"
mutagen sync flush <session-name>

# Clean all __pycache__ on remote
ssh <workspace>.coder "find ~/work/<repo> -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null"
```

### 6. Create Remote Command Helper

Create `~/.local/bin/hydra` (or your preferred name):

```bash
#!/usr/bin/env bash
set -euo pipefail

# Smart helper script to run commands on remote Coder workspaces
# Auto-detects which worktree you're in and routes to the mapped remote
#
# Usage: hydra [--remote <host>] <command>

# Default remote if no mapping found
DEFAULT_REMOTE="b200-hydra.coder"

# Remote working directory
REMOTE_WORKDIR="/home/ubuntu/work/modular"

# Worktree → Remote mapping function
# Edit this function to add new worktree mappings
get_remote_for_worktree() {
    local worktree="$1"
    case "$worktree" in
        "$HOME/work/modular")
            echo "b200-hydra.coder"
            ;;
        # Add more mappings as needed:
        # "$HOME/work/modular-feature-x")
        #     echo "gcore-h100.coder"
        #     ;;
        *)
            echo ""
            ;;
    esac
}

show_help() {
    echo "Usage: hydra [--remote <host>] <command>"
    echo ""
    echo "Options:"
    echo "  --remote <host>  Specify remote host (e.g., gcore-h100.coder)"
    echo "  --list           List worktree → remote mappings"
    echo "  --help           Show this help"
}

detect_remote() {
    local cwd="$PWD"
    while [[ "$cwd" != "/" ]]; do
        local remote
        remote="$(get_remote_for_worktree "$cwd")"
        if [[ -n "$remote" ]]; then
            echo "$remote"
            return 0
        fi
        cwd="$(dirname "$cwd")"
    done
    echo "$DEFAULT_REMOTE"
}

# Parse arguments
REMOTE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --remote)
            REMOTE="$2"
            [[ "$REMOTE" != *.coder ]] && REMOTE="${REMOTE}.coder"
            shift 2
            ;;
        --list|--help|-h)
            show_help
            exit 0
            ;;
        *)
            break
            ;;
    esac
done

if [[ $# -eq 0 ]]; then
    show_help
    exit 1
fi

# Auto-detect remote if not specified
if [[ -z "$REMOTE" ]]; then
    REMOTE="$(detect_remote)"
    echo "→ Detected remote: $REMOTE" >&2
fi

ssh -tt "$REMOTE" "cd $REMOTE_WORKDIR && $*"
```

```bash
chmod +x ~/.local/bin/hydra
```

**Usage:**
```bash
# Auto-detect remote from current worktree
hydra ./bazelw build //path:target
→ Detected remote: b200-hydra.coder

# Explicit remote override
hydra --remote gcore-h100 ./bazelw test //...

# List configured mappings
hydra --list
```

### 7. Create Zellij Layout (Optional)

Create `~/.config/zellij/layouts/<layout-name>.kdl`:

```kdl
layout {
  tab name="edit" cwd="/Users/<user>/work/<repo>" {
    pane split_direction="vertical" {
      pane size="70%" command="nvim"
      pane split_direction="horizontal" {
        pane name="agent" command="<ai-agent>"
        pane name="mutagen" command="mutagen" {
          args "sync" "monitor" "<session-name>"
        }
      }
    }
  }

  tab name="remote" hide_floating_panes=true {
    pane split_direction="vertical" {
      pane size="40%" name="agent-remote" command="<ai-agent>"
      pane split_direction="horizontal" {
        pane name="shell-1" command="ssh" {
          args "-tt" "<workspace>.coder" "cd /home/ubuntu/work/<repo> && exec bash -l"
        }
        pane name="shell-2" command="ssh" {
          args "-tt" "<workspace>.coder" "cd /home/ubuntu/work/<repo> && exec bash -l"
        }
      }
    }

    floating_panes {
      pane name="nvitop" command="ssh" {
        args "-tt" "<workspace>.coder" "python3 -m nvitop"
        x "10%"
        y "10%"
        width "80%"
        height "80%"
      }
    }
  }
}
```

Launch: `zellij --layout <layout-name>`

Toggle floating nvitop: `Alt+f`

## Daily Commands Reference

### Mutagen

```bash
mutagen sync list                    # Show all sessions
mutagen sync monitor <name>          # Real-time status
mutagen sync pause <name>            # Pause before large git ops
mutagen sync resume <name>           # Resume after workspace restart
mutagen sync flush <name>            # Force immediate sync
mutagen sync terminate <name>        # Stop session (keeps files)
```

### Zellij

- `Ctrl+a 1/2/...` - Switch tabs
- `Alt+f` - Toggle floating panes
- `Ctrl+a d` - Detach session

## Troubleshooting

### "Scanning files" takes forever
Large repos (10-50GB) take several minutes on first scan. This is normal.

### Workspace auto-stopped
After Coder workspace restarts:
```bash
mutagen sync resume <session-name>
```

### Need to change ignores
Must recreate the session:
```bash
mutagen sync terminate <session-name>
# Run create command again with new --ignore flags
```

### Permission issues
Session was created with `--default-file-mode=0644 --default-directory-mode=0755`. To change, recreate session.

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

~/work/modular-experiment/         ───►  gcore-h100-2.coder
  (branch: experiment)                   ~/work/modular
```

### Setup Steps

**1. Create local git worktrees:**
```bash
cd ~/work/modular
git worktree add ../modular-feature-x feature-x
git worktree add ../modular-experiment experiment
```

**2. Create Mutagen session for each worktree:**
```bash
# Session for gcore-h100
mutagen sync create \
  --name=modular-gcore \
  --sync-mode=one-way-replica \
  --symlink-mode=posix-raw \
  --default-file-mode=0644 \
  --default-directory-mode=0755 \
  --ignore="/.derived" --ignore="/bazel-*" --ignore="**/__pycache__" \
  --ignore="**/.venv" --ignore="**/*.venv" --ignore="/.git" \
  ~/work/modular-feature-x \
  gcore-h100.coder:/home/ubuntu/work/modular
```

**3. Add mapping to hydra script:**

Edit `~/.local/bin/hydra` and add to `get_remote_for_worktree()`:
```bash
"$HOME/work/modular-feature-x")
    echo "gcore-h100.coder"
    ;;
```

**4. Work in any worktree:**
```bash
cd ~/work/modular-feature-x
hydra ./bazelw build //path:target
→ Detected remote: gcore-h100.coder
```

### Managing Multiple Sessions

```bash
# List all sync sessions
mutagen sync list

# Pause all before large git operations
mutagen sync pause modular-hydra
mutagen sync pause modular-gcore

# Resume after workspace restarts
mutagen sync resume modular-hydra
```

## Python Debug Setup

For debugging Python Bazel targets with nvim-dap, use the `pydebug-setup` script:

```bash
# Interactive target selection with fzf
pydebug-setup

# Direct target
pydebug-setup //max/python/max/entrypoints:pipelines

# Refresh target cache
pydebug-setup -r

# Dry run (show commands without executing)
pydebug-setup -n

# Run locally instead of via hydra
pydebug-setup -l //path:target
```

This script:
1. Uses fzf to select a Bazel py_binary/py_test target
2. Runs `./bazelw run //target.venv` via hydra to create the venv
3. Installs debugpy into the venv

After setup, use nvim-dap with `<leader>ec` to start debugging.

## Key Design Decisions

1. **one-way-replica**: Local is authoritative. Prevents remote build artifacts from syncing back.

2. **posix-raw symlinks**: Both macOS and Linux are POSIX. Default "portable" mode breaks some symlinks.

3. **Ignore .git**: Each side manages its own git state independently.

4. **Ignore build outputs**: Bazel outputs can be 10-50GB. Syncing them defeats the purpose.

5. **Worktree-per-remote**: Each git worktree maps to one remote workspace, enabling parallel work on different branches with different GPU types.
