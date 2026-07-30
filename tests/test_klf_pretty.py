from __future__ import annotations

import importlib.machinery
import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path


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


KLF = load_script("klf_pretty", ROOT / "bin" / "klf-pretty")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class RecordParsingTests(unittest.TestCase):
    def test_json_adapter_populates_the_engine_neutral_record(self) -> None:
        line = (
            "[pod/model-frontend-65f8494bb4-b6fmr/main] "
            "2026-07-30T22:25:24.085272527+08:00 "
            '{"timestamp":"2026-07-30T14:25:24.084991Z",'
            '"level":"warning","logger":"common.rate_limiting.rate_limit",'
            '"file":"/workspace/rate_limit.py","line":98,'
            '"message":"No router available","status":"503"}'
        )

        record = KLF.parse_record(line)

        self.assertEqual(
            record.source,
            KLF.LogSource(
                pod="model-frontend-65f8494bb4-b6fmr", container="main"
            ),
        )
        self.assertEqual(record.timestamp, "2026-07-30T22:25:24.085272527+08:00")
        self.assertEqual(record.level, "WARN")
        self.assertEqual(record.logger, "common.rate_limiting.rate_limit")
        self.assertEqual(record.message, "No router available")
        self.assertEqual(record.location, "/workspace/rate_limit.py:98")
        self.assertEqual(record.fields, (("status", "503"),))
        self.assertEqual(record.raw, line)

    def test_unknown_format_preserves_its_body_and_ansi(self) -> None:
        body = "\x1b[33mRank0 Task exit code: 1\x1b[0m  "
        line = (
            "[pod/sglang-worker-0/sglang] "
            f"2026-07-30T14:25:23.303050648Z {body}"
        )

        record = KLF.parse_record(line)

        self.assertEqual(record.source, KLF.LogSource("sglang-worker-0", "sglang"))
        self.assertEqual(record.timestamp, "2026-07-30T14:25:23.303050648Z")
        self.assertEqual(record.message, body)
        self.assertIsNone(record.level)
        self.assertIsNone(record.logger)
        self.assertEqual(record.raw, line)

    def test_invalid_json_uses_the_raw_fallback(self) -> None:
        record = KLF.parse_record("{not-json}")

        self.assertEqual(record.message, "{not-json}")
        self.assertEqual(record.fields, ())


class RendererTests(unittest.TestCase):
    def test_renderer_normalizes_time_and_aligns_columns(self) -> None:
        line = (
            "[pod/model-frontend-65f8494bb4-b6fmr/main] "
            "2026-07-30T22:25:24.085272527+08:00 "
            '{"level":"warning","logger":"common.rate_limiting.rate_limit",'
            '"message":"No router available"}'
        )

        rendered = KLF.Renderer(color=False).render(KLF.parse_record(line))

        self.assertEqual(rendered[0:12], "14:25:24.085")
        self.assertEqual(rendered[13:18], "WARN ")
        self.assertEqual(rendered[19:43].rstrip(), "model-frontend/b6fmr")
        self.assertEqual(rendered[44:62].rstrip(), "rate_limit")
        self.assertEqual(rendered[63:], "No router available")

    def test_structured_fields_are_unambiguous(self) -> None:
        record = KLF.parse_record(
            '{"timestamp":"2026-07-30T14:25:24Z","level":"info",'
            '"logger":"package.module","message":"hello",'
            '"plain":"ok","spaced":"two words","empty":"",'
            '"nested":{"ready":true}}'
        )

        rendered = KLF.Renderer(color=False).render(record)

        self.assertTrue(
            rendered.endswith(
                'hello plain=ok spaced="two words" empty="" nested={"ready":true}'
            )
        )

    def test_embedded_newlines_remain_one_physical_line(self) -> None:
        record = KLF.parse_record('{"message":"first\\nsecond"}')

        rendered = KLF.Renderer(color=False).render(record)

        self.assertIn("first\\nsecond", rendered)
        self.assertNotIn("first\nsecond", rendered)

    def test_source_shortening_handles_common_kubernetes_shapes(self) -> None:
        deployment = KLF.LogSource(
            "debugging-brendanduke-trt-router-65c6007f-5464479b97-f9rhw",
            "main",
        )
        grove = KLF.LogSource(
            "debugging--0654-0-brendanduked1-0-brendanduked1-ldr-tw4zr",
            "main",
        )
        stateful = KLF.LogSource(
            "kimi-k3-sglang-debugging-brendanduke-0",
            "sglang",
        )
        grove_init = KLF.LogSource(
            "debugging--0654-0-brendanduked1-0-brendanduked1-ldr-d99ws",
            "grove-initc",
        )

        self.assertEqual(KLF.source_label(deployment, 24), "trt-router/f9rhw")
        self.assertEqual(len(KLF.source_label(grove, 24)), 24)
        self.assertTrue(KLF.source_label(grove, 24).endswith("ldr-tw4zr"))
        self.assertEqual(KLF.source_label(stateful, 24), "brendanduke-0:sglang")
        self.assertEqual(KLF.source_label(grove_init, 24), "ldr-d99ws:grove-initc")

    def test_color_does_not_change_visible_layout(self) -> None:
        record = KLF.parse_record(
            "[pod/model-router-12345678-abcde/main] "
            '2026-07-30T14:25:24Z {"level":"error","message":"failed"}'
        )
        plain = KLF.Renderer(color=False).render(record)
        colored = KLF.Renderer(color=True).render(record)

        self.assertEqual(ANSI.sub("", colored), plain)
        self.assertIn("\x1b[1;31m", colored)
        self.assertIn("\x1b[38;5;", colored)


class CommandTests(unittest.TestCase):
    def test_executable_formats_a_pipe_without_adding_color(self) -> None:
        line = (
            "[pod/model-router-12345678-abcde/main] "
            '2026-07-30T14:25:24Z {"level":"info","message":"ready"}\n'
        )

        result = subprocess.run(
            [str(ROOT / "bin" / "klf-pretty")],
            input=line,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.count("\n"), 1)
        self.assertNotRegex(result.stdout, ANSI)
        self.assertTrue(result.stdout.endswith("ready\n"))


if __name__ == "__main__":
    unittest.main()
