import importlib.machinery
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest import mock


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

    def test_existing_review_reuses_worktree_with_local_edits(self):
        state_path, state = self.prepare_worktree()
        (self.worktree / "file").write_text("work in progress\n")
        self.assertEqual(
            review.existing_review("basetenlabs/baseten", 1, self.root),
            (self.worktree, state_path.parent),
        )
        self.assertEqual((self.worktree / "file").read_text(), "work in progress\n")
        self.assertEqual(review.git(self.worktree, "rev-parse", "HEAD"), state["head"])
        with self.assertRaisesRegex(RuntimeError, "Open this PR with R first"):
            review.existing_review("basetenlabs/baseten", 2, self.root)
        with self.assertRaisesRegex(RuntimeError, "belongs to"):
            review.existing_review("other/baseten", 1, self.root)

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
            worktree, source, diff_range, _ = review.prepare(
                "basetenlabs/baseten", 1, self.root
            )
            self.assertEqual((worktree, source), (self.worktree, self.worktree))
            self.assertEqual(diff_range, f"{baseline}..{head}")
            self.assertEqual(review.git(self.checkout, "rev-parse", "HEAD"), base_tip)
            self.assertEqual(
                review.git(worktree, "diff", "--name-only", diff_range), "file"
            )
            layout = review.layout(
                "basetenlabs/baseten", 1, worktree, source, diff_range
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
        baseline = review.git(self.checkout, "rev-parse", "HEAD")
        dockerfile = review.PROJECT / "docker/gpu.sglang.Dockerfile"
        patchfile = review.STACK_PATHS[0] / "001_fixture.patch"
        (self.checkout / patchfile).parent.mkdir(parents=True)
        (self.checkout / patchfile).write_text("fixture patch\n")
        (self.checkout / dockerfile).write_text(
            "RUN pip install flashinfer-python==0.6.18\n"
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
        ):
            worktree, applied_source, diff_range, _ = review.prepare(
                "basetenlabs/baseten", 1, self.root
            )
        self.assertEqual(applied_source, source)
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
