# gpu-fleet

Summons the **fleet layer**: one floating GPU monitor per GPU container you own,
inside the current Zellij session. Multi-node by construction — built for
interactive dev pods and managed disaggregated inference deployments.

```
C-a F   summon/reconcile the fleet layer
C-a f   hide/show it (Zellij's floating-panes toggle, unchanged)
q       quit one nvitop (its pane closes)
```

## How it works

1. `b10-gpu fleet` asks **Kubernetes** which GPU containers you own in the
   `baseten`, `baseten-devenv`, `dynamo`, and `mp-devenv` namespaces of the
   rcli-selected context. Ownership means `$FLEET_USER` (default `$USER`)
   appears in the pod name, `baseten.co/model`, or Helm instance label. Only
   containers with a positive `nvidia.com/gpu` request are included, so managed
   frontends and routers are excluded. Local `.rexec*.yaml` files play no part:
   they are sync plumbing, not an authority (ADR 0001).
2. Each pane runs `kubectl exec -it <pod> -c <gpu-container>`. It uses an
   installed `nvitop`, otherwise `uvx --from nvitop nvitop`, and finally
   `nvidia-smi -l 1`. No ssh shim or port-forward is involved, so a newly
   Running pod is immediately monitorable and dead tunnels cannot break it.
3. **Reconcile by respawn**: pressing `C-a F` re-queries the fleet. If the
   live panes already match, it just toggles the layer. If the fleet changed,
   all fleet panes are killed and respawned with fresh layout. Pane processes
   are tracked via a `GPU_FLEET_PANE=<namespace>/<pod>` marker in their command
   line.
4. **Adaptive layout**: portrait-first tiling uses at most two columns. Six pods
   use 2×3, eight use 2×4, and a full 18-pane NVL72 rack uses 2×9.

## Failure modes

- Expired cluster auth: the launcher pane stays open with the fleet-query
  error and the remedy (usually `rcli select`). Re-auth, press `C-a F` again.
- A pane dies (API stream drop, pod deleted): it closes itself
  (`close-on-exit`); the next `C-a F` reconciles.
- A GPU image has none of `nvitop`, `uvx`, or `nvidia-smi`: the pane reports
  the missing monitor and waits for the next reconciliation.

## Knobs

- `FLEET_USER` — owner token if it differs from `$USER`.
- `b10-gpu fleet [--json|--all-phases|--owner X]` — the underlying query,
  usable standalone.
- `b10-gpu --namespace <namespace> fleet` — restrict discovery to one namespace
  for a one-off query.
