"""MAT-1815: 受入を書いたセッションは、その見直しを閉じられない。

同じ理由で止めるのは2回まで、という遮断器はここにも効く。2回止められても直さなければ、3回目は通る。それは仕様。
"""
import json
import time
import unittest

import tests.test_harness as base
from tests.test_harness import issue

START = {"hook_event_name": "SessionStart", "session_id": "sr1"}
STOP = {"hook_event_name": "Stop", "session_id": "sr1"}
NAMED = "DEMO-9 受入を書いたセッションが、その見直しを閉じている"
BUILT = "DEMO-9 受入の見直しが、建てたセッションのうちに閉じている"


def iso(seconds_from_now=0):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + seconds_from_now))


class SelfReviewTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        self.w.accept("DEMO-1", True)
        self.first = self.w.commit("DEMO-1 の受入を置く")

    def issues(self, review, sha, target="unstarted", closed_at=None):
        """DEMO-2 は自動の受入を持ち、見直しの DEMO-9 を待つ。review は DEMO-9 の状態。"""
        w = self.w
        done = review == "completed"
        return [issue("DEMO-1", "completed", w.auto("DEMO-1", self.first)),
                issue("DEMO-2", target, w.auto("DEMO-2", sha), blocked_by={"DEMO-9": review}),
                issue("DEMO-9", review, "受入（見直し）: DEMO-2 の受入の抜け道を別の文脈が挙げて直す"
                      + (" https://example.com/r9" if done else ""), completed_at=(closed_at or iso()) if done else None)]

    def test_session_that_wrote_the_acceptance_cannot_close_its_review(self):
        w = self.w
        w.linear(self.issues("completed", self.first)[:1])
        w.run("status", hook=START)
        w.accept("DEMO-2", False)                                   # このセッションが受入を書き
        sha = w.commit("DEMO-2 の受入を置く")
        w.linear(self.issues("completed", sha))                     # 同じセッションのうちに見直しを閉じた
        verdict = json.loads(w.run("check", hook=STOP)[1])
        self.assertEqual(verdict["decision"], "block")
        self.assertIn(NAMED, verdict["reason"])
        w.linear(self.issues("unstarted", sha))                     # 見直しを開き直せば、止めない
        self.assertEqual(w.run("check", hook=STOP), (0, ""))

    def test_another_session_may_close_the_review_and_fix_the_acceptance(self):
        w = self.w
        w.accept("DEMO-2", False)
        sha = w.commit("DEMO-2 の受入を置く")                       # 受入は、このセッションより前からある
        w.linear(self.issues("unstarted", sha))
        w.run("status", hook=START)
        w.write("accept/DEMO-2_check", "#!/bin/sh\n# 抜け道を塞いだ\nexit 1\n", True)
        fixed = w.commit("受入の抜け道を塞ぐ")
        w.linear(self.issues("completed", fixed))
        self.assertEqual(w.run("check", hook=STOP), (0, ""))

    def test_review_already_closed_before_the_session_is_left_alone(self):
        w = self.w
        w.accept("DEMO-2", False)
        sha = w.commit("DEMO-2 の受入を置く")
        w.linear(self.issues("completed", sha))
        w.run("status", hook=START)
        self.assertEqual(w.run("check", hook=STOP), (0, ""))

    def build(self):
        w = self.w
        w.accept("DEMO-2", False)
        w.run("setup")
        return w.commit("受入とフックを置く")

    def test_builder_cannot_finish_with_its_own_review_closed(self):
        w = self.w
        sha = self.build()
        w.linear(self.issues("completed", sha))                     # フックのあるセッションが1度も走っていない
        rc, out = w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(BUILT, out)
        w.linear(self.issues("unstarted", sha))
        rc, out = w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)

    def test_an_old_session_record_does_not_excuse_the_builder(self):
        w = self.w
        w.linear(self.issues("completed", self.first)[:1])
        w.run("status", hook={"hook_event_name": "SessionStart", "session_id": "old"})   # 受入を書く前の、古い記録
        time.sleep(1.2)
        sha = self.build()
        w.linear(self.issues("completed", sha))
        rc, out = w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(BUILT, out)

    def test_a_session_that_started_after_the_review_was_closed_does_not_excuse_the_builder(self):
        w = self.w
        sha = self.build()
        w.linear(self.issues("completed", sha))                     # 建てたセッションが閉じた
        time.sleep(1.2)
        w.run("status", hook=START)                                 # そのあとに記録を作っても、閉じたのはそのセッションではない
        rc, out = w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(BUILT, out)

    def test_build_check_does_not_second_guess_a_later_session(self):
        w = self.w
        sha = self.build()
        w.linear(self.issues("unstarted", sha))
        time.sleep(1.2)
        w.run("status", hook=START)                                 # 受入が置かれたあとに始まったセッションが
        w.linear(self.issues("completed", sha, closed_at=iso(5)))   # 見直しを閉じた
        rc, out = w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)

    def test_progress_ends_the_build_time_question(self):
        w = self.w
        sha = self.build()
        w.linear(self.issues("completed", sha, target="started"))   # もう着手している。建て終わりの話ではない
        w.git("checkout", "-q", "-b", "demo-2-impl")
        w.git("checkout", "-q", "main")
        _, out = w.run("check", "--wellformed")
        self.assertNotIn(BUILT, out)


if __name__ == "__main__":
    unittest.main()
