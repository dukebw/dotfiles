---
name: opencode-remote
description: Operate, install, and troubleshoot the macOS remote OpenCode setup and publish artifacts through here-now. Use when working with remote OpenCode, phone access, port 4096, ai.opencode.web, Tailscale Serve, shared oc sessions, generated reports, or here-now.
---

# Remote OpenCode

Use this runbook for the machine-local OpenCode server shared by laptop TUI
clients and a phone browser.

## Architecture

```text
Phone browser
    | authenticated private HTTPS request over Tailscale
Tailscale Serve
    | http://127.0.0.1:4096
One native OpenCode 2 managed service: embedded web UI and API
    | repository and shell tools on the Mac
Laptop TUI and API clients using normal service discovery

Generated static artifact
    | authenticated publication from the Baseten Tailnet
here-now
    | centrally hosted company-wide share URL
```

## Security invariants

- Bind OpenCode only to `127.0.0.1:4096`.
- Tailscale is the remote access boundary. Keep native service authentication
  enabled for client compatibility; Keychain-only password storage is not required.
- Native credentials may live in OpenCode's local service configuration and
  registration files, both mode `0600`. Keep credentials out of agent output,
  command arguments, plists, environment files, and Git.
- Use `tailscale serve`, never `tailscale funnel`. Funnel is public.
- Keep generated reports self-contained and free of credentials, customer
  secrets, shell tokens, active scripts, or data requiring narrower access.
  Treat here-now artifacts as visible company-wide.
- Resolve `go/<slug>` as `http://go/<slug>` because go links use Tailscale
  MagicDNS. Read `http://go/here-now-llm` before publishing and use its current
  API contract rather than a copied endpoint.
- Do not commit the Tailscale URL, IPs, account email, device names, auth keys,
  certificates, logs, or process state.
- Run service restarts from an independent process or Terminal. For a phone-only
  migration, arm an independent rollback watchdog before cutover and verify
  authenticated web UI/API access through Tailscale before committing the change.
  Restarting the server disconnects agents currently using that server.

## Files and state

| Purpose | Version-controlled source | Installed path |
| --- | --- | --- |
| OpenCode shim | `~/dotfiles/bin/opencode` | `~/.local/bin/opencode` |
| MCP compatibility bridge | `~/dotfiles/bin/opencode-mcp-remote` | `~/.local/bin/opencode-mcp-remote` |
| Version updater | `~/dotfiles/bin/opencode-update` | `~/.local/bin/opencode-update` |
| Service availability monitor | `~/dotfiles/bin/opencode-web-server` | `~/.local/bin/opencode-web-server` |
| LaunchAgent | `~/dotfiles/launchd/ai.opencode.web.plist` | `~/Library/LaunchAgents/ai.opencode.web.plist` |
| Update LaunchAgent | `~/dotfiles/launchd/ai.opencode.update.plist` | `~/Library/LaunchAgents/ai.opencode.update.plist` |
| here-now publisher | `~/dotfiles/bin/here-now-publish` | `~/.local/bin/here-now-publish` |
| Global commands | `~/dotfiles/opencode/commands` | `~/.config/opencode/commands` |
| TUI config | `~/dotfiles/opencode/cli.json` | `~/.config/opencode/cli.json` |
| Notify plugin and scripts | `~/dotfiles/opencode/{plugins,scripts}` | `~/.config/opencode/{plugins,scripts}` |
| Attach function | `~/dotfiles/zsh/.zshrc` | `~/.zshrc` |
| This skill | `~/dotfiles/.claude/skills/opencode-remote` | `~/.claude/skills/opencode-remote` |

`cli.json` is the only TUI config OpenCode 2 reads (`tui.json` was one-shot
migrated into it and is retired). OpenCode itself writes `cli.json` via
tmp+rename, which replaces the symlink with a plain file — when `cli.json`
edits stop appearing in `git status`, re-run `install.sh` to restore the link.

Native service settings, including the persistent password, live in
`~/.config/opencode/service.json`. Discovery and client authentication use
`~/.local/state/opencode/service.json`. Both files must remain mode `0600`.
The old Keychain item (`ai.opencode.web` / `opencode-server`) may remain as a
backup; startup and client discovery do not depend on it.

Tailscale Serve configuration is local Tailscale state and is intentionally
not stored in Git.

## Install

Install the dotfile links:

```zsh
cd ~/dotfiles
./install.sh
opencode-update --no-restart
```

For a fresh installation, configure the native service before loading the
LaunchAgent. These settings stop an existing managed service, so run them
from an independent Terminal with sessions idle:

```zsh
opencode service set hostname 127.0.0.1
opencode service set port 4096
opencode service set env OPENCODE_DISABLE_FFF 1
opencode service set env OPENCODE_DISABLE_AUTOUPDATE 1
opencode service get password >/dev/null
```

The last command creates a persistent generated password if one is absent.
When migrating an existing phone login, preserve its password without passing
the secret in process arguments. Do not run a second server against the same
session database during migration.

From an independent Terminal, check whether the job is already loaded:

```zsh
launchctl print gui/$UID/ai.opencode.web
```

If it is loaded, unload it before bootstrapping the installed definition:

```zsh
launchctl bootout \
  gui/$UID \
  "$HOME/Library/LaunchAgents/ai.opencode.web.plist"
```

Start the agent:

```zsh
launchctl bootstrap \
  gui/$UID \
  "$HOME/Library/LaunchAgents/ai.opencode.web.plist"

launchctl bootstrap \
  gui/$UID \
  "$HOME/Library/LaunchAgents/ai.opencode.update.plist"
```

The wrapper defaults to `~/work/baseten`. To run it manually against a
different repository, set `OPENCODE_WEB_DIRECTORY` in that invocation. Do not
use this variable for secrets.

## Configure Tailscale Serve

The standalone macOS client can install its CLI integration from Tailscale
Settings. Until then, replace `tailscale` below with
`/Applications/Tailscale.app/Contents/MacOS/Tailscale`.

Set `TERM=dumb` when invoking the app-bundled CLI from launchd or another
environment without `TERM`. Otherwise it can print a GUI startup error with
exit status zero instead of the requested JSON; validate the response as well
as the exit status.

Create the persistent, tailnet-only mapping:

```zsh
tailscale serve --bg http://127.0.0.1:4096
```

Discover the current private URL rather than recording it:

```zsh
tailscale serve status
```

On Android, keep Tailscale connected and open the reported private HTTPS URL
directly. Authenticate with username `opencode` and the native service password,
then add the page to the home screen. Use the bare origin in the browser.
Humans can run `opencode pair` locally to see pairing credentials; agents must
not expose its output in logs or chat.

Android Always-on VPN can keep Tailscale connected; do not enable blocking
connections without VPN unless that behavior is explicitly desired.

## Publish artifacts with here-now

Use here-now for static HTML, Markdown, and small text/code bundles intended
for company-wide internal access. Do not use the user-owned Mac as the coworker
hosting layer.

Read the live agent instructions before every publication:

```zsh
curl -fsSL http://go/here-now-llm
```

Pass the current Tailscale base URL from those instructions to the publisher:

```zsh
here-now-publish \
  --base-url <base-url> \
  --alias <local-alias> \
  --title <title> \
  <artifact.html>
```

The first publication creates a share. Later publications with the same alias
add versions to that share and print the same stable URL. Alias mappings live
only under `~/.local/state/here-now/aliases`; they must not be committed. Omit
`--alias` when a fresh share is desired.

## Daily use

The `oc` shell function uses normal service discovery and preserves the pane's
current directory. Ordinary `opencode` commands reach the same backend:

```zsh
oc
oc -c
oc -s <session-id>
```

Verify the discovered service address and PID:

```zsh
opencode service status
opencode api get /api/health
```

## OpenCode 2 service model

There is one native managed service for the shared session database. The
`ai.opencode.web` LaunchAgent keeps the Mac awake and calls `opencode service
start` every 30 seconds; this reuses a healthy service and starts it if absent.
It does not run an independent `opencode serve` backend. Fixed loopback binding
and authentication come from native service configuration, not environment-only
`OPENCODE_SERVER_PASSWORD` (which service mode ignores).

Use native discovery for CLI, API, MCP, and TUI clients. Never run an ordinary
`serve` or `--standalone` server alongside it against the same database: the
servers can execute the same session concurrently and omit pending tool results
from model requests. Separate account databases also need separate service
configuration and listener ports before running simultaneously.

MCP OAuth and verification now use the same service:

```zsh
opencode mcp auth <name>
opencode mcp list
```

Plugin code reloads lazily per project directory, cache-keyed on file mtime —
editing a plugin changes nothing for already-open directories until a config
file changes or a session starts in a fresh directory. Confirm which code is
live via the `loading plugin ... ?mtime=` lines in
`~/.local/share/opencode/log/opencode.log`, and confirm notification delivery
via `~/.cache/pane-notify.log`, which logs every attempt including suppressed
duplicates.

Config edits hot-reload, but propagation through the dotfiles symlinks can lag
minutes. Verify with `opencode api get /api/config`; restart the native service
from an independent Terminal when the change must apply now.

## Operations

Inspect the job:

```zsh
launchctl print gui/$UID/ai.opencode.web
```

Restart the backend from an independent Terminal:

```zsh
opencode service restart
```

Kickstarting `ai.opencode.web` only restarts its availability monitor. To stop
the backend for maintenance, unload the monitor first or it will start the
service again on its next check.

Inspect local logs:

```zsh
tail -f "$HOME/Library/Logs/opencode-web.error.log"
tail -f "$HOME/Library/Logs/opencode-update.log"
```

The availability monitor uses `KeepAlive` and `caffeinate -i`. It restarts
the native service after failure and prevents idle system sleep even on battery. The
update LaunchAgent checks `@opencode-ai/cli@beta` daily at 04:00, atomically
activates new builds, restarts the server, and rolls back when the new server
does not become healthy. Closing a MacBook lid still normally sleeps the
machine. After a reboot, the user must log in before these user LaunchAgents
can operate normally; unlocking Keychain is no longer required for the server.

## Verify and troubleshoot

Check in this order:

```zsh
launchctl print gui/$UID/ai.opencode.web
launchctl print gui/$UID/ai.opencode.update
opencode service status
opencode api get /api/health
lsof -nP -iTCP:4096 -sTCP:LISTEN
curl -o /dev/null -sS -w '%{http_code}\n' http://127.0.0.1:4096/api/health
curl -fsSL http://go/here-now-llm
tailscale serve status
tailscale status
```

The listener must be `127.0.0.1:4096`, and the unauthenticated health request
must return `401`. The PID returned through native API discovery must match
the listener and the authenticated Tailscale health endpoint. Common failures
are a closed lid, disconnected Tailscale, stale browser credentials, or a
second server using the same database or port. An authenticated request to the
bare Tailscale origin must return the OpenCode HTML UI.

## Rotate the password

With sessions idle, use an independent Terminal to unset the native service
password, generate a new persistent password with `opencode service get password`,
and restart the service. That command displays the new password: run it only
in the human's terminal, never in agent-visible output. Browsers must log in
again; ordinary CLI clients obtain credentials through native discovery.
