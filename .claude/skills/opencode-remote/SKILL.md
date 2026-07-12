---
name: opencode-remote
description: Operate, install, and troubleshoot the macOS remote OpenCode setup using launchd, Keychain, Tailscale Serve, and the oc attach function. Use when working with remote OpenCode, phone access, port 4096, ai.opencode.web, Tailscale Serve, or shared oc sessions.
---

# Remote OpenCode

Use this runbook for the machine-local OpenCode server shared by laptop TUI
clients and a phone browser.

## Architecture

```text
Phone browser
    | private HTTPS over Tailscale
Tailscale Serve
    | http://127.0.0.1:4096
OpenCode Web, supervised by launchd
    | repository and shell tools on the Mac
Laptop TUI clients using `opencode attach`
```

## Security invariants

- Bind OpenCode only to `127.0.0.1:4096`.
- Keep HTTP Basic authentication enabled through `OPENCODE_SERVER_PASSWORD`.
- Store the password only in macOS Keychain. Never print it, pass it as a
  command argument, write it to a plist or environment file, or commit it.
- Use `tailscale serve`, never `tailscale funnel`. Funnel is public.
- Do not commit the Tailscale URL, IPs, account email, device names, auth keys,
  certificates, logs, or process state.
- Run service restarts from an independent Terminal. Restarting the server
  disconnects agents currently using that server.

## Files and state

| Purpose | Version-controlled source | Installed path |
| --- | --- | --- |
| Server wrapper | `~/dotfiles/bin/opencode-web-server` | `~/.local/bin/opencode-web-server` |
| LaunchAgent | `~/dotfiles/launchd/ai.opencode.web.plist` | `~/Library/LaunchAgents/ai.opencode.web.plist` |
| Attach function | `~/dotfiles/zsh/.zshrc` | `~/.zshrc` |
| This skill | `~/dotfiles/.claude/skills/opencode-remote` | `~/.claude/skills/opencode-remote` |

The password is a local Keychain generic-password item:

- Service: `ai.opencode.web`
- Account: `opencode-server`

Tailscale Serve configuration is local Tailscale state and is intentionally
not stored in Git.

## Install

Install the dotfile links:

```zsh
cd ~/dotfiles
./install.sh
```

Store a long, fixed password from the password manager. Keeping `-w` as the
last argument makes `security` prompt without putting the password in shell
history or process arguments:

```zsh
security add-generic-password \
  -U \
  -a "opencode-server" \
  -s "ai.opencode.web" \
  -w
```

Confirm the item exists without reading its secret:

```zsh
security find-generic-password \
  -a "opencode-server" \
  -s "ai.opencode.web"
```

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
```

The wrapper defaults to `~/work/baseten`. To run it manually against a
different repository, set `OPENCODE_WEB_DIRECTORY` in that invocation. Do not
use this variable for secrets.

## Configure Tailscale Serve

The standalone macOS client can install its CLI integration from Tailscale
Settings. Until then, replace `tailscale` below with
`/Applications/Tailscale.app/Contents/MacOS/Tailscale`.

Create the persistent, tailnet-only mapping:

```zsh
tailscale serve --bg http://127.0.0.1:4096
```

Discover the current private URL rather than recording it:

```zsh
tailscale serve status
```

On Android, keep Tailscale connected, open the reported HTTPS URL, authenticate
as user `opencode`, and add the page to the home screen. Android Always-on VPN
can keep Tailscale connected; do not enable blocking connections without VPN
unless that behavior is explicitly desired.

## Daily use

The `oc` shell function retrieves the password from Keychain and attaches the
TUI to the shared backend while preserving the pane's current directory:

```zsh
oc
oc -c
oc -s <session-id>
```

Do not use plain `opencode` when the intent is to share the live backend with
the phone. Seeing the same persisted session list is not proof of attachment.
Verify an attached client with:

```zsh
pgrep -fl "opencode attach"
```

## Operations

Inspect the job:

```zsh
launchctl print gui/$UID/ai.opencode.web
```

Restart it from an independent Terminal:

```zsh
launchctl kickstart -k gui/$UID/ai.opencode.web
```

Inspect local logs:

```zsh
tail -f "$HOME/Library/Logs/opencode-web.error.log"
```

The LaunchAgent uses `KeepAlive` and `caffeinate -i`. It restarts OpenCode after
failure and prevents idle system sleep even on battery. Closing a MacBook lid
still normally sleeps the machine. After a reboot, the user must log in and
unlock the Keychain before this user LaunchAgent can operate normally.

## Verify and troubleshoot

Check in this order:

```zsh
launchctl print gui/$UID/ai.opencode.web
lsof -nP -iTCP:4096 -sTCP:LISTEN
curl -o /dev/null -sS -w '%{http_code}\n' http://127.0.0.1:4096/global/health
tailscale serve status
tailscale status
```

The listener must be `127.0.0.1:4096`, and the unauthenticated health request
must return `401`. Common failures are a locked or missing Keychain item, a
closed lid, disconnected Tailscale, a stale password cached on the phone, or a
second OpenCode process already using port 4096.

## Rotate the password

Run the secure `security add-generic-password -U ... -w` command from the
install section, then restart the LaunchAgent from an independent Terminal.
Browsers and TUI clients must authenticate again with the new password.
