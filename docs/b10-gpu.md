# b10-gpu

`b10-gpu` is a small helper for Baseten Vultr B200 dev nodes. It makes the
manual Kubernetes/DCGM/rexec operations repeatable without hiding the underlying
objects: nodes, pods, StatefulSets, DCGM exporters, and node-debugger pods.

The tool defaults to `~/.config/rexec/config.yaml` for kubeconfig, namespace,
and pod. Pass `--kubeconfig` to override it.

```bash
export K=~/work/benchmarks/gpu-dev/runbooks/vultr-dev-env/vultr-us-sea-prod-1.yaml
```

## Commands

### List Assignable Nodes

```bash
b10-gpu nodes --kubeconfig "$K"
```

Lists schedulable nodes matching `nvidia.com/gpu.product=NVIDIA-B200`, with a
ready node condition and allocatable GPUs.

### Show GPU Status

```bash
b10-gpu status --all --kubeconfig "$K"
b10-gpu status f307cc291a7c --kubeconfig "$K"
```

Creates a temporary node-debugger pod and runs host-level `nvidia-smi` from
`chroot /host`. This is slower than scraping DCGM, but it avoids stale exporter
metrics and matches the authoritative process view used by `b10-gpu owner`.

### List Pods On A Node

```bash
b10-gpu pods f307cc291a7c --kubeconfig "$K"
```

Runs the equivalent of:

```bash
kubectl --kubeconfig "$K" get pods -A --field-selector spec.nodeName=<node> -o wide
```

### Map GPU Owners

```bash
b10-gpu owner f307cc291a7c --kubeconfig "$K"
```

Creates a temporary node-debugger pod, runs host-level `nvidia-smi` from
`chroot /host`, scans host `/proc/*/fd` for `/dev/nvidia*` handles, maps pod
cgroups back to Kubernetes pods, prints the result, and deletes the debugger pod.

This is the command to use when container-local `nvidia-smi` shows GPU memory but
`No running processes found`.

### Move The Configured rexec Pod

```bash
b10-gpu move f307cc291a7c --kubeconfig "$K" --dry-run
b10-gpu move f307cc291a7c --kubeconfig "$K" --yes
```

The source node is discovered from the configured pod. The target accepts the
full node name or a unique suffix. The command patches the owning StatefulSet's
pod template with:

```yaml
nodeSelector:
  kubernetes.io/hostname: <target-node>
```

Then it waits for the pod to run on the target node, terminates the configured
Mutagen session, and runs `rexec --setup` to create a fresh SSH shim and one-way
sync session for the new pod instance.

Use `--from <node-suffix>` to make the command fail if the pod is not currently
on the expected source node.

## Smoke Tests

Run these after changing `b10-gpu`.

### `b10-gpu nodes`

```bash
b10-gpu nodes --kubeconfig "$K"
```

Expected: the assignable Vultr B200 nodes are listed, including
`b200-node-001-f307cc291a7c`.

### `b10-gpu status --all`

```bash
b10-gpu status --all --kubeconfig "$K"
```

Expected: four nodes are shown, with eight GPU rows per node. Each row includes
memory used and utilization.

If all B200 nodes are filtered out, the command exits non-zero and prints the
candidate node readiness reasons. For example, when the node controller has
marked the nodes unreachable, the diagnostic includes `Ready=Unknown` and
`reason=NodeStatusUnknown`.

### `b10-gpu status <node>`

```bash
b10-gpu status f307cc291a7c --kubeconfig "$K"
```

Expected: only `b200-node-001-f307cc291a7c` is shown, with eight GPU rows.

Negative check:

```bash
b10-gpu status does-not-exist --kubeconfig "$K"
```

Expected: a clear unknown-node error.

### `b10-gpu pods <node>`

```bash
b10-gpu pods f307cc291a7c --kubeconfig "$K"
```

Expected: the configured dev pod appears, plus GPU operator pods on the same
node.

Cross-check:

```bash
kubectl --kubeconfig "$K" get pods -A \
  --field-selector spec.nodeName=b200-node-001-f307cc291a7c \
  -o wide
```

### `b10-gpu owner <node>`

```bash
b10-gpu owner f307cc291a7c --kubeconfig "$K"
```

Expected on a mostly free node: no compute apps. Device handles may include
`dcgm-exporter`, `nvidia-device-plugin`, `nv-hostengine`,
`nvidia-persistenced`, or `nvitop`.

Verify cleanup:

```bash
kubectl --kubeconfig "$K" get pods -n default | grep node-debugger || true
```

Expected: no lingering debugger pod from the command.

### `b10-gpu move <node>`

Dry-run:

```bash
b10-gpu move f307cc291a7c --kubeconfig "$K" --dry-run
```

Expected: prints the pod, StatefulSet, current node, and target node without
changing anything.

No-op move when already on the target:

```bash
b10-gpu move f307cc291a7c --kubeconfig "$K" --yes
```

Expected: reports that the pod is already on the target node and does not roll
the StatefulSet.

Real move, only when a safe target node is free:

```bash
b10-gpu move <other-free-node> --kubeconfig "$K" --yes
```

Expected: patches the StatefulSet, waits for the pod to run on the target node,
terminates the old configured Mutagen session, refreshes `rexec`, and leaves a
new Mutagen session watching the configured sync.
