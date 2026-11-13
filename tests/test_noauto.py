"""MAT-1881: 自動の受入が1本も無い Project（仕事が、証拠と人で確かめるものだけ）でも、建て終わりになり、現在地と門が働く。"""
import json
import os
import re
import unittest

import tests.test_harness as base
from tests.test_harness import issue

EVIDENCE = "受入（証拠）: 会場を予約し、予約の確認がある <完了時に、リンクと日付>"
PERSON = "受入（人）: 依頼者が、告知文を確かめる"


class NoAutomaticAcceptanceTest(unittest.TestCase):
    def setUp(self):
        w = self.w = base.World()                               # 入口の受入は harness accept。accept/ は無い
        self.addCleanup(w.close)
        w.run("setup")
        w.commit("入口とフックを置く")
        self.issues = [issue("DEMO-1", "unstarted", EVIDENCE),
                       issue("DEMO-2", "unstarted", PERSON, blocked_by=["DEMO-1"])]
        w.linear(self.issues)

    def command(self, cmd):
        """入口の受入コマンドを差し替えて commit する。"""
        with open(os.path.join(self.w.repo, "AGENTS.md"), encoding="utf-8") as f:
            text = f.read()
        self.w.write("AGENTS.md", re.sub(r"(?m)^- 受入: .*$", lambda _: f"- 受入: `{cmd}`（出力は Issue ID ごとの緑・赤）", text))
        return self.w.commit("受入コマンドを変える")

    def test_build_is_finished_without_an_automatic_acceptance(self):
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)
        self.assertIn("整っている", out)
        self.assertIn("受入  緑 0 ／ 赤 0 ／ 未実装 0", out)
        self.assertIn("前線  DEMO-1", out)
        self.assertIn("待ち  DEMO-2", out)

    def test_the_position_is_derived(self):
        rc, out = self.w.run("status")
        self.assertEqual(rc, 0)
        self.assertNotIn("走らせられなかった", out)
        self.assertIn("受入  緑 0 ／ 赤 0 ／ 未実装 0", out)
        self.assertIn("食い違い  なし", out)

    def test_the_stop_gate_still_holds_a_session(self):
        self.w.run("status", hook={"hook_event_name": "SessionStart", "session_id": "s1"})
        self.issues[0]["state"] = {"name": "Done", "type": "completed"}         # 証拠を書かずに閉じた
        self.w.linear(self.issues)
        _, out = self.w.run("check", hook={"hook_event_name": "Stop", "session_id": "s1"})
        data = json.loads(out)
        self.assertEqual(data.get("decision"), "block", out)
        self.assertIn("DEMO-1 Done（証拠）だが、証拠のリンクが無い", data["reason"])

    def test_an_automatic_issue_whose_line_is_missing_is_still_named(self):
        self.w.accept("DEMO-3", False)
        sha = self.command("true")                              # 何も出さずに、終了コード0で終わる受入コマンド
        self.issues += [issue("DEMO-3", "unstarted", self.w.auto("DEMO-3", sha), blocked_by=["DEMO-0"]),
                        issue("DEMO-0", "unstarted", "受入（見直し）: 受入の抜け道を別の文脈が挙げて直す")]
        self.w.linear(self.issues)
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn("DEMO-3 Todo だが、main の受入に出てこない", out)

    def test_a_command_that_fails_without_a_line_is_still_an_error(self):
        self.command("sh -c 'echo 壊れている >&2; exit 3'")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn("受入を走らせられない", out)
        _, out = self.w.run("status")
        self.assertIn("受入  走らせられなかった", out)

    def test_the_project_is_completed_when_nothing_is_open(self):
        done = [issue("DEMO-1", "completed", "受入（証拠）: 会場を予約し、予約の確認がある https://example.com/booking 2026-12-01"),
                issue("DEMO-2", "completed", PERSON, blocked_by={"DEMO-1": "completed"})]
        self.w.linear(done)                                     # Project はまだ進行中
        _, out = self.w.run("status")
        self.assertIn("Project を完了にする", out)
        self.w.linear(done, status="completed")
        _, out = self.w.run("status")
        self.assertIn("食い違い  なし", out)

    def test_the_merge_gate_has_nothing_to_hold(self):
        self.w.write("app/main.txt", "v2\n")
        self.w.commit("原稿を直す")
        rc, out = self.w.run("gate")
        self.assertEqual(rc, 0, out)

    def test_the_merge_gate_refuses_a_green_acceptance_disappearing_into_empty_output(self):
        self.w.accept("DEMO-3", True)
        before = self.w.commit("緑の自動受入を置く")
        self.command("true")
        rc, out = self.w.run("gate", before)
        self.assertEqual(rc, 1, out)
        self.assertIn("DEMO-3", out)
        self.assertIn("緑だった受入が消えた", out)

    def test_a_mixed_project_still_counts_automatic_acceptance(self):
        self.w.accept("DEMO-3", False)
        sha = self.w.commit("赤の自動受入を置く")
        self.issues += [issue("DEMO-3", "unstarted", self.w.auto("DEMO-3", sha), blocked_by=["DEMO-0"]),
                        issue("DEMO-0", "unstarted", "受入（見直し）: 受入の抜け道を別の文脈が挙げて直す")]
        self.w.linear(self.issues)
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)
        self.assertIn("受入  緑 0 ／ 赤 0 ／ 未実装 1", out)
        self.assertIn("食い違い  なし", out)


if __name__ == "__main__":
    unittest.main()
