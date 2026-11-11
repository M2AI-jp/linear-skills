"""MAT-1833: 建て終わりに、人が確かめるIssueが1本ある。"""
import unittest

import tests.test_harness as base
from tests.test_harness import issue

NAMED = "人が確かめるIssue（受入（人））が無い"


class HumanIssueTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        _, self.issues = base.HarnessTest.standard(self)
        self.w.run("setup")
        self.w.commit("フックを登録する")

    def test_build_is_not_finished_without_an_issue_for_a_person(self):
        base.HarnessTest.just_built(self, self.issues, human=False)
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(NAMED, out)

    def test_build_is_finished_with_one(self):
        base.HarnessTest.just_built(self, self.issues)
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)
        self.assertIn("DEMO-H 題 DEMO-H（Todo）", out)        # 人のIssueは、ふつうの仕事として前線に出る

    def test_a_canceled_one_does_not_count(self):
        base.HarnessTest.just_built(self, self.issues, human=False)
        self.issues.append(issue("DEMO-H", "canceled", "受入（人）: 依頼者が、仮置きにした基準を確かめる"))
        self.w.linear(self.issues)
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(NAMED, out)

    def test_an_issue_that_only_mentions_a_person_does_not_count(self):
        base.HarnessTest.just_built(self, self.issues, human=False)
        self.issues.append(issue("DEMO-K", "unstarted", "依頼者に確かめてもらうこと: 仮置きの基準"))    # 受入（人）と宣言していない
        self.w.linear(self.issues)
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(NAMED, out)

    def test_an_issue_that_talks_about_the_declaration_does_not_count(self):
        base.HarnessTest.just_built(self, self.issues, human=False)
        self.issues.append(issue("DEMO-K", "unstarted", "この Project に受入（人）は立てない"))   # 文中に語があるだけ
        self.w.linear(self.issues)
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(NAMED, out)

    def test_one_in_backlog_counts(self):
        base.HarnessTest.just_built(self, self.issues, human=False)
        self.issues.append(issue("DEMO-H", "backlog", "受入（人）: 依頼者が、仮置きにした基準を確かめる"))
        self.w.linear(self.issues)
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)

    def test_the_position_does_not_nag_about_it_after_the_build(self):
        self.w.linear(self.issues)                              # 進行中の形（見直しは済み、人のIssueはもう無い）
        _, out = self.w.run("status")
        self.assertNotIn(NAMED, out)
        self.assertIn("食い違い  なし", out)


if __name__ == "__main__":
    unittest.main()
