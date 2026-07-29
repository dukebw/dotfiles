# Kubernetes is the authority for the GPU fleet; monitoring bypasses rexec

The multi-node GPU fleet layer discovers containers by querying Kubernetes
(`b10-gpu fleet`) across the `baseten`, `baseten-devenv`, `dynamo`, and
`mp-devenv` namespaces. Ownership is identified from the pod name and stable
workload labels; a container enters the fleet only when it requests a GPU.
This covers personal dev pods and managed serving workers without including
CPU frontends and routers. Each monitor pane connects to the exact GPU container
via `kubectl exec`, not through the rexec ssh shim used by the rest of the remote
workflow. `.rexec*.yaml` files are an implementation detail of the sync
(mutagen) concern and say nothing authoritative about which pods exist;
kubectl exec needs no per-pod setup and no port-forward tunnels (which drop
several times a day), so a freshly created pod is monitorable the moment it is
Running. The trade: monitoring requires live cluster auth at launch time, and
a dropped API-server stream kills a pane. Both are accepted because discovery
has the same dependency, making "re-auth and press the key again" the single
failure story.

## Considered Options

- Fleet from `.rexec*.yaml` globbing (rejected: binds fleet identity to sync
  plumbing; a pod without sync setup would be invisible).
- Transport over the rexec ssh shim (rejected: reintroduces per-pod setup and
  tunnel flakiness into a read-only monitor).
- Fleet/pane logic all inside b10-gpu (rejected: Zellij pane mechanics don't
  belong in a kubectl wrapper; instead b10-gpu exposes the pure `fleet` query
  and a thin Zellij launcher consumes it).
