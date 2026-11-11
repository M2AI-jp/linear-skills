"""MAT-1845: 入口に、その場かぎりの指示が残らない。

入口の「進め方」は、機構が読む5項目の場所。建てたセッションがそこに「現在の許可範囲は…」のような、
その場かぎりの指示を書くと、次のセッションはそれを規則として読み、頼まれた仕事を断る。
"""
import unittest

import tests.test_harness as base

NAMED = "入口の「進め方」に、5項目以外の行がある"
ENTRY = ("## 進め方\n"
         "- 正本: https://linear.app/demo/project/demo-0123456789ab\n"
         "- Linearの叩き方: `{linear}`\n"
         "- 受入: `{accept}`（出力は Issue ID ごとの緑・赤）\n"
         "- モジュール: app = 予約\n"
         "- 確認が要る: 本番の設定変更、送信\n")


class EntryTest(unittest.TestCase):
    def setUp(self):
        self.w = base.World()
        self.addCleanup(self.w.close)
        _, self.issues = base.HarnessTest.standard(self)
        with open(self.w.repo + "/AGENTS.md", encoding="utf-8") as f:
            text = f.read()
        self.head, _, self.block = text.partition("## 進め方\n")
        self.block = "## 進め方\n" + self.block

    def entry(self, before="", inside="", after=""):
        self.w.write("AGENTS.md", self.head + before + self.block + inside + after)
        self.w.commit("入口を書き換える")
        return self.w.run("status")[1]

    def test_a_clean_entry_is_not_named(self):
        self.assertNotIn(NAMED, self.w.run("status")[1])

    def test_a_sentence_about_the_current_scope_inside_the_block_is_named(self):
        out = self.entry(inside="\n現在の許可範囲は計画・受入・ハーネス整備のみ。CLI本体は実装しない。\n")
        self.assertIn(NAMED, out)
        self.assertIn("現在の許可範囲は計画・受入・ハーネス整備のみ", out)       # どの行かを言う

    def test_an_extra_list_item_inside_the_block_is_named(self):
        out = self.entry(inside="- 許可範囲: 計画と受入だけ。実装はしない\n")
        self.assertIn(NAMED, out)
        self.assertIn("許可範囲", out)

    def test_it_keeps_the_build_from_finishing(self):
        base.HarnessTest.just_built(self, self.issues)
        self.w.run("setup")
        self.w.commit("フックを登録する")
        self.assertEqual(self.w.run("check", "--wellformed")[0], 0)
        self.entry(inside="\n実装は次の指示を待つ。\n")
        rc, out = self.w.run("check", "--wellformed")
        self.assertEqual(rc, 1)
        self.assertIn(NAMED, out)

    def test_text_outside_the_block_is_left_alone(self):
        out = self.entry(before="このリポジトリは予約の受付を扱う。\n\n", after="\n## 開発の記録\n\n- 2026-01-01: 最初の版\n\n現在の版は 1.0。\n")
        self.assertNotIn(NAMED, out)
        self.assertIn("食い違い  なし", out)

    def test_blank_lines_and_the_five_items_in_any_order_are_fine(self):
        lines = self.block.strip("\n").split("\n")
        self.block = "\n".join([lines[0], "", lines[5], lines[4], "", lines[3], lines[2], lines[1]]) + "\n"
        out = self.entry()
        self.assertNotIn(NAMED, out)
        self.assertIn("食い違い  なし", out)


if __name__ == "__main__":
    unittest.main()
