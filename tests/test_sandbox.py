"""MAT-1814: Codexのサンドボックスの中でも、harness が落ちずに動く。

Codex の workspace-write は、作業フォルダには書けるが .git の中には（すでにあるファイルにも）書けない。
エージェントが手で走らせる harness は、その中で動く。フックのほうは外で動くので、
先にフックが .git/harness を作っていて、あとから中で手で走らせる、という順番も起きる。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import tests.test_harness as base

COUNTS = "受入  緑 1 ／ 赤 0 ／ 未実装 2"


def chmod_tree(top, writable):
    for folder, _, files in os.walk(top):
        for name in [folder] + [os.path.join(folder, f) for f in files]:
            if not os.path.islink(name):
                mode = os.stat(name).st_mode
                os.chmod(name, mode | 0o200 if writable else mode & ~0o222)


class SandboxTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        _, self.issues = base.HarnessTest.standard(self)
        self.git = os.path.join(self.w.repo, ".git")

    def lock(self):
        """.git の中を、すでにあるものも含めて、書けなくする。"""
        chmod_tree(self.git, False)
        self.addCleanup(chmod_tree, self.git, True)
        with self.assertRaises(OSError):                      # 書けるなら、この試験は何も確かめていない
            open(os.path.join(self.git, "probe"), "w").close()

    def files(self):
        """作業ツリーと .git にあるもの全部（無視されているものも含む）。ファイルは種別・権限・大きさ・更新時刻、
        フォルダは存在と権限。空フォルダを足す、中身を書き換える、鍵を外して書き戻す、のどれも差になる。"""
        seen = {}
        for folder, dirs, names in os.walk(self.w.repo):
            for n in dirs + names:
                full = os.path.join(folder, n)
                st = os.lstat(full)
                key = os.path.relpath(full, self.w.repo)
                seen[key] = (st.st_mode,) if n in dirs else (st.st_mode, st.st_size, st.st_mtime_ns)
        return seen

    def run_all(self, session):
        start = {"hook_event_name": "SessionStart", "session_id": session}
        stop = {"hook_event_name": "Stop", "session_id": session}
        rc, out = self.w.run("status")
        self.assertEqual(rc, 0)
        self.assertIn(COUNTS, out)
        self.assertIn("食い違い  なし", out)
        self.assertEqual(self.w.run("status", hook=start)[0], 0)
        self.assertEqual(self.w.run("check", hook=stop), (0, ""))
        self.w.write("app/new.txt", "commit していない\n")
        verdict = json.loads(self.w.run("check", hook=stop)[1])
        self.assertEqual(verdict["decision"], "block")
        self.assertIn("commit されていない変更が 1 件ある（app/new.txt）", verdict["reason"])
        os.remove(os.path.join(self.w.repo, "app/new.txt"))

    def test_everything_works_and_nothing_is_written_when_git_dir_is_locked(self):
        self.lock()
        before = self.files()
        self.run_all("sb1")
        self.assertEqual(self.files(), before)                # .git にも作業ツリーにも、何も足していない

    def test_it_also_works_after_a_hook_has_already_made_its_place_in_git(self):
        self.run_all("sb0")                                   # 外で動くフックが、先に .git/harness を作った
        self.assertTrue(os.path.isdir(os.path.join(self.git, "harness")))
        self.lock()
        before = self.files()
        self.run_all("sb2")
        self.assertEqual(self.files(), before)

    def test_build_check_passes_when_git_dir_is_locked(self):
        base.HarnessTest.just_built(self, self.issues)
        self.w.run("setup")
        self.w.commit("フックを登録する")
        self.lock()
        before = self.files()
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 0, out)
        self.assertIn("整っている", out)
        self.assertEqual(self.files(), before)

    def test_place_left_by_the_older_version_is_replaced_when_writable_and_left_alone_when_locked(self):
        self.w.git("worktree", "add", "-q", "--detach", ".git/harness/tree", "HEAD")     # 前の版は git worktree を置いていた
        self.assertEqual(len(self.w.git("worktree", "list").splitlines()), 2)
        chmod_tree(self.git, False)
        try:
            before = self.files()
            self.run_all("sb3")
            self.assertEqual(self.files(), before)
            self.assertEqual(len(self.w.git("worktree", "list").splitlines()), 2)        # 書けないときは、触らない
        finally:
            chmod_tree(self.git, True)
        self.run_all("sb4")
        self.assertEqual(len(self.w.git("worktree", "list").splitlines()), 1)            # 書けるときは、登録ごと片づける

    @unittest.skipUnless(shutil.which("codex"), "codex が無い環境では飛ばす")
    def test_inside_the_real_codex_sandbox(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)

        def sandboxed(*command):
            return subprocess.run(["codex", "sandbox", "-c", 'sandbox_mode="workspace-write"', "--", *command],
                                  cwd=os.path.realpath(self.w.repo), capture_output=True, text=True, timeout=180,
                                  stdin=subprocess.DEVNULL, env={**base.ENV, "CODEX_HOME": home})

        # サンドボックス自体が立たない環境がある（GitHub の Linux ランナーは bwrap が loopback を作れない）。
        # 飛ばしてよいのは、その既知の失敗だけ。macOS では飛ばさない。飛ばしたら「見ていない」であって「通った」ではない。
        probe = sandboxed("/bin/sh", "-c", "exit 0")
        if probe.returncode != 0:
            known = "bwrap:" in probe.stderr and ("RTM_NEWADDR" in probe.stderr or "Operation not permitted" in probe.stderr)
            if sys.platform == "darwin" or not known:
                self.fail("Codex のサンドボックスが立たない: " + probe.stderr[-400:])
            self.skipTest("この環境では Codex のサンドボックスが立たない: " + probe.stderr.strip()[-200:])
        before = self.files()
        for args in (["status"], ["check"]):
            p = sandboxed(base.HARNESS, *args)
            self.assertEqual(p.returncode, 0, p.stderr[-600:])
        self.assertEqual(self.files(), before)
        self.assertIn(COUNTS, sandboxed(base.HARNESS, "status").stdout)


if __name__ == "__main__":
    unittest.main()
