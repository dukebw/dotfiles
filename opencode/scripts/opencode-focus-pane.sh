#!/bin/bash
# Notification click handler: focus the zellij pane whose opencode TUI shows
# the given session, then raise the iTerm2 window/tab hosting that zellij
# client. Invoked via terminal-notifier -execute, so it runs outside any
# terminal — PATH must be set explicitly.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

session_id="${1:?usage: opencode-focus-pane.sh <session_id> [session_title]}"
session_title="${2:-}"

script_dir=$(cd "$(dirname "$0")" && pwd)
resolved=$("$script_dir/opencode-resolve-pane.sh" "$session_id" "$session_title" || true)
if [ -n "$resolved" ]; then
  read -r zellij_session pane_id <<<"$resolved"
  exec "$HOME/.local/bin/zellij-focus-pane" "$zellij_session" "$pane_id"
fi
open -a iTerm
