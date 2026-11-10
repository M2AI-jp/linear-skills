"""MAT-1818: 一時フォルダにも書けない場所で、harness が作業ツリーを汚さず、フックの残した結果を使う。

Codex のサンドボックスは、設定で /tmp と TMPDIR も書けなくできる。そのとき書けるのは作業フォルダだけ。
harness は、作業フォルダの中に自分の置き場を作ってはいけない（作れば、それを「commit されていない変更」と名指しする）。
フックは外で動いて .git/harness に受入の結果を残しているので、中からはそれを読む。

HARNESS_STORE は、.git の外の置き場を1か所に決める環境変数。試験では、書けないフォルダを指して「どこにも書けない」を作る。
"""
import os
import unittest

import tests.test_harness as base
from tests.test_sandbox import COUNTS, chmod_tree

STOP = {"hook_event_name": "Stop", "session_id": "ns1"}


class NoStoreTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        _, self.issues = base.HarnessTest.standard(self)
        self.git = os.path.join(self.w.repo, ".git")
        self.dead = os.path.join(self.w.dir, "nowhere")
        os.makedirs(self.dead)
        os.chmod(self.dead, 0o555)
        self.addCleanup(os.chmod, self.dead, 0o755)
        self.env = {"HARNESS_STORE": self.dead, "TMPDIR": self.dead}

    def lock(self):
        chmod_tree(self.git, False)
        self.addCleanup(chmod_tree, self.git, True)
        for folder in (self.git, self.dead):
            with self.assertRaises(OSError):                  # 書けるなら、この試験は何も確かめていない
                open(os.path.join(folder, "probe"), "w").close()

    def everything(self):
        """作業ツリー、.git、書けないフォルダの中身ぜんぶ。ファイルは種別・権限・大きさ・更新時刻、フォルダは存在と権限。"""
        seen = {}
        for top in (self.w.repo, self.dead):
            for folder, dirs, names in os.walk(top):
                for n in dirs + names:
                    full = os.path.join(folder, n)
                    st = os.lstat(full)
                    seen[full] = (st.st_mode,) if n in dirs else (st.st_mode, st.st_size, st.st_mtime_ns)
        for shared in ("/tmp", "/var/tmp", "/usr/tmp"):       # 指された場所を無視して、共用の一時フォルダへ逃げていないか
            for n in (os.listdir(shared) if os.path.isdir(shared) else []):
                if n.startswith("harness"):
                    full = os.path.join(shared, n)
                    seen[full] = sorted((f, os.lstat(os.path.join(d, f)).st_mtime_ns)
                                        for d, _, fs in os.walk(full) for f in fs)
        return seen

    def test_result_left_by_a_hook_is_used_and_nothing_is_written(self):
        self.assertIn(COUNTS, self.w.run("status")[1])        # 外で動くフックが、.git/harness に結果を残した
        self.lock()
        before = self.everything()
        rc, out = self.w.run("status", env=self.env)
        self.assertEqual(rc, 0)
        self.assertIn(COUNTS, out)
        self.assertIn("食い違い  なし", out)
        self.assertEqual(self.everything(), before)

    def test_without_a_result_it_says_so_and_still_reports_what_linear_knows(self):
        self.lock()
        before = self.everything()
        rc, out = self.w.run("status", env=self.env)
        self.assertEqual(rc, 0)
        self.assertIn("受入  走らせられなかった", out)
        self.assertIn("前線  DEMO-2 題 DEMO-2（Todo）", out)
        self.assertIn("待ち  DEMO-3 題 DEMO-3（DEMO-2 待ち）", out)
        self.assertEqual(self.everything(), before)

    def test_build_check_passes_on_the_hook_side_result_and_does_not_blame_itself(self):
        base.HarnessTest.just_built(self, self.issues)
        self.w.run("setup")
        self.w.commit("フックを登録する")
        self.assertEqual(self.w.run("status")[0], 0)          # フック側の結果ができる
        self.lock()
        before = self.everything()
        rc, out = self.w.run("check", "--wellformed", env=self.env)
        self.assertEqual(rc, 0, out)
        self.assertIn("整っている", out)
        self.assertNotIn("commit されていない変更", out)
        self.assertEqual(self.everything(), before)

    def test_build_check_fails_plainly_when_no_result_exists_anywhere(self):
        base.HarnessTest.just_built(self, self.issues)
        self.w.run("setup")
        self.w.commit("フックを登録する")
        self.lock()
        rc, out = self.w.run("check", "--wellformed", env=self.env)
        self.assertEqual(rc, 1)
        self.assertIn("受入を走らせられない", out)
        self.assertNotIn("commit されていない変更", out)

    def test_stop_hook_with_nowhere_to_remember_lets_the_session_go(self):
        self.lock()
        self.w.write("app/new.txt", "commit していない\n")
        rc, out = self.w.run("check", hook=STOP, env=self.env)
        self.assertEqual(rc, 0)
        self.assertNotIn('"decision": "block"', out)

    def test_place_named_by_the_variable_is_used_when_it_can_be_written(self):
        os.chmod(self.dead, 0o755)
        self.lock_git_only()
        rc, out = self.w.run("status", env={"HARNESS_STORE": self.dead})
        self.assertEqual(rc, 0)
        self.assertIn(COUNTS, out)
        self.assertTrue(os.listdir(self.dead))                # 指した場所に置いた
        self.assertEqual(self.w.git("status", "--porcelain", "--ignored"), "")

    def lock_git_only(self):
        chmod_tree(self.git, False)
        self.addCleanup(chmod_tree, self.git, True)


if __name__ == "__main__":
    unittest.main()
