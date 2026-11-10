"""MAT-1816: Codexのエンジンで、フックが現在地を渡し、停止の門が止めて通す。

Codex の本体を、台本どおりに答える手元の「モデル」につないで走らせる。ログインも実物のモデルも要らない。
使い捨ての CODEX_HOME を使い、~/.codex には触らない。codex が無い環境では飛ばす。
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import tests.test_harness as base

SKILL = os.path.dirname(base.HARNESS)


class CodexSetupTest(unittest.TestCase):
    def test_setup_says_what_codex_still_needs_from_a_person(self):
        """Codex は、信頼されていないフックを黙って走らせない。登録しただけでは動かないことを、登録の時点で言う。"""
        w = base.World()
        self.addCleanup(w.close)
        w.commit("init")
        _, out = w.run("setup")
        self.assertIn(".codex/hooks.json", out)
        self.assertIn("Codex では、このリポジトリを信頼し、フックを確認する操作が初回に要る", out)


@unittest.skipUnless(shutil.which("codex"), "codex が無い環境では飛ばす")
class CodexEngineTest(unittest.TestCase):
    def setUp(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        base.HarnessTest.standard(self)
        shutil.copytree(SKILL, os.path.join(w.repo, ".agents", "skills", "linear-workflow"))   # Codexがスキルを探す場所
        w.run("setup")
        w.commit("スキルとフックを置く")
        self.repo = os.path.realpath(w.repo)
        self.requests, self.fix = [], True
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
                work = os.path.join(test.repo, "app", "work.txt")
                if n == 1:                                           # エージェントが仕事をして、commit しなかった
                    with open(work, "w", encoding="utf-8") as f:
                        f.write("commit していない\n")
                elif test.fix and os.path.exists(work):              # 止められたので、片づけた
                    os.remove(work)
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

    def codex(self):
        p = subprocess.run(["codex", "exec", "--ephemeral", "--dangerously-bypass-hook-trust", "-s", "workspace-write",
                            "-C", self.repo, "続きやって"], capture_output=True, text=True, timeout=200,
                           stdin=subprocess.DEVNULL, env={**base.ENV, "CODEX_HOME": self.home})
        return p.returncode, p.stdout + p.stderr

    def test_position_reaches_the_model_and_the_stop_gate_blocks_until_fixed(self):
        rc, out = self.codex()
        self.assertEqual(rc, 0, out[-800:])
        self.assertEqual(len(self.requests), 2, out[-800:])
        first, second = (json.dumps(json.loads(body), ensure_ascii=False) for body in self.requests)
        for needle in ("現在地（導出", "受入  緑 1 ／ 赤 0 ／ 未実装 2", "前線  DEMO-2", "linear-workflow: ", "## 進め方"):
            self.assertIn(needle, first)
        self.assertNotIn("止める前に", first)
        self.assertIn("止める前に、このセッションで生じた食い違いを直す", second)
        self.assertIn("commit されていない変更が 1 件ある（app/work.txt）", second)
        self.assertEqual(self.w.git("status", "--porcelain"), "")

    def test_same_reason_stops_twice_and_the_third_time_lets_go(self):
        self.fix = False
        rc, out = self.codex()
        self.assertEqual(rc, 0, out[-800:])
        self.assertEqual(len(self.requests), 3, out[-800:])


if __name__ == "__main__":
    unittest.main()
