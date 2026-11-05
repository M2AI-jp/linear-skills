# linear-skills リポジトリの入口

ここはスキルの置き場所で、導入先ではない。`skills/` に置いてあるものは、このリポジトリで作業する間は起動しない。手順として適用せず、編集・監査の対象として読む。

作業の前に [DESIGN.md](DESIGN.md) を読む。何を目指していて、前の版がどこで逸れたかが書いてある。要求の正本はユーザー原文（Codexのスレッド履歴）で、DESIGN.md とスキル本文はそこから導いた設計。設計の維持を新しい要求に昇格させない。

前の版の記録は `../../Documents/ChatGPT/Linear/`。`SSOT.md` は当時の設計方針、`acceptance/CASES.md` は受入入力、`acceptance/SCORECARD.md` は当時の採点方法。いずれも現在の必須工程ではない。

## 責任フォルダ

| フォルダ | 役割と境界 |
|---|---|
| [skills/linear-workflow/](skills/linear-workflow/AGENTS.md) | 配布するスキル本体。手順だけを持ち、業務の許可・受入基準・進捗を持たない |
| [hooks/](hooks/README.md) | 起動の案内。入口のパスを1行返すだけ。業務の許可・状態遷移・完了を持たない。**無効化してある** |
| [templates/](templates/repo-AGENTS.md) | 導入先リポジトリの `AGENTS.md` の雛形。次の担当が対象のProjectを見つけるための入口 |
| `.github/workflows/` | 配布物の構造・リンク検査と、無効のまま配布されていることの検査 |

各フォルダの役割はそのフォルダの `AGENTS.md` か `README.md` が持つ。重複して書かない。

## 仕事の現在地

このリポジトリの仕事は Linear で追跡している。作業の前に読む。

- Project: [linear-workflow の実用検証](https://linear.app/matsunai/project/linear-workflow-%E3%81%AE%E5%AE%9F%E7%94%A8%E6%A4%9C%E8%A8%BC-f1a2dfe6fa67)（`da83b721-9486-4a8b-a836-3e7cd14c2f1e`）
- 完成条件、固定した技術・テスト・統合基準は Project 本文にある
- Issue になっていない計画は、同 Project の Document「Issue にできていない計画」にある。ワークスペースが Linear 無料プランのアクティブ Issue 上限に達しているため。上限が外れたら Issue にして Document を消す

会話の記憶や過去の報告より、Linear の現在の本文と状態を優先する。進捗の台帳をこのリポジトリに作らない。

前の版（3スキル＋共通契約＋Hook）は Project `052491f9-4937-4c82-8bb5-c7b0fb563ecd` が所有する。2026-10-14 に干渉を理由に撤去され、Completed のまま残っている。当時の記録として読み、その受入を現在の合格に流用しない。経緯は DESIGN.md にある。

同梱Hookに対する opt-in の行は、このファイルに**書かない**。opt-in の書き方は [templates/repo-AGENTS.md](templates/repo-AGENTS.md) の最後にある。Hookは文字列の一致で判定するので、ここにその行を引用するだけでも opt-in になる。引用しないこと自体が設定であり、CIで検査している。

理由は、スキルを編集している最中に、そのスキル自身の案内を受け取らないため。このリポジトリで作業する間は、Hookを有効にしても案内は出ない。

`hooks/` のコードを有効化する変更は、理由と確認方法を書いてから行う。現在の進捗や状態の写しをこの入口へ追加しない。
