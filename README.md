# linear-workflow

Linearで追跡している仕事を、計画から実行・確認・引継ぎまで進めるスキル。コードもコード以外（調査、資料、設定、外部サービスの操作、人への連絡）も扱う。

[skills/linear-workflow/SKILL.md](skills/linear-workflow/SKILL.md) の1ファイル。これだけ。

## 導入

1. `skills/linear-workflow/` を、導入先の `.agents/skills/`（Codex）または `.claude/skills/`（Claude Code）へフォルダごと置く
2. 導入先リポジトリ直下の `AGENTS.md`（または `CLAUDE.md`）に、対象のLinear ProjectのURL、毎回読む正本、触ってよい範囲と確認が必要な操作を書く。これがないと次のセッションは対象を特定できない
3. 指定Projectの読取だけで接続を確かめる

このリポジトリの `AGENTS.md` と `DESIGN.md` は導入先へコピーしない。開発の記録で、スキルの動作には不要。

外すときは置いたフォルダを消す。

## いまは導入されていない

`skills/` はClaude CodeもCodexもスキルを探さない場所なので、ここに置いてあるだけでは何も起動しない。`~/.codex/skills/` と `~/.claude/skills/` にリンクはない。

## 確かめたこと・確かめていないこと

確かめたのは、frontmatterと配布物の構造だけ。

**スキル本文が実際の仕事で機能するかは確かめていない。** これは観測では確かめられない。実際に使って、次のセッションがLinearだけから再開できるかを見るしかない。

前の版（3スキル＋182行の共通契約＋Hook）は2026-09-23に配布され、2026-10-14に他の開発への干渉を理由に撤去された。経緯は [DESIGN.md](DESIGN.md)。
