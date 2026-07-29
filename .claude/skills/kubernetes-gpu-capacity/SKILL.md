---
name: kubernetes-gpu-capacity
description: Inspect Kubernetes GPU capacity by joining label-selected nodes to per-node pod GPU requests, including dedicated or tainted nodes and active controller checks. Use when asked which GPU nodes are free, which pods allocate GPUs, whether a rack or dedicated node set has capacity, or before deploying a GPU workload.
---

# Kubernetes GPU Capacity

Use this skill to answer capacity questions from current Kubernetes state. Do
not infer capacity from pod counts, hostname substrings, remembered rack names,
or an earlier listing.

## Safety Rules

- Pass `--context` on every `kubectl` command. Never rely on the current context.
- Use node labels as the source of truth for reservation, GPU type, rack, and
  dedicated ownership.
- Sum pod GPU **requests**, because requests are what the scheduler reserves.
  Do not count pods, GPU limits, or device allocations.
- Never delete, scale, patch, or restart an occupying workload without explicit
  user approval.
- Capacity is volatile. Repeat the complete check immediately before deployment.
- A momentary `0/N` is not durable capacity while an active controller can
  recreate pods on those nodes.

## Prerequisites

Require `kubectl` and `jq`. Confirm access before investigating:

```bash
kubectl --context "$CONTEXT" auth can-i list nodes
kubectl --context "$CONTEXT" auth can-i list pods --all-namespaces
```

If the workload-plane context is missing, run `rcli sync --provider rancher`
and select it with `rcli select --provider rancher`. Do not conclude that access
is unavailable before trying that workflow.

## Inputs

Make these inputs explicit:

```bash
CONTEXT=<workload-plane-context>
NODE_SELECTOR='baseten-internal/customer-reservation=mp-devenv,baseten.co/gpu-type=nvidia-gb300'
```

Append exact label selectors when the question is narrower:

```bash
NODE_SELECTOR="$NODE_SELECTOR,nvidia.com/gpu.clique=<clique-id>"
DEDICATED=<dedicated-value>
NODE_SELECTOR="$NODE_SELECTOR,dedicated=$DEDICATED"
```

Never substitute a node-name prefix for the clique label.

## Capacity Inventory

Select the candidate nodes, reject cordoned or unready nodes, carry the
dedicated and clique labels through, and query pods by exact `spec.nodeName`.
For each pod, sum every container's `resources.requests["nvidia.com/gpu"]`.
Count bound `Running` and `Pending` pods; exclude terminal `Succeeded` and
`Failed` pods.

```bash
results=$(
  while IFS=$'\t' read -r node dedicated clique allocatable_gpu; do
    used_gpu=$(kubectl --context "$CONTEXT" get pods -A \
      --field-selector "spec.nodeName=$node" -o json | jq \
      '[.items[]
        | select(.status.phase == "Running" or .status.phase == "Pending")
        | [.spec.containers[]?
          | .resources.requests["nvidia.com/gpu"] // "0"
          | tonumber]
        | add // 0]
       | add // 0')

    printf '%s | dedicated=%s | clique=%s | gpu_used=%s/%s\n' \
      "$node" "$dedicated" "$clique" "$used_gpu" "$allocatable_gpu"
  done < <(kubectl --context "$CONTEXT" get nodes -l "$NODE_SELECTOR" -o json |
    jq -r '.items[]
      | select(.spec.unschedulable != true)
      | select(any(.status.conditions[];
          .type == "Ready" and .status == "True"))
      | [.metadata.name,
         (.metadata.labels.dedicated // "none"),
         (.metadata.labels["nvidia.com/gpu.clique"] // "none"),
         (.status.allocatable["nvidia.com/gpu"] // "0")]
      | @tsv')
)

printf '%s\n' "$results" | sort -t= -k4,4n
```

Rows with `gpu_used=0/N` are GPU-unallocated at that snapshot. Preserve the
denominator rather than assuming every node has the same GPU count.

For a few dozen nodes, one pod query per node is clear and exact. For hundreds
or thousands of nodes, fetch all pods once and group them by `spec.nodeName`
client-side to avoid excessive API calls.

## Show The GPU-Allocating Pods

Use the same candidate-node query. Do not switch to `get pods -o wide | grep`.

```bash
while read -r node; do
  kubectl --context "$CONTEXT" get pods -A \
    --field-selector "spec.nodeName=$node" -o json | jq -r \
    --arg node "$node" '.items[]
      | select(.status.phase == "Running" or .status.phase == "Pending")
      | ([.spec.containers[]?
          | .resources.requests["nvidia.com/gpu"] // "0"
          | tonumber]
         | add // 0) as $gpu
      | select($gpu > 0)
      | [$node,
         .metadata.namespace,
         .metadata.name,
         $gpu,
         .status.phase,
         ((.metadata.ownerReferences // [])
           | map(.kind + "/" + .name)
           | join(","))]
      | @tsv'
done < <(kubectl --context "$CONTEXT" get nodes -l "$NODE_SELECTOR" -o json |
  jq -r '.items[]
    | select(.spec.unschedulable != true)
    | select(any(.status.conditions[];
        .type == "Ready" and .status == "True"))
    | .metadata.name')
```

Report columns as node, namespace, pod, requested GPUs, phase, and immediate
owner. Follow owner references when the user asks what manages the pods.

## Controller Durability Check

Before declaring nodes deployable, determine whether an existing controller can
recreate pods there. Inspect the GPU pods' owner chain and the managing Helm
release. On Baseten Dynamo deployments, also search `DynamoGraphDeployment`
specs for the dedicated selector:

```bash
kubectl --context "$CONTEXT" get dynamographdeployments.nvidia.com -A -o json |
  jq -r --arg dedicated "$DEDICATED" '.items[]
    | select(([.. | objects | .dedicated? // empty]
      | index($dedicated)) != null)
    | [.metadata.namespace,
       .metadata.name,
       (.status.state // "unknown"),
       (.status.conditions[-1].message // "")]
    | @tsv'
```

Also inspect the named release when one is found:

```bash
helm --kube-context "$CONTEXT" -n <namespace> status <release>
```

Treat a `0/N` gap as unavailable if an active controller still targets those
nodes. Pods can disappear during a rollout and return seconds later.

## Taints And Tolerations

Show node taints:

```bash
kubectl --context "$CONTEXT" get nodes -l "$NODE_SELECTOR" -o json |
  jq -r '.items[]
    | [.metadata.name,
       ((.spec.taints // [])
         | map(.key + "=" + (.value // "") + ":" + .effect)
         | join(","))]
    | @tsv'
```

Show an occupying pod's tolerations:

```bash
kubectl --context "$CONTEXT" -n <namespace> get pod <pod> -o json |
  jq '{node: .spec.nodeName, tolerations: .spec.tolerations}'
```

`NoSchedule` prevents new scheduling but does not evict an existing pod.
Matching toleration means the pod can schedule or be recreated there.
`NoExecute` is the taint effect that can evict an existing pod.

## Required Report

Return:

1. Context and exact node selector.
2. Candidate node count, grouped by clique when relevant.
3. Per-node `dedicated`, `clique`, and `gpu_used/allocatable` table.
4. Free node count and exact node names.
5. GPU-allocating pods and requested GPU counts.
6. Active owners or controllers that make apparently free capacity transient.
7. Any taint/toleration implications.

State the observation time and distinguish current observation from durable
deployment capacity.
