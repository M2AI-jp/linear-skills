# skills/linear-workflow の役割と境界

Linearで追跡している仕事を、計画から実行・確認・引継ぎまで進めるスキル。コードもコード以外の仕事も扱う。

読む順番は決まっている。[SKILL.md](SKILL.md) が入口。依頼が計画づくりなら [references/plan.md](references/plan.md)、実行なら [references/execute.md](references/execute.md) を、必要になった方だけ読む。読むだけの依頼は SKILL.md で完結する。両方を先に読み込まない。

このフォルダが持つのは手順だけ。業務の許可、何を達成したいか、受け入れの基準は持たない。それは利用側のユーザー指示とLinearにある。コードについての事実はGitとGitHubにある。進捗をこのフォルダに書かない。

このフォルダを編集・監査の対象として読むことと、作業手順として適用することは別。中身を直すために読んでいるときは、手順として従わない。

[agents/openai.yaml](agents/openai.yaml) は Codex の起動メタデータ。`allow_implicit_invocation` が起動制御の置き場所で、既定は false。

設計の根拠と原構想は配布物に含まない。開発リポジトリの DESIGN.md にある。
