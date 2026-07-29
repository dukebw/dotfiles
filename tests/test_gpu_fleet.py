from __future__ import annotations

import importlib.machinery
import importlib.util
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
) -> dict:
    labels = {"baseten.co/model": model} if model else {}
    return {
        "metadata": {"namespace": namespace, "name": name, "labels": labels},
        "spec": {
            "nodeName": f"node-{name}",
            "containers": [
                {
                    "name": container_name,
                    "resources": {"requests": {"nvidia.com/gpu": str(gpus)}},
                }
                for container_name, gpus in containers
            ],
        },
        "status": {
            "phase": phase,
            "containerStatuses": [
                {"name": container_name, "ready": phase == "Running"}
                for container_name, _ in containers
            ],
        },
    }


class B10GPUFleetTests(unittest.TestCase):
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
        with mock.patch.object(
            B10_GPU, "kubectl_json", return_value={"items": fixtures}
        ):
            result = B10_GPU.owned_pods(
                {}, list(B10_GPU.DEFAULT_FLEET_NAMESPACES), "brendanduke", False
            )

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
        with mock.patch.object(
            B10_GPU, "kubectl_json", return_value={"items": [fixture]}
        ):
            result = B10_GPU.owned_pods(
                {}, list(B10_GPU.DEFAULT_FLEET_NAMESPACES), "brendanduke", True
            )

        self.assertEqual(result[0]["phase"], "Succeeded")

    def test_one_row_per_gpu_container(self) -> None:
        fixture = pod(
            "dynamo",
            "brendanduke-multi-container",
            [("worker-a", 2), ("sidecar", 0), ("worker-b", 2)],
        )
        with mock.patch.object(
            B10_GPU, "kubectl_json", return_value={"items": [fixture]}
        ):
            result = B10_GPU.owned_pods(
                {}, list(B10_GPU.DEFAULT_FLEET_NAMESPACES), "brendanduke", False
            )

        self.assertEqual(
            [(row["container"], row["gpus"]) for row in result],
            [("worker-a", 2), ("worker-b", 2)],
        )


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
                {"namespace": "dynamo", "name": "worker", "container": "main"}
            ),
            "v5:dynamo/worker:main",
        )

    def test_pane_command_targets_gpu_container_and_has_fallbacks(self) -> None:
        fleet_pod = {
            "namespace": "mp-devenv",
            "name": "sglang-worker",
            "container": "sglang",
            "model": "kimi-k3-sglang-debugging-brendanduke",
            "node": "apse8-a0001",
        }
        command = GPU_FLEET.pane_command(
            {"kubeconfig": "/tmp/kubeconfig"},
            fleet_pod,
            {"x": "1%", "y": "2%", "width": "90%", "height": "80%"},
        )

        self.assertIn("GPU_FLEET_PANE=v5:mp-devenv/sglang-worker:sglang", command)
        self.assertEqual(command[command.index("-c") + 1], "sglang")
        monitor_command = command[-1]
        self.assertIn("command -v nvitop", monitor_command)
        self.assertIn("uvx --from nvitop nvitop", monitor_command)
        self.assertIn("nvidia-smi -l 1", monitor_command)


if __name__ == "__main__":
    unittest.main()
