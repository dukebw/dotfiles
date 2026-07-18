#!/bin/bash
# Post the opencode turn-finished notification, unless the zellij pane showing
# the session is already in view (focused pane + iTerm2 frontmost). Invoked by
# the notify plugin running in the opencode server, so changes here take
# effect without a server restart.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

session_id="${1:?usage: opencode-notify.sh <session_id> [session_title]}"
session_title="${2:-opencode session}"

script_dir=$(cd "$(dirname "$0")" && pwd)
resolved=$("$script_dir/opencode-resolve-pane.sh" "$session_id" "$session_title" || true)
if [ -n "$resolved" ]; then
  read -r zellij_session pane_id <<<"$resolved"
  if "$HOME/.local/bin/zellij-pane-is-focused" "$zellij_session" "$pane_id"; then
    exit 0
  fi
fi

sq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
/opt/homebrew/bin/terminal-notifier -group "$session_id" \
  -title "opencode — turn finished" -message "$session_title" -sound Glass \
  -execute "$(sq "$script_dir/opencode-focus-pane.sh") $(sq "$session_id") $(sq "$session_title")"
