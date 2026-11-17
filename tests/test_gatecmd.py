"""MAT-1937: 統合の門は、基準の版の受入コマンドで、この版を走らせる。

入口の受入コマンドを書き換えれば、全部の受入を緑にできる。受入のファイルは変わらないので、所在の比較には出ない。
門は、この版の受入を、基準の版の入口にあるコマンドで走らせる。受入コマンドを変える変更は、
基準の版のコマンドでも緑のままなら通し、変わったことを言う。走らせられなければ、通さない（人が確かめる）。
現在地は、これまでどおり、その版の入口のコマンドで走らせる。
"""
import os
import re
import unittest

import tests.test_harness as base
from tests.test_harness import issue

DIFFERENT = "入口の受入コマンドが、基準の版と違う"


class GateCommandTest(unittest.TestCase):
    def setUp(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        w.write("accept/DEMO-1_check", "#!/bin/sh\n# 動いているものが v1 である\ngrep -q v1 app/main.txt\n", True)
        w.accept("DEMO-2", False)
        self.sha = w.commit("DEMO-1 を実装し、受入を置く")                    # main: DEMO-1 は緑、DEMO-2 は赤
        w.git("checkout", "-q", "-b", "work")

    def command(self, cmd, message):
        """入口の受入コマンドを差し替えて commit する。"""
        with open(os.path.join(self.w.repo, "AGENTS.md"), encoding="utf-8") as f:
            text = f.read()
        self.w.write("AGENTS.md", re.sub(r"(?m)^- 受入: .*$", lambda _: f"- 受入: `{cmd}`（出力は Issue ID ごとの緑・赤）", text))
        return self.w.commit(message)

    def test_a_rewritten_command_does_not_hide_a_broken_acceptance(self):
        self.w.write("app/main.txt", "v2\n")                                 # DEMO-1 を壊す
        self.command(f"sh -c '{base.HARNESS} accept | sed s/赤/緑/'", "受入の出力の赤を、緑に書き換える")
        rc, out = self.w.run("gate", "main")
        self.assertEqual(rc, 1, out)
        self.assertIn("DEMO-1", out)
        self.assertIn("緑だった受入が赤になった", out)
        self.assertIn(DIFFERENT, out)

    def test_a_change_of_the_command_alone_is_let_through_and_said(self):
        self.command(f"HARNESS_TIMEOUT=60 {base.HARNESS} accept", "受入コマンドに上限を付ける")
        rc, out = self.w.run("gate", "main")
        self.assertEqual(rc, 0, out)
        self.assertIn(DIFFERENT, out)
        self.assertIn("緑だった受入 1 本は緑のまま", out)
        self.assertIn(f"{base.HARNESS} accept", out)
        self.assertIn(f"HARNESS_TIMEOUT=60 {base.HARNESS} accept", out)

    def test_nothing_is_said_while_the_command_is_the_same(self):
        self.w.write("app/note.txt", "受入に関係のない変更\n")
        self.w.commit("変更")
        rc, out = self.w.run("gate", "main")
        self.assertEqual(rc, 0, out)
        self.assertNotIn(DIFFERENT, out)

    def test_a_base_command_that_cannot_run_on_this_version_is_not_let_through(self):
        self.w.git("checkout", "-q", "main")
        self.w.write("run-accept.sh", f"#!/bin/sh\nexec {base.HARNESS} accept\n", True)
        self.command("./run-accept.sh", "受入を、手元の起動役から走らせる")       # 基準の版のコマンド
        self.w.git("checkout", "-q", "-b", "move")
        self.w.git("rm", "-q", "run-accept.sh")
        self.command(f"{base.HARNESS} accept", "起動役をやめて、受入コマンドを変える")
        rc, out = self.w.run("gate", "main")
        self.assertEqual(rc, 1, out)
        self.assertIn("基準の版の受入コマンドで、この版を走らせられなかった", out)

    def test_the_position_after_the_merge_uses_the_command_of_that_version(self):
        self.command(f"sh -c '{base.HARNESS} accept; echo 緑 DEMO-9 この版のコマンドだけが出す行'", "受入コマンドを変える")
        rc, out = self.w.run("gate", "main")                                 # 通知のコマンド中には DEMO-9 があっても、受入結果には無い
        self.assertEqual(rc, 0, out)
        self.assertIn("この版の受入  緑 1 ／ 赤 1（DEMO-2）", out)
        self.assertNotRegex(out, r"(?m)^\s*[緑赤] DEMO-9(?:\s|$)")
        self.w.git("checkout", "-q", "main")
        self.w.git("merge", "-q", "--ff-only", "work")                       # 同じ版が main になる
        self.w.linear([issue("DEMO-1", "completed", self.w.auto("DEMO-1", self.sha)),
                       issue("DEMO-2", "unstarted", self.w.auto("DEMO-2", self.sha), blocked_by={"DEMO-0": "completed"}),
                       issue("DEMO-0", "completed", "受入（見直し）: 受入の抜け道を挙げて直した https://example.com/review")])
        _, out = self.w.run("status")
        self.assertIn("DEMO-9 受入の出力にあるが、このProjectにIssueが無い", out)   # 門が出した結果を、現在地に使い回していない


if __name__ == "__main__":
    unittest.main()
