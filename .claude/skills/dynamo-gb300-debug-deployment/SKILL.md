---
name: dynamo-gb300-debug-deployment
description: Deploy, upgrade, verify, and recover GB300 DynamoGraphDeployment debug or development workloads with Grove and NVIDIA ComputeDomains. Use for DGD or Dynamo model Helm deployments on ali-apse8-mpdev-1 or similar workload-plane clusters, especially two-node MNNVL workers, ComputeDomain membership, ResourceClaim cleanup, safe image upgrades, and CUDA_ERROR_NOT_READY failures.
---

# Dynamo GB300 Debug Deployment

Deploy GB300 Dynamo workloads without overlapping old and new MNNVL claims.
Examples default to `ali-apse8-mpdev-1`, but derive cluster-specific names,
labels, namespaces, and paths from the selected values file and live resources.

## Scope

Use this skill for debug and development deployments that combine:

- `DynamoGraphDeployment` workers managed through Grove.
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
- Require explicit user approval before deleting an existing DGD unless the
  user already requested deployment or upgrade of that named debug release.
- Every deployment created for Brendan must have a short base name containing
  the exact contiguous segment `-debugging-brendanduke`.
- After creation, verify every generated pod name contains both `debugging` and
  `brendanduke`. Rename and recreate if controller truncation removes either.
- Do not patch `ComputeDomain.status.nodes` during a normal rollout. A status
  patch is recovery-only because it races the NVIDIA controller.
- Do not treat `ComputeDomain.status.status=Ready` as sufficient on the legacy
  DRA driver. Verify cardinality, claims, and helper DaemonSets.
- Preserve unrelated live configuration drift. Diff before upgrade and ask if
  the desired values are ambiguous.

## Required Inputs

Make these explicit before changing the cluster:

```bash
CONTEXT=ali-apse8-mpdev-1
NAMESPACE=dynamo
RELEASE=<name-containing--debugging-brendanduke>
VALUES_FILE=<absolute-path-to-values.yaml>
CHART_DIR=<absolute-path-to-helm/charts/baseten-dynamo-model>
IMAGE=<immutable-dynamo-image-reference>
```

Discover rather than guess the worker rack DGD and ComputeDomains:

```bash
kubectl --context "$CONTEXT" -n "$NAMESPACE" get dynamographdeployments \
  -l "baseten.co/model=$RELEASE"

kubectl --context "$CONTEXT" -n "$NAMESPACE" get computedomains \
  -l "baseten.co/model=$RELEASE"
```

For the known K3 debug deployment, the defaults are:

```text
context: ali-apse8-mpdev-1
namespace: dynamo
release: k3-mtp-debugging-brendanduke
rack DGD: k3-mtp-debugging-brendanduke-rack-01
```

Do not carry these resource names to another deployment.

## Preflight

Confirm context and permissions:

```bash
kubectl --context "$CONTEXT" cluster-info
kubectl --context "$CONTEXT" auth can-i get pods -n "$NAMESPACE"
kubectl --context "$CONTEXT" auth can-i delete dynamographdeployments -n "$NAMESPACE"
kubectl --context "$CONTEXT" auth can-i get resourceclaims -n "$NAMESPACE"
kubectl --context "$CONTEXT" auth can-i get computedomains -n "$NAMESPACE"
```

Inspect the release, image, worker DGDs, ComputeDomains, claims, and pods:

```bash
helm --kube-context "$CONTEXT" -n "$NAMESPACE" status "$RELEASE"
helm --kube-context "$CONTEXT" -n "$NAMESPACE" get values "$RELEASE" -o yaml

kubectl --context "$CONTEXT" -n "$NAMESPACE" get dynamographdeployments \
  -l "baseten.co/model=$RELEASE" -o wide
kubectl --context "$CONTEXT" -n "$NAMESPACE" get computedomains \
  -l "baseten.co/model=$RELEASE" -o yaml
kubectl --context "$CONTEXT" -n "$NAMESPACE" get resourceclaims -o wide
kubectl --context "$CONTEXT" -n "$NAMESPACE" get pods \
  -l "baseten.co/model=$RELEASE" -o wide
```

Identify the installed DRA driver version. Legacy installations such as
`v25.3.2` use `spec.numNodes` and `status.nodes` and require the recreate
procedure below.

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
helm template "$RELEASE" "$CHART_DIR" \
  -n "$NAMESPACE" \
  -f "$VALUES_FILE" >"$RENDERED"
kubeconform -strict -summary -ignore-missing-schemas "$RENDERED"
```

Inspect all rendered image references and reject unintended changes:

```bash
grep -o 'image: .*' "$RENDERED" | sort -u
HELM_DIFF_COLOR=false helm --kube-context "$CONTEXT" diff upgrade \
  "$RELEASE" "$CHART_DIR" \
  -n "$NAMESPACE" \
  -f "$VALUES_FILE" \
  --allow-unreleased
```

Do not silently overwrite live drift. If only some source changes should ship,
render a temporary deployment values file that preserves the intended live
values, explain it, and keep the source file aligned with the user's decision.

## Legacy MNNVL Recreate Upgrade

Until the DRA driver is upgraded, do not allow a two-node MNNVL group to roll
with old and replacement ResourceClaims concurrently.

For a debug deployment, use this sequence:

1. Delete the worker rack DGD, or scale all of its worker components to zero.
2. Wait until its worker pods and ResourceClaims are deleted.
3. Verify each ComputeDomain has no stale membership.
4. Apply the Helm image upgrade.
5. Restore workers if they were scaled separately. Helm recreates a deleted rack
   DGD from the desired values.
6. Wait for each ComputeDomain helper DaemonSet to reach exactly the expected
   ready count.
7. Only then allow TRT-LLM initialization to be considered healthy.

Deleting the rack DGD is the simpler debug workflow because it replaces the
whole tightly coupled worker graph. Record its manifest first:

```bash
RACK_DGD=<discovered-worker-rack-dgd>
DGD_BACKUP=$(mktemp)
kubectl --context "$CONTEXT" -n "$NAMESPACE" get dynamographdeployment \
  "$RACK_DGD" -o yaml >"$DGD_BACKUP"
printf 'Saved rack DGD to %s\n' "$DGD_BACKUP"
kubectl --context "$CONTEXT" -n "$NAMESPACE" delete dynamographdeployment \
  "$RACK_DGD"
```

Do not proceed merely because pods disappeared. Poll until no worker pods owned
by the rack DGD and no release ResourceClaims remain. Rancher watch streams may
end with HTTP/2 `INTERNAL_ERROR`, so prefer bounded GET polling over a single
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

Before re-creation, legacy ComputeDomains should have no old worker membership.
If status remains populated after all old pods and claims are gone, stop. Treat
that as a DRA controller cleanup failure; do not start replacement workers into
the stale domain.

Apply the already validated release:

```bash
helm --kube-context "$CONTEXT" upgrade --install \
  "$RELEASE" "$CHART_DIR" \
  -n "$NAMESPACE" \
  -f "$VALUES_FILE"
```

## ComputeDomain Gates

For legacy domains, compare desired and reported membership explicitly:

```bash
kubectl --context "$CONTEXT" -n "$NAMESPACE" get computedomains \
  -l "baseten.co/model=$RELEASE" -o json |
  jq -r '.items[]
    | [.metadata.name,
       (.spec.numNodes | tostring),
       ((.status.nodes // []) | length | tostring),
       (.status.status // ""),
       ((.status.nodes // []) | map(.name) | join(","))]
    | @tsv'
```

Require all of the following before declaring fabric setup healthy:

- `length(status.nodes) == spec.numNodes` for every legacy ComputeDomain.
- Exactly one allocated and reserved claim per current worker pod.
- Every claim owner and `reservedFor` entry names a current pod.
- The generated helper DaemonSet has `desiredNumberScheduled == numberReady ==
  spec.numNodes`.
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
  -l "baseten.co/model=$RELEASE" -o name
```

Poll DGD conditions and pod readiness with bounded `get` calls. Do not interpret
Rancher watch-stream `INTERNAL_ERROR` warnings as workload failures.

```bash
kubectl --context "$CONTEXT" -n "$NAMESPACE" get dynamographdeployments \
  -l "baseten.co/model=$RELEASE" -o json |
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
  sh -c "ps -eo pid,etimes,pcpu,pmem,comm,args | \
    grep -E 'nvcc|ptxas|ninja|gcc|cc1plus' | grep -v grep || true"
```

After all DGDs report Ready, verify the old worker image has no remaining pods,
the frontend image stayed pinned when intended, and the endpoint passes the
requested smoke test.

## Recovery Only

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

For production with no downtime, use blue-green deployments with distinct DGD,
ComputeDomain, and channel-template names. Each revision gets an isolated
ComputeDomain. Move traffic only after the new revision's claims, helper
DaemonSets, workers, and endpoint are healthy. Delete the old revision only
after drain completes.

Blue-green requires enough spare GPU capacity for both revisions. Do not reuse
one stable ComputeDomain between old and new revisions.

## Long-Term Platform Fix

Upgrade the NVIDIA DRA driver and enable:

```yaml
featureGates:
  IMEXDaemonsWithDNSNames: true
  ComputeDomainCliques: true
```

With a compatible current driver, follow NVIDIA guidance to set
`ComputeDomain.spec.numNodes: 0` and inspect `ComputeDomainClique` resources for
membership. Validate this on GB300 before removing the legacy recreate gate.

## Required Report

Report:

1. Context, namespace, release, chart, values file, and immutable image.
2. Capacity and reservation result, including exact clique.
3. Render and Helm diff summary, including preserved live drift.
4. DRA driver version and whether the legacy recreate path was used.
5. Old worker pod and ResourceClaim cleanup result.
6. Per-ComputeDomain desired/reported node count and helper DaemonSet readiness.
7. DGD and pod readiness, restart counts, and startup stage.
8. Endpoint smoke-test result or the precise remaining blocker.
