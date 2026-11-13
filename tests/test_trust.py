"""MAT-1891: サンドボックスの中から置かれた結果を、外で動くフックが信じない。

harness は、受入の結果とセッションの記録を置き場に覚える。.git の中に書けない場所（Codex のサンドボックスの中）では、
.git の外（HARNESS_STORE、TMPDIR、/tmp）に置く。外の置き場には、中のエージェントも書ける。名前は予測できる。
.git の中に書けるプロセス（外で動くフック、人が外で走らせる判定）は、外の置き場にあるものを使わない。
"""
import hashlib
import json
import os
import time
import unittest

import tests.test_harness as base
from tests.test_harness import issue
from tests.test_sandbox import COUNTS, chmod_tree

FORGED = "受入  緑 3 ／ 赤 0 ／ 未実装 0"
BUILT = "DEMO-0 受入の見直しが、建てたセッションのうちに閉じている"


class TrustTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        _, self.issues = base.HarnessTest.standard(self)            # DEMO-1 は緑、DEMO-2 と DEMO-3 は赤
        self.outside = os.path.join(self.w.dir, "outside")
        os.makedirs(self.outside)
        self.env = {"HARNESS_STORE": self.outside}
        self.place = os.path.join(self.outside, "harness-" + hashlib.sha256(
            os.path.realpath(self.w.repo).encode()).hexdigest()[:16])

    def plant(self):
        """.git の外の置き場に、main のいまの版の結果として、緑だけを置く。"""
        path = os.path.join(self.place, "accept", self.w.git("rev-parse", "HEAD") + ".json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"results": {i: {"ok": True, "text": "置かれた結果", "tail": []}
                                   for i in ("DEMO-1", "DEMO-2", "DEMO-3")}}, f, ensure_ascii=False)

    def lock(self):
        git = os.path.join(self.w.repo, ".git")
        chmod_tree(git, False)
        self.addCleanup(chmod_tree, git, True)

    def test_a_planted_result_is_not_used_where_git_is_writable(self):
        self.plant()
        _, out = self.w.run("status", env=self.env)
        self.assertIn(COUNTS, out)
        self.assertNotIn(FORGED, out)

    def test_the_stop_gate_is_not_fooled_by_a_planted_result(self):
        start = {"hook_event_name": "SessionStart", "session_id": "t1"}
        self.w.run("status", hook=start, env=self.env)
        self.w.write("app/main.txt", "v2\n")
        self.w.commit("DEMO-2 を実装したことにする")                  # 受入は赤いまま。この版の結果は、まだ誰も出していない
        self.plant()
        self.issues[1]["state"] = {"name": "Done", "type": "completed"}
        self.w.linear(self.issues)
        _, out = self.w.run("check", hook={"hook_event_name": "Stop", "session_id": "t1"}, env=self.env)
        verdict = json.loads(out) if out else {}
        self.assertEqual(verdict.get("decision"), "block", out)
        self.assertIn("DEMO-2 題 DEMO-2 … Done なのに受入が落ちている", verdict["reason"])

    def test_the_merge_gate_is_not_fooled_by_a_planted_result(self):
        self.w.git("checkout", "-q", "-b", "work")
        self.w.write("accept/DEMO-1_check", "#!/bin/sh\n# DEMO-1 の観測できる結果\nexit 1\n", True)   # 緑だった受入を赤にした
        self.w.commit("壊す")
        self.plant()                                                # この版の結果として、緑を置く
        rc, out = self.w.run("gate", "main", env=self.env)
        self.assertEqual(rc, 1, out)
        self.assertIn("緑だった受入が赤になった", out)

    def test_a_planted_session_record_does_not_excuse_the_builder(self):
        base.HarnessTest.just_built(self, self.issues)
        self.w.run("setup")
        self.w.commit("フックを登録する")
        time.sleep(1.2)
        os.makedirs(os.path.join(self.place, "session"))
        with open(os.path.join(self.place, "session", "planted.json"), "w", encoding="utf-8") as f:
            json.dump({"keys": [], "blocks": {}, "started": time.time()}, f)        # 受入のあとに始まったセッションがあったことにする
        closed = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + 5))
        self.issues[3] = issue("DEMO-0", "completed", "受入（見直し）: 受入の抜け道を挙げて直した https://example.com/review",
                               completed_at=closed)                 # 建てたセッションが、見直しを自分で閉じた
        self.w.linear(self.issues)
        rc, out = self.w.run("check", "--wellformed", env=self.env)
        self.assertEqual(rc, 1, out)
        self.assertIn(BUILT, out)

    def test_where_git_is_not_writable_the_outside_place_is_still_used(self):
        self.lock()                                                 # サンドボックスの中。自分で出した結果は、外の置き場にしか置けない
        _, out = self.w.run("status", env=self.env)
        self.assertIn(COUNTS, out)
        self.assertTrue(os.path.isdir(os.path.join(self.place, "accept")))
        self.plant()                                                # 同じ置き場の結果を、次に走らせたときに読む
        _, out = self.w.run("status", env=self.env)
        self.assertIn(FORGED, out)


if __name__ == "__main__":
    unittest.main()
