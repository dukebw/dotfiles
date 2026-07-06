# gpu-fleet

Summons the **fleet layer**: one floating nvitop pane per GPU dev pod you own,
inside the current Zellij session. Multi-node by construction — built for
working across several pods at once (e.g. disaggregated inference).

```
C-a F   summon/reconcile the fleet layer
C-a f   hide/show it (Zellij's floating-panes toggle, unchanged)
q       quit one nvitop (its pane closes)
```

## How it works

1. `b10-gpu fleet` asks **Kubernetes** which pods you own — pods in the dev
   namespace of the rcli-selected context whose name starts with your user
   prefix (`$FLEET_USER`, default `$USER`). Local `.rexec*.yaml` files play no
   part: they are sync plumbing, not an authority (ADR 0001).
2. Each pane runs `kubectl exec -it <pod> -- uvx --from nvitop nvitop`. No ssh
   shim, no port-forward: a freshly created pod is monitorable the moment it
   is Running, and dead tunnels can't take the monitor down.
3. **Reconcile by respawn**: pressing `C-a F` re-queries the fleet. If the
   live panes already match, it just toggles the layer. If the fleet changed,
   all fleet panes are killed and respawned with fresh layout. Pane processes
   are tracked via a `GPU_FLEET_PANE=<pod>` marker in their command line.
4. **Adaptive layout**: 1 pod → full-size; 2–3 → side-by-side columns;
   more → full-size cascade you cycle through (nvitop needs ~80 columns, so
   tiling stops at three).

## Failure modes

- Expired cluster auth: the launcher pane stays open with the fleet-query
  error and the remedy (usually `rcli select`). Re-auth, press `C-a F` again.
- A pane dies (API stream drop, pod deleted): it closes itself
  (`close-on-exit`); the next `C-a F` reconciles.

## Knobs

- `FLEET_USER` — owner prefix if it differs from `$USER`.
- `b10-gpu fleet [--json|--all-phases|--owner X]` — the underlying query,
  usable standalone.
