"""MAT-1894: 事故のあとで塞ぐ穴。サンドボックスの中の結果、古い実行の印、開始時に見えなかった結果。

1. Codex のサンドボックスの中のプロセスは、.git に書けても（.git を書ける場所に足した設定）、.git の中の置き場に書かない。
   2026-11-13 に、中で走らせた受入（Codex の本体を使う検査は、入れ子にできず赤い）の結果を、外で動く停止のフックが使い、
   完了済みの Issue 3本を「Done なのに受入が落ちている」と名指しした。セッションは、それを開き直した。
2. 走らせている途中の印に書いてある番号のプロセスを、確かめずに止めない。待ちもしない。
   機械を再起動したあと、その番号は別のプロセスのものになっている。
3. 開始時に受入の結果が無かったセッションが、緑だった受入を壊したら、止める。
"""
import json
import os
import signal
import subprocess
import time
import unittest
from unittest.mock import patch

import tests.test_harness as base
import tests.test_slow as slow
from tests.test_sandbox import COUNTS

INSIDE = {"CODEX_SANDBOX": "seatbelt", "CODEX_SANDBOX_NETWORK_DISABLED": "1"}   # Codex が、サンドボックスの中に置く変数
START = {"hook_event_name": "SessionStart", "session_id": "h1"}
STOP = {"hook_event_name": "Stop", "session_id": "h1"}


class InsideTheSandboxTest(unittest.TestCase):
    def setUp(self):
        # この検査の「外」は、実行元のCodex環境を引き継がずに作る。
        env = {k: v for k, v in base.ENV.items() if k not in INSIDE}
        environment = patch.dict(base.ENV, env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        w = self.w = base.World()
        self.addCleanup(w.close)
        _, self.issues = base.HarnessTest.standard(self)
        self.outside = os.path.join(w.dir, "outside")
        os.makedirs(self.outside)
        self.inside = {**INSIDE, "HARNESS_STORE": self.outside}

    def assert_inside_preserves_existing_store(self, flag):
        self.w.run("status", hook=START)
        place = os.path.join(self.w.repo, ".git", "harness")

        def contents():
            found = {}
            for folder, _, files in os.walk(place):
                for name in files:
                    path = os.path.join(folder, name)
                    with open(path, "rb") as f:
                        found[os.path.relpath(path, place)] = (os.stat(path).st_mtime_ns, f.read())
            return found

        before = contents()
        self.assertTrue(before)
        # 外の既存結果を読めても、中の再実行や同じsession_idの記録で上書きしてはいけない。
        rc, out = self.w.run("status", "--fresh", hook=START,
                             env={flag: INSIDE[flag], "HARNESS_STORE": self.outside})
        self.assertEqual(rc, 0, out)
        self.assertIn(COUNTS, json.loads(out)["hookSpecificOutput"]["additionalContext"])
        after = contents()
        changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        self.assertEqual(changed, [], "中の実行が .git の置き場を書き換えた")
        self.assertTrue(os.listdir(self.outside))

    def test_codex_sandbox_alone_preserves_the_existing_outside_hook_store(self):
        self.assert_inside_preserves_existing_store("CODEX_SANDBOX")

    def test_network_disabled_alone_preserves_the_existing_outside_hook_store(self):
        self.assert_inside_preserves_existing_store("CODEX_SANDBOX_NETWORK_DISABLED")

    def test_nothing_is_put_in_git_from_inside_even_when_git_is_writable(self):
        _, out = self.w.run("status", env=self.inside)
        self.assertIn(COUNTS, out)
        self.assertFalse(os.path.exists(os.path.join(self.w.repo, ".git", "harness")))
        self.assertTrue(os.listdir(self.outside))                            # 中で出した結果は、外の置き場にある

    def test_a_result_from_inside_is_not_used_by_the_hook_outside(self):
        self.w.write("accept/DEMO-1_check", '#!/bin/sh\n# DEMO-1 の観測できる結果\n[ -z "$CODEX_SANDBOX" ]\n', True)
        sha = self.w.commit("入れ子にできない検査のように、サンドボックスの中では通らない受入")
        self.issues[0]["description"] = self.w.auto("DEMO-1", sha)
        self.w.linear(self.issues)
        _, out = self.w.run("status", hook=START)                            # 外で動くフック
        self.assertIn(COUNTS, json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.w.run("status", "--fresh", env=self.inside)                     # 中のエージェントが、手で走らせ直した（DEMO-1 は赤い）
        self.assertEqual(self.w.run("check", hook=STOP), (0, ""))            # 外のフックは、中で出た赤を使わない
        self.assertIn(COUNTS, self.w.run("status")[1])


class StaleMarkTest(unittest.TestCase):
    """走らせている途中の印（置き場の accept/<版>.run。中身は {"pid": 番号}）が、実行が消えたあとに残っている。"""

    def setUp(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        _, self.issues = base.HarnessTest.standard(self)
        self.assertIn(COUNTS, w.run("status")[1])
        self.place = os.path.join(w.repo, ".git", "harness", "accept")
        self.bystander = subprocess.Popen(["sleep", "120"])                  # 関係のないプロセス。再起動のあと、印の番号はこういうものを指す
        self.addCleanup(self.bystander.wait)
        self.addCleanup(self.bystander.kill)
        self.w.write("app/main.txt", "v2\n")
        self.sha = self.w.commit("main が動いた")                             # この版の結果は、まだ無い

    def mark(self, sha):
        with open(os.path.join(self.place, sha + ".run"), "w", encoding="utf-8") as f:
            json.dump({"pid": self.bystander.pid}, f)

    def test_a_mark_for_another_version_does_not_get_a_bystander_stopped(self):
        self.mark("0" * 40)
        self.assertIn(COUNTS, self.w.run("status")[1])
        time.sleep(0.5)
        self.assertIsNone(self.bystander.poll())
        self.assertEqual([n for n in os.listdir(self.place) if not n.endswith(".json")], [])   # 古い印は片づけた

    def test_a_mark_for_this_version_is_not_taken_for_a_run_in_progress(self):
        self.mark(self.sha)
        _, out = self.w.run("status", hook=START, env={"HARNESS_TIMEOUT": "20"})
        self.assertIn(COUNTS, json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.bystander.poll())


class BlindStartTest(unittest.TestCase):
    """受入は3本で6秒かかり、フックが待つのは2秒。開始時に、受入の結果は無い。"""

    slow, context, until = (getattr(slow.SlowAcceptanceTest, name) for name in ("slow", "context", "until"))

    def setUp(self):
        slow.SlowAcceptanceTest.setUp(self)
        self.slow("DEMO-1", True, body='sleep 2\ngrep -q v1 app/main.txt || exit 1')
        sha = self.w.commit("DEMO-1 の受入は、動いているものを見る")
        self.issues[0]["description"] = self.w.auto("DEMO-1", sha)
        self.w.linear(self.issues)

    def test_a_session_that_broke_a_green_acceptance_is_held_once_the_result_is_there(self):
        self.assertIn(slow.GOING, self.context())
        self.w.write("app/main.txt", "v2\n")
        self.w.commit("このセッションが、緑だった受入を壊す変更を main に入れた")

        def held():
            out = self.w.run("check", hook=slow.STOP, env=self.env)[1]
            verdict = json.loads(out) if out else {}
            return verdict if verdict.get("decision") == "block" else None

        verdict = self.until(held)
        self.assertIn("DEMO-1 題 DEMO-1 … Done なのに受入が落ちている", verdict["reason"])

    def test_the_start_version_result_exempts_only_the_preexisting_problem_after_main_moves(self):
        self.issues[1]["state"] = {"name": "Done", "type": "completed"}
        self.w.linear(self.issues)
        self.assertIn(slow.GOING, self.context())
        self.until(lambda: "受入  緑 1 ／ 赤 1 ／ 未実装 1"
                   in self.w.run("status", env=self.env)[1])
        # 開始時の結果は出たが、停止フックはまだ呼んでいない。その後 main が動く。
        self.w.write("app/main.txt", "v2\n")
        self.w.commit("このセッションが DEMO-1 を壊した")

        def held():
            out = self.w.run("check", hook=slow.STOP, env=self.env)[1]
            verdict = json.loads(out) if out else {}
            return verdict if verdict.get("decision") == "block" else None

        verdict = self.until(held)
        self.assertIn("DEMO-1 題 DEMO-1 … Done なのに受入が落ちている", verdict["reason"])
        self.assertNotIn("DEMO-2 題", verdict["reason"])


class InterruptedAcceptanceTest(unittest.TestCase):
    until = slow.SlowAcceptanceTest.until

    def test_sigterm_does_not_report_success(self):
        self.w = w = base.World()
        self.addCleanup(w.close)
        pidfile = os.path.join(w.dir, "pid")
        w.write("accept/DEMO-1_check", '#!/bin/sh\necho $$ > "$PIDFILE"\nexec sleep 50\n', True)
        process = subprocess.Popen([base.HARNESS, "accept"], cwd=w.repo, start_new_session=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env={**base.ENV, "PIDFILE": pidfile, "HARNESS_TIMEOUT": "60"})
        child = None
        try:
            def started():
                if os.path.exists(pidfile):
                    with open(pidfile) as f:
                        return f.read().strip()

            child = int(self.until(started))
            process.terminate()
            out, err = process.communicate(timeout=10)
            self.assertNotEqual(process.returncode, 0, out + err)
        finally:
            for pid, grouped in ((process.pid, True), (child, False)):
                if pid is not None:
                    try:
                        (os.killpg if grouped else os.kill)(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
