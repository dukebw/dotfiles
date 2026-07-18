#!/bin/bash
# Notification click handler: focus the zellij pane whose opencode TUI shows
# the given session, then raise the iTerm2 window/tab hosting that zellij
# client. Invoked by the notify plugin via terminal-notifier -execute, so it
# runs outside any terminal — PATH must be set explicitly.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

session_id="${1:?usage: opencode-focus-pane.sh <session_id> [session_title]}"
session_title="${2:-}"

running_zellij_sessions() {
  zellij list-sessions --no-formatting 2>/dev/null | grep -v EXITED | awk '{print $1}'
}

# Find the pane showing this opencode session. Best match first:
#   1. TUI pinned to the session (`opencode attach ... -s <id>` in pane_command)
#   2. Pane title equal to / containing the session title (the opencode TUI
#      sets its terminal title to the current session title, so this catches
#      TUIs that navigated to the session interactively)
pane_id=""
zellij_session=""
for zs in $(running_zellij_sessions); do
  match=$(zellij --session "$zs" action list-panes --json --all 2>/dev/null |
    jq -r --arg sid "$session_id" --arg t "$session_title" '
      [ .[] | select(.is_plugin == false) ] as $panes
      | ( [ $panes[] | select(.pane_command // "" | contains($sid)) ]
        + (if $t == "" then [] else
            [ $panes[] | select((.title // "") == $t) ]
          + [ $panes[] | (.title // "") as $pt
              | select(($pt | length) >= 12
                and (($pt | inside($t)) or ($t | inside($pt)))) ]
          end) )
      | first | if . == null then empty else "terminal_\(.id)" end')
  if [ -n "$match" ]; then
    pane_id="$match"
    zellij_session="$zs"
    break
  fi
done

if [ -n "$pane_id" ]; then
  exec "$HOME/.local/bin/zellij-focus-pane" "$zellij_session" "$pane_id"
fi
open -a iTerm
