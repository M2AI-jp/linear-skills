# linear-skills リポジトリの入口

ここはメタハーネスの置き場所で、導入先ではない。`skills/linear-workflow/` のスキルは、このリポジトリでは起動しない（スキルを探す場所に置いていない）。手順として適用せず、編集・監査の対象として読む。機構（`harness`）だけは、このリポジトリ自身に適用している。下の「進め方」がその入口。

作業の前に [DESIGN.md](DESIGN.md) を読む。要求、根幹の問題、作ったもの、失敗の記録が書いてある。要求の正本はユーザー原文で、DESIGN.md とスキル本文はそこから導いた設計。設計の維持を新しい要求に昇格させない。

配布物は [skills/linear-workflow/SKILL.md](skills/linear-workflow/SKILL.md) と `skills/linear-workflow/harness` の2つ。**ここにファイルを増やす変更は、理由を DESIGN.md に書いてから行う。** 最小のファイル数が要求で、受入が検査している。

現在地は、セッションの開始時に渡る（`skills/linear-workflow/harness status` でも出る）。**この入口と DESIGN.md に、進捗や状態の写しを作らない。** 写しは片方だけ古くなる（2026-11-06 に実際にそうなった）。

直すのは型か機構。規則文を足して直したことにしない。使っていない間に、観測で代用する装置を作らない。検証用のProject、採点表、判定書、指紋の類を増やさない。試行するなら、使い捨てで、終わったら残さない。やり方と落とし穴は DESIGN.md の「試行のやり方」。

前の版（3スキル＋共通契約＋Hook）は Linear Project `052491f9-4937-4c82-8bb5-c7b0fb563ecd` が所有する。2026-10-14 に干渉を理由に撤去され、Completed のまま残っている（Issueはアーカイブ済みで、読める）。当時の記録として読み、その受入を現在の合格に流用しない。当時の資料は `../../Documents/ChatGPT/Linear/` にある（`SSOT.md` は当時の設計方針、`acceptance/` は受入入力と採点方法）。いずれも現在の必須工程ではない。

## 進め方
- 正本: https://linear.app/matsunai/project/linear-skills-メタハーネス-f87a91fbda72
- Linearの叩き方: `~/.local/bin/linear-api`（GraphQLのJSONを標準入力で渡す）
- 受入: `skills/linear-workflow/harness accept`（出力は Issue ID ごとの緑・赤）
- モジュール: skills/linear-workflow = 配布物、. = つなぎ
- 確認が要る: Linearの既存Issueのアーカイブと削除、スキルの導入（`~/.claude/skills`・`~/.codex/skills`・ほかのリポジトリへの配置）、このリポジトリの外への一切の操作
