"""MAT-1862: 受入が読む補助ファイルを書き換えると、名指しされる。

受入が4行の起動役で、確かめる中身が共有の補助（accept/checks.py のようなもの）にあると、
補助を書き換えても、所在のパスだけを比べる機構には見えない。弱めても、見直しで直しても、同じ。
受入（accept/<Issue ID>_<名前>）と同じ置き場にある、Issue ID で始まらないファイルは、そこにある受入の一部として比べる。
置き場の外のファイルは、所在に並べたものだけを比べる。
"""
import json
import unittest

import tests.test_harness as base
from tests.test_harness import issue

LIB = "accept/lib.sh"
STRICT = 'expect() { [ "$1" = "$2" ]; }\n'
WEAK = "expect() { true; }\n"


def lines(out, *needles):
    """出力のうち、needles を全部含む行。"""
    return [x for x in out.splitlines() if all(n in x for n in needles)]


class SharedTest(unittest.TestCase):
    def setUp(self):
        self.w = w = base.World()
        self.addCleanup(w.close)
        w.write(LIB, STRICT)
        w.write("accept/data/sample.txt", "v1\n")
        w.write("tests/helper.sh", STRICT)
        w.write("tests/other.sh", "# 受入とは関係のないテスト\n")
        for ident, want in (("DEMO-1", "v1"), ("DEMO-2", "v2")):
            w.write(f"accept/{ident}_check",
                    f'#!/bin/sh\n# {ident} の観測できる結果\n. "$(dirname "$0")/lib.sh"\nexpect "$(cat app/main.txt)" {want}\n', True)
        self.sha = w.commit("受入と、受入が読む補助を置く")
        self.put(self.sha, self.sha)

    def put(self, one, two, extra_one="", more=()):
        """DEMO-1 は Done で緑、DEMO-2 は Todo で赤。所在は、渡した版。"""
        w = self.w
        self.issues = [
            issue("DEMO-1", "completed", f"受入（自動）: DEMO-1 の観測できる結果 accept/DEMO-1_check@{one}{extra_one}"),
            issue("DEMO-2", "unstarted", f"受入（自動）: DEMO-2 の観測できる結果 accept/DEMO-2_check@{two}",
                  blocked_by={"DEMO-0": "completed"}),
            issue("DEMO-0", "completed", "受入（見直し）: 受入の抜け道を挙げて直した https://example.com/review"),
            issue("DEMO-H", "unstarted", "受入（人）: 担当者が、できあがりを確かめる"), *more]
        w.linear(self.issues)

    def status(self):
        return self.w.run("status")[1]

    # ---- 置き場の補助 ----

    def test_nothing_is_named_while_the_helper_is_as_anchored(self):
        out = self.status()
        self.assertIn("食い違い  なし", out)

    def test_a_weakened_helper_on_main_names_every_issue_that_keeps_its_acceptance_there(self):
        self.w.write(LIB, WEAK)
        self.w.commit("補助を整理する")
        out = self.status()
        for ident in ("DEMO-1", "DEMO-2"):
            hit = lines(out, ident, LIB, "変わった")
            self.assertTrue(hit, f"{ident} が名指しされていない:\n{out}")
            self.assertIn(self.sha[:7], hit[0])                       # どの版から変わったかを言う
        self.assertNotIn("食い違い  なし", out)

    def test_rewriting_the_anchor_clears_it_for_that_issue_only(self):
        self.w.write(LIB, WEAK)
        new = self.w.commit("補助を整理する")
        self.put(new, self.sha)
        out = self.status()
        self.assertFalse(lines(out, "DEMO-1", LIB), out)
        self.assertTrue(lines(out, "DEMO-2", LIB, "変わった"), out)
        self.put(new, new)
        self.assertFalse(lines(self.status(), LIB))

    def test_a_removed_helper_is_named(self):
        self.w.git("rm", "-q", LIB)
        self.w.commit("補助を消す")
        self.assertTrue(lines(self.status(), "DEMO-1", LIB), self.status())

    def test_a_data_file_under_the_acceptance_folder_counts(self):
        self.w.write("accept/data/sample.txt", "v2\n")
        self.w.commit("見本を差し替える")
        out = self.status()
        self.assertTrue(lines(out, "DEMO-1", "accept/data/sample.txt", "変わった"), out)

    def test_a_helper_added_later_counts(self):
        self.w.write("accept/conftest.sh", "# あとから足した、全部の受入に効く設定\n")
        self.w.commit("設定を足す")
        self.assertTrue(lines(self.status(), "DEMO-1", "accept/conftest.sh"), self.status())

    def test_the_stop_gate_stops_the_session_that_changed_the_helper(self):
        w = self.w
        w.run("status", hook={"hook_event_name": "SessionStart", "session_id": "s1"})
        stop = {"hook_event_name": "Stop", "session_id": "s1"}
        self.assertEqual(w.run("check", hook=stop), (0, ""))
        w.write(LIB, WEAK)
        w.commit("DEMO-2 を通す")
        verdict = json.loads(w.run("check", hook=stop)[1])
        self.assertEqual(verdict["decision"], "block")
        self.assertIn(LIB, verdict["reason"])

    def test_the_build_finished_check_does_not_pass_with_a_changed_helper(self):
        self.w.write(LIB, WEAK)
        self.w.commit("補助を整理する")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(LIB, out)

    # ---- ブランチと作業ツリー ----

    def test_a_helper_changed_in_the_working_tree_is_named(self):
        self.w.write(LIB, WEAK)
        out = self.status()
        self.assertTrue(lines(out, LIB, "作業ツリーで変わっている"), out)

    def test_a_helper_changed_on_a_branch_is_named(self):
        w = self.w
        w.git("checkout", "-q", "-b", "demo-2-impl")
        w.write(LIB, WEAK)
        w.commit("DEMO-2 を実装")
        out = self.status()
        self.assertTrue(lines(out, LIB, "ブランチ"), out)

    # ---- 名指ししないもの ----

    def test_another_issues_acceptance_added_to_the_folder_is_not_a_change(self):
        w = self.w
        w.write("accept/DEMO-4_check", "#!/bin/sh\n# DEMO-4 の観測できる結果\nexit 1\n", True)
        w.write("accept/DEMO-4_sample.txt", "DEMO-4 だけが読む見本\n")
        new = w.commit("DEMO-4 の受入を置く")
        self.put(self.sha, self.sha, more=[issue(
            "DEMO-4", "unstarted", f"受入（自動）: DEMO-4 の観測できる結果 accept/DEMO-4_check@{new}",
            blocked_by={"DEMO-0": "completed"})])
        out = self.status()
        self.assertFalse(lines(out, "変わった"), out)
        self.assertIn("食い違い  なし", out)

    def test_product_code_next_to_nothing_is_not_a_change(self):
        self.w.write("app/main.txt", "v1\n# 実装を進めた\n")
        self.w.write("app/new.txt", "x\n")
        self.w.commit("DEMO-9 実装")
        self.assertFalse(lines(self.status(), "変わった"), self.status())

    # ---- 置き場の外 ----

    def test_a_file_outside_the_folder_is_compared_when_the_anchor_lists_it(self):
        self.put(self.sha, self.sha, extra_one=f" tests/helper.sh@{self.sha}")
        self.assertIn("食い違い  なし", self.status())
        self.w.write("tests/helper.sh", WEAK)
        self.w.commit("テストを整理する")
        out = self.status()
        self.assertTrue(lines(out, "DEMO-1", "tests/helper.sh", "変わった"), out)
        self.assertFalse(lines(out, "DEMO-2", "tests/helper.sh"), out)      # 並べていないIssueは名指ししない

    def test_files_next_to_a_listed_file_outside_the_folder_are_left_alone(self):
        self.put(self.sha, self.sha, extra_one=f" tests/helper.sh@{self.sha}")
        self.w.write("tests/other.sh", "# 関係のないテストを直した\n")
        self.w.commit("ほかのテストを直す")
        out = self.status()
        self.assertFalse(lines(out, "tests/other.sh"), out)
        self.assertIn("食い違い  なし", out)


if __name__ == "__main__":
    unittest.main()
