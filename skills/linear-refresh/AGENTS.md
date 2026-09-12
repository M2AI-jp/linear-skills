# Refresh系統の責任

このリポジトリ自体を開発する場合だけ、既存の開発入口から正本・担当Issue・技術方針を確認する。配布先では利用者の既存入口・指定Project・正本を引き継ぎ、開発Projectや開発専用SSOT.mdを要求しない。共通規則は[共通運用契約](../linear/references/contract.md)。`SKILL.md`は原要求・指定実態から現在の計画を構築・再整理し、`agents/openai.yaml`は明示起動だけを担う。

計画・依存・受入の変更は[PM](../linear-pm/SKILL.md)への受渡しと、Hook・Gitの仕事分割・業務評価へ返す。構文はskill-creatorのquick_validate.py、実行と接続の評価は担当Issueの受入で確認する。
