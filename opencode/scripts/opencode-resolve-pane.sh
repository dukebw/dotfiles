#!/bin/bash
# Resolve which zellij pane shows the given opencode session; print
# "<zellij_session> <pane_id>" on success, exit 1 if none found.
# Best match first:
#   1. TUI pinned to the session (`opencode attach ... -s <id>` in pane_command)
#   2. Pane title equal to / containing the session title (the opencode TUI
#      sets its terminal title to the current session title, so this catches
#      TUIs that navigated to the session interactively)
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

session_id="${1:?usage: opencode-resolve-pane.sh <session_id> [session_title]}"
session_title="${2:-}"

running_zellij_sessions() {
  zellij list-sessions --no-formatting 2>/dev/null | grep -v EXITED | awk '{print $1}'
}

for zs in $(running_zellij_sessions); do
  match=$(zellij --session "$zs" action list-panes --json -c 2>/dev/null |
    jq -r --arg sid "$session_id" --arg t "$session_title" '
      [ .[] | select(.is_plugin == false) ] as $panes
      # Title matching only against panes running an opencode TUI — other
      # tools (Claude Code) set look-alike session-topic titles.
      | [ $panes[] | select(.pane_command // "" | contains("opencode")) ] as $ocpanes
      | ( [ $panes[] | select(.pane_command // "" | contains($sid)) ]
        + (if $t == "" then [] else
            [ $ocpanes[] | select((.title // "") == $t) ]
            # Fuzzy: manually renamed panes carry prefixes ("OC | ...") and
            # get ellipsis-truncated, so also accept a pane title containing
            # a healthy prefix of the session title.
          + [ $ocpanes[] | (.title // "" | sub("(\\.\\.\\.|…)$"; "")) as $pt
              | select(($pt | length) >= 12
                and (($pt | inside($t)) or ($t | inside($pt))
                  or (($t[0:20]) as $tp
                      | ($tp | length) >= 12 and ($pt | contains($tp))))) ]
          end) )
      | first | if . == null then empty else "terminal_\(.id)" end')
  if [ -n "$match" ]; then
    echo "$zs $match"
    exit 0
  fi
done
exit 1
