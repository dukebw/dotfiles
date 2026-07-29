#!/bin/bash
# Post an opencode attention notification, unless the zellij pane showing the
# session is already in view (focused pane + iTerm2 frontmost). Invoked by the
# notify plugin running in the opencode server.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

session_id="${1:?usage: opencode-notify.sh <session_id> [session_title] [notification_title] [notification_message]}"
session_title="${2:-opencode session}"
notification_title="${3:-opencode — turn finished}"
notification_message="${4:-$session_title}"

sq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
log() { echo "$(date '+%F %T') opencode-notify: $*" >>"$HOME/.cache/pane-notify.log"; }

script_dir=$(cd "$(dirname "$0")" && pwd)
resolved=$("$script_dir/opencode-resolve-pane.sh" "$session_id" "$session_title" || true)
log "sid=$session_id title='$session_title' notification='$notification_title' resolved='${resolved:-NONE}'"
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
  -title "$notification_title" -message "$notification_message" -sound Glass \
  -execute "$click"
