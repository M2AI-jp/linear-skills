"""MAT-1942: 止める相手がもう消えていても、シグナルを送れなくても、harness が落ちない。

macOS では、プロセスグループに、終了済みで回収待ちのプロセスしか残っていないと、グループへのシグナルが
「許可がない」（PermissionError）で失敗する。時間切れの受入を止めたあとの後始末で、まれに起きる。
Codex のサンドボックスの中から、外で動いている実行にシグナルを送ったときも、同じ失敗になる。
どちらも、harness が例外で落ちる理由ではない。
"""
import contextlib
import io
import os
import unittest
from unittest.mock import patch

import tests.test_harness as base
import tests.test_named as named
import tests.test_slow as slow


def refuse(*args):
    raise PermissionError(1, "Operation not permitted")


class GoneTest(unittest.TestCase):
    def test_a_timeout_is_still_reported_when_the_group_cannot_be_signalled(self):
        harness = named.load_harness()
        with patch.object(harness.os, "killpg", refuse):
            rc, out, err = harness.sh("sleep 3", ".", 1)
        self.assertIsNone(rc)
        self.assertEqual(err, "1 秒で終わらなかった")

    def test_the_acceptance_is_red_and_the_others_still_run(self):
        w = base.World()
        self.addCleanup(w.close)
        w.write("accept/DEMO-1_check", "#!/bin/sh\n# 終わらない受入\nsleep 3\n", True)
        w.accept("DEMO-2", True)
        harness = named.load_harness()
        harness.TIMEOUT = 1
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(w.repo)
        printed = io.StringIO()
        with patch.object(harness.os, "killpg", refuse), contextlib.redirect_stdout(printed):
            rc = harness.cmd_accept()
        self.assertEqual(rc, 1)
        self.assertIn("赤 DEMO-1 終わらない受入", printed.getvalue())
        self.assertIn("1 秒で終わらなかった", printed.getvalue())
        self.assertIn("緑 DEMO-2", printed.getvalue())


class UnstoppableOldRunTest(unittest.TestCase):
    """古い版の実行が走っていて、それにシグナルを送れない（サンドボックスの中から、外の実行へ）。"""

    slow, context, until = (getattr(slow.SlowAcceptanceTest, name) for name in ("slow", "context", "until"))

    def setUp(self):
        slow.SlowAcceptanceTest.setUp(self)
        self.release = os.path.join(self.w.dir, "release")
        self.env["RELEASE"] = self.release
        self.addCleanup(lambda: open(self.release, "a").close())
        self.slow("DEMO-1", True, body='while [ ! -f "$RELEASE" ]; do sleep 0.1; done')
        self.w.commit("解放されるまで終わらない受入")

    def test_it_waits_instead_of_crashing(self):
        self.assertIn(slow.GOING, self.context())                            # 古い版の実行が、走っている
        self.w.write("app/main.txt", "v2\n")
        self.w.commit("main が動いた")
        harness = named.load_harness()
        repo = harness.Repo(self.w.repo)
        place = os.path.join(self.w.repo, ".git", "harness", "accept")
        with patch.object(harness.os, "kill", refuse):
            waited = harness.accept_at(repo, repo.sha, wait=1)                # フックの待ち方
            asked = harness.accept_at(repo, repo.sha)                         # 手で走らせたときの待ち方
        self.assertEqual(waited, {"pending": True})
        self.assertIn("error", asked)
        self.assertNotIn("results", asked)
        self.assertTrue([n for n in os.listdir(place) if n.endswith(".run")])   # 古い実行の印は、消していない
        open(self.release, "a").close()                                      # 古い実行が、自分で終わる
        self.until(lambda: not [n for n in os.listdir(place) if n.endswith(".run")])


if __name__ == "__main__":
    unittest.main()
