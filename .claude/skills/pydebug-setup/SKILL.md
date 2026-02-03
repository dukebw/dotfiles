---
name: pydebug-setup
description: Set up Python debugging for Bazel targets. Use when the user mentions pydebug-setup, debugpy, Python debugging, nvim-dap, or setting up a debug venv for Bazel Python targets.
---

# Python Debug Setup for Bazel Targets

The `pydebug-setup` script automates setting up Python debugging environments for Bazel targets.

## Location

`~/.local/bin/pydebug-setup`

## Usage

```bash
# Interactive target selection with fzf
pydebug-setup

# Direct target (skip fzf)
pydebug-setup //max/python/max/entrypoints:pipelines

# Refresh target cache before selecting
pydebug-setup -r

# Dry run (show commands without executing)
pydebug-setup -n

# Run locally instead of via hydra (remote)
pydebug-setup -l //path:target
```

## What It Does

1. **Queries Bazel** for all `py_binary` and `py_test` targets
2. **Caches results** in `~/.cache/pydebug-setup/targets.txt` (1 hour TTL)
3. **Uses fzf** for interactive fuzzy selection with color-coded prefixes:
   - `[bin]` (green) - py_binary targets
   - `[test]` (yellow) - py_test targets
4. **Creates venv** by running `./bazelw run //target.venv` via hydra
5. **Installs debugpy** into the venv

## Integration with nvim-dap

After running `pydebug-setup`, the venv at `.venv` will have debugpy installed. The nvim-dap configuration in `~/.config/nvim/lua/kickstart/plugins/debug.lua` automatically detects the remote venv and configures Python debugging.

### Debug Keybindings

| Key | Action |
|-----|--------|
| `<leader>ec` | Start/Continue debugging |
| `<leader>eb` | Toggle breakpoint |
| `<leader>eB` | Set conditional breakpoint |
| `<leader>es` | Step into |
| `<leader>en` | Step over (next) |
| `<leader>eS` | Step out |
| `<leader>et` | Terminate |
| `<leader>eg` | Toggle DAP UI |

## Example Workflow

```bash
# 1. Set up debug environment (from ~/work/modular)
cd ~/work/modular
pydebug-setup //max/python/max/entrypoints:pipelines

# 2. Start remote-nvim session
# In nvim: <leader>rs to connect to remote

# 3. Open Python file and set breakpoints
# <leader>eb on lines you want to debug

# 4. Start debugging
# <leader>ec to launch debugger
```

## Dependencies

- `fzf` - for interactive selection
- `hydra` - for running commands on remote (see mutagen-remote-workflow skill)
- `bazel` / `bazelw` - for querying targets and creating venvs
