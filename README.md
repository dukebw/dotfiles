# dotfiles

My macOS development environment configuration.

## Quick Start

```bash
# Clone the repo
git clone git@github.com:dukebw/dotfiles.git ~/dotfiles

# Run the installer
cd ~/dotfiles && ./install.sh
```

## What's Included

### CLI Tools (via Homebrew)
- fd, ripgrep, fzf - fast search tools
- neovim - editor
- zellij - terminal multiplexer
- git-delta - beautiful git diffs
- tmux, pyenv, and more

### GUI Apps
- Amethyst - tiling window manager
- Discord, Slack, Linear
- XQuartz - X11 for SSH clipboard
- Hack Nerd Font Mono

### Development Environment
- oh-my-zsh with vi-mode
- pyenv + Python 3.12
- nvm + Node.js
- pnpm
- Rust + cargo tools (tokei, tree-sitter-cli)
- Kubernetes pod remote execution with Mutagen sync

### Config Files
- `zsh/.zshrc` - shell configuration
- `git/.gitconfig` - git with delta integration
- `zellij/config.kdl` - zellij terminal multiplexer
- `opencode/opencode.json` - OpenCode config
- `ssh/config.template` - X11 forwarding for Coder

### Remote Helpers
- `bin/rexec` - run commands in a configured Kubernetes GPU dev pod over an SSH shim
- `bin/r` - flush local changes with Mutagen, run remote command, and capture local logs
- `bin/rlog` - run remote command and mirror logs from `/home/ubuntu/shared/logs`
- `bin/b10-gpu` - inspect Vultr B200 dev nodes, map GPU owners, and move the configured `rexec` pod
- `bin/setup-b200-shared-sync` - setup Mutagen one-way sync from remote shared dir

## Kubernetes Pod Remote Execution

The main remote loop is local editing plus remote execution in a GPU dev pod:

```text
Local editor/Git/kubeconfig
  |
  | Mutagen one-way sync over SSH
  v
Kubernetes GPU pod workdir
  |
  | command runs through ssh -> kubectl port-forward -> pod sshd
  v
stdout/stderr mirrored to local logs
```

Quick commands:

```bash
rexec --setup       # install/start pod SSH shim and Mutagen session
r nvidia-smi        # sync then run in the pod
rexec --tty bash    # interactive shell in the remote workdir
```

Config is local-only because it is machine- and pod-specific. `rexec` uses
`--config`, then `REXEC_CONFIG`, then the nearest `.rexec.yaml`, then
`~/.config/rexec/config.yaml`. See [`docs/rexec-kubernetes-pod.md`](docs/rexec-kubernetes-pod.md)
for architecture diagrams, setup, security model, config shape, and troubleshooting.

## Baseten GPU Dev Helpers

`b10-gpu` wraps the common Vultr B200 dev-node operations:

```bash
b10-gpu nodes
b10-gpu status --all
b10-gpu status f307cc291a7c
b10-gpu pods f307cc291a7c
b10-gpu owner f307cc291a7c
b10-gpu move f307cc291a7c --dry-run
```

By default it reads the kubeconfig, namespace, and pod from
`~/.config/rexec/config.yaml`. See [`docs/b10-gpu.md`](docs/b10-gpu.md) for
command details and smoke tests.

## Remote Log Sync

One-time setup:

```bash
setup-b200-shared-sync
```

Run remote commands with auto-mirrored logs:

```bash
rlog --label deepseek -- ./bazelw run --config=disable-lint //max/tests/integration/tools:generate_llm_logits -- \
  --framework max --pipeline deepseek-ai/DeepSeek-R1 --device gpu:0,1,2,3,4,5,6,7 \
  --encoding float8_e4m3fn --output /home/ubuntu/shared/logs/deepseek/output.json
```

Logs appear locally under `~/shared/b200-hydra/logs/<label>/<run-id>/`.

## Manual Steps After Install

1. Copy SSH keys from another machine
2. Create `.rexec.yaml` in each synced worktree or `~/.config/rexec/config.yaml`
3. Run `rexec --setup` from the local repo you want synced
4. iTerm2: Set font to "Hack Nerd Font Mono", style "No Title Bar"
5. System Settings -> Keyboard -> Shortcuts: Set Ctrl+N for Desktop N

## Neovim

Neovim config is managed separately at [dukebw/kickstart.nvim](https://github.com/dukebw/kickstart.nvim).
