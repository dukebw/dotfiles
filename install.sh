#!/bin/bash
set -e

DOTFILES_DIR="$HOME/dotfiles"

echo "🚀 Starting macOS setup..."

# ------------------------------------------------------------------------------
# Homebrew
# ------------------------------------------------------------------------------
if ! command -v brew &> /dev/null; then
    echo "==> Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
else
    echo "==> Homebrew already installed"
fi

# ------------------------------------------------------------------------------
# Homebrew packages
# ------------------------------------------------------------------------------
echo "==> Installing Homebrew packages..."
brew bundle install --file="$DOTFILES_DIR/Brewfile"

# ------------------------------------------------------------------------------
# oh-my-zsh
# ------------------------------------------------------------------------------
if [ ! -d "$HOME/.oh-my-zsh" ]; then
    echo "==> Installing oh-my-zsh..."
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
else
    echo "==> oh-my-zsh already installed"
fi

# ------------------------------------------------------------------------------
# Symlinks
# ------------------------------------------------------------------------------
echo "==> Creating symlinks..."

# Backup existing files if they exist and aren't symlinks
backup_and_link() {
    local src="$1"
    local dst="$2"
    if [ -e "$dst" ] && [ ! -L "$dst" ]; then
        echo "    Backing up $dst to $dst.backup"
        mv "$dst" "$dst.backup"
    fi
    ln -sf "$src" "$dst"
    echo "    Linked $dst -> $src"
}

backup_and_link "$DOTFILES_DIR/zsh/.zshrc" "$HOME/.zshrc"
backup_and_link "$DOTFILES_DIR/git/.gitconfig" "$HOME/.gitconfig"

mkdir -p "$HOME/.config/zellij"
backup_and_link "$DOTFILES_DIR/zellij/config.kdl" "$HOME/.config/zellij/config.kdl"

mkdir -p "$HOME/.local/bin"
backup_and_link "$DOTFILES_DIR/bin/r" "$HOME/.local/bin/r"
backup_and_link "$DOTFILES_DIR/bin/rlog" "$HOME/.local/bin/rlog"
backup_and_link "$DOTFILES_DIR/bin/b10-gpu" "$HOME/.local/bin/b10-gpu"
backup_and_link "$DOTFILES_DIR/bin/gpu-fleet" "$HOME/.local/bin/gpu-fleet"
backup_and_link "$DOTFILES_DIR/bin/setup-b200-shared-sync" "$HOME/.local/bin/setup-b200-shared-sync"
backup_and_link "$DOTFILES_DIR/bin/remote-clangd" "$HOME/.local/bin/remote-clangd"
backup_and_link "$DOTFILES_DIR/bin/check-remote-clangd-nvim" "$HOME/.local/bin/check-remote-clangd-nvim"
backup_and_link "$DOTFILES_DIR/.local/bin/pydebug-setup" "$HOME/.local/bin/pydebug-setup"
backup_and_link "$DOTFILES_DIR/bin/rexec" "$HOME/.local/bin/rexec"
backup_and_link "$DOTFILES_DIR/bin/opencode" "$HOME/.local/bin/opencode"
backup_and_link "$DOTFILES_DIR/bin/opencode-mcp-remote" "$HOME/.local/bin/opencode-mcp-remote"
backup_and_link "$DOTFILES_DIR/bin/opencode-update" "$HOME/.local/bin/opencode-update"
backup_and_link "$DOTFILES_DIR/bin/opencode-web-server" "$HOME/.local/bin/opencode-web-server"
backup_and_link "$DOTFILES_DIR/bin/gh-stack-upstream-sync" "$HOME/.local/bin/gh-stack-upstream-sync"
backup_and_link "$DOTFILES_DIR/bin/here-now-publish" "$HOME/.local/bin/here-now-publish"
backup_and_link "$DOTFILES_DIR/bin/zellij-focus-pane" "$HOME/.local/bin/zellij-focus-pane"
backup_and_link "$DOTFILES_DIR/bin/claude-code-notify" "$HOME/.local/bin/claude-code-notify"
backup_and_link "$DOTFILES_DIR/bin/zellij-pane-is-focused" "$HOME/.local/bin/zellij-pane-is-focused"
backup_and_link "$DOTFILES_DIR/bin/klf-pretty" "$HOME/.local/bin/klf-pretty"

mkdir -p "$HOME/Library/LaunchAgents"
backup_and_link "$DOTFILES_DIR/launchd/ai.opencode.web.plist" "$HOME/Library/LaunchAgents/ai.opencode.web.plist"
backup_and_link "$DOTFILES_DIR/launchd/ai.opencode.update.plist" "$HOME/Library/LaunchAgents/ai.opencode.update.plist"
backup_and_link "$DOTFILES_DIR/launchd/ai.gh-stack.upstream-sync.plist" "$HOME/Library/LaunchAgents/ai.gh-stack.upstream-sync.plist"

mkdir -p "$HOME/.config/opencode"
backup_and_link "$DOTFILES_DIR/opencode/AGENTS.md" "$HOME/.config/opencode/AGENTS.md"
backup_and_link "$DOTFILES_DIR/opencode/opencode.json" "$HOME/.config/opencode/opencode.json"
backup_and_link "$DOTFILES_DIR/opencode/commands" "$HOME/.config/opencode/commands"
backup_and_link "$DOTFILES_DIR/opencode/plugins" "$HOME/.config/opencode/plugins"
backup_and_link "$DOTFILES_DIR/opencode/scripts" "$HOME/.config/opencode/scripts"
backup_and_link "$DOTFILES_DIR/opencode/cli.json" "$HOME/.config/opencode/cli.json"

mkdir -p "$HOME/.claude"
backup_and_link "$DOTFILES_DIR/claude/settings.json" "$HOME/.claude/settings.json"

mkdir -p "$HOME/.claude/skills"
for skill_dir in "$DOTFILES_DIR/.claude/skills"/*; do
    if [ -d "$skill_dir" ]; then
        skill_name=$(basename "$skill_dir")
        backup_and_link "$skill_dir" "$HOME/.claude/skills/$skill_name"
    fi
done

# ------------------------------------------------------------------------------
# SSH config (append X11 forwarding if not present)
# ------------------------------------------------------------------------------
echo "==> Configuring SSH..."
mkdir -p "$HOME/.ssh"
if ! grep -q "ForwardX11" "$HOME/.ssh/config" 2>/dev/null; then
    cat "$DOTFILES_DIR/ssh/config.template" >> "$HOME/.ssh/config"
    echo "    Added X11 forwarding to SSH config"
else
    echo "    X11 forwarding already in SSH config"
fi

# ------------------------------------------------------------------------------
# Neovim config
# ------------------------------------------------------------------------------
if [ ! -d "$HOME/.config/nvim" ]; then
    echo "==> Cloning Neovim config..."
    git clone git@github.com:dukebw/kickstart.nvim.git "$HOME/.config/nvim"
else
    echo "==> Neovim config already exists"
fi

# ------------------------------------------------------------------------------
# Rust
# ------------------------------------------------------------------------------
if ! command -v cargo &> /dev/null; then
    echo "==> Installing Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
else
    echo "==> Rust already installed"
fi

echo "==> Installing cargo tools..."
source "$HOME/.cargo/env"
cargo install tokei tree-sitter-cli 2>/dev/null || true

# ------------------------------------------------------------------------------
# pyenv + Python
# ------------------------------------------------------------------------------
if [ ! -d "$HOME/.pyenv" ]; then
    echo "==> Installing pyenv..."
    curl https://pyenv.run | bash
else
    echo "==> pyenv already installed"
fi

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)" 2>/dev/null || true

if ! pyenv versions | grep -q "3.12"; then
    echo "==> Installing Python 3.12..."
    pyenv install 3.12
    pyenv global 3.12
else
    echo "==> Python 3.12 already installed"
fi

echo "==> Installing Python packages..."
pip install --upgrade pip debugpy pynvim 2>/dev/null || true

# ------------------------------------------------------------------------------
# nvm + Node
# ------------------------------------------------------------------------------
if [ ! -d "$HOME/.nvm" ]; then
    echo "==> Installing nvm..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

if ! command -v node &> /dev/null; then
    echo "==> Installing Node.js..."
    nvm install node
else
    echo "==> Node.js already installed"
fi

# ------------------------------------------------------------------------------
# pnpm
# ------------------------------------------------------------------------------
if ! command -v pnpm &> /dev/null; then
    echo "==> Installing pnpm..."
    curl -fsSL https://get.pnpm.io/install.sh | sh -
else
    echo "==> pnpm already installed"
fi

# ------------------------------------------------------------------------------
# git-lfs
# ------------------------------------------------------------------------------
echo "==> Configuring git-lfs..."
git lfs install

# ------------------------------------------------------------------------------
# Done!
# ------------------------------------------------------------------------------
echo ""
echo "✅ Setup complete!"
echo ""
echo "Manual steps remaining:"
echo "  1. Copy SSH keys from another machine (AirDrop recommended)"
echo "  2. Create .rexec.yaml in a worktree or ~/.config/rexec/config.yaml"
echo "  3. Run: rexec --setup"
echo "  4. iTerm2 -> Settings -> Profiles -> Text -> Font: 'Hack Nerd Font Mono'"
echo "  5. iTerm2 -> Settings -> Profiles -> Window -> Style: 'No Title Bar'"
echo "  6. System Settings -> Keyboard -> Shortcuts -> Mission Control:"
echo "     Set Ctrl+1/2/3/etc for 'Switch to Desktop 1/2/3/etc'"
echo "  7. Open a new terminal or run: source ~/.zshrc"
echo "  8. System Settings -> Notifications -> terminal-notifier:"
echo "     allow notifications, style 'Alerts' (stays on screen; used by"
echo "     opencode/Claude Code turn-finished notifications)"
echo "  9. Follow .claude/skills/opencode-remote/SKILL.md to provision the"
echo "     native service, LaunchAgent, and private Tailscale Serve mapping"
echo ""
echo "To set git identity (if not in .gitconfig):"
echo "  git config --global user.name 'Your Name'"
echo "  git config --global user.email 'your@email.com'"
