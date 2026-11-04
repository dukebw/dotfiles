# b10-gpu

`b10-gpu fleet` lists the GPU containers you own. `bin/gpu-fleet` builds its
Zellij monitor panes on this query (ADR 0001). For node, GPU, and dev-pod
management, use `intertubin` (`intertubin nodes`, `intertubin gpus`,
`intertubin pods`).

The tool uses the current `kubectl` context selected by `rcli select`, then runs
Kubernetes commands against the matching rcli-generated kubeconfig under
`~/.rcli/kubeconfig/`. If several providers contain the same context, it uses
`default_provider` from `~/.rcli/config.yaml`, such as
`~/.rcli/kubeconfig/tailscale/<context>.yaml`. A single matching provider or
legacy `~/.rcli/kubeconfig/<context>.yaml` file also works. Run this first:

```bash
rcli select
```

## List Your GPU Fleet

```bash
b10-gpu fleet
b10-gpu --namespace dynamo fleet
```

By default, fleet discovery queries `baseten`, `baseten-devenv`, `dynamo`, and
`mp-devenv` concurrently, with `status.phase=Running` filtered by the API server.
`--all-phases` includes terminal and pending pods in those same namespaces.
It selects pods whose name, `baseten.co/model`, or Helm
instance label contains the owner token, then returns one row per container
with a positive `nvidia.com/gpu` request. This includes owned managed serving
workers while excluding their CPU frontends and routers. Results include the
namespace, GPU container, requested GPU count, readiness, and node.
