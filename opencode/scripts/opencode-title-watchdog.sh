#!/bin/bash
# Restore OpenCode's latest OSC title if Zellij replaces or clears it.
set -uo pipefail

zellij_session="${1:?usage: opencode-title-watchdog.sh <zellij_session> <pane_id> <owner_pid>}"
pane_id="${2:?usage: opencode-title-watchdog.sh <zellij_session> <pane_id> <owner_pid>}"
owner_pid="${3:?usage: opencode-title-watchdog.sh <zellij_session> <pane_id> <owner_pid>}"
zellij_bin="${ZELLIJ_BIN:-zellij}"
poll_interval_sec="${OPENCODE_TITLE_POLL_INTERVAL_SEC:-2}"
last_session_title=""

while kill -0 "$owner_pid" 2>/dev/null; do
  title=$(
    "$zellij_bin" --session "$zellij_session" action list-panes --json 2>/dev/null |
      jq -r --arg pane_id "${pane_id#terminal_}" \
        '.[] | select((.id | tostring) == $pane_id and .is_plugin == false) | .title // empty' |
      head -n 1
  )

  case "$title" in
    "OC | "*) last_session_title="$title" ;;
    OpenCode) last_session_title="" ;;
    *)
      if [ -n "$last_session_title" ]; then
        printf '\033]0;%s\007' "$last_session_title"
      fi
      ;;
  esac

  sleep "$poll_interval_sec"
done
