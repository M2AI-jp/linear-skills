"""MAT-1893: 受入が時間内に終わらなくても、走らせ続けて、次に使う。

フックは長く待てない。待つ時間（HARNESS_TIMEOUT）を過ぎたら、打ち切って捨てるのではなく、走らせたまま戻る。
終われば、その版の結果として置き場に残り、次の呼び出しが使う。手で走らせたときと統合の門は、最後まで待つ。
"""
import json
import os
import re
import time
import unittest

import tests.test_harness as base
from tests.test_sandbox import COUNTS

START = {"hook_event_name": "SessionStart", "session_id": "sl1"}
STOP = {"hook_event_name": "Stop", "session_id": "sl1"}
GOING = "走らせ続けている"


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class SlowAcceptanceTest(unittest.TestCase):
    """受入は3本で、1本が2秒かかる（全部で6秒）。フックが待つのは2秒。1本ごとの上限は60秒。"""

    def setUp(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        self.runs = os.path.join(w.dir, "runs")
        self.pid = os.path.join(w.dir, "pid")
        self.env = {"HARNESS_TIMEOUT": "2", "RUNS": self.runs, "PIDFILE": self.pid}
        with open(os.path.join(w.repo, "AGENTS.md"), encoding="utf-8") as f:
            text = f.read()
        w.write("AGENTS.md", re.sub(r"(?m)^- 受入: .*$", lambda _: f"- 受入: `HARNESS_TIMEOUT=60 {base.HARNESS} accept`", text))
        for ident, ok in (("DEMO-1", True), ("DEMO-2", False), ("DEMO-3", False)):
            self.slow(ident, ok)
        sha = w.commit("遅い受入を置く")
        self.issues = [base.issue("DEMO-1", "completed", w.auto("DEMO-1", sha)),
                       base.issue("DEMO-2", "unstarted", w.auto("DEMO-2", sha), blocked_by={"DEMO-0": "completed"}),
                       base.issue("DEMO-3", "unstarted", w.auto("DEMO-3", sha),
                                  blocked_by={"DEMO-0": "completed", "DEMO-2": "unstarted"}),
                       base.issue("DEMO-0", "completed", "受入（見直し）: 受入の抜け道を挙げて直した https://example.com/review")]
        w.linear(self.issues)

    def slow(self, ident, ok, body='sleep 2\necho {ident} >> "$RUNS"'):
        self.w.write(f"accept/{ident}_check", f"#!/bin/sh\n# {ident} の観測できる結果\n{body.format(ident=ident)}\nexit {0 if ok else 1}\n", True)

    def context(self):
        rc, out = self.w.run("status", hook=START, env=self.env)
        self.assertEqual(rc, 0, out)
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]

    def until(self, check, seconds=90):
        end = time.time() + seconds
        while time.time() < end:
            got = check()
            if got:
                return got
            time.sleep(0.5)
        self.fail("時間内にそうならなかった")

    def ran(self):
        with open(self.runs, encoding="utf-8") as f:
            return sorted(f.read().split())

    def test_a_hook_stops_waiting_and_the_run_goes_on_to_be_used_next_time(self):
        first = self.context()
        self.assertLess(len(self.ran()) if os.path.exists(self.runs) else 0, 3)   # フックは、3本とも終わるのを待っていない
        self.assertIn(GOING, first)
        self.assertNotIn("走らせられなかった", first)                        # 途中であって、失敗ではない
        self.assertNotIn(COUNTS, first)
        self.assertIn("前線  DEMO-2 題 DEMO-2（Todo）", first)                # Linearから分かることは、待たずに出す
        self.until(lambda: COUNTS in self.context())
        self.assertEqual(self.ran(), ["DEMO-1", "DEMO-2", "DEMO-3"])         # 途中でやり直していない。1本ずつ、1回だけ
        place = os.path.join(self.w.repo, ".git", "harness", "accept")
        self.assertEqual([n for n in os.listdir(place) if not n.endswith(".json")], [])   # 結果のほかには、何も残っていない
        self.assertEqual(self.w.git("status", "--porcelain"), "")

    def test_by_hand_it_waits_to_the_end(self):
        rc, out = self.w.run("status", env=self.env)
        self.assertEqual(rc, 0)
        self.assertIn(COUNTS, out)
        self.assertNotIn(GOING, out)

    def test_the_merge_gate_waits_to_the_end(self):
        self.w.run("status", env=self.env)
        self.w.git("checkout", "-q", "-b", "work")
        self.w.write("app/main.txt", "v2\n")
        self.w.commit("変更")
        rc, out = self.w.run("gate", "main", env=self.env)
        self.assertEqual(rc, 0, out)
        self.assertIn("緑だった受入 1 本は緑のまま", out)

    def test_the_merge_gate_waits_and_refuses_a_slow_regression(self):
        self.w.run("status", env=self.env)
        self.w.git("checkout", "-q", "-b", "work")
        self.slow("DEMO-1", False)
        self.w.commit("緑だった受入を壊す")
        rc, out = self.w.run("gate", "main", env=self.env)
        self.assertEqual(rc, 1, out)
        self.assertIn("DEMO-1", out)
        self.assertIn("緑だった受入が赤になった", out)

    def test_a_failed_background_command_is_remembered_without_restarting(self):
        with open(os.path.join(self.w.repo, "AGENTS.md"), encoding="utf-8") as f:
            text = f.read()
        self.w.write("fail.sh", '#!/bin/sh\necho run >> "$RUNS"\nsleep 4\nexit 3\n', True)
        self.w.write("AGENTS.md", re.sub(r"(?m)^- 受入: .*$", "- 受入: `./fail.sh`", text))
        self.w.commit("行を出さずに失敗する遅いコマンド")
        self.assertIn(GOING, self.context())
        self.until(lambda: GOING not in self.context())                     # 終わった（行を出さずに落ちた）
        self.assertIn("受入  走らせられなかった", self.context())
        self.assertIn("受入  走らせられなかった", self.context())
        self.assertEqual(self.ran(), ["run"])                               # 呼ばれるたびに、やり直していない

    def test_what_could_not_be_seen_at_the_start_does_not_hold_the_session(self):
        self.issues[1]["state"] = {"name": "Done", "type": "completed"}       # 前からある食い違い: DEMO-2 は Done だが、受入は赤い
        self.w.linear(self.issues)
        self.assertIn(GOING, self.context())                                 # 開始時には、受入の結果がまだ無い
        self.until(lambda: "DEMO-2 題 DEMO-2 … Done なのに受入が落ちている" in self.w.run("status", env=self.env)[1])
        self.assertEqual(self.w.run("check", hook=STOP, env=self.env), (0, ""))
        self.issues[2]["state"] = {"name": "Done", "type": "completed"}       # このセッションが、赤いまま DEMO-3 を閉じた
        self.w.linear(self.issues)
        verdict = json.loads(self.w.run("check", hook=STOP, env=self.env)[1])
        self.assertEqual(verdict.get("decision"), "block")
        self.assertIn("DEMO-3 題 DEMO-3 … Done なのに受入が落ちている", verdict["reason"])
        self.assertNotIn("DEMO-2 題", verdict["reason"])

    def test_when_main_moves_the_run_for_the_old_version_is_stopped(self):
        self.slow("DEMO-3", False, body='echo $$ > "$PIDFILE"\nexec sleep 50')     # この版の実行は、自分では終わらない
        self.w.commit("終わらない受入")
        self.assertIn(GOING, self.context())
        old = int(self.until(lambda: os.path.exists(self.pid) and open(self.pid).read().strip()))
        self.assertTrue(alive(old))
        self.slow("DEMO-3", False)
        self.w.commit("受入を直す")                                           # main が動いた
        rc, out = self.w.run("status", env=self.env)
        self.assertIn("受入  緑 1 ／ 赤 0 ／ 未実装 2", out)                   # 新しい版の結果
        self.until(lambda: not alive(old), 10)

    def test_a_timed_out_acceptance_takes_what_it_started_with_it(self):
        self.slow("DEMO-1", True, body='sleep 50 &\necho $! > "$PIDFILE"\nwait')
        rc, out = self.w.run("accept", env=self.env)                          # 1本ごとの上限は2秒
        self.assertEqual(rc, 1)
        self.assertIn("赤 DEMO-1", out)
        self.assertIn("2 秒で終わらなかった", out)
        child = int(open(self.pid).read().strip())
        self.until(lambda: not alive(child), 10)


if __name__ == "__main__":
    unittest.main()
