# If you come from bash you might have to change your $PATH.
# export PATH=$HOME/bin:$HOME/.local/bin:/usr/local/bin:$PATH

# Path to your Oh My Zsh installation.
export ZSH="$HOME/.oh-my-zsh"

# Set name of the theme to load --- if set to "random", it will
# load a random theme each time Oh My Zsh is loaded, in which case,
# to know which specific one was loaded, run: echo $RANDOM_THEME
# See https://github.com/ohmyzsh/ohmyzsh/wiki/Themes
ZSH_THEME="robbyrussell"

# Set list of themes to pick from when loading at random
# Setting this variable when ZSH_THEME=random will cause zsh to load
# a theme from this variable instead of looking in $ZSH/themes/
# If set to an empty array, this variable will have no effect.
# ZSH_THEME_RANDOM_CANDIDATES=( "robbyrussell" "agnoster" )

# Uncomment the following line to use case-sensitive completion.
# CASE_SENSITIVE="true"

# Uncomment the following line to use hyphen-insensitive completion.
# Case-sensitive completion must be off. _ and - will be interchangeable.
# HYPHEN_INSENSITIVE="true"

# Uncomment one of the following lines to change the auto-update behavior
# zstyle ':omz:update' mode disabled  # disable automatic updates
# zstyle ':omz:update' mode auto      # update automatically without asking
# zstyle ':omz:update' mode reminder  # just remind me to update when it's time

# Uncomment the following line to change how often to auto-update (in days).
# zstyle ':omz:update' frequency 13

# Uncomment the following line if pasting URLs and other text is messed up.
# DISABLE_MAGIC_FUNCTIONS="true"

# Uncomment the following line to disable colors in ls.
# DISABLE_LS_COLORS="true"

# Uncomment the following line to disable auto-setting terminal title.
# DISABLE_AUTO_TITLE="true"

# Uncomment the following line to enable command auto-correction.
# ENABLE_CORRECTION="true"

# Uncomment the following line to display red dots whilst waiting for completion.
# You can also set it to another string to have that shown instead of the default red dots.
# e.g. COMPLETION_WAITING_DOTS="%F{yellow}waiting...%f"
# Caution: this setting can cause issues with multiline prompts in zsh < 5.7.1 (see #5765)
# COMPLETION_WAITING_DOTS="true"

# Uncomment the following line if you want to disable marking untracked files
# under VCS as dirty. This makes repository status check for large repositories
# much, much faster.
# DISABLE_UNTRACKED_FILES_DIRTY="true"

# Uncomment the following line if you want to change the command execution time
# stamp shown in the history command output.
# You can set one of the optional three formats:
# "mm/dd/yyyy"|"dd.mm.yyyy"|"yyyy-mm-dd"
# or set a custom format using the strftime function format specifications,
# see 'man strftime' for details.
# HIST_STAMPS="mm/dd/yyyy"

# Would you like to use another custom folder than $ZSH/custom?
# ZSH_CUSTOM=/path/to/new-custom-folder

# Which plugins would you like to load?
# Standard plugins can be found in $ZSH/plugins/
# Custom plugins may be added to $ZSH_CUSTOM/plugins/
# Example format: plugins=(rails git textmate ruby lighthouse)
# Add wisely, as too many plugins slow down shell startup.
plugins=(git vi-mode)

source $ZSH/oh-my-zsh.sh

# User configuration

# export MANPATH="/usr/local/man:$MANPATH"

# You may need to manually set your language environment
# export LANG=en_US.UTF-8

# Preferred editor for local and remote sessions
# if [[ -n $SSH_CONNECTION ]]; then
#   export EDITOR='vim'
# else
#   export EDITOR='nvim'
# fi

# Compilation flags
# export ARCHFLAGS="-arch $(uname -m)"

# Set personal aliases, overriding those provided by Oh My Zsh libs,
# plugins, and themes. Aliases can be placed here, though Oh My Zsh
# users are encouraged to define aliases within a top-level file in
# the $ZSH_CUSTOM folder, with .zsh extension. Examples:
# - $ZSH_CUSTOM/aliases.zsh
# - $ZSH_CUSTOM/macos.zsh
# For a full list of active aliases, run `alias`.
#
# Example aliases
# alias zshconfig="mate ~/.zshrc"
# alias ohmyzsh="mate ~/.oh-my-zsh"
alias k=kubectl
alias klf-raw='kubectl logs --follow --all-pods=true --all-containers=true --prefix'
# Stern owns pod discovery and resilient streams; klf-pretty owns rendering.
klf() {
  stern --only-log-lines --color=never --timestamps=default --timezone=UTC \
    --template '{{printf "[pod/%s/%s] %s\n" .PodName .ContainerName .Message}}' \
    "$@" | klf-pretty
}
alias gc!='git -c core.commentChar=";" commit --verbose --amend'
claude-remote() {
  caffeinate -i /Users/brendanduke/.local/bin/claude "$@" --remote-control "Baseten Remote"
}

lidawake() {
  if [[ "$(pmset -g | awk '/SleepDisabled/ { print $2 }')" == 1 ]]; then
    sudo pmset -a disablesleep 0
    echo "Closed-lid wake disabled"
  else
    sudo pmset -a disablesleep 1
    echo "Closed-lid wake enabled"
  fi
}

# Homebrew
eval "$(/opt/homebrew/bin/brew shellenv)"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
if command -v nvm >/dev/null 2>&1; then
  path=("${(@)path:#$NVM_DIR/versions/node/*/bin}")
  nvm use --silent default >/dev/null
fi

# pnpm
export PNPM_HOME="$HOME/Library/pnpm"
case ":$PATH:" in
  *":$PNPM_HOME/bin:"*) ;;
  *) export PATH="$PNPM_HOME/bin:$PATH" ;;
esac
# pnpm end

# pyenv
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# Rust/Cargo
. "$HOME/.cargo/env"

# fzf
if [[ -o interactive && -o zle ]]; then
  source <(fzf --zsh) 2>/dev/null
fi

# Editor
export EDITOR=nvim

# fd alias (hidden files)
alias fdh="fd --hidden --no-ignore"
export PATH="$HOME/.local/bin:$PATH"

# Remote log runner wrapper.
r() {
  "$HOME/.local/bin/r" "$@"
}

rlog() {
  "$HOME/.local/bin/rlog" "$@"
}

oc() {
  local opencode_server_password

  opencode_server_password=$(
    /usr/bin/security find-generic-password \
      -a "opencode-server" \
      -s "ai.opencode.web" \
      -w
  ) || return 1

  # OpenCode 2 mounts every route under /api; a bare origin makes the TUI
  # request /session/... and 404.
  OPENCODE_SERVER_PASSWORD="$opencode_server_password" \
    command opencode \
      --server http://127.0.0.1:4096/api \
      "$@" \
      "$PWD"
}

# Stamp `opencode run` sessions with a "[run]" title marker so the notify
# plugin suppresses their turn-end notifications (run is headless). Only
# interactive TUI sessions should notify. `oc` uses `command opencode`, so it
# bypasses this wrapper.
opencode() {
  if [[ "$1" != run ]]; then
    command opencode "$@"
    return
  fi
  shift
  local -a args=()
  local titled=false
  while (( $# )); do
    case "$1" in
      -h|--help|--wizard)
        command opencode run "$@"
        return
        ;;
      --title=*)
        args+=("--title=[run] ${${1#--title=}#\[run\] }")
        titled=true
        ;;
      --title)
        args+=("--title" "[run] ${${2:-}#\[run\] }")
        shift
        titled=true
        ;;
      *)
        args+=("$1")
        ;;
    esac
    shift
  done
  if ! $titled; then
    local label="${args[-1]:-}"
    [[ "$label" == -* ]] && label=""
    args=(--title "[run] ${label:0:40}" "${args[@]}")
  fi
  command opencode run "${args[@]}"
}
