"""MAT-1931: 監査で残った穴。走らせられなかった基準の版、受入を走らせる場所の残りもの、受入を変えてよい場合の言い方。

1. 統合の門は、基準の版の受入を走らせられなかったら、通さない（緑だった受入が分からない）。
   基準の版そのものに受入が無い・受入コマンドが行を出さずに落ちる、は別。そこでは守るものが無く、直す変更を入れられなくなるので、理由を言って通す。
   走らせられなかった、という結果は覚えない。次に呼ばれたら、やり直す。
2. 受入を走らせる場所は、版をまたいで使い回す。前の版の受入が作った、追跡されていないファイル（無視されているものも）を残さない。
3. 受入が、Issueに書いた版から変わっているときの直し方は、見直しで直した場合も言う。
"""
import os
import re
import contextlib
import io
import types
import unittest
from unittest.mock import patch

import tests.test_harness as base
from tests.test_harness import issue
from tests.test_sandbox import COUNTS

ONE_GREEN = "受入  緑 1 ／ 赤 0 ／ 未実装 0"


def load_harness():
    harness = types.ModuleType("audit_harness")
    with open(base.HARNESS, encoding="utf-8") as f:
        exec(compile(f.read(), base.HARNESS, "exec"), harness.__dict__)
    return harness


class GateBaseTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        _, self.issues = base.HarnessTest.standard(self)                     # DEMO-1 は緑、DEMO-2 と DEMO-3 は赤
        self.tree = os.path.join(load_harness().Repo(self.w.repo).store, "tree")

    def block_the_place(self):
        """受入を走らせる場所を、用意できなくする。場所の名前で、ただのファイルを置く。"""
        os.makedirs(os.path.dirname(self.tree), exist_ok=True)
        with open(self.tree, "w", encoding="utf-8") as f:
            f.write("場所ではない\n")

    def command(self, cmd, message):
        with open(os.path.join(self.w.repo, "AGENTS.md"), encoding="utf-8") as f:
            text = f.read()
        self.w.write("AGENTS.md", re.sub(r"(?m)^- 受入: .*$", lambda _: f"- 受入: `{cmd}`（出力は Issue ID ごとの緑・赤）", text))
        return self.w.commit(message)

    def test_a_base_that_could_not_be_run_does_not_let_a_change_through(self):
        self.w.git("checkout", "-q", "-b", "work")
        self.w.write("accept/DEMO-1_check", "#!/bin/sh\n# DEMO-1 の観測できる結果\nexit 1\n", True)   # 緑だった受入を赤にする変更
        self.w.commit("壊す")
        self.block_the_place()
        rc, out = self.w.run("gate", "main")
        self.assertEqual(rc, 1, out)
        self.assertIn("基準の版の受入を走らせられなかった", out)
        self.assertNotIn("通す", out)

    def test_a_base_whose_own_command_fails_is_let_through_with_the_reason(self):
        self.command("sh -c 'echo 壊れている >&2; exit 3'", "受入コマンドが壊れた版が main に入っている")
        self.w.git("checkout", "-q", "-b", "work")
        self.command(f"{base.HARNESS} accept", "受入コマンドを直す")              # 直す変更は、入れられなければならない
        rc, out = self.w.run("gate", "main")
        self.assertEqual(rc, 0, out)
        self.assertIn("基準の版に受入が無い", out)
        self.assertIn("壊れている", out)

    def test_a_base_from_before_the_entry_is_let_through(self):
        w = base.World(entry=False)
        self.addCleanup(w.close)
        w.commit("入口の無い版")
        w.git("checkout", "-q", "-b", "work")
        w.write("AGENTS.md", "# demo\n\n## 進め方\n- 正本: https://linear.app/demo/project/demo-0123456789ab\n"
                f"- 受入: `{base.HARNESS} accept`\n")
        w.accept("DEMO-1", True)
        w.commit("入口と受入を足す")
        rc, out = w.run("gate", "main")
        self.assertEqual(rc, 0, out)
        self.assertIn("基準の版に受入が無い", out)

    def test_a_run_that_could_not_be_made_is_tried_again(self):
        self.block_the_place()
        self.assertIn("受入  走らせられなかった", self.w.run("status")[1])
        os.remove(self.tree)                                                 # 原因が無くなった
        self.assertIn(COUNTS, self.w.run("status")[1])

    def test_an_empty_success_is_a_result_and_is_not_run_again(self):
        marker = os.path.join(self.w.dir, "ran")
        self.command(f"echo ran >> {marker}", "行が無いが正常に終わる受入")
        self.w.run("status")
        self.w.run("status")
        with open(marker, encoding="utf-8") as f:
            self.assertEqual(f.read().splitlines(), ["ran"])

    def test_reported_results_are_protected_even_if_the_command_exits_nonzero(self):
        self.command("sh -c 'echo 緑 DEMO-1 守るべき受入; exit 1'", "結果を出して異常終了する受入")
        self.w.git("checkout", "-q", "-b", "work")
        self.command("echo 赤 DEMO-1 壊れた受入", "緑を赤に変える")
        rc, out = self.w.run("gate", "main")
        self.assertEqual(rc, 1, out)
        self.assertIn("DEMO-1", out)
        self.assertNotIn("基準の版に受入が無い", out)


class LeftoverTest(unittest.TestCase):
    def setUp(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        w.write(".gitignore", "build/\n")
        w.write("accept/DEMO-1_check", "#!/bin/sh\n# DEMO-1 の観測できる結果\n"
                "mkdir -p build && echo x > build/out.txt && echo x > left-behind.txt\n", True)   # 走るたびに、追跡されないものを作る
        sha = w.commit("受入が、走らせる場所にものを作る")
        self.issues = [issue("DEMO-1", "completed", w.auto("DEMO-1", sha))]
        w.linear(self.issues)

    def test_what_an_earlier_version_left_is_not_there_for_the_next(self):
        self.assertIn(ONE_GREEN, self.w.run("status")[1])
        self.w.write("accept/DEMO-1_check", "#!/bin/sh\n# DEMO-1 の観測できる結果\n"
                     "[ ! -e left-behind.txt ] && [ ! -e build/out.txt ]\n", True)
        sha = self.w.commit("ものを作るのをやめた")
        self.issues[0]["description"] = self.w.auto("DEMO-1", sha)
        self.w.linear(self.issues)
        self.assertIn(ONE_GREEN, self.w.run("status")[1])

    def test_an_untracked_nested_repository_is_also_removed(self):
        self.w.write("accept/DEMO-1_check", "#!/bin/sh\n# 受入が作った入れ子のリポジトリ\n"
                     "git init -q build/nested && echo x > build/nested/out.txt\n", True)
        sha = self.w.commit("受入が入れ子のリポジトリを作る")
        self.issues[0]["description"] = self.w.auto("DEMO-1", sha)
        self.w.linear(self.issues)
        self.assertIn(ONE_GREEN, self.w.run("status")[1])
        self.w.write("accept/DEMO-1_check", "#!/bin/sh\n# 入れ子のリポジトリも残さない\n[ ! -e build ]\n", True)
        sha = self.w.commit("前の版が作った入れ子のリポジトリが無い")
        self.issues[0]["description"] = self.w.auto("DEMO-1", sha)
        self.w.linear(self.issues)
        self.assertIn(ONE_GREEN, self.w.run("status")[1])


class RunnerFailureTest(unittest.TestCase):
    def test_timeout_exception_and_missing_result_block_once_and_are_retried(self):
        # 一時間待つ代わりに実行境界で故障させる。forkした実行者と置き場は実物を使う。
        harness = load_harness()
        for failure in ("timeout", "exception", "missing"):
            with self.subTest(failure=failure):
                w = base.World()
                self.addCleanup(w.close)
                w.accept("DEMO-1", True)
                w.commit()
                repo = harness.Repo(w.repo)
                real_sh = harness.sh

                def fail(*args, **kwargs):
                    if failure == "timeout":
                        return None, "", "上限の時間で終わらなかった"
                    if failure == "exception":
                        raise OSError("実行途中の故障")
                    os._exit(0)  # 結果を置かずに実行者が消える。

                output = io.StringIO()
                with patch.object(harness, "sh", side_effect=fail), contextlib.redirect_stdout(output):
                    self.assertEqual(harness.cmd_gate(repo, "main"), 1)
                self.assertIn("基準の版の受入を走らせられなかった", output.getvalue())
                with patch.object(harness, "sh", side_effect=real_sh):
                    result = harness.accept_at(repo, repo.sha)
                self.assertTrue(result.get("results", {}).get("DEMO-1", {}).get("ok"), result)


class WordingTest(unittest.TestCase):
    def test_a_changed_acceptance_may_have_been_fixed_by_a_review(self):
        w = self.w = base.World()
        self.addCleanup(w.close)
        base.HarnessTest.standard(self)
        w.write("accept/DEMO-2_check", "#!/bin/sh\n# 抜け道を塞いだ\nexit 1\n", True)   # 見直しが直して、所在を書き直す前に切れた
        w.commit("受入の抜け道を塞ぐ")
        _, out = w.run("status")
        named = [line for line in out.splitlines() if "DEMO-2 受入が、Issueに書いた版" in line]
        self.assertEqual(len(named), 1, out)
        self.assertIn("見直しで直した・基準を人が変えたのなら、所在を新しい commit に書き直して", named[0])


if __name__ == "__main__":
    unittest.main()
