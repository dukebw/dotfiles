import importlib.machinery
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("review_pr", str(ROOT / "bin/review-pr"))
spec = importlib.util.spec_from_loader(loader.name, loader)
review = importlib.util.module_from_spec(spec)
loader.exec_module(review)
HELPER = Path.home() / "work/baseten" / review.PROJECT / "bin/sglang_dev.py"


class ReviewPRTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="review-pr-test-", dir=Path.home() / "work"
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.checkout = self.root / "baseten"
        self.worktree = self.root / "baseten-pr1"
        self.init_repo(self.checkout)
        (self.checkout / ".gitignore").write_text(f"/{review.PROJECT}/sglang/\n")
        (self.checkout / "file").write_text("original\n")
        self.commit(self.checkout)

    def init_repo(self, path):
        review.run("git", "init", path)
        review.git(path, "config", "user.name", "Review fixture")
        review.git(path, "config", "user.email", "review@example.test")
        review.git(path, "config", "commit.gpgsign", "false")
        review.git(path, "config", "core.hooksPath", "/dev/null")

    def commit(self, path):
        review.git(path, "add", "-A")
        review.git(path, "commit", "-m", "Fixture")
        return review.git(path, "rev-parse", "HEAD")

    def prepare_worktree(self):
        return review.prepare_worktree(
            self.checkout,
            self.worktree,
            "basetenlabs/baseten",
            review.git(self.checkout, "rev-parse", "HEAD"),
        )

    def test_dirty_worktree_and_local_commits_are_preserved(self):
        _, state = self.prepare_worktree()
        self.prepare_worktree()
        (self.worktree / "file").write_text("user edit\n")
        with self.assertRaisesRegex(RuntimeError, "Preserve local changes"):
            self.prepare_worktree()
        local_head = self.commit(self.worktree)
        with self.assertRaisesRegex(RuntimeError, "HEAD changed"):
            self.prepare_worktree()
        self.assertNotEqual(local_head, state["head"])
        self.assertEqual((self.worktree / "file").read_text(), "user edit\n")
        self.assertEqual(review.git(self.worktree, "rev-parse", "HEAD"), local_head)

    def test_existing_worktree_is_not_claimed(self):
        review.git(self.checkout, "worktree", "add", "--detach", self.worktree, "HEAD")
        with self.assertRaisesRegex(RuntimeError, "not created by review-pr"):
            self.prepare_worktree()

    def test_review_worktree_repo_mismatch_is_rejected(self):
        state_path, state = self.prepare_worktree()
        with self.assertRaisesRegex(RuntimeError, "belongs to"):
            review.prepare_worktree(
                self.checkout, self.worktree, "other/baseten", state["head"]
            )
        self.assertEqual(json.loads(state_path.read_text()), state)

    def test_main_opens_review_tabs_in_both_zellij_launch_modes(self):
        work = self.root / "work"
        work.mkdir()
        self.checkout = self.checkout.rename(work / "baseten")
        self.worktree = work / "baseten-pr1"
        baseline = review.git(self.checkout, "rev-parse", "HEAD")
        (self.checkout / "file").write_text("PR change\n")
        head = self.commit(self.checkout)
        review.git(self.checkout, "update-ref", "refs/pull/1/head", head)
        execute = review.run
        opened = []

        def local_tools(*args, **kwargs):
            if args[:3] == ("gh", "pr", "view"):
                return json.dumps({"headRefOid": head, "baseRefOid": baseline})
            if args[0] == "zellij":
                opened.append(args)
                return ""
            args = tuple(
                str(self.checkout)
                if arg == "https://github.com/basetenlabs/baseten.git"
                else arg
                for arg in args
            )
            return execute(*args, **kwargs)

        with (
            mock.patch.object(review.Path, "home", return_value=self.root),
            mock.patch.object(review, "run", side_effect=local_tools),
        ):
            for options, in_session in (
                (["--ai"], True),
                (["--ai"], False),
                ([], True),
                ([], False),
                (["--prepare-only"], True),
            ):
                with (
                    self.subTest(options=options, in_session=in_session),
                    mock.patch.object(review.sys, "argv", ["review-pr", "1", *options]),
                    mock.patch.dict(
                        review.os.environ,
                        {"ZELLIJ_SESSION_NAME": "review-test" if in_session else ""},
                    ),
                    mock.patch.object(review.os, "execvp") as attach,
                ):
                    opened.clear()
                    review.main()
                    git_dir = review.git(
                        self.worktree, "rev-parse", "--absolute-git-dir"
                    )
                    metadata = Path(git_dir) / "pr-review"
                    filename = "agent.kdl" if "--ai" in options else "layout.kdl"
                    view = metadata / filename
                    contents = view.read_text()
                    tabs = re.findall(r'^\s*tab name="([^"]+)"', contents, re.M)
                    self.assertEqual(
                        tabs, ["PR 1", "AI review 1"] if "--ai" in options else ["PR 1"]
                    )
                    self.assertIn('tab name="PR 1" focus=true', contents)
                    self.assertIn('pane name="GitHub review #1"', contents)
                    self.assertIn(f"DiffviewOpen {baseline}..{head}", contents)
                    if "--ai" in options:
                        self.assertIn('pane name="OpenCode review"', contents)
                        self.assertIn(f'"--model" "{review.REVIEW_MODEL}"', contents)
                    if "--prepare-only" in options:
                        self.assertEqual(opened, [])
                        attach.assert_not_called()
                    elif in_session:
                        self.assertEqual(
                            opened, [("zellij", "action", "new-tab", "--layout", view)]
                        )
                        attach.assert_not_called()
                    else:
                        self.assertEqual(opened, [])
                        attach.assert_called_once_with(
                            "zellij", ["zellij", "--layout", str(view)]
                        )
            (self.worktree / "file").write_text("local edit\n")
            opened.clear()
            with (
                mock.patch.object(review.sys, "argv", ["review-pr", "1", "--ai"]),
                mock.patch.object(review.os, "execvp") as attach,
                self.assertRaisesRegex(RuntimeError, "Preserve local changes"),
            ):
                review.main()
            self.assertEqual(opened, [])
            attach.assert_not_called()
            self.assertEqual((self.worktree / "file").read_text(), "local edit\n")

    def test_prepare_uses_merge_base_and_refreshes_only_review_worktree(self):
        baseline = review.git(self.checkout, "rev-parse", "HEAD")
        (self.checkout / "file").write_text("PR change\n")
        head = self.commit(self.checkout)
        review.git(self.checkout, "update-ref", "refs/pull/1/head", head)
        review.git(self.checkout, "checkout", "--detach", baseline)
        (self.checkout / "base_only").write_text("unrelated target branch change\n")
        base_tip = self.commit(self.checkout)
        pr = {"headRefOid": head, "baseRefOid": base_tip}
        execute = review.run

        def local_github(*args, **kwargs):
            if args[:3] == ("gh", "pr", "view"):
                return json.dumps(pr)
            args = tuple(
                str(self.checkout)
                if arg == "https://github.com/basetenlabs/baseten.git"
                else arg
                for arg in args
            )
            return execute(*args, **kwargs)

        with mock.patch.object(review, "run", side_effect=local_github):
            worktree, sources, diff_range, _ = review.prepare(
                "basetenlabs/baseten", 1, self.root
            )
            self.assertEqual(worktree, self.worktree)
            self.assertEqual(sources, [])
            self.assertEqual(diff_range, f"{baseline}..{head}")
            self.assertEqual(review.git(self.checkout, "rev-parse", "HEAD"), base_tip)
            self.assertEqual(
                review.git(worktree, "diff", "--name-only", diff_range), "file"
            )
            layout = review.layout(
                "basetenlabs/baseten", 1, worktree, sources, diff_range
            )
            self.assertIn('pane name="Full PR diff"', layout)
            self.assertNotIn("stacked=true", layout)
            self.assertNotIn("Applied SGLang source", layout)
            review.git(self.checkout, "checkout", "--detach", head)
            (self.checkout / "file").write_text("updated PR\n")
            pr["headRefOid"] = self.commit(self.checkout)
            review.git(
                self.checkout, "update-ref", "refs/pull/1/head", pr["headRefOid"]
            )
            review.git(self.checkout, "checkout", "--detach", base_tip)
            review.prepare("basetenlabs/baseten", 1, self.root)
            self.assertEqual((worktree / "file").read_text(), "updated PR\n")
            self.assertEqual(review.git(self.checkout, "rev-parse", "HEAD"), base_tip)

    def test_mixed_pr_defaults_to_full_diff_with_applied_source_companion(self):
        dockerfile = review.PROJECT / "docker/gpu.sglang.Dockerfile"
        (self.checkout / dockerfile).parent.mkdir(parents=True)
        dockerfile_text = "RUN python3 -c 'import flashinfer; assert flashinfer.__version__ == \"0.7.2\"'\n"
        (self.checkout / dockerfile).write_text(dockerfile_text)
        baseline = self.commit(self.checkout)
        patchfile = review.STACK_PATHS[0] / "001_fixture.patch"
        (self.checkout / patchfile).parent.mkdir(parents=True)
        (self.checkout / patchfile).write_text("fixture patch\n")
        (self.checkout / dockerfile).write_text(
            dockerfile_text + "ENV SGLANG_CPU_WORKERS=4\n"
        )
        head = self.commit(self.checkout)
        review.git(self.checkout, "update-ref", "refs/pull/1/head", head)
        source = self.worktree / review.PROJECT / "sglang"
        execute = review.run

        def local_github(*args, **kwargs):
            if args[:3] == ("gh", "pr", "view"):
                return json.dumps({"headRefOid": head, "baseRefOid": baseline})
            args = tuple(
                str(self.checkout)
                if arg == "https://github.com/basetenlabs/baseten.git"
                else arg
                for arg in args
            )
            return execute(*args, **kwargs)

        with (
            mock.patch.object(review, "run", side_effect=local_github),
            mock.patch.object(review, "prepare_sglang", return_value=source),
            mock.patch.object(
                review,
                "prepare_flashinfer",
                side_effect=AssertionError("Unexpected FlashInfer replay"),
            ),
        ):
            worktree, applied_source, diff_range, _ = review.prepare(
                "basetenlabs/baseten", 1, self.root
            )
        self.assertEqual(applied_source, [("SGLang", source)])
        self.assertEqual(diff_range, f"{baseline}..{head}")
        self.assertEqual(
            review.git(worktree, "diff", "--name-only", diff_range).splitlines(),
            [str(dockerfile), str(patchfile)],
        )
        layout = review.layout(
            "basetenlabs/baseten", 1, worktree, applied_source, diff_range
        )
        self.assertIn("pane stacked=true", layout)
        full = re.search(r'pane name="Full PR diff"[^}]+}', layout).group()
        self.assertIn("focus=true expanded=true", full)
        self.assertIn(f'cwd "{worktree}"', full)
        self.assertIn(f"DiffviewOpen {diff_range}", full)
        applied = re.search(r'pane name="Applied SGLang source"[^}]+}', layout).group()
        self.assertNotIn("focus=true", applied)
        self.assertIn("start_suspended=true", applied)
        self.assertIn(f'cwd "{source}"', applied)
        self.assertIn(f"DiffviewOpen {review.BASE_REF}..{review.HEAD_REF}", applied)
        combined = review.layout(
            "basetenlabs/baseten",
            1,
            worktree,
            [*applied_source, ("FlashInfer", self.root / "flashinfer")],
            diff_range,
            include_agent=True,
        )
        self.assertIn('pane name="Full PR diff"', combined)
        self.assertIn('pane name="Applied SGLang source"', combined)
        self.assertIn('pane name="Applied FlashInfer source"', combined)
        self.assertIn('pane name="OpenCode review"', combined)

    def flashinfer_dockerfile(self, version, *patches):
        text = f"RUN python3 -c 'import flashinfer; assert flashinfer.__version__ == \"{version}\"'\n"
        for name in patches:
            text += (
                f"COPY docker/flashinfer/{name} /tmp/\n"
                "RUN flashinfer_dir=\"$(python3 -c 'import flashinfer')\" && \\\n"
                f'    patch --forward --batch --fuzz=0 -d "$flashinfer_dir" -p1 --input=/tmp/{name} && \\\n'
                f"    rm /tmp/{name}\n"
            )
        return text

    def test_flashinfer_patch_comparison_order_pin_change_refresh_and_local_edits(self):
        project = self.checkout / review.PROJECT
        patches = project / "docker/flashinfer"
        patches.mkdir(parents=True)
        dockerfile = project / "docker/gpu.sglang.Dockerfile"
        first, second = "z_fixture.patch", "a_fixture.patch"
        patch = "Title: Review fixture\n\n--- a/kernel.py\n+++ b/kernel.py\n@@ -1 +1 @@\n-value = {before}\n+value = {after}\n"
        (patches / first).write_text(patch.format(before=0, after=1))
        dockerfile.write_text(self.flashinfer_dockerfile("0.7.2", first))
        baseline = self.commit(self.checkout)
        (patches / first).write_text(patch.format(before=0, after=2))
        (patches / second).write_text(patch.format(before=2, after=3))
        dockerfile.write_text(self.flashinfer_dockerfile("0.7.3", first, second))
        head = self.commit(self.checkout)
        review.git(self.checkout, "update-ref", "refs/pull/1/head", head)
        wheels = {}
        for version in ("0.7.2", "0.7.3"):
            wheel = self.root / f"flashinfer_python-{version}-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("flashinfer/kernel.py", "value = 0\n")
                if version == "0.7.3":
                    archive.writestr(
                        "flashinfer/upstream_only.py", "new_release = True\n"
                    )
            wheels[version] = wheel
        execute = review.run
        pr = {"headRefOid": head, "baseRefOid": baseline}

        def local_github(*args, **kwargs):
            if args[:3] == ("gh", "pr", "view"):
                return json.dumps(pr)
            args = tuple(
                str(self.checkout)
                if arg == "https://github.com/basetenlabs/baseten.git"
                else arg
                for arg in args
            )
            return execute(*args, **kwargs)

        with (
            mock.patch.object(review, "run", side_effect=local_github),
            mock.patch.object(
                review,
                "flashinfer_wheel",
                side_effect=lambda version, cache: wheels[version],
            ),
        ):
            worktree, sources, diff_range, metadata = review.prepare(
                "basetenlabs/baseten", 1, self.root
            )
            source = metadata / "flashinfer"
            self.assertEqual(sources, [("FlashInfer", source)])
            self.assertEqual(
                review.git(source, "show", f"{review.BASE_REF}:kernel.py"), "value = 1"
            )
            self.assertEqual(
                review.git(source, "show", f"{review.HEAD_REF}:kernel.py"), "value = 3"
            )
            self.assertEqual(
                review.git(
                    source, "diff", "--name-only", review.BASE_REF, review.HEAD_REF
                ).splitlines(),
                ["kernel.py", "upstream_only.py"],
            )
            self.assertEqual(review.git(worktree, "status", "--porcelain"), "")
            layout = review.layout(
                "basetenlabs/baseten",
                1,
                worktree,
                sources,
                diff_range,
                include_agent=True,
            )
            self.assertIn('pane name="Applied FlashInfer source"', layout)
            self.assertNotIn("Applied SGLang source", layout)
            self.assertIn('tab name="AI review 1"', layout)
            with mock.patch.object(
                review,
                "init_flashinfer",
                side_effect=AssertionError("Unexpected replay"),
            ):
                self.assertEqual(
                    review.prepare("basetenlabs/baseten", 1, self.root)[1], sources
                )
            (patches / second).write_text(patch.format(before=2, after=4))
            pr["headRefOid"] = self.commit(self.checkout)
            review.git(
                self.checkout, "update-ref", "refs/pull/1/head", pr["headRefOid"]
            )
            review.prepare("basetenlabs/baseten", 1, self.root)
            self.assertEqual(
                review.git(source, "show", f"{review.HEAD_REF}:kernel.py"), "value = 4"
            )
            (patches / second).write_text(patch.format(before=99, after=5))
            pr["headRefOid"] = self.commit(self.checkout)
            review.git(
                self.checkout, "update-ref", "refs/pull/1/head", pr["headRefOid"]
            )
            with self.assertRaisesRegex(RuntimeError, "git .*apply"):
                review.prepare("basetenlabs/baseten", 1, self.root)
            self.assertEqual(
                review.git(source, "show", f"{review.HEAD_REF}:kernel.py"), "value = 4"
            )
            (source / "kernel.py").write_text("local edit\n")
            with self.assertRaisesRegex(RuntimeError, "Preserve local changes"):
                review.prepare("basetenlabs/baseten", 1, self.root)
            self.assertEqual((source / "kernel.py").read_text(), "local edit\n")

    def test_flashinfer_stack_rejects_ambiguous_version_and_unknown_patch_input(self):
        dockerfile = self.checkout / review.PROJECT / "docker/gpu.sglang.Dockerfile"
        dockerfile.parent.mkdir(parents=True)
        for text, error in (
            (
                self.flashinfer_dockerfile("0.7.2")
                + self.flashinfer_dockerfile("0.7.3"),
                "one FlashInfer version",
            ),
            (
                self.flashinfer_dockerfile("0.7.2", "fixture.patch").replace(
                    "COPY ", "# COPY "
                ),
                "Unsupported FlashInfer patch command",
            ),
            (
                self.flashinfer_dockerfile("0.7.2", "fixture.patch").replace(
                    "patch --forward", "unknown-patch --forward"
                ),
                "lack a supported application command",
            ),
        ):
            with self.subTest(error=error):
                dockerfile.write_text(text)
                head = self.commit(self.checkout)
                with self.assertRaisesRegex(RuntimeError, error):
                    review.flashinfer_stack(self.checkout, head)

    def test_flashinfer_stack_preserves_patch_text_and_follows_semicolon_run_order(
        self,
    ):
        project = self.checkout / review.PROJECT
        (project / "docker/flashinfer").mkdir(parents=True)
        adapter = "adapter diff\n \n"
        kernel = "kernel diff\n\n"
        (project / "docker/flashinfer_nvfp4_adapter.patch").write_text(adapter)
        (project / "docker/flashinfer/kernel.patch").write_text(kernel)
        dockerfile = self.flashinfer_dockerfile("0.7.2") + (
            "COPY docker/flashinfer/kernel.patch /tmp/\n"
            "COPY docker/flashinfer_nvfp4_adapter.patch /tmp/\n"
            'RUN set -eu; flashinfer_dir="/installed/flashinfer"; \\\n'
            '    patch --forward --batch --fuzz=0 -d "$flashinfer_dir" -p1 --input=/tmp/flashinfer_nvfp4_adapter.patch; \\\n'
            '    patch --forward --batch --fuzz=0 -d "$flashinfer_dir" -p1 --input=/tmp/kernel.patch\n'
        )
        (project / "docker/gpu.sglang.Dockerfile").write_text(dockerfile)
        head = self.commit(self.checkout)
        self.assertEqual(
            review.flashinfer_stack(self.checkout, head),
            (
                "0.7.2",
                [("flashinfer_nvfp4_adapter.patch", adapter), ("kernel.patch", kernel)],
            ),
        )

    def test_flashinfer_wheel_download_cache_and_integrity(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("flashinfer/kernel.py", "value = 0\n")
        wheel_bytes = payload.getvalue()
        artifact = {
            "filename": "flashinfer_python-0.7.2-py3-none-any.whl",
            "url": "https://files.pythonhosted.org/fixture.whl",
            "digests": {"sha256": hashlib.sha256(wheel_bytes).hexdigest()},
        }
        requests = []

        def download(url, **kwargs):
            requests.append(url)
            return io.BytesIO(
                json.dumps({"urls": [artifact]}).encode()
                if url.endswith("/json")
                else wheel_bytes
            )

        with mock.patch.object(review.urllib.request, "urlopen", side_effect=download):
            wheel = review.flashinfer_wheel("0.7.2", self.root / "wheels")
            self.assertEqual(wheel.read_bytes(), wheel_bytes)
            self.assertEqual(
                review.flashinfer_wheel("0.7.2", self.root / "wheels"), wheel
            )
            self.assertEqual(requests.count(artifact["url"]), 1)
            wheel.write_bytes(b"corrupt")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                review.flashinfer_wheel("0.7.2", self.root / "wheels")
            artifact["digests"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                review.flashinfer_wheel("0.7.2", self.root / "bad-wheels")
            self.assertFalse((self.root / "bad-wheels" / artifact["filename"]).exists())

    def test_flashinfer_wheel_rejects_escaping_and_git_metadata_paths(self):
        for index, name in enumerate(
            (
                "flashinfer/../outside",
                "flashinfer/.git/config",
                "flashinfer/.GiT/config",
            )
        ):
            with self.subTest(name=name):
                wheel = self.root / "unsafe.whl"
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr(name, "unsafe\n")
                with self.assertRaisesRegex(
                    RuntimeError, "Invalid FlashInfer wheel path"
                ):
                    review.init_flashinfer(
                        wheel, "0.7.2", [], self.root / f"source-{index}"
                    )
                self.assertFalse((self.root / "outside").is_file())

    @unittest.skipUnless(
        HELPER.exists(), "Requires the Baseten SGLang development helper"
    )
    def test_full_stack_comparison_pin_change_reuse_and_local_edits(self):
        self.check_stack_comparison("numbered", "numbered")

    @unittest.skipUnless(
        HELPER.exists(), "Requires the Baseten SGLang development helper"
    )
    def test_series_stack_comparison_pin_change_reuse_and_local_edits(self):
        self.check_stack_comparison("series", "series")

    @unittest.skipUnless(
        HELPER.exists(), "Requires the Baseten SGLang development helper"
    )
    def test_numbered_to_series_stack_comparison(self):
        self.check_stack_comparison("numbered", "series")

    def check_stack_comparison(self, base_format, head_format):
        # Synthetic upstream releases exercise the real installed helper.
        upstream = self.root / "upstream"
        self.init_repo(upstream)
        (upstream / "model.py").write_text("value = 0\n")
        self.commit(upstream)
        review.git(upstream, "tag", "v1.0.0")
        (upstream / "upstream_only.py").write_text("new_release = True\n")
        self.commit(upstream)
        review.git(upstream, "tag", "v2.0.0")
        cache = self.root / "sglang-review.git"
        review.run("git", "init", "--bare", cache)
        review.git(cache, "remote", "add", "origin", str(upstream))

        project = self.checkout / review.PROJECT
        (project / "bin").mkdir(parents=True)
        shutil.copyfile(HELPER, project / "bin/sglang_dev.py")
        shutil.copyfile(
            HELPER.parent / "patch_stack.py", project / "bin/patch_stack.py"
        )
        (project / "versions").mkdir()
        version = project / "versions/sglang.env"
        version.write_text("ENGINE_SHA=v1.0.0\n")
        patches = project / "docker/sglang/patches"
        patches.mkdir(parents=True)
        header = (
            "Title: Synthetic review fixture\nOrigin: Original fixture\nUpstream PR: None\n"
            "Problem: Verify applied source comparisons\nImplementation: Change a fixture value\n"
            "Dependencies: Earlier fixture patches\nValidation: Local Git replay\n\n"
        )
        patch = (
            "diff --git a/model.py b/model.py\n--- a/model.py\n+++ b/model.py\n"
            "@@ -1 +1 @@\n-value = {before}\n+value = {after}\n"
        )
        first_patch = patches / (
            "001_fixture.patch" if base_format == "numbered" else "z_fixture.patch"
        )
        first_patch.write_text(header + patch.format(before=0, after=1))
        if base_format == "series":
            (patches / "series").write_text(f"{first_patch.name}\n")
        baseline = self.commit(self.checkout)
        if base_format != head_format:
            first_patch = first_patch.rename(patches / "z_fixture.patch")
        first_patch.write_text(header + patch.format(before=0, after=2))
        second_patch = patches / (
            "002_fixture_2.patch" if head_format == "numbered" else "a_fixture.patch"
        )
        second_patch.write_text(header + patch.format(before=2, after=3))
        if head_format == "series":
            (patches / "series").write_text(
                f"# Dependency order, not filename order\n{first_patch.name}\n\n{second_patch.name}\n"
            )
        version.write_text("ENGINE_SHA=v2.0.0\n")
        head = self.commit(self.checkout)
        state_path, state = self.prepare_worktree()
        source = review.prepare_sglang(
            self.checkout,
            self.worktree,
            baseline,
            head,
            state_path,
            state,
            cache,
        )
        self.assertEqual(
            review.git(source, "show", f"{review.BASE_REF}:model.py"), "value = 1"
        )
        self.assertEqual(
            review.git(source, "show", f"{review.HEAD_REF}:model.py"), "value = 3"
        )
        self.assertEqual(
            review.git(
                source, "diff", "--name-only", review.BASE_REF, review.HEAD_REF
            ).splitlines(),
            ["model.py", "upstream_only.py"],
        )
        self.assertEqual(review.git(source, "status", "--porcelain"), "")
        self.assertEqual(review.git(self.checkout, "status", "--porcelain"), "")
        self.assertEqual(review.git(self.worktree, "status", "--porcelain"), "")
        with mock.patch.object(
            review, "init_source", side_effect=AssertionError("Unexpected replay")
        ):
            self.assertEqual(
                review.prepare_sglang(
                    self.checkout,
                    self.worktree,
                    baseline,
                    head,
                    state_path,
                    state,
                    cache,
                ),
                source,
            )
        second_patch.write_text(header + patch.format(before=2, after=4))
        updated_head = self.commit(self.checkout)
        review.prepare_sglang(
            self.checkout,
            self.worktree,
            baseline,
            updated_head,
            state_path,
            state,
            cache,
        )
        self.assertEqual(
            review.git(source, "show", f"{review.BASE_REF}:model.py"), "value = 1"
        )
        self.assertEqual(
            review.git(source, "show", f"{review.HEAD_REF}:model.py"), "value = 4"
        )
        if head_format == "numbered":
            (patches / "002_collision.patch").write_text(
                header + patch.format(before=4, after=5)
            )
            error = "Duplicate patch ordering index 002"
        else:
            (patches / "series").write_text(
                f"{first_patch.name}\n{second_patch.name}\n{first_patch.name}\n"
            )
            error = "Duplicate patch in series: z_fixture.patch"
        conflicting_head = self.commit(self.checkout)
        with mock.patch.object(
            review, "cache_pin", side_effect=AssertionError("Unexpected fetch")
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                f"Proposed SGLang patch stack is invalid: {error}",
            ):
                review.prepare_sglang(
                    self.checkout,
                    self.worktree,
                    baseline,
                    conflicting_head,
                    state_path,
                    state,
                    cache,
                )
        self.assertEqual(state["source_revisions"], [baseline, updated_head])
        self.assertEqual(review.git(source, "status", "--porcelain"), "")
        (source / "model.py").write_text("user edit\n")
        with self.assertRaisesRegex(RuntimeError, "Preserve local changes"):
            review.prepare_sglang(
                self.checkout,
                self.worktree,
                baseline,
                updated_head,
                state_path,
                state,
                cache,
            )
        self.assertEqual((source / "model.py").read_text(), "user edit\n")


if __name__ == "__main__":
    unittest.main()
