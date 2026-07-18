#!/bin/bash
# Post the opencode turn-finished notification, unless the zellij pane showing
# the session is already in view (focused pane + iTerm2 frontmost). Invoked by
# the notify plugin running in the opencode server, so changes here take
# effect without a server restart.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

session_id="${1:?usage: opencode-notify.sh <session_id> [session_title]}"
session_title="${2:-opencode session}"

sq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
log() { echo "$(date '+%F %T') opencode-notify: $*" >>"$HOME/.cache/pane-notify.log"; }

script_dir=$(cd "$(dirname "$0")" && pwd)
resolved=$("$script_dir/opencode-resolve-pane.sh" "$session_id" "$session_title" || true)
log "sid=$session_id title='$session_title' resolved='${resolved:-NONE}'"
if [ -n "$resolved" ]; then
  read -r zellij_session pane_id <<<"$resolved"
  if "$HOME/.local/bin/zellij-pane-is-focused" "$zellij_session" "$pane_id"; then
    log "suppressed: $pane_id in view"
    exit 0
  fi
  # Bake the resolved pane into the click action: re-resolving on click costs
  # a ~1.3s zellij list-panes round-trip per session, which reads as lag.
  click="$(sq "$HOME/.local/bin/zellij-focus-pane") $(sq "$zellij_session") $(sq "$pane_id")"
else
  click="$(sq "$script_dir/opencode-focus-pane.sh") $(sq "$session_id") $(sq "$session_title")"
fi

/opt/homebrew/bin/terminal-notifier -group "$session_id" \
  -title "opencode — turn finished" -message "$session_title" -sound Glass \
  -execute "$click"
