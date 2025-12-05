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
- Coder CLI for remote development

### Config Files
- `zsh/.zshrc` - shell configuration
- `git/.gitconfig` - git with delta integration
- `zellij/config.kdl` - zellij terminal multiplexer
- `ssh/config.template` - X11 forwarding for Coder

## Manual Steps After Install

1. Copy SSH keys from another machine
2. `coder login https://rde.modular.com && coder config-ssh`
3. iTerm2: Set font to "Hack Nerd Font Mono", style "No Title Bar"
4. System Settings → Keyboard → Shortcuts: Set Ctrl+N for Desktop N

## Neovim

Neovim config is managed separately at [dukebw/kickstart.nvim](https://github.com/dukebw/kickstart.nvim).
