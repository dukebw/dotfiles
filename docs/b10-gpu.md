# b10-gpu

`b10-gpu` is a small helper for Baseten Vultr B200 dev nodes. It makes the
manual Kubernetes/DCGM operations repeatable without hiding the underlying
objects: nodes, pods, StatefulSets, DCGM exporters, and node-debugger pods.

The tool uses the current `kubectl` context selected by `rcli select`, then runs
Kubernetes commands against the matching rcli-generated kubeconfig at
`~/.rcli/kubeconfig/<context>.yaml`. Run this first:

```bash
rcli select
```

## Commands

### List Assignable Nodes

```bash
b10-gpu nodes
```

Lists schedulable nodes matching `nvidia.com/gpu.product=NVIDIA-B200`, with a
ready node condition and allocatable GPUs.

### Show GPU Status

```bash
b10-gpu status --all
b10-gpu status f307cc291a7c
```

Creates a temporary node-debugger pod and runs host-level `nvidia-smi` from
`chroot /host`. This is slower than scraping DCGM, but it avoids stale exporter
metrics and matches the authoritative process view used by `b10-gpu owner`.

### List Pods On A Node

```bash
b10-gpu pods f307cc291a7c
```

Runs the equivalent of:

```bash
kubectl get pods -A --field-selector spec.nodeName=<node> -o wide
```

### List Your GPU Fleet

```bash
b10-gpu fleet
b10-gpu --namespace dynamo fleet
```

By default, fleet discovery queries `baseten`, `baseten-devenv`, `dynamo`, and
`mp-devenv`. It selects Running pods whose name, `baseten.co/model`, or Helm
instance label contains the owner token, then returns one row per container
with a positive `nvidia.com/gpu` request. This includes owned managed serving
workers while excluding their CPU frontends and routers. Results include the
namespace, GPU container, requested GPU count, readiness, and node.

### Map GPU Owners

```bash
b10-gpu owner f307cc291a7c
```

Creates a temporary node-debugger pod, runs host-level `nvidia-smi` from
`chroot /host`, scans host `/proc/*/fd` for `/dev/nvidia*` handles, maps pod
cgroups back to Kubernetes pods, prints the result, and deletes the debugger pod.

This is the command to use when container-local `nvidia-smi` shows GPU memory but
`No running processes found`.

### Move A Dev Pod

```bash
b10-gpu move f307cc291a7c --pod <dev-pod-name> --dry-run
b10-gpu move f307cc291a7c --pod <dev-pod-name> --yes
```

The source node is discovered from the pod. The target accepts the full node name
or a unique suffix. The command patches the owning StatefulSet's pod template
with:

```yaml
nodeSelector:
  kubernetes.io/hostname: <target-node>
```

Then it waits for the pod to run on the target node and runs
`rexec --setup --flush` to create a fresh SSH shim for the new pod instance and
block until the sync re-push completes. A fresh node disk makes Mutagen
safety-halt the existing session (`Halted due to one-sided root emptying`); the
flush detects that signature and auto-resets the session so the worktree is
re-pushed from local.

Use `--from <node-suffix>` to make the command fail if the pod is not currently
on the expected source node.

`rexec --setup --flush` discovers its config from the current directory (nearest
`.rexec.yaml`, else the global config), so run `b10-gpu move` from the worktree
whose session you want refreshed, or pass `--rexec-config <path>`. Sessions for
other worktrees synced to the same pod heal themselves on their next `r` /
`rexec --flush` use.

## Smoke Tests

Run these after changing `b10-gpu`.

### `b10-gpu nodes`

```bash
b10-gpu nodes
```

Expected: the assignable Vultr B200 nodes are listed, including
`b200-node-001-f307cc291a7c`.

### `b10-gpu status --all`

```bash
b10-gpu status --all
```

Expected: four nodes are shown, with eight GPU rows per node. Each row includes
memory used and utilization.

If all B200 nodes are filtered out, the command exits non-zero and prints the
candidate node readiness reasons. For example, when the node controller has
marked the nodes unreachable, the diagnostic includes `Ready=Unknown` and
`reason=NodeStatusUnknown`.

### `b10-gpu status <node>`

```bash
b10-gpu status f307cc291a7c
```

Expected: only `b200-node-001-f307cc291a7c` is shown, with eight GPU rows.

Negative check:

```bash
b10-gpu status does-not-exist
```

Expected: a clear unknown-node error.

### `b10-gpu pods <node>`

```bash
b10-gpu pods f307cc291a7c
```

Expected: the configured dev pod appears, plus GPU operator pods on the same
node.

Cross-check:

```bash
kubectl get pods -A \
  --field-selector spec.nodeName=b200-node-001-f307cc291a7c \
  -o wide
```

### `b10-gpu owner <node>`

```bash
b10-gpu owner f307cc291a7c
```

Expected on a mostly free node: no compute apps. Device handles may include
`dcgm-exporter`, `nvidia-device-plugin`, `nv-hostengine`,
`nvidia-persistenced`, or `nvitop`.

Verify cleanup:

```bash
kubectl get pods -n default | grep node-debugger || true
```

Expected: no lingering debugger pod from the command.

### `b10-gpu move <node>`

Dry-run:

```bash
b10-gpu move f307cc291a7c --pod <dev-pod-name> --dry-run
```

Expected: prints the pod, StatefulSet, current node, and target node without
changing anything.

No-op move when already on the target:

```bash
b10-gpu move f307cc291a7c --pod <dev-pod-name> --yes
```

Expected: reports that the pod is already on the target node and does not roll
the StatefulSet.

Real move, only when a safe target node is free:

```bash
b10-gpu move <other-free-node> --pod <dev-pod-name> --yes
```

Expected: patches the StatefulSet, waits for the pod to run on the target node,
refreshes `rexec`, auto-resets the Mutagen session halted by the recreated
remote root, and returns only after the re-push completes with the session
watching the configured sync.
