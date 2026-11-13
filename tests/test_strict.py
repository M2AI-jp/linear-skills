"""MAT-1934: 監査の残り。このセッションが足した未 commit、数字だけの証拠、字下げした結果の行。

1. 開始時に未 commit があっても、このセッションが足した未 commit は、名指しされて止まる。前からある分では止めない。
2. 受入（証拠）と受入（見直し）の完了に要るのは、リンクか commit。数字だけの並び（日付、金額）は数えない。
3. 受入の結果の行は、行の頭から始まる。落ちた受入の出力の末尾（字下げして出す）の中の行は、結果ではない。
"""
import json
import os
import unittest

import tests.test_harness as base
from tests.test_harness import issue

START = {"hook_event_name": "SessionStart", "session_id": "st1"}
STOP = {"hook_event_name": "Stop", "session_id": "st1"}


class OwnUncommittedTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        base.HarnessTest.standard(self)

    def verdict(self):
        rc, out = self.w.run("check", hook=STOP)
        self.assertEqual(rc, 0, out)
        return json.loads(out) if out else {}

    def test_work_added_by_the_session_is_named_though_the_tree_was_dirty_at_the_start(self):
        self.w.write("app/theirs.txt", "ほかのセッションが置いた、commit していないもの\n")
        self.w.run("status", hook=START)
        self.assertEqual(self.w.run("check", hook=STOP), (0, ""))            # 前からある分では止めない
        self.w.write("app/mine.txt", "このセッションが足した、commit していないもの\n")
        held = self.verdict()
        self.assertEqual(held.get("decision"), "block", held)
        self.assertIn("app/mine.txt", held["reason"])
        self.assertNotIn("app/theirs.txt", held["reason"])
        os.remove(os.path.join(self.w.repo, "app", "mine.txt"))
        self.assertEqual(self.w.run("check", hook=STOP), (0, ""))            # 片づければ通る。前からある分は残っていてよい

    def test_a_file_added_beside_an_untracked_one_is_named(self):
        self.w.write("notes/theirs.txt", "追跡されていないフォルダに、前からあるもの\n")
        self.w.run("status", hook=START)
        self.w.write("notes/mine.txt", "同じフォルダに、このセッションが足したもの\n")
        held = self.verdict()
        self.assertEqual(held.get("decision"), "block", held)
        self.assertIn("notes/mine.txt", held["reason"])
        self.assertNotIn("notes/theirs.txt", held["reason"])

    def test_the_position_still_shows_what_was_there_before(self):
        self.w.write("app/theirs.txt", "ほかのセッションが置いた、commit していないもの\n")
        self.w.run("status", hook=START)
        _, out = self.w.run("status")
        self.assertIn("commit されていない変更が 1 件ある（app/theirs.txt）", out)


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        self.w.accept("DEMO-1", True)
        self.sha = self.w.commit("DEMO-1 を実装し、受入を置く")

    def named(self, declaration):
        self.w.linear([issue("DEMO-1", "completed", self.w.auto("DEMO-1", self.sha)),
                       issue("DEMO-5", "completed", declaration)])
        return "DEMO-5 Done" in self.w.run("status")[1] and "証拠のリンクが無い" in self.w.run("status")[1]

    def test_digits_alone_are_not_evidence(self):
        self.assertTrue(self.named("受入（証拠）: 見積を送り、受領の返信がある 20261113"))
        self.assertTrue(self.named("受入（証拠）: 入金 1200000 円を確かめた"))
        self.assertTrue(self.named("受入（見直し）: 受入の抜け道を別の文脈が挙げて直す 20261113"))

    def test_a_link_or_a_commit_is_evidence(self):
        self.assertFalse(self.named("受入（証拠）: 見積を送り、受領の返信がある https://example.com/mail/1 2026-11-13"))
        self.assertFalse(self.named(f"受入（見直し）: 受入の抜け道を挙げて直した commit {self.sha[:9]}"))
        self.assertFalse(self.named(f"受入（見直し）: 受入の抜け道を挙げて直した {self.sha}"))


class ResultLineTest(unittest.TestCase):
    def test_an_indented_line_in_what_a_failing_acceptance_printed_is_not_a_result(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        w.write("accept/DEMO-1_check", "#!/bin/sh\n# DEMO-1 の観測できる結果\n"
                "echo '赤 DEMO-9 ほかの受入の出力を、そのまま出した'\nexit 1\n", True)
        sha = w.commit("落ちる受入が、結果の行に見えるものを出す")
        w.linear([issue("DEMO-1", "unstarted", w.auto("DEMO-1", sha), blocked_by={"DEMO-0": "completed"}),
                  issue("DEMO-0", "completed", "受入（見直し）: 受入の抜け道を挙げて直した https://example.com/review")])
        _, out = w.run("status")
        self.assertIn("受入  緑 0 ／ 赤 0 ／ 未実装 1", out)
        self.assertNotIn("DEMO-9", out)
        self.assertIn("食い違い  なし", out)


if __name__ == "__main__":
    unittest.main()
