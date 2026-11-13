"""MAT-1933: 導入先で統合の門が効く条件と、受入だけの commit の書き方を言う。

harness setup が作るのは、検査を走らせる workflow だけ。GitHub でその検査を main の必須チェックにしなければ、
緑だった受入を赤にする変更も、赤いままマージできる。作るときに、人がやる操作として言う。
"""
import os
import shutil
import subprocess
import unittest

import tests.test_harness as base

SKILL = os.path.dirname(base.HARNESS)
REQUIRED = "必須チェック"


class AdoptTest(unittest.TestCase):
    """スキルを置いた、GitHub に remote のあるリポジトリ（ネットワークは使わない）。"""

    def setUp(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        shutil.copytree(SKILL, os.path.join(w.repo, ".agents", "skills", "linear-workflow"))
        w.git("remote", "add", "origin", "https://github.com/example/demo.git")
        self.harness = os.path.join(w.repo, ".agents", "skills", "linear-workflow", "harness")
        self.flow = os.path.join(w.repo, ".github", "workflows", "accept.yml")

    def inside(self, *args):
        """導入先に置いた harness を走らせる。"""
        p = subprocess.run([self.harness, *args], cwd=self.w.repo, capture_output=True, text=True,
                           env=base.ENV, stdin=subprocess.DEVNULL, timeout=120)
        return p.returncode, p.stdout.strip()

    def test_setup_writes_the_gate_and_says_it_must_be_a_required_check(self):
        rc, out = self.inside("setup")
        self.assertEqual(rc, 0, out)
        with open(self.flow, encoding="utf-8") as f:
            self.assertRegex(f.read(), r"harness\W+gate")
        self.assertIn(REQUIRED, out)

    def test_it_is_said_again_while_the_gate_is_there(self):
        self.inside("setup")
        rc, out = self.inside("setup")                           # workflow はもうある。必須チェックにしたかは、機構からは見えない
        self.assertEqual(rc, 0, out)
        self.assertIn(REQUIRED, out)

    def test_setup_does_not_say_so_where_there_is_no_github(self):
        self.w.git("remote", "remove", "origin")
        rc, out = self.inside("setup")
        self.assertEqual(rc, 0, out)
        self.assertNotIn(REQUIRED, out)
        self.assertFalse(os.path.exists(self.flow))

    def test_the_build_check_names_a_missing_gate(self):
        _, issues = base.HarnessTest.standard(self)
        base.HarnessTest.just_built(self, issues)
        self.w.run("setup")                                      # リポジトリの外にある harness は、CI を作らない
        self.w.commit("フックだけを登録する")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn("CIに harness gate が無い", out)
        self.inside("setup")
        self.w.commit("CIの門を足す")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
