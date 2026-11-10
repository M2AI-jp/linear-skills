"""機構のテスト。モデルを呼ばない。仕込んだ固定データに対して、harness が名指しするかを見る。"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HARNESS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "skills", "linear-workflow", "harness")
FAKE_LINEAR = """#!/usr/bin/env python3
import json, sys
req = json.load(sys.stdin)
data = json.load(open(sys.argv[1], encoding="utf-8"))
if data.get("down"):
    sys.exit("network down")
if "project(" in req["query"]:
    print(json.dumps({"data": {"project": data["project"]}}))
else:
    print(json.dumps({"data": {"issues": {"nodes": data["issues"],
          "pageInfo": {"hasNextPage": False, "endCursor": None}}}}))
"""
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": os.devnull}
STATES = {"backlog": "Backlog", "unstarted": "Todo", "started": "In Progress",
          "completed": "Done", "canceled": "Canceled"}


def issue(ident, kind, desc="", archived=False, blocked_by=(), completed_at=None):
    """blocked_by は、待っているIssueのID→その状態の種類。並びで渡せば、どれも未着手。"""
    waits = blocked_by if isinstance(blocked_by, dict) else {b: "unstarted" for b in blocked_by}
    return {"identifier": ident, "title": "題 " + ident, "description": desc,
            "archivedAt": "2026-01-01T00:00:00Z" if archived else None, "completedAt": completed_at,
            "state": {"name": STATES[kind], "type": kind}, "projectMilestone": {"name": "予約"},
            "inverseRelations": {"nodes": [
                {"type": "blocks", "issue": {"identifier": b, "state": {"type": t}}} for b, t in waits.items()]}}


class World:
    def __init__(self, entry=True):
        self.dir = tempfile.mkdtemp()
        self.repo = os.path.join(self.dir, "repo")
        self.fixture = os.path.join(self.dir, "linear.json")
        fake = os.path.join(self.dir, "fake_linear.py")
        with open(fake, "w") as f:
            f.write(FAKE_LINEAR)
        os.makedirs(os.path.join(self.repo, "app"))
        self.git("init", "-q", "-b", "main")
        text = "# demo\n"
        if entry:
            text += ("\n## 進め方\n"
                     "- 正本: https://linear.app/demo/project/demo-0123456789ab\n"
                     f"- Linearの叩き方: `python3 {fake} {self.fixture}`\n"
                     f"- 受入: `{HARNESS} accept`（出力は Issue ID ごとの緑・赤）\n"
                     "- モジュール: app = 予約\n"
                     "- 確認が要る: 本番の設定変更、送信\n")
        self.write("AGENTS.md", text)
        self.write("app/main.txt", "v1\n")

    def git(self, *args):
        p = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, env=ENV)
        assert p.returncode == 0, p.stderr
        return p.stdout.strip()

    def write(self, path, text, executable=False):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
        if executable:
            os.chmod(full, 0o755)

    def accept(self, ident, ok=True):
        self.write(f"accept/{ident}_check", f"#!/bin/sh\n# {ident} の観測できる結果\nexit {0 if ok else 1}\n", True)
        return f"accept/{ident}_check"

    def commit(self, message="work"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def linear(self, issues, status="started", down=False):
        with open(self.fixture, "w", encoding="utf-8") as f:
            json.dump({"down": down, "issues": issues,
                       "project": {"id": "p1", "name": "デモ", "status": {"type": status, "name": status},
                                   "projectMilestones": {"nodes": [{"name": "予約"}]}}}, f, ensure_ascii=False)

    def run(self, *args, hook=None, cwd=None):
        # フックは --hook を付けて、標準入力にJSONを渡す。手で走らせるときは標準入力を閉じない（読まれないこと）
        if hook:
            p = subprocess.run([HARNESS, *args, "--hook"], cwd=cwd or self.repo, capture_output=True, text=True,
                               env=ENV, input=json.dumps(hook))
        else:
            reader, writer = os.pipe()
            try:
                p = subprocess.run([HARNESS, *args], cwd=cwd or self.repo, capture_output=True, text=True,
                                   env=ENV, stdin=reader, timeout=120)
            finally:
                os.close(reader)
                os.close(writer)
        return p.returncode, p.stdout.strip()

    def auto(self, ident, sha):
        return f"受入（自動）: {ident} の観測できる結果 accept/{ident}_check@{sha}"

    def json(self, path):
        with open(os.path.join(self.repo, path), encoding="utf-8") as f:
            return json.load(f)

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class HarnessTest(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.addCleanup(self.w.close)

    def standard(self):
        """DEMO-1 は Done で緑、DEMO-2 は Todo で赤、DEMO-3 は DEMO-2 待ち。食い違いは無い。
        DEMO-0 は受入を見直したIssueで、もう閉じている。DEMO-2 と DEMO-3 はそれを待っていた。"""
        w = self.w
        w.accept("DEMO-1", True)
        w.accept("DEMO-2", False)
        w.accept("DEMO-3", False)
        sha = w.commit("DEMO-1 を実装し、受入を置く")
        issues = [issue("DEMO-1", "completed", w.auto("DEMO-1", sha)),
                  issue("DEMO-2", "unstarted", w.auto("DEMO-2", sha), blocked_by={"DEMO-0": "completed"}),
                  issue("DEMO-3", "unstarted", w.auto("DEMO-3", sha),
                        blocked_by={"DEMO-0": "completed", "DEMO-2": "unstarted"}),
                  issue("DEMO-0", "completed", "受入（見直し）: 受入の抜け道を挙げて直した https://example.com/review")]
        w.linear(issues)
        return sha, issues

    def just_built(self, issues):
        """建てた直後の形にする。見直しの DEMO-0 はまだ開いていて、DEMO-2 と DEMO-3 はそれを待っている。"""
        issues[3]["state"] = {"name": "Todo", "type": "unstarted"}
        issues[3]["description"] = "受入（見直し）: 受入の抜け道を別の文脈が挙げて直す"
        for waiting in issues[1:3]:
            for node in waiting["inverseRelations"]["nodes"]:
                if node["issue"]["identifier"] == "DEMO-0":
                    node["issue"]["state"]["type"] = "unstarted"
        self.w.linear(issues)

    def test_no_entry_means_no_output(self):
        w = World(entry=False)
        self.addCleanup(w.close)
        w.commit("init")
        for sub in ("status", "check"):
            self.assertEqual(w.run(sub, hook={"hook_event_name": "Stop", "session_id": "s"}), (0, ""))
        self.assertEqual(w.run("status", cwd=w.dir), (0, ""))
        self.assertFalse(os.path.exists(os.path.join(w.repo, ".git", "harness")))
        w.write("AGENTS.md", "# demo\n\n## 進め方\n- 受入: `true`\n")       # 書きかけの入口も、入口ではない
        self.assertEqual(w.run("status"), (0, ""))
        rc, out = w.run("check", "--wellformed")                            # 建て終わりの判定だけは黙らない
        self.assertEqual(rc, 1)
        self.assertIn("入口が無い", out)

    def test_consistent_state_is_reported_as_position(self):
        self.standard()
        rc, out = self.w.run("status")
        self.assertEqual(rc, 0)
        self.assertIn("受入  緑 1 ／ 赤 0 ／ 未実装 2", out)
        self.assertIn("前線  DEMO-2 題 DEMO-2（Todo）", out)
        self.assertIn("待ち  DEMO-3 題 DEMO-3（DEMO-2 待ち）", out)
        self.assertIn("食い違い  なし", out)
        self.assertIn("確認が要る  本番の設定変更、送信", out)

    def test_rewritten_acceptance_is_named(self):
        self.standard()
        w = self.w
        w.write("accept/DEMO-1_check", "#!/bin/sh\n# 弱めた\nexit 0\n", True)
        w.commit("refactor")
        _, out = w.run("status")
        self.assertIn("DEMO-1 受入が、Issueに書いた版（", out)
        self.assertIn("accept/DEMO-1_check", out)

    def test_done_with_red_acceptance_is_named(self):
        sha, issues = self.standard()
        w = self.w
        w.write("app/main.txt", "v2 壊した\n")
        w.accept("DEMO-1", False)
        new = w.commit("DEMO-2 のついでに")
        issues[0]["description"] = w.auto("DEMO-1", new)
        w.linear(issues)
        _, out = w.run("status")
        self.assertIn("受入  緑 0 ／ 赤 1 ／ 未実装 2", out)
        self.assertIn("DEMO-1 題 DEMO-1 … Done なのに受入が落ちている", out)

    def test_unreachable_artifact_is_named(self):
        sha, issues = self.standard()
        w = self.w
        os.remove(os.path.join(w.repo, "accept/DEMO-1_check"))
        w.commit("片付け")
        issues.append(issue("DEMO-4", "completed", "受入（証拠）: 顧客に送った"))
        w.linear(issues)
        _, out = w.run("status")
        self.assertIn("DEMO-1 受入が main から消えた: accept/DEMO-1_check", out)
        self.assertIn("DEMO-1 Done だが、main の受入に出てこない（成果に到達できない）", out)
        self.assertIn("DEMO-4 Done（証拠）だが、証拠のリンクが無い", out)

    def test_state_that_contradicts_reality_is_named(self):
        sha, issues = self.standard()
        w = self.w
        w.accept("DEMO-5", True)
        sha2 = w.commit("受入を足す")
        issues[1]["state"] = {"name": "In Progress", "type": "started"}          # 着手中だが何も無い
        issues.append(issue("DEMO-5", "unstarted", w.auto("DEMO-5", sha2)))      # 着手前から緑
        issues.append(issue("DEMO-6", "unstarted", "やること"))                   # 受入が無い
        w.linear(issues)
        w.git("checkout", "-q", "-b", "demo-3-list")
        w.write("app/main.txt", "v2\n")
        w.commit("一覧を出す")
        w.git("checkout", "-q", "main")
        _, out = w.run("status")
        self.assertIn("DEMO-2 In Progress だが、ブランチも commit も無い", out)
        self.assertIn("DEMO-3 ブランチ demo-3-list（main より 1 先）があるのに Todo のまま", out)
        self.assertIn("DEMO-5 受入が main で緑なのに Todo", out)
        self.assertIn("DEMO-6 Todo だが、受入が無い", out)

    def test_branch_changing_acceptance_is_named(self):
        self.standard()
        w = self.w
        w.git("checkout", "-q", "-b", "demo-2-impl")
        w.write("accept/DEMO-2_check", "#!/bin/sh\n# 通るようにした\nexit 0\n", True)
        _, out = w.run("status")
        self.assertIn("DEMO-2 受入が、このブランチ／作業ツリーで変わっている: accept/DEMO-2_check", out)

    def test_linear_unreachable_is_one_line_and_never_blocks(self):
        sha, issues = self.standard()
        self.w.linear(issues, down=True)
        rc, out = self.w.run("status")
        self.assertEqual(rc, 0)
        self.assertIn("Linear  届かない: network down", out)
        self.assertIn("受入  緑 1 ／ 赤 2", out)
        rc, out = self.w.run("check", hook={"hook_event_name": "Stop", "session_id": "s9"})
        self.assertEqual(rc, 0)
        self.assertNotIn("block", out)

    def test_stop_gate_blocks_new_mismatch_then_breaker_lets_go(self):
        sha, issues = self.standard()
        w = self.w
        issues.append(issue("DEMO-6", "unstarted", "やること"))   # 開始前からある食い違い
        w.linear(issues)
        rc, out = w.run("status", hook={"hook_event_name": "SessionStart", "session_id": "s1"})
        context = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(context["hookEventName"], "SessionStart")
        self.assertIn("DEMO-6 Todo だが、受入が無い", context["additionalContext"])
        stop = {"hook_event_name": "Stop", "session_id": "s1"}
        self.assertEqual(w.run("check", hook=stop), (0, ""))       # 前からある食い違いでは止めない

        w.write("app/main.txt", "v2\n")
        w.accept("DEMO-2", True)
        w.commit("DEMO-2 を実装")                                  # 現実は動いた。Linearは Todo のまま
        for _ in range(2):
            rc, out = w.run("check", hook=stop)
            verdict = json.loads(out)
            self.assertEqual(verdict["decision"], "block")
            self.assertIn("DEMO-2 受入が main で緑なのに Todo", verdict["reason"])
            self.assertNotIn("DEMO-6", verdict["reason"])
        rc, out = w.run("check", hook=stop)                        # 3回目は通す
        self.assertEqual(rc, 0)
        self.assertIn("同じ理由で2回止めたので通した", json.loads(out)["systemMessage"])

        issues[1]["state"] = {"name": "Done", "type": "completed"}
        issues[1]["description"] = w.auto("DEMO-2", w.git("rev-parse", "HEAD"))
        issues[2]["inverseRelations"]["nodes"] = issues[2]["inverseRelations"]["nodes"][:1]
        w.linear(issues)
        self.assertEqual(w.run("check", hook=stop), (0, ""))       # 書き戻したら黙って通す

    def test_acceptance_printing_broken_bytes_does_not_crash_the_runner(self):
        w = self.w
        w.write("accept/DEMO-1_check", "#!/bin/sh\n# 壊れたバイト列を出して落ちる\nprintf '\\343\\201 broken\\n'; exit 1\n", True)
        sha = w.commit("受入")
        w.linear([issue("DEMO-1", "unstarted", w.auto("DEMO-1", sha))])
        rc, out = w.run("status")
        self.assertEqual(rc, 0)
        self.assertIn("受入  緑 0 ／ 赤 0 ／ 未実装 1", out)

    def test_uncommitted_work_is_named_and_stops_the_session_that_made_it(self):
        self.standard()
        w = self.w
        stop = {"hook_event_name": "Stop", "session_id": "s3"}
        w.run("status", hook={"hook_event_name": "SessionStart", "session_id": "s3"})
        w.write("app/main.txt", "v2 実装したが commit していない\n")
        w.write("app/new.txt", "新しいファイル\n")
        _, out = w.run("status")
        self.assertIn("commit されていない変更が 2 件ある（app/main.txt、app/new.txt）", out)
        self.assertIn("直し方は ", out)
        verdict = json.loads(w.run("check", hook=stop)[1])
        self.assertEqual(verdict["decision"], "block")
        self.assertIn("commit されていない変更が 2 件ある", verdict["reason"])
        w.git("checkout", "-q", "-b", "demo-2-impl")
        w.commit("DEMO-2 途中まで")
        verdict = json.loads(w.run("check", hook=stop)[1])         # commit したら、次は Linear が動いていないことを言う
        self.assertIn("DEMO-2 ブランチ demo-2-impl（main より 1 先）があるのに Todo のまま", verdict["reason"])
        self.assertNotIn("commit されていない", verdict["reason"])

    def test_work_left_uncommitted_before_the_session_does_not_stop_it(self):
        self.standard()
        w = self.w
        w.write("notes.txt", "前からある\n")
        w.run("status", hook={"hook_event_name": "SessionStart", "session_id": "s4"})
        self.assertEqual(w.run("check", hook={"hook_event_name": "Stop", "session_id": "s4"}), (0, ""))

    def test_merge_gate_refuses_green_to_red(self):
        self.standard()
        w = self.w
        base = w.git("rev-parse", "HEAD")
        w.accept("DEMO-9", False)
        w.commit("新しい受入（赤）を足す")
        rc, out = w.run("gate", base)
        self.assertEqual(rc, 0, out)
        self.assertIn("この版の受入  緑 1 ／ 赤 3（DEMO-2、DEMO-3、DEMO-9）", out)   # 赤いまま入るものも、見えるようにする
        w.accept("DEMO-1", False)
        w.commit("壊す")
        rc, out = w.run("gate", base)
        self.assertEqual(rc, 1)
        self.assertIn("DEMO-1", out)
        self.assertIn("緑だった受入が赤になった", out)
        os.remove(os.path.join(w.repo, "accept/DEMO-1_check"))
        w.commit("消す")
        rc, out = w.run("gate", base)
        self.assertEqual(rc, 1)
        self.assertIn("緑だった受入が消えた", out)

    def test_wellformed_and_setup(self):
        self.just_built(self.standard()[1])
        w = self.w
        rc, out = w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn("フックに harness status が登録されていない", out)
        w.write(".claude/settings.json", json.dumps({"permissions": {"deny": ["Bash(rm *)"]}}))
        self.assertEqual(w.run("setup")[0], 0)
        old = w.json(".claude/settings.json")
        old["hooks"]["Stop"][0]["hooks"][0]["command"] = "x/harness check"      # 前の版が登録した形
        w.write(".claude/settings.json", json.dumps(old))
        self.assertEqual(w.run("setup")[0], 0)                                  # 足さずに、書き換える
        settings = w.json(".claude/settings.json")
        self.assertIn("check --hook", settings["hooks"]["Stop"][0]["hooks"][0]["command"])
        self.assertEqual(settings["permissions"], {"deny": ["Bash(rm *)"]})
        self.assertEqual(len(settings["hooks"]["SessionStart"]), 1)
        self.assertEqual(len(settings["hooks"]["Stop"]), 1)
        self.assertTrue(os.path.exists(os.path.join(w.repo, ".codex/hooks.json")))
        w.commit("フックを登録")
        rc, out = w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)
        self.assertIn("整っている", out)

    def test_registered_hook_command_runs_and_fails_open(self):
        self.standard()
        w = self.w
        w.run("setup")
        command = w.json(".claude/settings.json")["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        p = subprocess.run(command, shell=True, cwd=w.repo, capture_output=True, text=True, env=ENV,
                           input=json.dumps({"hook_event_name": "SessionStart", "session_id": "s2"}))
        self.assertEqual(p.returncode, 0)
        self.assertIn("additionalContext", p.stdout)
        self.assertIn("--hook", command)
        p = subprocess.run(command.replace("harness", "missing"), shell=True, cwd=w.repo, capture_output=True, text=True, env=ENV)
        self.assertEqual((p.returncode, p.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
