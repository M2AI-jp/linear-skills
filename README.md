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

確かめたこと。

- 配布物の構造（1ファイル、frontmatterの形、相対リンクの解決）。CIが検査している
- **スキル名を言われなくても選ばれ、`linear` の別の意味では選ばれない。** Claude Codeで非対話セッション8件（sonnetとopus）。`MAT-123`、linear.appのURL、`AGENTS.md` に対象ProjectのURLがある状態での「再開したい」で選ばれ、線形回帰・linear search・無関係な作業では選ばれなかった。Codexでは、スキルを置いた場合だけ本文固有の規則に従った（置かない対照は、本文が禁じている「現状維持」を答えた）
- **導入先のパス。** Codexは `.agents/skills/`、Claude Codeは `.claude/skills/`。どちらも実際に読み込まれた
- **引き継ぎ。** 使い捨ての小さな案件で、1本目が計画をLinearに書いて実装し途中で止め、**冷たい別セッションに `続きやって` だけを渡した。** 2本目はLinearから現在地を復元し、前の報告を信じずに実データで再検証して同じ結果を再現し、終わった仕事をやり直さず、権限で塞いだ経路を迂回もしなかった。1本目の成果物は実行して報告どおりだった

確かめていないこと。

- **Issue層の状態遷移**（Todo→In Progress→In Review→Done）。このワークスペースは無料プランのアクティブIssue上限（`USAGE_LIMIT_EXCEEDED` / `activeIssueCount`）に達していて、誰もIssueを作れない
- **サブエージェントを好きなだけ呼ばせる使い方。** 試行の課題が小さく、分ける利得が無いので呼ばないのが正しかった。この課題では測れない

前の版（3スキル＋182行の共通契約＋Hook）は2026-09-23に配布され、2026-10-14に他の開発への干渉を理由に撤去された。経緯は [DESIGN.md](DESIGN.md)。
