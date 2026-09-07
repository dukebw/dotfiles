---
name: dynamo-gb300-debug-deployment
description: Deploy and verify GB300 debug workloads using direct Grove PodCliqueSets or DynamoGraphDeployments and NVIDIA ComputeDomains. Use for multi-node debug deployments, safe image/config changes, claim cleanup, and MNNVL startup failures; discover the actual controller and fixed or elastic membership mode before acting.
---

# Dynamo GB300 Debug Deployment

Deploy GB300 Dynamo workloads without overlapping old and new MNNVL claims.
Derive the cluster, controller, resource names, labels, and paths from the
selected values, rendered chart, and live owner references. A model name or an
old incident does not select a deployment.

## Scope

Use this skill for debug and development deployments that combine:

- Direct Grove `PodCliqueSet` workers or `DynamoGraphDeployment`-managed workers.
- Multi-node GB300 workers using NVIDIA `ComputeDomain` channel claims.
- Helm releases from `helm/charts/baseten-dynamo-model`.

Do not use this workflow as a zero-downtime production rollout. Use blue-green
deployment for production, as described below.

## Related Skills

- Load `kubernetes-gpu-capacity` before selecting nodes or deploying. Capacity
  is a live Kubernetes observation, not a reservation.
- Load `gpu-reservation-api` when the cluster's dev GPU policy requires a
  dashboard reservation. Reserve before deployment and release when finished.
- Load `dynamo-image-build` when an image must be built. This skill starts from
  an existing immutable image reference.
- Use `b10-bench` after readiness when endpoint validation is requested.

## Safety Rules

- Pass `--context "$CONTEXT"` on every `kubectl` command. Pass
  `--kube-context "$CONTEXT"` on every Helm command.
- Run `rcli sync --provider rancher` and `rcli select --provider rancher` before
  concluding that cluster access is unavailable.
- Verify RBAC with `kubectl auth can-i` before modifying resources.
- Never infer GPU capacity from pod counts or remembered node names.
- Never delete another user's workload or release to obtain capacity.
- Require explicit user approval before deleting an existing workload unless the
  user already requested deployment or upgrade of that named debug release.
- Every deployment created for Brendan must have a short base name containing
  the exact contiguous segment `-debugging-brendanduke`.
- After creation, verify every generated pod name contains both `debugging` and
  `brendanduke`. Rename and recreate if controller truncation removes either.
- Do not patch `ComputeDomain.status.nodes` during a normal rollout. A status
  patch is recovery-only because it races the NVIDIA controller.
- Do not treat `ComputeDomain.status.status=Ready` as sufficient. Verify current
  membership, claims, and helper DaemonSets using the discovered membership mode.
- Preserve unrelated live configuration drift. Diff before upgrade and ask if
  the desired values are ambiguous.
- For reserved debug GPUs, arm cluster-side cleanup before activating GPU
  replicas. Persist the lease deadline and exact controller UIDs outside
  temporary directories; a laptop process is not a cleanup backstop. Rearm the
  guard if a controller is recreated, and verify release when finished.
- Redact secrets before printing or exporting manifests, values, or logs.
  Do not dump environments or command lines to diagnose startup.

## Required Inputs

Make these explicit before changing the cluster:

| Variable | Source |
| --- | --- |
| `CONTEXT` | Selected workload-plane context |
| `NAMESPACE` | Selected deployment values |
| `RELEASE` | Short name containing `-debugging-brendanduke` |
| `VALUES_FILE`, `CHART_DIR` | Explicit files in the active workspace |
| `ZERO_GPU_VALUES_FILE` | Overlay that keeps every GPU-owning root at zero replicas |
| `IMAGE` | Immutable image reference for this experiment |
| `ROOT_KIND`, `ROOT_NAME` | GPU-owning controller from the rendered chart/live owners |
| `MODEL_SELECTOR` | Labels verified against the rendered and live resources |

`ROOT_KIND` is `podcliquesets.grove.io` for direct Grove, or the discovered
`dynamographdeployments.nvidia.com` root for DGD-managed workers. Do not delete a
generated child PCS while its DGD can recreate it. Repeat the checks for every
GPU-owning root in a multi-role release.

Discover supported resources before using kind-specific commands:

```bash
kubectl --context "$CONTEXT" api-resources --api-group=grove.io
kubectl --context "$CONTEXT" api-resources --api-group=nvidia.com
kubectl --context "$CONTEXT" api-resources --api-group=resource.nvidia.com
```

## Preflight

Confirm context and permissions:

```bash
kubectl --context "$CONTEXT" cluster-info
kubectl --context "$CONTEXT" auth can-i get pods -n "$NAMESPACE"
kubectl --context "$CONTEXT" auth can-i patch "$ROOT_KIND" -n "$NAMESPACE"
kubectl --context "$CONTEXT" auth can-i delete "$ROOT_KIND" -n "$NAMESPACE"
kubectl --context "$CONTEXT" auth can-i get resourceclaims -n "$NAMESPACE"
kubectl --context "$CONTEXT" auth can-i get computedomains -n "$NAMESPACE"
```

For an existing release, inspect its controller, ComputeDomains, claims, and
pods. Use protected artifact files for full values/manifests and redact before
sharing them. If labels are not propagated to a ComputeDomain, follow claim
domain IDs and owner references rather than treating an empty label query as
evidence that no domain exists.

```bash
helm --kube-context "$CONTEXT" -n "$NAMESPACE" status "$RELEASE"
kubectl --context "$CONTEXT" -n "$NAMESPACE" get "$ROOT_KIND" "$ROOT_NAME" -o wide
kubectl --context "$CONTEXT" -n "$NAMESPACE" get computedomains \
  -l "$MODEL_SELECTOR" -o wide
kubectl --context "$CONTEXT" -n "$NAMESPACE" get resourceclaims -o wide
kubectl --context "$CONTEXT" -n "$NAMESPACE" get pods \
  -l "$MODEL_SELECTOR" -o wide
```

Identify the installed DRA driver version and inspect each domain's schema and
membership. Do not infer behavior from an old version number:

- `spec.numNodes > 0`: fixed membership; compare against that declared count.
- `spec.numNodes == 0`: elastic membership; derive expected active members from
  current worker pods and allocated claims, not from zero. Inspect
  `ComputeDomainClique` resources when the installed driver exposes them.

```bash
kubectl --context "$CONTEXT" -n nvidia-dra-driver-gpu get deployments -o json |
  jq -r '.items[].spec.template.spec.containers[]
    | select(.name == "compute-domain")
    | .image'
```

Use `kubernetes-gpu-capacity` immediately before deployment. Verify the exact
reservation, GPU type, and `nvidia.com/gpu.clique` selectors from values.

## Render And Diff

Change only the requested image or configuration in the source values file.
Render and validate before touching the cluster:

```bash
RENDERED=$(mktemp)
helm --kube-context "$CONTEXT" template "$RELEASE" "$CHART_DIR" \
  -n "$NAMESPACE" \
  -f "$VALUES_FILE" -f "$ZERO_GPU_VALUES_FILE" >"$RENDERED"
kubeconform -strict -summary -ignore-missing-schemas "$RENDERED"
```

Inspect all rendered image references and reject unintended changes:

```bash
grep -o 'image: .*' "$RENDERED" | sort -u
HELM_DIFF_COLOR=false helm --kube-context "$CONTEXT" diff upgrade \
  "$RELEASE" "$CHART_DIR" \
  -n "$NAMESPACE" \
  -f "$VALUES_FILE" -f "$ZERO_GPU_VALUES_FILE" \
  --allow-unreleased
```

Do not silently overwrite live drift. If only some source changes should ship,
render a temporary deployment values file that preserves the intended live
values, explain it, and keep the source file aligned with the user's decision.

## Debug Recreate Upgrade

Keep old and replacement MNNVL claims from overlapping during a debug image or
configuration change. This is a debug cleanup workflow, not a production rollout.

For a debug deployment, use this sequence:

1. Save the current root UIDs and manifests. Scale a direct PCS to zero, or
   scale/delete the actual GPU-owning DGD roots as authorized.
2. Wait until its worker pods and ResourceClaims are deleted.
3. Verify old GPU compute processes are gone and each domain has no old members.
   After scale-to-zero, an elastic domain object and a 0/0 helper DaemonSet may
   remain legitimately; do not wait for the object itself to disappear.
4. Apply the Helm image upgrade with GPU replicas held at zero.
5. Verify or rearm the UID-bound cleanup guard before restoring GPU workers.
6. Wait for each ComputeDomain helper DaemonSet to reach exactly the expected
   ready count.
7. Only then allow TRT-LLM initialization to be considered healthy.

Do not proceed merely because pods disappeared. Poll until no worker pods owned
by the selected roots and no corresponding ResourceClaims remain. Use recorded
UIDs and owner references to distinguish a replacement from the old workload.
Rancher watch streams may end with HTTP/2 `INTERNAL_ERROR`, so prefer bounded GET polling over a single
long `kubectl wait`.

List claims with owner and reservation information:

```bash
kubectl --context "$CONTEXT" -n "$NAMESPACE" get resourceclaims -o json |
  jq -r --arg release "$RELEASE" '.items[]
    | select(.metadata.name | startswith($release))
    | [.metadata.name,
       (.metadata.ownerReferences[0].kind // ""),
       (.metadata.ownerReferences[0].name // ""),
       ((.status.reservedFor // []) | map(.name) | join(",")),
       (.status.allocation.devices.results[0].pool // "")]
    | @tsv'
```

Before re-creation, ComputeDomains should have no old worker membership.
If old worker membership remains after all old pods and claims are gone, stop.
Treat that as a DRA controller cleanup failure; do not start replacement workers
into the stale domain.

Apply the already validated release:

```bash
helm --kube-context "$CONTEXT" upgrade --install \
  "$RELEASE" "$CHART_DIR" \
  -n "$NAMESPACE" \
  -f "$VALUES_FILE" -f "$ZERO_GPU_VALUES_FILE"
```

## ComputeDomain Gates

Inspect membership per domain, joining claims and their current pod owners when
labels are not propagated to the domain:

```bash
kubectl --context "$CONTEXT" -n "$NAMESPACE" get computedomains \
  -l "$MODEL_SELECTOR" -o json |
  jq -r '.items[]
    | [.metadata.name,
       (.spec.numNodes | tostring),
       ((.status.nodes // []) | length | tostring),
       (.status.status // ""),
       ((.status.nodes // []) | map(.name) | join(","))]
    | @tsv'
```

Require all of the following before declaring fabric setup healthy:

- Fixed membership: `length(status.nodes) == spec.numNodes`.
- Elastic membership: members match the distinct nodes of that domain's active
  worker pods/claims. `spec.numNodes == 0` is not the active-member count.
- Exactly one allocated and reserved claim per current worker pod.
- Every claim owner and `reservedFor` entry names a current pod.
- The helper DaemonSet has `desiredNumberScheduled == numberReady ==` the
  expected active-member count; no old helper pods remain.
- Every member node has the expected `nvidia.com/gpu.clique` label.

Find helper DaemonSets by ComputeDomain UID, not truncated name:

```bash
CD=<compute-domain-name>
CD_UID=$(kubectl --context "$CONTEXT" -n "$NAMESPACE" get computedomain \
  "$CD" -o jsonpath='{.metadata.uid}')
kubectl --context "$CONTEXT" -n nvidia-dra-driver-gpu get daemonsets \
  -l "resource.nvidia.com/computeDomain=$CD_UID" -o wide
```

If the driver does not label the DaemonSet, inspect ComputeDomain status nodes
and match the generated DaemonSet's
`spec.template.spec.nodeSelector["resource.nvidia.com/computeDomain"]` to the
ComputeDomain UID.

## Readiness And Logs

Verify every generated pod name contains both required naming tokens:

```bash
kubectl --context "$CONTEXT" -n "$NAMESPACE" get pods \
  -l "$MODEL_SELECTOR" -o name
```

Poll the actual controller conditions and pod readiness with bounded `get`
calls. Do not interpret Rancher watch-stream `INTERNAL_ERROR` warnings as
workload failures.

```bash
kubectl --context "$CONTEXT" -n "$NAMESPACE" get "$ROOT_KIND" \
  -l "$MODEL_SELECTOR" -o json |
  jq -r '.items[]
    | [.metadata.name,
       ((.status.conditions // [])
         | map(.type + "=" + (.status | tostring) + ":" +
             (.reason // "") + ":" + (.message // ""))
         | join(" | "))]
    | @tsv'
```

During TRT-LLM startup, distinguish active work from failure:

- `CUDA_ERROR_NOT_READY` from `cuMemImportFromShareableHandle` indicates broken
  MNNVL/ComputeDomain setup.
- FlashInfer `ninja`, `nvcc`, `ptxas`, `gcc`, or `cc1plus` processes indicate
  active kernel compilation. There is no reliable completion percentage.
- Cubin downloads, autotuning, CUDA graph capture, and KV-cache allocation are
  expected startup stages.
- A refused health connection can be expected until the engine opens its health
  port. Compare against the configured startup-probe budget.
- Repeated restarts, a terminated compiler, traceback, or no log/process
  progress requires investigation.

Inspect compiler activity without modifying the pod:

```bash
kubectl --context "$CONTEXT" -n "$NAMESPACE" exec <leader-pod> -- \
  sh -c "ps -eo pid,etimes,pcpu,pmem,comm | \
    grep -E 'nvcc|ptxas|ninja|gcc|cc1plus' | grep -v grep || true"
```

After all current worker pods and their controllers are ready, verify the old
worker image has no remaining pods, the frontend image stayed pinned when
intended, and the endpoint passes the requested smoke test.

## Recovery Only

For elastic domains, repair/recreate through the owning controller and installed
driver; do not patch status to simulate membership. For a fixed-membership
driver, use manual status repair only when its version-specific recovery
procedure requires it and the conditions below are satisfied.

Manual `status.nodes` patching is not a normal rollout step. It can race the
ComputeDomain controller and can select the wrong nodes.

Use it only when all of these are true:

- The rollout already failed.
- Active claims and helper DaemonSet-selected nodes are known exactly.
- `status.nodes` contains stale nodes not referenced by active claims.
- The user approves surgical recovery instead of recreate.

Before any patch, save the ComputeDomain, claims, helper DaemonSet, and pod
state. Derive the replacement node list from active claim allocation pools and
the helper DaemonSet selector. After patching, require exact cardinality,
helper DaemonSet readiness, and a clean TRT-LLM supervisor restart. Never copy
node names or IP addresses from an earlier incident.

## Production Rollouts

For production with no downtime, use blue-green deployments with distinct controller,
ComputeDomain, and channel-template names. Each revision gets an isolated
ComputeDomain. Move traffic only after the new revision's claims, helper
DaemonSets, workers, and endpoint are healthy. Delete the old revision only
after drain completes.

Blue-green requires enough spare GPU capacity for both revisions. Do not reuse
one stable ComputeDomain between old and new revisions.

## Platform Changes

Driver upgrades, feature gates, and membership-mode migrations are separate
platform operations. Consult documentation for the installed version and obtain
approval rather than applying a remembered cluster fix during model deployment.

## Required Report

Report:

1. Context, namespace, release, chart, values file, and immutable image.
2. Capacity and reservation result, including exact clique.
3. Render and Helm diff summary, including preserved live drift.
4. Actual root kind/UIDs, DRA driver version, and fixed or elastic membership mode.
5. Old worker pod and ResourceClaim cleanup result.
6. Per-ComputeDomain desired/reported node count and helper DaemonSet readiness.
7. Controller and pod readiness, restart counts, and startup stage.
8. Endpoint smoke-test result or the precise remaining blocker.
9. Cleanup deadline/guard evidence, resource teardown, and verified reservation release.
