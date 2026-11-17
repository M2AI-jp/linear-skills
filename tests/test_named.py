"""MAT-1938: 名指しのうち、テストの無かったものを確かめる。

いまの動きを、確定仕様として置く。Issue の無い ID、Canceled の受入、モジュール表、Project の状態、所在、
入口が読めないとき、Linear のページングと鍵の経路、門の基準の決め方。
"""
import io
import json
import os
import re
import types
import unittest
from unittest.mock import patch

import tests.test_harness as base
from tests.test_harness import issue

REVIEW = issue("DEMO-0", "completed", "受入（見直し）: 受入の抜け道を挙げて直した https://example.com/review")


def load_harness():
    """harness を、その場で読み込む（モジュールとして置いていないので）。"""
    harness = types.ModuleType("named_harness")
    with open(base.HARNESS, encoding="utf-8") as f:
        exec(compile(f.read(), base.HARNESS, "exec"), harness.__dict__)
    return harness


class NamedTest(unittest.TestCase):
    def setUp(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        w.accept("DEMO-1", True)
        w.accept("DEMO-2", False)
        self.sha = w.commit("DEMO-1 を実装し、受入を置く")
        self.issues = [issue("DEMO-1", "completed", w.auto("DEMO-1", self.sha)),
                       issue("DEMO-2", "unstarted", w.auto("DEMO-2", self.sha), blocked_by={"DEMO-0": "completed"}),
                       REVIEW]

    def project(self, issues, status="started", milestones=("予約",)):
        """Linear の固定データを、Milestone と状態を指定して置く。"""
        with open(self.w.fixture, "w", encoding="utf-8") as f:
            json.dump({"down": False, "issues": issues,
                       "project": {"id": "p1", "name": "デモ", "status": {"type": status, "name": status},
                                   "projectMilestones": {"nodes": [{"name": m} for m in milestones]}}}, f, ensure_ascii=False)

    def entry(self, key, value):
        """入口の1行を書き換える。value が None なら、その行を消す。"""
        with open(os.path.join(self.w.repo, "AGENTS.md"), encoding="utf-8") as f:
            text = f.read()
        line = "" if value is None else f"- {key}: {value}\n"
        self.w.write("AGENTS.md", re.sub(rf"(?m)^- {re.escape(key)}: .*\n", lambda _: line, text))
        self.w.commit(f"入口の「{key}」を変える")

    def status(self, **env):
        return self.w.run("status", env=env or None)[1]

    # ---- 受入の出力と Issue ----

    def test_an_id_in_the_output_with_no_issue_is_named(self):
        self.w.accept("DEMO-9", True)
        self.w.commit("Issue の無い受入")
        self.w.linear(self.issues)
        self.assertIn("DEMO-9 受入の出力にあるが、このProjectにIssueが無い", self.status())

    def test_an_acceptance_left_for_a_canceled_issue_is_named_until_it_is_removed(self):
        self.issues[1] = issue("DEMO-2", "canceled", self.w.auto("DEMO-2", self.sha))
        self.w.linear(self.issues)
        self.assertIn("DEMO-2 Canceled だが、受入が残っている。受入を消す", self.status())
        self.w.git("rm", "-q", "accept/DEMO-2_check")
        self.w.commit("中止した受入を消す")
        self.assertNotIn("受入が残っている", self.status())

    def test_an_automatic_acceptance_without_a_place_is_named(self):
        self.issues[1] = issue("DEMO-2", "unstarted", "受入（自動）: 今日の予約4件が一覧に出る", blocked_by={"DEMO-0": "completed"})
        self.w.linear(self.issues)
        self.assertIn("DEMO-2 受入（自動）に所在（パス@commit）が無い", self.status())

    def test_a_version_that_is_not_in_the_repository_is_named(self):
        self.issues[1] = issue("DEMO-2", "unstarted", "受入（自動）: 4件出る accept/DEMO-2_check@abcdef1234",
                               blocked_by={"DEMO-0": "completed"})
        self.w.linear(self.issues)
        self.assertIn("DEMO-2 受入の版 abcdef1 がこのリポジトリに無い: accept/DEMO-2_check", self.status())

    # ---- モジュール表 ----

    def test_a_module_folder_that_does_not_exist_is_named(self):
        self.entry("モジュール", "app2 = 予約")
        self.w.linear(self.issues)
        self.assertIn("入口のモジュール app2 が無い", self.status())

    def test_a_milestone_in_the_entry_that_the_project_lacks_is_named(self):
        self.w.write("docs/README.md", "資料\n")
        self.entry("モジュール", "app = 予約、docs = 資料")
        self.w.linear(self.issues)
        self.assertIn("入口の Milestone「資料」がProjectに無い", self.status())

    def test_a_milestone_of_the_project_without_a_folder_is_named(self):
        self.project(self.issues, milestones=("予約", "連携"))
        self.assertIn("Milestone「連携」に対応するディレクトリが入口に無い", self.status())

    # ---- Project の状態 ----

    def test_a_completed_project_with_an_open_issue_is_named(self):
        self.project(self.issues, status="completed")
        self.assertIn("Project は完了になっているが、開いているIssueがある", self.status())

    def test_a_completed_project_with_a_red_acceptance_is_named(self):
        self.issues[1] = issue("DEMO-2", "completed", self.w.auto("DEMO-2", self.sha))
        self.project(self.issues, status="completed")
        out = self.status()
        self.assertIn("Project は完了になっているが、受入が落ちている", out)
        self.assertIn("DEMO-2 題 DEMO-2 … Done なのに受入が落ちている", out)

    def test_a_project_with_everything_done_and_green_is_to_be_completed(self):
        self.w.accept("DEMO-2", True)
        sha = self.w.commit("DEMO-2 を実装する")
        self.issues[1] = issue("DEMO-2", "completed", self.w.auto("DEMO-2", sha))
        self.project(self.issues)
        self.assertIn("開いているIssueが無く、受入が全部緑。Project を完了にする", self.status())
        self.project(self.issues, status="completed")
        self.assertIn("食い違い  なし", self.status())

    # ---- 入口と Linear ----

    def test_an_entry_whose_source_is_not_a_linear_project_says_so(self):
        self.entry("正本", "https://example.com/somewhere")
        self.assertIn("Linear  届かない: 入口の「正本」がLinearのProjectのURLではない", self.status())

    def test_no_command_and_no_key_says_what_to_write(self):
        self.entry("Linearの叩き方", None)
        self.w.linear(self.issues)
        self.assertIn("入口の「Linearの叩き方」に、GraphQLのJSONを標準入力で受けるコマンドを", self.status(LINEAR_API_KEY=""))

    def test_an_entry_without_an_acceptance_command_says_so(self):
        self.entry("受入", None)
        self.w.linear(self.issues)
        self.assertRegex(self.status(), r"受入  走らせられなかった: この版（[0-9a-f]{7}）の入口に受入コマンドが無い")

    def test_an_error_from_linear_is_not_taken_for_an_empty_project(self):
        fake = os.path.join(self.w.dir, "errors.py")
        with open(fake, "w", encoding="utf-8") as f:
            f.write('import json\nprint(json.dumps({"errors": [{"message": "rate limited"}]}))\n')
        self.entry("Linearの叩き方", f"`python3 {fake}`")
        self.assertIn("Linear  届かない: Linearがエラーを返した", self.status())

    def test_issues_on_a_later_page_are_read(self):
        fake = os.path.join(self.w.dir, "paged.py")
        with open(fake, "w", encoding="utf-8") as f:
            f.write("import json, sys\nreq = json.load(sys.stdin)\ndata = json.load(open(sys.argv[1], encoding='utf-8'))\n"
                    "if 'project(' in req['query']:\n    print(json.dumps({'data': {'project': data['project']}}))\n"
                    "else:\n    after = (req.get('variables') or {}).get('after')\n"
                    "    nodes = data['issues'][1:] if after == 'c1' else data['issues'][:1]\n"
                    "    print(json.dumps({'data': {'issues': {'nodes': nodes, 'pageInfo': "
                    "{'hasNextPage': after != 'c1', 'endCursor': 'c1'}}}}))\n")
        self.entry("Linearの叩き方", f"`python3 {fake} {self.w.fixture}`")
        self.w.linear(self.issues)                               # DEMO-1 は1ページ目、DEMO-2 と DEMO-0 は2ページ目
        out = self.status()
        self.assertIn("前線  DEMO-2 題 DEMO-2（Todo）", out)
        self.assertIn("食い違い  なし", out)

    def test_the_key_goes_to_linear_and_nowhere_else(self):
        harness = load_harness()
        seen = []

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def urlopen(request, timeout=None):
            seen.append(request)
            return Reply(json.dumps({"data": {"viewer": {"id": "u1"}}}).encode())

        with patch.dict(os.environ, {"LINEAR_API_KEY": "lin_api_test"}), \
                patch.object(harness.urllib.request, "urlopen", urlopen):
            data = harness.linear({"Linearの叩き方": ""}, "query{viewer{id}}", {})
        self.assertEqual(data, {"viewer": {"id": "u1"}})
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].full_url, "https://api.linear.app/graphql")
        self.assertEqual(seen[0].get_header("Authorization"), "lin_api_test")
        self.assertEqual(json.loads(seen[0].data)["query"], "query{viewer{id}}")


class GateBaseChoiceTest(unittest.TestCase):
    """門の基準の版の決め方。"""

    def setUp(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        w.accept("DEMO-1", True)
        w.commit("DEMO-1 を実装し、受入を置く")
        w.accept("DEMO-1", False)
        self.head = w.commit("緑だった受入を、main の上で赤にした")

    def test_a_base_of_all_zeros_means_the_commit_before(self):
        rc, out = self.w.run("gate", "0" * 40)                   # 最初の push。GitHub は、前の版を全部ゼロで渡す
        self.assertEqual(rc, 1, out)
        self.assertIn("緑だった受入が赤になった", out)

    def test_a_base_that_is_this_version_means_the_commit_before(self):
        rc, out = self.w.run("gate", self.head)
        self.assertEqual(rc, 1, out)
        self.assertIn("緑だった受入が赤になった", out)

    def test_no_base_means_main(self):
        self.w.git("checkout", "-q", "-b", "work")
        self.w.write("app/main.txt", "v2\n")
        self.w.commit("変更")
        rc, out = self.w.run("gate")                             # main と同じところから分かれた。main で赤いものは、守るものではない
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
