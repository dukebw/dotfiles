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

mkdir -p "$HOME/.config/opencode"
backup_and_link "$DOTFILES_DIR/opencode/opencode.json" "$HOME/.config/opencode/opencode.json"

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
echo "  2. Run: coder login https://rde.modular.com && coder config-ssh"
echo "  3. iTerm2 → Settings → Profiles → Text → Font: 'Hack Nerd Font Mono'"
echo "  4. iTerm2 → Settings → Profiles → Window → Style: 'No Title Bar'"
echo "  5. System Settings → Keyboard → Shortcuts → Mission Control:"
echo "     Set Ctrl+1/2/3/etc for 'Switch to Desktop 1/2/3/etc'"
echo "  6. Open a new terminal or run: source ~/.zshrc"
echo ""
echo "To set git identity (if not in .gitconfig):"
echo "  git config --global user.name 'Your Name'"
echo "  git config --global user.email 'your@email.com'"
