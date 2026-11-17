"""MAT-1939: 小さな直し。実行ビット、setup の照合、リポジトリの外の harness、夏時間、受入に渡す環境。

1. harness の実行ビットが落ちると、フックは黙って何もしない。建て終わりの判定が名指しする。
2. setup と建て終わりの判定は、このスキルのフックだけを照合する。関係のない既存のフックを書き換えず、登録済みとも見なさない。
3. リポジトリの外に置いた harness の setup は、CI を作らない。そのことを言う。
4. 見直しを閉じた時刻は、夏時間のある土地でも正しく読む。
5. 受入に、Linear の鍵と、本物の作業ツリーの場所を渡さない。
"""
import json
import os
import shutil
import subprocess
import sys
import time
import unittest

import tests.test_harness as base
import tests.test_selfreview as selfreview
from tests.test_harness import issue

SKILL = os.path.dirname(base.HARNESS)
OTHERS = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "./test-harness.sh status"}]}],
                    "Stop": [{"hooks": [{"type": "command", "command": "npm run harness:check"}]}]}}


class ExecutableTest(unittest.TestCase):
    """スキルを置いたリポジトリ。建て終わっている。"""

    def setUp(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        shutil.copytree(SKILL, os.path.join(w.repo, ".agents", "skills", "linear-workflow"))
        self.rel = os.path.join(".agents", "skills", "linear-workflow", "harness")
        self.harness = os.path.join(w.repo, self.rel)
        _, issues = base.HarnessTest.standard(self)
        base.HarnessTest.just_built(self, issues)
        self.inside("setup")
        w.commit("スキルを置き、フックを登録する")
        rc, out = self.inside("check", "--wellformed")
        self.assertEqual(rc, 0, out)

    def inside(self, *args):
        """実行ビットに頼らずに走らせる（判定は、エージェントが python3 で走らせることもある）。"""
        p = subprocess.run([sys.executable, self.harness, *args], cwd=self.w.repo, capture_output=True, text=True,
                           env=base.ENV, stdin=subprocess.DEVNULL, timeout=120)
        return p.returncode, p.stdout.strip()

    def test_a_harness_that_cannot_be_executed_is_named(self):
        os.chmod(self.harness, 0o644)
        rc, out = self.inside("check", "--wellformed")
        self.assertEqual(rc, 1, out)
        self.assertIn("実行ビット", out)

    def test_a_harness_recorded_without_the_executable_bit_is_named(self):
        self.w.git("update-index", "--chmod=-x", self.rel)        # 手元では実行できるが、clone した先では実行できない
        self.w.git("commit", "-q", "-m", "実行ビットを落として記録する")
        os.chmod(self.harness, 0o755)
        rc, out = self.inside("check", "--wellformed")
        self.assertEqual(rc, 1, out)
        self.assertIn("実行ビット", out)


class OtherHooksTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        _, self.issues = base.HarnessTest.standard(self)
        for name in (".claude/settings.json", ".codex/hooks.json"):
            self.w.write(name, json.dumps(OTHERS, ensure_ascii=False, indent=2) + "\n")
        self.w.commit("関係のないフックが、前からある")

    def commands(self, name, event):
        return [h["command"] for g in self.w.json(name)["hooks"][event] for h in g["hooks"]]

    def test_setup_leaves_hooks_that_are_not_its_own(self):
        rc, out = self.w.run("setup")
        self.assertEqual(rc, 0, out)
        for name in (".claude/settings.json", ".codex/hooks.json"):
            start, stop = self.commands(name, "SessionStart"), self.commands(name, "Stop")
            self.assertIn("./test-harness.sh status", start, name)
            self.assertIn("npm run harness:check", stop, name)
            self.assertTrue(any("linear-workflow/harness" in c and "status --hook" in c for c in start), start)
            self.assertTrue(any("linear-workflow/harness" in c and "check --hook" in c for c in stop), stop)

    def test_the_build_check_does_not_take_them_for_its_own(self):
        base.HarnessTest.just_built(self, self.issues)
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1, out)
        self.assertIn("フックに harness status が登録されていない", out)
        self.assertIn("フックに harness check が登録されていない", out)


class OutsideHarnessTest(unittest.TestCase):
    def test_setup_from_outside_the_repository_says_it_made_no_gate(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        w.git("remote", "add", "origin", "https://github.com/example/demo.git")
        rc, out = w.run("setup")                                  # このテストの harness は、World のリポジトリの外にある
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(os.path.join(w.repo, ".github", "workflows", "accept.yml")))
        self.assertIn("リポジトリの外", out)
        self.assertIn("CI", out)


class SummerTimeTest(unittest.TestCase):
    """受入が置かれたあとに始まったセッションが、見直しを閉じた。建てたセッションが閉じたのではない。"""

    def setUp(self):
        selfreview.SelfReviewTest.setUp(self)

    def test_a_later_session_counts_where_summer_time_is_in_force(self):
        w = self.w
        w.accept("DEMO-2", False)
        w.run("setup")
        sha = w.commit("受入とフックを置く")
        w.linear(selfreview.SelfReviewTest.issues(self, "unstarted", sha))
        time.sleep(1.2)
        w.run("status", hook=selfreview.START)
        w.linear(selfreview.SelfReviewTest.issues(self, "completed", sha, closed_at=selfreview.iso(5)))
        # どちらかは、いつも夏時間の中にある（北半球は3〜11月、南半球は10〜4月）
        for zone in ("Australia/Sydney", "America/New_York"):
            with self.subTest(zone=zone):
                rc, out = w.run("check", "--wellformed", env={"TZ": zone})
                self.assertEqual(rc, 0, out)


class AcceptanceEnvironmentTest(unittest.TestCase):
    def setUp(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        w.write("accept/DEMO-1_check", "#!/bin/sh\n# 受入に、Linear の鍵と、本物の作業ツリーの場所が渡っていない\n"
                '[ -z "$LINEAR_API_KEY" ] && [ -z "$HARNESS_ROOT" ]\n', True)
        sha = w.commit("受入を置く")
        w.linear([issue("DEMO-1", "completed", w.auto("DEMO-1", sha))])
        self.env = {"LINEAR_API_KEY": "lin_api_secret"}

    def test_the_key_and_the_working_tree_are_not_handed_to_an_acceptance(self):
        self.assertIn("受入  緑 1 ／ 赤 0 ／ 未実装 0", self.w.run("status", env=self.env)[1])

    def test_nor_when_the_acceptances_are_run_by_hand(self):
        rc, out = self.w.run("accept", env=self.env)
        self.assertEqual(rc, 0, out)
        self.assertIn("緑 DEMO-1", out)


if __name__ == "__main__":
    unittest.main()
