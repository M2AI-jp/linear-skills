"""MAT-1803: 受入は、書いたのとは別の文脈に攻めさせてから実装に入る。

機構のテスト（test_harness.py）とは別のファイルに置く。受入はIssueが所有するので、
このIssueの受入が赤い間に、ほかのIssueの受入を赤くしない。
"""
import unittest

import tests.test_harness as base
from tests.test_harness import issue

NAMED = " 受入が、別の文脈に攻めさせるIssueを待っていない"


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        for ident in ("DEMO-1", "DEMO-2", "DEMO-3", "DEMO-4", "DEMO-5"):
            self.w.accept(ident, ident == "DEMO-1")
        self.sha = self.w.commit("受入を置く")

    def issues(self):
        w, sha = self.w, self.sha
        return [
            issue("DEMO-1", "completed", w.auto("DEMO-1", sha)),                                     # 閉じたIssueには求めない
            issue("DEMO-2", "unstarted", w.auto("DEMO-2", sha), blocked_by={"DEMO-9": "completed"}),  # 閉じた見直しを待っていた
            issue("DEMO-3", "unstarted", w.auto("DEMO-3", sha), blocked_by={"DEMO-8": "unstarted"}),  # 開いている見直しを待っている
            issue("DEMO-4", "unstarted", w.auto("DEMO-4", sha), blocked_by={"DEMO-7": "completed"}),  # 見直しではないIssueしか待っていない
            issue("DEMO-5", "unstarted", w.auto("DEMO-5", sha)),                                      # 何も待っていない
            issue("DEMO-9", "completed", "受入（見直し）: DEMO-2 の受入の抜け道を別の文脈が挙げて直した https://example.com/r9"),
            issue("DEMO-8", "unstarted", "受入（見直し）: DEMO-3 の受入の抜け道を別の文脈が挙げる"),
            issue("DEMO-7", "completed", "受入（証拠）: API鍵を受け取った https://example.com/key"),
        ]

    def test_open_acceptance_must_wait_for_a_review_issue(self):
        self.w.linear(self.issues())
        _, out = self.w.run("status")
        for ident in ("DEMO-4", "DEMO-5"):
            self.assertIn(ident + NAMED, out)
        for ident in ("DEMO-1", "DEMO-2", "DEMO-3", "DEMO-7", "DEMO-8", "DEMO-9"):
            self.assertNotIn(ident + NAMED, out)
        self.assertIn("DEMO-8 題 DEMO-8（Todo）", out)                 # 見直しは、ふつうの仕事として前線に出る
        self.assertIn("DEMO-3 題 DEMO-3（DEMO-8 待ち）", out)

    def test_review_closed_without_evidence_is_named(self):
        issues = self.issues()
        issues[5]["description"] = "受入（見直し）: 抜け道は無かった"
        self.w.linear(issues)
        _, out = self.w.run("status")
        self.assertIn("DEMO-9 Done（見直し）だが、証拠のリンクが無い", out)

    def test_starting_before_the_review_is_done_is_named(self):
        issues = self.issues()
        issues[2]["state"] = {"name": "In Progress", "type": "started"}
        self.w.linear(issues)
        _, out = self.w.run("status")
        self.assertIn("DEMO-3 が、DEMO-8 の終わる前に着手されている", out)
        self.assertNotIn("DEMO-2 が、", out)


if __name__ == "__main__":
    unittest.main()
