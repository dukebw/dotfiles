from __future__ import annotations

import importlib.machinery
import importlib.util
import re
import sys
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
    sys.modules[name] = module
    loader.exec_module(module)
    return module


REXEC = load_script("rexec", ROOT / "bin" / "rexec")


class MutagenSessionNameTests(unittest.TestCase):
    def test_nested_repositories_in_different_worktrees_do_not_collide(self) -> None:
        baseten = "/Users/example/work/baseten/mp/project/trt-llm"
        baseten_k3 = "/Users/example/work/baseten-k3/mp/project/trt-llm"

        baseten_name = REXEC.mutagen_session_name(baseten, "clangd")
        baseten_k3_name = REXEC.mutagen_session_name(baseten_k3, "clangd")

        self.assertNotEqual(baseten_name, baseten_k3_name)
        self.assertRegex(baseten_name, re.compile(r"^trt-llm-[0-9a-f]{8}-clangd$"))
        self.assertRegex(baseten_k3_name, re.compile(r"^trt-llm-[0-9a-f]{8}-clangd$"))

    def test_name_is_stable_for_the_same_root(self) -> None:
        root = "/Users/example/work/baseten/mp/project/trt-llm"

        self.assertEqual(
            REXEC.mutagen_session_name(root, "clangd"),
            REXEC.mutagen_session_name(root, "clangd"),
        )

    @mock.patch.object(REXEC, "repair_halted_mutagen_session")
    @mock.patch.object(REXEC, "mutagen_session_state")
    def test_matching_legacy_session_is_reused(
        self,
        session_state: mock.Mock,
        repair: mock.Mock,
    ) -> None:
        legacy_state = {
            "status": "Watching for changes",
            "alpha_url": "/Users/example/work/baseten",
            "beta_url": "example-pod:/workspace/baseten",
        }
        session_state.side_effect = lambda name: (
            legacy_state if name == "baseten-clangd" else None
        )
        config = {
            "local_root": "/Users/example/work/baseten",
            "remote_workdir": "/workspace/baseten",
            "ssh_alias": "example-pod",
            "mutagen_session": "baseten-12345678-clangd",
            "legacy_mutagen_session": "baseten-clangd",
        }

        with mock.patch.object(REXEC, "eprint"):
            REXEC.ensure_mutagen_session(config)

        self.assertEqual(config["mutagen_session"], "baseten-clangd")
        repair.assert_called_once_with(config)

    @mock.patch.object(REXEC, "run")
    @mock.patch.object(REXEC, "mutagen_session_state")
    def test_colliding_legacy_session_creates_hashed_session(
        self,
        session_state: mock.Mock,
        run: mock.Mock,
    ) -> None:
        legacy_state = {
            "status": "Watching for changes",
            "alpha_url": "/Users/example/work/other/mp/project/trt-llm",
            "beta_url": "example-pod:/workspace/other/mp/project/trt-llm",
        }
        session_state.side_effect = lambda name: (
            legacy_state if name == "trt-llm-clangd" else None
        )
        config = {
            "local_root": "/Users/example/work/baseten/mp/project/trt-llm",
            "remote_workdir": "/workspace/baseten/mp/project/trt-llm",
            "ssh_alias": "example-pod",
            "mutagen_session": "trt-llm-12345678-clangd",
            "legacy_mutagen_session": "trt-llm-clangd",
            "ignore": [],
        }

        with mock.patch.object(REXEC, "eprint"):
            REXEC.ensure_mutagen_session(config)

        create_command = run.call_args.args[0]
        self.assertEqual(config["mutagen_session"], "trt-llm-12345678-clangd")
        self.assertEqual(create_command[0:3], ["mutagen", "sync", "create"])
        self.assertIn("trt-llm-12345678-clangd", create_command)

    @mock.patch.object(REXEC, "repair_halted_mutagen_session")
    @mock.patch.object(REXEC, "mutagen_session_state")
    def test_existing_session_with_matching_endpoints_is_reused(
        self,
        session_state: mock.Mock,
        repair: mock.Mock,
    ) -> None:
        session_state.return_value = {
            "status": "Watching for changes",
            "alpha_url": "/Users/example/work/baseten/mp/project/trt-llm",
            "beta_url": "example-pod:/workspace/baseten/mp/project/trt-llm",
        }
        config = {
            "local_root": "/Users/example/work/baseten/mp/project/trt-llm",
            "remote_workdir": "/workspace/baseten/mp/project/trt-llm",
            "ssh_alias": "example-pod",
            "mutagen_session": "trt-llm-12345678-clangd",
            "legacy_mutagen_session": "trt-llm-clangd",
        }

        with mock.patch.object(REXEC, "eprint"):
            REXEC.ensure_mutagen_session(config)

        self.assertEqual(config["mutagen_session"], "trt-llm-12345678-clangd")
        repair.assert_called_once_with(config)

    @mock.patch.object(REXEC, "run")
    @mock.patch.object(REXEC, "repair_halted_mutagen_session")
    @mock.patch.object(REXEC, "mutagen_session_state")
    def test_existing_session_with_drifted_endpoints_fails_loud(
        self,
        session_state: mock.Mock,
        repair: mock.Mock,
        run: mock.Mock,
    ) -> None:
        session_state.return_value = {
            "status": "Watching for changes",
            "alpha_url": "/Users/example/work/baseten/mp/project/trt-llm",
            "beta_url": "example-pod:/workspace/stale-trt-llm",
        }
        config = {
            "local_root": "/Users/example/work/baseten/mp/project/trt-llm",
            "remote_workdir": "/workspace/baseten/mp/project/trt-llm",
            "ssh_alias": "example-pod",
            "mutagen_session": "trt-llm-12345678-clangd",
            "legacy_mutagen_session": "trt-llm-clangd",
        }

        with mock.patch.object(REXEC, "eprint"):
            with self.assertRaises(SystemExit) as ctx:
                REXEC.ensure_mutagen_session(config)

        message = str(ctx.exception.code)
        self.assertIn("trt-llm-12345678-clangd", message)
        self.assertIn("example-pod:/workspace/stale-trt-llm", message)
        self.assertIn("example-pod:/workspace/baseten/mp/project/trt-llm", message)
        self.assertIn("mutagen sync terminate trt-llm-12345678-clangd", message)
        repair.assert_not_called()
        run.assert_not_called()

    @mock.patch.object(REXEC.subprocess, "run")
    def test_session_state_parses_sync_endpoints(self, run: mock.Mock) -> None:
        run.return_value = mock.Mock(
            returncode=0,
            stdout="""Name: trt-llm-clangd
Alpha:
\tURL: /Users/example/work/baseten/mp/project/trt-llm
\tSynchronizable contents:
\t\t10 files (1 MB)
Beta:
\tURL: example-pod:/workspace/baseten/mp/project/trt-llm
\tSynchronizable contents:
\t\t10 files (1 MB)
Status: Watching for changes
""",
        )

        state = REXEC.mutagen_session_state("trt-llm-clangd")

        self.assertEqual(
            state,
            {
                "status": "Watching for changes",
                "alpha_files": 10,
                "beta_files": 10,
                "alpha_url": "/Users/example/work/baseten/mp/project/trt-llm",
                "beta_url": "example-pod:/workspace/baseten/mp/project/trt-llm",
            },
        )


if __name__ == "__main__":
    unittest.main()
