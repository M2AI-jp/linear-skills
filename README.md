# linear-workflow

Linearで追跡している仕事を、計画から実行・確認・引継ぎまで進めるためのスキル。コードもコード以外（調査、資料、設定、外部サービスの操作、人への連絡）も扱う。

解きたい問題は、セッションが切れると前回の結論が失われ、次のセッションが古いコードと古い完了報告を正しいものとして扱って同じ場所を壊し直すこと。出力の質は渡された入力で決まり、その出力が次のセッションの入力になる。Linearは、その入力を置く場所として使う。

背景と設計の根拠は [DESIGN.md](DESIGN.md)。

## パッケージの中身

配布するのは `skills/linear-workflow/` のフォルダ全体と、導入先に置く入口の雛形。

| ファイル | 中身 |
|---|---|
| [skills/linear-workflow/SKILL.md](skills/linear-workflow/SKILL.md) | 入口。問題、最初に読むもの、置き場所、3つのモード、汚染の合図、聞くこと・聞かないこと |
| [references/plan.md](skills/linear-workflow/references/plan.md) | 計画をつくる・立て直す。完成条件とE2Eを実装前に決める。MilestoneとIssueの切り方。導入先に入口を置く |
| [references/execute.md](skills/linear-workflow/references/execute.md) | 実行して確かめる。状態ごとの行動、試行の記録、詰まったときの戻り方、完了の条件 |
| [skills/linear-workflow/AGENTS.md](skills/linear-workflow/AGENTS.md) | このフォルダの役割と境界、読む順番 |
| [agents/openai.yaml](skills/linear-workflow/agents/openai.yaml) | Codexの起動メタデータ。起動制御の置き場所 |
| [templates/repo-AGENTS.md](templates/repo-AGENTS.md) | 導入先リポジトリの `AGENTS.md` の雛形 |
| [hooks/](hooks/README.md) | 起動の案内。**無効化した状態で入っている** |

必要なモードの参照ファイルだけを読む。読むだけの依頼では `SKILL.md` しか読み込まない。

## いまは導入されていない

このリポジトリは置き場所であって、導入先ではない。`skills/` はClaude CodeもCodexもスキルを探さない場所なので、ここに置いてあるだけでは何も起動しない。

- `~/.codex/skills/` と `~/.claude/skills/` にこのスキルへのリンクはない
- `~/.codex/hooks.json` にこのパッケージのhandlerはない
- `hooks/route.py` は `DISARMED = True`。`install.py` は `--enable-interception` なしでは何も書かない
- `agents/openai.yaml` は `allow_implicit_invocation: false`。名前を言わない依頼で勝手に選ばれない
- このリポジトリの `AGENTS.md` にはHookのopt-in行がない。有効にしてもここでは案内が出ない

いまの作業に干渉させたくない間は、この状態のままにしておく。CIがこの4点を検査しているので、どれかを外すと落ちる。

## 導入

1. 操作するProject、達成したいこと、許可された範囲を決める。LinearのMCP接続を用意する。Git／GitHubはコードを扱う場合だけ必要
2. `skills/linear-workflow/` を、導入先の `.agents/skills/`（Codex）または `.claude/skills/`（Claude Code）へ、`AGENTS.md`・`references/`・`agents/` を含めてフォルダごと置く
3. [templates/repo-AGENTS.md](templates/repo-AGENTS.md) を埋めて、導入先リポジトリ直下の `AGENTS.md`（または `CLAUDE.md`）にする。対象のProject、毎回読む正本、許可範囲を書く。**これがないと次のセッションは対象を特定できない**
4. Codexでは `$linear-workflow` と明示して呼ぶ。名前を言わなくても選ばれるようにしたくなったら `agents/openai.yaml` の `allow_implicit_invocation` を `true` にする
5. まず指定Projectの読取だけで接続を確かめる。置いたことと構文が通ったことは、業務で有効だという意味ではない

このリポジトリの `AGENTS.md`・`DESIGN.md`・`templates/` は導入先へコピーしない。開発用の記録と雛形で、スキルの動作には不要。

外すときは置いたフォルダを消す。Hookを有効にしていた場合は `python3 hooks/install.py --remove`。

## 確かめたこと・確かめていないこと

確かめたのは、同梱コードの単体試験（13件）と、配布物の構造・リンク・無効化の検査。`hooks/` が無効のまま何も返さないこと、有効化したときリポジトリ側のopt-inが必須になること、`linear algebra` やスキル名の言及だけでは発火しないことを含む。

確かめていないのは、このスキルで実在の案件を一巡させた結果。前の版（3スキル＋Hook）は2026-09-23に配布され、2026-10-14に他の開発への干渉を理由に撤去された。その経緯は [DESIGN.md](DESIGN.md) にある。今回の版で、計画→実行→矛盾の発覚→Linearの訂正→別セッションからの再開が成立するかは、まだ観測していない。

テストコードを別文脈のエージェントが定性レビューする循環は、`references/execute.md` の指示として書いてあるだけで、実行して観測していない。
