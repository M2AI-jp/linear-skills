"""MAT-1890: サンドボックスの中で建てたセッションにも、建て終わりの判定が届く。

Codex のサンドボックスは、既定でネットワークを閉じている。エージェントが中で走らせる harness は Linear に届かない。
フックは外で動く。だから、フックが登録済みで入口がまだ無いところから建てたセッションには、停止のフックが建て終わりを判定する。
中で走らせた harness は、届かない理由と、どうするかを言う。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import tests.test_harness as base

SKILL = os.path.dirname(base.HARNESS)
NOT_YET = "まだ整っていない"
NO_PERSON = "人が確かめるIssue（受入（人））が無い"
OUTSIDE = "サンドボックスの外で走らせる"
CLOSED = {"CODEX_SANDBOX_NETWORK_DISABLED": "1"}        # Codex が、ネットワークを閉じたサンドボックスの中に置く変数


def entry(w):
    """入口のブロック。World(entry=False) の場所に、あとから書く。"""
    return ("\n## 進め方\n"
            "- 正本: https://linear.app/demo/project/demo-0123456789ab\n"
            f"- Linearの叩き方: `python3 {os.path.join(w.dir, 'fake_linear.py')} {w.fixture}`\n"
            f"- 受入: `{base.HARNESS} accept`（出力は Issue ID ごとの緑・赤）\n"
            "- モジュール: app = 予約\n"
            "- 確認が要る: 本番の設定変更、送信\n")


def build(test, human):
    """入口を書き、受入を置いて commit し、Linear を建てた直後の形にする。human=False なら、人が確かめるIssueを立て忘れている。"""
    if not hasattr(test, "issues"):
        test.w.write("AGENTS.md", "# demo\n" + entry(test.w))
        _, test.issues = base.HarnessTest.standard(test)
    base.HarnessTest.just_built(test, test.issues, human=human)


class BuiltBySessionTest(unittest.TestCase):
    """フックは登録済みで、入口はまだ無い。そこから始まったセッションが建てる。"""

    def setUp(self):
        w = self.w = base.World(entry=False)
        self.addCleanup(w.close)
        w.run("setup")
        w.commit("人が先にフックを登録した")
        self.start = {"hook_event_name": "SessionStart", "session_id": "s1"}
        self.stop = {"hook_event_name": "Stop", "session_id": "s1"}

    def verdict(self, hook=None):
        rc, out = self.w.run("check", hook=hook or self.stop)
        self.assertEqual(rc, 0, out)
        return json.loads(out) if out else {}

    def test_nothing_is_said_while_there_is_no_entry(self):
        self.assertEqual(self.w.run("status", hook=self.start), (0, ""))
        self.assertEqual(self.w.run("check", hook=self.stop), (0, ""))
        self.assertEqual(self.w.git("status", "--porcelain"), "")           # 作業ツリーには何も置かない

    def test_the_session_that_built_is_held_until_the_build_is_finished(self):
        self.w.run("status", hook=self.start)
        build(self, human=False)
        held = self.verdict()
        self.assertEqual(held.get("decision"), "block", held)
        self.assertIn(NOT_YET, held["reason"])
        self.assertIn(NO_PERSON, held["reason"])
        build(self, human=True)                                             # 名指しされたものを直した
        self.assertNotIn("decision", self.verdict())

    def test_a_finished_build_is_let_go_the_first_time(self):
        self.w.run("status", hook=self.start)
        build(self, human=True)
        self.assertNotIn("decision", self.verdict())

    def test_uncommitted_work_of_the_build_is_named(self):
        self.w.run("status", hook=self.start)
        build(self, human=True)
        self.w.write("app/note.txt", "commit していない\n")
        held = self.verdict()
        self.assertEqual(held.get("decision"), "block", held)
        self.assertIn("commit されていない変更が 1 件ある（app/note.txt）", held["reason"])

    def test_the_same_reason_holds_twice_and_the_third_time_lets_go(self):
        self.w.run("status", hook=self.start)
        build(self, human=False)
        self.assertEqual(self.verdict().get("decision"), "block")
        self.assertEqual(self.verdict().get("decision"), "block")
        third = self.verdict()
        self.assertNotIn("decision", third)
        self.assertIn("同じ理由で2回止めたので通した", third.get("systemMessage", ""))
        self.assertIn(NO_PERSON, third["systemMessage"])

    def test_after_the_build_it_is_an_ordinary_session(self):
        self.w.run("status", hook=self.start)
        build(self, human=True)
        self.assertNotIn("decision", self.verdict())
        self.w.write("app/new.txt", "commit していない\n")                    # 建て終えたあとに生じた食い違い
        held = self.verdict()
        self.assertEqual(held.get("decision"), "block", held)
        self.assertIn("止める前に、このセッションで生じた食い違いを直す", held["reason"])
        self.assertNotIn(NOT_YET, held["reason"])

    def test_the_builder_still_cannot_close_the_review_of_its_own_acceptances(self):
        self.w.run("status", hook=self.start)
        build(self, human=True)
        self.assertNotIn("decision", self.verdict())                        # 建て終えた
        self.issues[3]["state"] = {"name": "Done", "type": "completed"}      # そのセッションが、見直しを自分で閉じた
        self.issues[3]["description"] = "受入（見直し）: 受入の抜け道を挙げて直した https://example.com/review"
        self.w.linear(self.issues)
        held = self.verdict()
        self.assertEqual(held.get("decision"), "block", held)
        self.assertIn("DEMO-0 受入を書いたセッションが、その見直しを閉じている", held["reason"])

    def test_a_later_session_is_not_judged_as_a_build(self):
        self.w.run("status", hook=self.start)
        build(self, human=False)                                            # 建て終わっていないまま、次のセッションが始まった
        later = {"hook_event_name": "SessionStart", "session_id": "s2"}
        rc, out = self.w.run("status", hook=later)
        self.assertIn("現在地（導出", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.w.run("check", hook={"hook_event_name": "Stop", "session_id": "s2"}), (0, ""))

    def test_a_session_whose_start_was_not_seen_is_not_judged_as_a_build(self):
        build(self, human=False)                                            # 開始のフックが走らなかった。建てたかどうかは分からない
        self.assertEqual(self.w.run("check", hook=self.stop), (0, ""))
        self.w.write("app/new.txt", "commit していない\n")
        held = self.verdict()
        self.assertEqual(held.get("decision"), "block", held)                # 最初の停止を開始として、そこからの食い違いは止める
        self.assertNotIn(NOT_YET, held["reason"])


class ClosedNetworkTest(unittest.TestCase):
    """Codex のサンドボックスの中で、Linear に届かないとき。"""

    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        _, self.issues = base.HarnessTest.standard(self)

    def test_it_says_where_to_run_instead(self):
        self.w.linear(self.issues, down=True)
        for args in (["status"], ["check"], ["check", "--wellformed"]):
            _, out = self.w.run(*args, env=CLOSED)
            self.assertIn("届かない", out, args)
            self.assertIn(OUTSIDE, out, args)

    def test_it_does_not_say_so_outside_the_sandbox(self):
        self.w.linear(self.issues, down=True)
        for args in (["status"], ["check"], ["check", "--wellformed"]):
            _, out = self.w.run(*args)
            self.assertIn("届かない", out, args)
            self.assertNotIn("サンドボックス", out, args)

    def test_it_does_not_say_so_when_linear_is_reached(self):
        _, out = self.w.run("status", env=CLOSED)                           # 中からでも届く叩き方（ネットワークを使わないもの）がある
        self.assertIn("食い違い  なし", out)
        self.assertNotIn("サンドボックス", out)

    @unittest.skipUnless(shutil.which("codex"), "codex が無い環境では飛ばす")
    def test_inside_the_real_codex_sandbox(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        store = tempfile.mkdtemp()                                          # 中からは .git に書けない。置き場を、片づけられる場所にする
        self.addCleanup(shutil.rmtree, store, True)

        def sandboxed(*command):
            return subprocess.run(["codex", "sandbox", "-c", 'sandbox_mode="workspace-write"', "--", *command],
                                  cwd=os.path.realpath(self.w.repo), capture_output=True, text=True, timeout=180,
                                  stdin=subprocess.DEVNULL, env={**base.ENV, "CODEX_HOME": home, "TMPDIR": store})

        probe = sandboxed("/bin/sh", "-c", "exit 0")                        # 飛ばしてよいのは、サンドボックスが立たない既知の環境だけ
        if probe.returncode != 0:
            known = "bwrap:" in probe.stderr and ("RTM_NEWADDR" in probe.stderr or "Operation not permitted" in probe.stderr)
            if sys.platform == "darwin" or not known:
                self.fail("Codex のサンドボックスが立たない: " + probe.stderr[-400:])
            self.skipTest("この環境では Codex のサンドボックスが立たない: " + probe.stderr.strip()[-200:])
        self.w.linear(self.issues, down=True)
        out = sandboxed(base.HARNESS, "status").stdout                      # 変数は Codex 自身が置く
        self.assertIn("届かない", out)
        self.assertIn(OUTSIDE, out)


@unittest.skipUnless(shutil.which("codex"), "codex が無い環境では飛ばす")
class CodexBuildTest(unittest.TestCase):
    """Codex の本体を、台本どおりに答える手元の「モデル」につなぐ。使い捨ての CODEX_HOME を使い、~/.codex には触らない。"""

    def setUp(self):
        w = self.w = base.World(entry=False)
        self.addCleanup(w.close)
        shutil.copytree(SKILL, os.path.join(w.repo, ".agents", "skills", "linear-workflow"))   # Codexがスキルを探す場所
        w.run("setup")
        w.commit("人が先にスキルを置き、フックを登録した")
        self.repo = os.path.realpath(w.repo)
        self.requests = []
        test = self

        class Scripted(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"data":[],"models":[]}')

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
                test.requests.append(body)
                n = len(test.requests)
                build(test, human=n > 1)                         # 1手目は人が確かめるIssueを立て忘れる。止められたら立てる
                events = [
                    {"type": "response.created", "response": {"id": f"r{n}"}},
                    {"type": "response.output_item.done", "item": {"type": "message", "role": "assistant", "id": f"m{n}",
                                                                   "content": [{"type": "output_text", "text": f"台本の返事 {n}"}]}},
                    {"type": "response.completed", "response": {"id": f"r{n}", "usage": {
                        "input_tokens": 1, "input_tokens_details": None, "output_tokens": 1,
                        "output_tokens_details": None, "total_tokens": 2}}},
                ]
                out = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.server = HTTPServer(("127.0.0.1", 0), Scripted)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        with open(os.path.join(self.home, "config.toml"), "w", encoding="utf-8") as f:
            f.write('model = "scripted"\nmodel_provider = "scripted"\n\n[model_providers.scripted]\nname = "scripted"\n'
                    f'base_url = "http://127.0.0.1:{self.server.server_address[1]}/v1"\nwire_api = "responses"\n\n'
                    f'[projects."{self.repo}"]\ntrust_level = "trusted"\n')

    def test_the_stop_hook_judges_the_build_outside_the_sandbox(self):
        p = subprocess.run(["codex", "exec", "--ephemeral", "--dangerously-bypass-hook-trust", "-s", "workspace-write",
                            "-C", self.repo, "Linearで進められるようにして"], capture_output=True, text=True, timeout=200,
                           stdin=subprocess.DEVNULL, env={**base.ENV, "CODEX_HOME": self.home})
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 0, out[-800:])
        self.assertEqual(len(self.requests), 2, out[-800:])
        first, second = (json.dumps(json.loads(body), ensure_ascii=False) for body in self.requests)
        self.assertNotIn("現在地（導出", first)                     # 入口が無い間、開始のフックは黙っている
        self.assertNotIn(NOT_YET, first)
        self.assertIn(NOT_YET, second)                              # 止められた理由が、次の手の入力に入る
        self.assertIn(NO_PERSON, second)
        rc, verdict = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, verdict)


if __name__ == "__main__":
    unittest.main()
