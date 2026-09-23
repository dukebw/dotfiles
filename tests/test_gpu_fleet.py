from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    if spec is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


B10_GPU = load_script("b10_gpu", ROOT / "bin" / "b10-gpu")
GPU_FLEET = load_script("gpu_fleet", ROOT / "bin" / "gpu-fleet")


def pod(
    namespace: str,
    name: str,
    containers: list[tuple[str, int]],
    *,
    model: str = "",
    phase: str = "Running",
    container_states: dict[str, str] | None = None,
    container_readiness: dict[str, bool] | None = None,
    privileged: tuple[str, ...] = (),
) -> dict:
    labels = {"baseten.co/model": model} if model else {}
    container_states = container_states or {}
    container_readiness = container_readiness or {}
    return {
        "metadata": {"namespace": namespace, "name": name, "labels": labels},
        "spec": {
            "nodeName": f"node-{name}",
            "containers": [
                {
                    "name": container_name,
                    "resources": {"requests": {"nvidia.com/gpu": str(gpus)}},
                    **(
                        {"securityContext": {"privileged": True}}
                        if container_name in privileged
                        else {}
                    ),
                }
                for container_name, gpus in containers
            ],
        },
        "status": {
            "phase": phase,
            "containerStatuses": [
                {
                    "name": container_name,
                    "ready": container_readiness.get(
                        container_name,
                        phase == "Running"
                        and container_states.get(container_name, "running")
                        == "running",
                    ),
                    "state": {
                        container_states.get(
                            container_name,
                            "running" if phase == "Running" else "terminated",
                        ): {}
                    },
                }
                for container_name, _ in containers
            ],
        },
    }


def node(name: str, gpus: int = 0) -> dict:
    allocatable = {"nvidia.com/gpu": str(gpus)} if gpus else {}
    return {"metadata": {"name": name}, "status": {"allocatable": allocatable}}


class KubeconfigResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(directory) / "kubeconfig"
        self.root.mkdir()
        self.enterContext(
            mock.patch.object(B10_GPU, "DEFAULT_RCLI_KUBECONFIG_DIR", self.root)
        )

    def kubeconfig(self, provider: str = "") -> Path:
        path = self.root / provider / "gcp-ue4-prod-2.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def test_default_provider_resolves_duplicate_cluster_files(self) -> None:
        paths = {provider: self.kubeconfig(provider) for provider in ("rancher", "tailscale")}
        self.kubeconfig()
        for provider, expected in paths.items():
            with self.subTest(provider=provider):
                (self.root.parent / "config.yaml").write_text(
                    f"default_provider: {provider}\nselect_mode: kubectl\n"
                )
                self.assertEqual(
                    B10_GPU.rcli_kubeconfig_for_context("gcp-ue4-prod-2"),
                    str(expected),
                )

    def test_single_legacy_or_provider_file_needs_no_default(self) -> None:
        for provider in ("", "rancher", "tailscale"):
            with self.subTest(provider=provider):
                path = self.kubeconfig(provider)
                self.assertEqual(
                    B10_GPU.rcli_kubeconfig_for_context("gcp-ue4-prod-2"), str(path)
                )
                path.unlink()

    def test_ambiguous_files_without_matching_default_fail(self) -> None:
        self.kubeconfig("rancher")
        self.kubeconfig("tailscale")
        for config in ("", "default_provider: gcp\n"):
            with self.subTest(config=config):
                (self.root.parent / "config.yaml").write_text(config)
                with self.assertRaisesRegex(B10_GPU.CommandError, "default_provider"):
                    B10_GPU.rcli_kubeconfig_for_context("gcp-ue4-prod-2")

    def test_invalid_provider_config_reports_an_error(self) -> None:
        self.kubeconfig("rancher")
        self.kubeconfig("tailscale")
        for config in ("[", "- tailscale\n", "default_provider: [tailscale]\n"):
            with self.subTest(config=config):
                (self.root.parent / "config.yaml").write_text(config)
                with self.assertRaises(B10_GPU.CommandError):
                    B10_GPU.rcli_kubeconfig_for_context("gcp-ue4-prod-2")


class B10GPUFleetTests(unittest.TestCase):
    def mock_kubernetes(self, pods: list[dict], nodes: list[dict] | None = None):
        def query(ctx, args):
            if args == ["get", "nodes"]:
                return {"items": nodes or []}
            self.assertEqual(args[:2], ["get", "pods"])
            namespace = args[args.index("--namespace") + 1]
            running_only = "status.phase=Running" in args
            return {
                "items": [
                    pod
                    for pod in pods
                    if pod["metadata"]["namespace"] == namespace
                    and (not running_only or pod["status"]["phase"] == "Running")
                ]
            }

        return mock.patch.object(B10_GPU, "kubectl_json", side_effect=query)

    def test_owned_pods_cover_dev_dynamo_and_sglang_shapes(self) -> None:
        fixtures = [
            pod("baseten", "brendanduke-dev-pod-b200-0", [("dev", 1)]),
            pod(
                "dynamo",
                "debugging--0654-0-brendandukep1-ldr",
                [("main", 4)],
                model="debugging-brendanduke-trt",
            ),
            pod(
                "dynamo",
                "controller-truncated-worker",
                [("main", 4)],
                model="k3-debugging-brendanduke",
            ),
            pod(
                "mp-devenv",
                "kimi-k3-sglang-debugging-brendanduke-0",
                [("sglang", 4)],
                model="kimi-k3-sglang-debugging-brendanduke",
            ),
            pod(
                "dynamo",
                "debugging-brendanduke-trt-frontend",
                [("main", 0)],
                model="debugging-brendanduke-trt",
            ),
            pod("dynamo", "someone-elses-worker", [("main", 4)], model="other-model"),
            pod("dynamo", "brendanduke-finished", [("main", 4)], phase="Succeeded"),
            pod("other", "brendanduke-other-namespace", [("main", 4)]),
        ]
        with self.mock_kubernetes(fixtures) as query:
            result = B10_GPU.owned_pods(
                {}, list(B10_GPU.DEFAULT_FLEET_NAMESPACES), "brendanduke", False
            )

        query.assert_has_calls(
            [
                mock.call(
                    {},
                    [
                        "get", "pods", "--namespace", namespace,
                        "--field-selector", "status.phase=Running",
                    ],
                )
                for namespace in B10_GPU.DEFAULT_FLEET_NAMESPACES
            ],
            any_order=True,
        )
        self.assertEqual(query.call_count, len(B10_GPU.DEFAULT_FLEET_NAMESPACES))
        self.assertEqual(len(result), 4)
        self.assertEqual(
            {
                (row["namespace"], row["name"], row["container"], row["gpus"])
                for row in result
            },
            {
                ("baseten", "brendanduke-dev-pod-b200-0", "dev", 1),
                ("dynamo", "debugging--0654-0-brendandukep1-ldr", "main", 4),
                ("dynamo", "controller-truncated-worker", "main", 4),
                (
                    "mp-devenv",
                    "kimi-k3-sglang-debugging-brendanduke-0",
                    "sglang",
                    4,
                ),
            },
        )
        self.assertTrue(all(row["phase"] == "Running" for row in result))

    def test_all_phases_includes_terminal_gpu_pods(self) -> None:
        fixture = pod(
            "dynamo", "brendanduke-finished", [("main", 4)], phase="Succeeded"
        )
        with self.mock_kubernetes([fixture]) as query:
            result = B10_GPU.owned_pods(
                {}, list(B10_GPU.DEFAULT_FLEET_NAMESPACES), "brendanduke", True
            )

        self.assertEqual(result[0]["phase"], "Succeeded")
        query.assert_has_calls(
            [
                mock.call({}, ["get", "pods", "--namespace", namespace])
                for namespace in B10_GPU.DEFAULT_FLEET_NAMESPACES
            ],
            any_order=True,
        )
        self.assertEqual(query.call_count, len(B10_GPU.DEFAULT_FLEET_NAMESPACES))

    def test_explicit_namespace_queries_only_that_namespace(self) -> None:
        fixtures = [
            pod("custom-dev", "brendanduke-worker", [("main", 4)]),
            pod("dynamo", "brendanduke-other-worker", [("main", 4)]),
        ]
        with self.mock_kubernetes(fixtures) as query:
            result = B10_GPU.owned_pods({}, ["custom-dev"], "brendanduke", False)

        self.assertEqual([row["namespace"] for row in result], ["custom-dev"])
        query.assert_called_once_with(
            {},
            [
                "get", "pods", "--namespace", "custom-dev",
                "--field-selector", "status.phase=Running",
            ],
        )

    def test_one_row_per_gpu_container(self) -> None:
        fixture = pod(
            "dynamo",
            "brendanduke-multi-container",
            [("worker-a", 2), ("sidecar", 0), ("worker-b", 2)],
        )
        with self.mock_kubernetes([fixture]):
            result = B10_GPU.owned_pods(
                {}, list(B10_GPU.DEFAULT_FLEET_NAMESPACES), "brendanduke", False
            )

        self.assertEqual(
            [(row["container"], row["gpus"]) for row in result],
            [("worker-a", 2), ("worker-b", 2)],
        )

    def test_only_running_gpu_containers_are_monitorable(self) -> None:
        fixtures = [
            pod(
                "dynamo",
                "brendanduke-crashloop",
                [("main", 4)],
                container_states={"main": "waiting"},
            ),
            pod(
                "dynamo",
                "brendanduke-starting",
                [("main", 4)],
                container_readiness={"main": False},
            ),
        ]
        with self.mock_kubernetes(fixtures):
            result = B10_GPU.owned_pods(
                {}, list(B10_GPU.DEFAULT_FLEET_NAMESPACES), "brendanduke", False
            )

        self.assertEqual([row["name"] for row in result], ["brendanduke-starting"])

    def test_privileged_pod_on_gpu_node_is_fleeted_as_observer(self) -> None:
        # Privileged dev pods request no nvidia.com/gpu yet see every node GPU
        # via device passthrough — the fleet reports the node's allocation.
        dev = pod(
            "baseten",
            "b200-debugging-brendanduke-dev-0",
            [("dev", 0)],
            privileged=("dev",),
        )
        nodes = [node("node-b200-debugging-brendanduke-dev-0", gpus=8)]
        with self.mock_kubernetes([dev], nodes):
            result = B10_GPU.owned_pods(
                {}, list(B10_GPU.DEFAULT_FLEET_NAMESPACES), "brendanduke", False
            )

        self.assertEqual(
            [(row["name"], row["container"], row["gpus"]) for row in result],
            [("b200-debugging-brendanduke-dev-0", "dev", 8)],
        )

    def test_privileged_pod_on_gpu_less_node_stays_out_of_fleet(self) -> None:
        clangd = pod(
            "baseten",
            "remote-clangd-debugging-brendanduke-0",
            [("dev", 0)],
            privileged=("dev",),
        )
        nodes = [node("node-remote-clangd-debugging-brendanduke-0")]
        with self.mock_kubernetes([clangd], nodes):
            result = B10_GPU.owned_pods(
                {}, list(B10_GPU.DEFAULT_FLEET_NAMESPACES), "brendanduke", False
            )

        self.assertEqual(result, [])

    def test_unprivileged_zero_request_pod_needs_no_node_query(self) -> None:
        plain = pod("baseten", "brendanduke-cpu-only", [("dev", 0)])
        with self.mock_kubernetes([plain]) as kubectl_json_mock:
            result = B10_GPU.owned_pods(
                {}, list(B10_GPU.DEFAULT_FLEET_NAMESPACES), "brendanduke", False
            )

        self.assertEqual(result, [])
        self.assertEqual(kubectl_json_mock.call_count, len(B10_GPU.DEFAULT_FLEET_NAMESPACES))


class GPUFleetLauncherTests(unittest.TestCase):
    def test_six_panes_use_a_two_by_three_grid(self) -> None:
        geometries = GPU_FLEET.geometry(6)

        self.assertEqual(len(geometries), 6)
        self.assertEqual({geometry["x"] for geometry in geometries}, {"0%", "50%"})
        self.assertEqual(
            {geometry["y"] for geometry in geometries}, {"0%", "33%", "66%"}
        )
        self.assertTrue(all(geometry["width"] == "50%" for geometry in geometries))
        self.assertTrue(all(geometry["height"] == "33%" for geometry in geometries))

    def test_eight_panes_use_a_two_by_four_grid(self) -> None:
        geometries = GPU_FLEET.geometry(8)

        self.assertEqual(len(geometries), 8)
        self.assertEqual({geometry["x"] for geometry in geometries}, {"0%", "50%"})
        self.assertEqual(
            {geometry["y"] for geometry in geometries},
            {"0%", "25%", "50%", "75%"},
        )
        self.assertTrue(all(geometry["width"] == "50%" for geometry in geometries))
        self.assertTrue(all(geometry["height"] == "25%" for geometry in geometries))

    def test_full_nvl72_rack_uses_a_two_by_nine_grid(self) -> None:
        geometries = GPU_FLEET.geometry(18)

        self.assertEqual(len(geometries), 18)
        self.assertEqual({geometry["x"] for geometry in geometries}, {"0%", "50%"})
        self.assertEqual(
            {geometry["y"] for geometry in geometries},
            {"0%", "11%", "22%", "33%", "44%", "55%", "66%", "77%", "88%"},
        )
        self.assertTrue(all(geometry["width"] == "50%" for geometry in geometries))
        self.assertTrue(all(geometry["height"] == "11%" for geometry in geometries))

    def test_pane_key_includes_container(self) -> None:
        self.assertEqual(
            GPU_FLEET.pod_key(
                {
                    "context": "ali-apse8-mpdev-1",
                    "namespace": "dynamo",
                    "name": "worker",
                    "container": "main",
                }
            ),
            "v6:ali-apse8-mpdev-1:dynamo/worker:main",
        )

    def test_fleet_merges_selected_and_unique_extra_contexts(self) -> None:
        selected = {
            "context": "gcp-ue4-prod-2",
            "kubeconfig": "/tmp/gcp",
            "pods": [{"name": "gcp-worker"}],
        }
        ali = {
            "context": "ali-apse8-mpdev-1",
            "kubeconfig": "/tmp/ali",
            "pods": [{"name": "ali-worker"}],
        }
        with mock.patch.object(
            GPU_FLEET, "query_fleet", side_effect=[selected, ali]
        ) as query:
            pods = GPU_FLEET.fleet(
                ["gcp-ue4-prod-2", "ali-apse8-mpdev-1", "ali-apse8-mpdev-1"]
            )

        self.assertEqual(
            query.call_args_list,
            [mock.call(), mock.call("ali-apse8-mpdev-1")],
        )
        self.assertEqual(
            pods,
            [
                {
                    "name": "gcp-worker",
                    "context": "gcp-ue4-prod-2",
                    "kubeconfig": "/tmp/gcp",
                },
                {
                    "name": "ali-worker",
                    "context": "ali-apse8-mpdev-1",
                    "kubeconfig": "/tmp/ali",
                },
            ],
        )

    def test_live_pane_ids_uses_zellij_launch_commands_in_current_tab(self) -> None:
        panes = [
            {
                "id": 10,
                "is_plugin": False,
                "exited": False,
                "tab_id": 2,
                "terminal_command": "gpu-fleet",
            },
            {
                "id": 11,
                "is_plugin": False,
                "exited": False,
                "tab_id": 2,
                "terminal_command": (
                    "env GPU_FLEET_PANE=v6:gcp:dynamo/worker:main kubectl exec"
                ),
            },
            {
                "id": 12,
                "is_plugin": False,
                "exited": False,
                "tab_id": 2,
                "terminal_command": (
                    "env GPU_FLEET_PANE=v6:gcp:dynamo/worker:main kubectl exec"
                ),
            },
            {
                "id": 13,
                "is_plugin": False,
                "exited": True,
                "tab_id": 2,
                "terminal_command": (
                    "env GPU_FLEET_PANE=v6:gcp:dynamo/exited:main kubectl exec"
                ),
            },
            {
                "id": 14,
                "is_plugin": False,
                "exited": False,
                "tab_id": 3,
                "terminal_command": (
                    "env GPU_FLEET_PANE=v6:gcp:dynamo/other-tab:main kubectl exec"
                ),
            },
        ]
        result = mock.Mock(returncode=0, stdout=json.dumps(panes), stderr="")
        with (
            mock.patch.dict(GPU_FLEET.os.environ, {"ZELLIJ_PANE_ID": "10"}),
            mock.patch.object(GPU_FLEET.subprocess, "run", return_value=result),
        ):
            pane_ids = GPU_FLEET.live_pane_ids()

        self.assertEqual(pane_ids, {"v6:gcp:dynamo/worker:main": [11, 12]})

    def test_main_spawns_only_the_missing_pane(self) -> None:
        pods = [
            {
                "namespace": "dynamo",
                "name": "worker-a",
                "container": "main",
                "context": "gcp",
                "kubeconfig": "/tmp/kubeconfig",
                "model": "model-a",
                "node": "apse8-a0001",
            },
            {
                "namespace": "dynamo",
                "name": "worker-b",
                "container": "main",
                "context": "ali",
                "kubeconfig": "/tmp/kubeconfig",
                "model": "model-b",
                "node": "apse8-a0002",
            },
        ]
        result = mock.Mock(returncode=0, stderr="")
        with (
            mock.patch.dict(GPU_FLEET.os.environ, {"ZELLIJ": "1"}),
            mock.patch.object(GPU_FLEET, "fleet", return_value=pods),
            mock.patch.object(
                GPU_FLEET,
                "live_pane_ids",
                return_value={GPU_FLEET.pod_key(pods[0]): [41]},
            ),
            mock.patch.object(GPU_FLEET.subprocess, "run", return_value=result) as run,
        ):
            GPU_FLEET.main()

        commands = [call.args[0] for call in run.call_args_list]
        spawned = [command for command in commands if command[:2] == ["zellij", "run"]]
        self.assertEqual(len(spawned), 1)
        self.assertIn(f"{GPU_FLEET.MARKER}={GPU_FLEET.pod_key(pods[1])}", spawned[0])
        self.assertFalse(
            any(
                "close-pane" in command or "toggle-floating-panes" in command
                for command in commands
            )
        )

    def test_main_closes_only_duplicate_and_stale_panes(self) -> None:
        fleet_pod = {
            "namespace": "dynamo",
            "name": "worker",
            "container": "main",
            "context": "gcp",
            "kubeconfig": "/tmp/kubeconfig",
            "model": "model",
            "node": "apse8-a0001",
        }
        key = GPU_FLEET.pod_key(fleet_pod)
        result = mock.Mock(returncode=0, stderr="")
        with (
            mock.patch.dict(GPU_FLEET.os.environ, {"ZELLIJ": "1"}),
            mock.patch.object(GPU_FLEET, "fleet", return_value=[fleet_pod]),
            mock.patch.object(
                GPU_FLEET,
                "live_pane_ids",
                return_value={key: [41, 42], "v5:dynamo/old-worker:main": [43]},
            ),
            mock.patch.object(GPU_FLEET.subprocess, "run", return_value=result) as run,
        ):
            GPU_FLEET.main()

        commands = [call.args[0] for call in run.call_args_list]
        closed_pane_ids = [
            command[command.index("--pane-id") + 1]
            for command in commands
            if "close-pane" in command
        ]
        self.assertCountEqual(
            closed_pane_ids,
            ["terminal_42", "terminal_43"],
        )
        self.assertTrue(
            any(
                "change-floating-pane-coordinates" in command
                and "terminal_41" in command
                for command in commands
            )
        )
        self.assertFalse(any(command[:2] == ["zellij", "run"] for command in commands))

    def test_pane_command_targets_gpu_container_and_has_fallbacks(self) -> None:
        fleet_pod = {
            "namespace": "mp-devenv",
            "name": "sglang-worker",
            "container": "sglang",
            "context": "ali-apse8-mpdev-1",
            "kubeconfig": "/tmp/kubeconfig",
            "model": "kimi-k3-sglang-debugging-brendanduke",
            "node": "apse8-a0001",
        }
        command = GPU_FLEET.pane_command(
            fleet_pod,
            {"x": "1%", "y": "2%", "width": "90%", "height": "80%"},
        )

        self.assertIn(
            "GPU_FLEET_PANE=v6:ali-apse8-mpdev-1:mp-devenv/sglang-worker:sglang",
            command,
        )
        self.assertEqual(command[command.index("-c") + 1], "sglang")
        monitor_command = command[-1]
        self.assertIn("command -v nvitop", monitor_command)
        self.assertIn("uvx --from nvitop nvitop", monitor_command)
        self.assertIn("nvidia-smi -l 1", monitor_command)


if __name__ == "__main__":
    unittest.main()
