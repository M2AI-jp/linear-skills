"""MAT-1832: Codexで建てたとき、Codexのフックの登録が黙って欠けない。

Codex のサンドボックスは、作業フォルダの中でも .codex に書けない。その中で harness setup を走らせると、
.codex/hooks.json を書けない。書けなかったことを言い、スキルを置いた側のフックが無ければ、建て終わりにしない。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import tests.test_harness as base

SKILL = os.path.dirname(base.HARNESS)
MISSING = "フックに harness status が登録されていない（.codex/hooks.json）"


class CodexSetupTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        _, self.issues = base.HarnessTest.standard(self)
        base.HarnessTest.just_built(self, self.issues)
        self.codex = os.path.join(self.w.repo, ".codex")

    def place(self, where):
        """スキルを置く。where は .agents（Codex）か .claude（Claude Code）。"""
        shutil.copytree(SKILL, os.path.join(self.w.repo, where, "skills", "linear-workflow"))

    def setup_raw(self):
        return subprocess.run([base.HARNESS, "setup"], cwd=self.w.repo, capture_output=True, text=True,
                              env=base.ENV, stdin=subprocess.DEVNULL, timeout=60)

    def lock_codex(self):
        os.makedirs(self.codex, exist_ok=True)
        os.chmod(self.codex, 0o555)
        self.addCleanup(os.chmod, self.codex, 0o755)
        with self.assertRaises(OSError):
            open(os.path.join(self.codex, "probe"), "w").close()

    def test_setup_says_which_file_it_could_not_write_and_fails(self):
        self.lock_codex()
        p = self.setup_raw()
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("Traceback", p.stdout + p.stderr)
        self.assertIn("フック: .claude/settings.json", p.stdout)                # 書けるほうは書く
        self.assertIn("書けなかった: .codex/hooks.json", p.stdout)
        self.assertIn("サンドボックスの外で", p.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.codex, "hooks.json")))
        self.assertTrue(os.path.exists(os.path.join(self.w.repo, ".claude", "settings.json")))

    def test_skill_placed_for_codex_needs_the_codex_hooks(self):
        self.place(".agents")
        self.lock_codex()
        self.setup_raw()
        self.w.commit("スキルと、書けたぶんのフックを置く")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(MISSING, out)
        self.assertIn("サンドボックスの外で", out)
        os.chmod(self.codex, 0o755)                                             # 人が、外で setup を走らせた
        self.assertEqual(self.setup_raw().returncode, 0)
        self.w.commit("Codexのフックを登録する")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)

    def test_skill_placed_for_claude_code_only_does_not_need_the_codex_hooks(self):
        self.place(".claude")
        self.assertEqual(self.setup_raw().returncode, 0)
        os.remove(os.path.join(self.codex, "hooks.json"))
        self.w.commit("スキルとフックを置く")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)
        os.remove(os.path.join(self.w.repo, ".claude", "settings.json"))
        self.w.commit("Claude Code のフックを消す")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn("フックに harness status が登録されていない（.claude/settings.json）", out)

    def test_skill_placed_for_both_needs_both(self):
        self.place(".agents")
        self.place(".claude")
        self.assertEqual(self.setup_raw().returncode, 0)
        os.remove(os.path.join(self.codex, "hooks.json"))
        self.w.commit("スキルとフックを置く")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(MISSING, out)

    def test_skill_kept_elsewhere_needs_one_of_them(self):
        self.assertEqual(self.setup_raw().returncode, 0)
        os.remove(os.path.join(self.codex, "hooks.json"))
        self.w.commit("フックを置く")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)

    def test_a_hooks_file_without_harness_does_not_count(self):
        self.place(".agents")
        self.assertEqual(self.setup_raw().returncode, 0)
        with open(os.path.join(self.codex, "hooks.json"), "w") as f:
            f.write("{}\n")                                                    # ファイルがあるだけでは、登録ではない
        self.w.commit("スキルと、中身の無いフックを置く")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(MISSING, out)

    def test_skill_placed_for_codex_does_not_need_the_claude_code_hooks(self):
        self.place(".agents")
        self.assertEqual(self.setup_raw().returncode, 0)
        os.remove(os.path.join(self.w.repo, ".claude", "settings.json"))
        self.w.commit("スキルと Codex のフックだけを置く")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)

    def test_setup_that_has_nothing_to_write_succeeds_where_it_cannot_write(self):
        self.assertEqual(self.setup_raw().returncode, 0)                        # 人が、外で済ませた後
        hooks = os.path.join(self.codex, "hooks.json")
        for path, mode in ((hooks, 0o444), (self.codex, 0o555)):
            os.chmod(path, mode)
        self.addCleanup(os.chmod, self.codex, 0o755)
        self.addCleanup(os.chmod, hooks, 0o644)
        p = self.setup_raw()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("書けなかった", p.stdout)

    @unittest.skipUnless(shutil.which("codex"), "codex が無い環境では飛ばす")
    def test_inside_the_real_codex_sandbox(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        repo = os.path.realpath(self.w.repo)

        def sandboxed(*command):
            return subprocess.run(["codex", "sandbox", "-c", 'sandbox_mode="workspace-write"', "--", *command],
                                  cwd=repo, capture_output=True, text=True, timeout=180,
                                  stdin=subprocess.DEVNULL, env={**base.ENV, "CODEX_HOME": home})

        probe = sandboxed("/bin/sh", "-c", "exit 0")
        if probe.returncode != 0:
            known = "bwrap:" in probe.stderr and ("RTM_NEWADDR" in probe.stderr or "Operation not permitted" in probe.stderr)
            if sys.platform == "darwin" or not known:
                self.fail("Codex のサンドボックスが立たない: " + probe.stderr[-400:])
            self.skipTest("この環境では Codex のサンドボックスが立たない: " + probe.stderr.strip()[-200:])
        p = sandboxed(base.HARNESS, "setup")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertNotIn("Traceback", p.stdout + p.stderr)
        self.assertIn("書けなかった: .codex/hooks.json", p.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.codex, "hooks.json")))


if __name__ == "__main__":
    unittest.main()
