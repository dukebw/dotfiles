---
name: mutagen-remote-workflow
description: Set up local editing + remote build workflow using Mutagen file sync with Coder workspaces. Use when the user wants to edit code locally in neovim while running builds/tests on a remote GPU server.
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

Create `~/.local/bin/<helper-name>`:

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
    echo "Usage: <helper-name> <command>"
    echo "Runs command on <workspace>.coder in ~/work/<repo>"
    exit 1
fi

ssh -tt <workspace>.coder "cd /home/ubuntu/work/<repo> && $*"
```

```bash
chmod +x ~/.local/bin/<helper-name>
```

Usage:
```bash
<helper-name> ./bazelw build //path:target
<helper-name> ./bazelw test //...
<helper-name> python3 script.py
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

## Key Design Decisions

1. **one-way-replica**: Local is authoritative. Prevents remote build artifacts from syncing back.

2. **posix-raw symlinks**: Both macOS and Linux are POSIX. Default "portable" mode breaks some symlinks.

3. **Ignore .git**: Each side manages its own git state independently.

4. **Ignore build outputs**: Bazel outputs can be 10-50GB. Syncing them defeats the purpose.
