# Linear契約モジュールの責任

このリポジトリ自体を開発する場合だけ、リポジトリの既存入口から開発正本と担当Issueを確認する。配布先での利用は利用者の既存入口・指定Project・正本を引き継ぎ、開発Projectや開発専用SSOT.mdを要求しない。`references/contract.md`は共通規則、`SKILL.md`は対象の受渡しと呼出順、`agents/openai.yaml`は入口の暗黙選択と明示起動のメタデータを持つ。

共通契約の変更はRefresh／PM・受入の影響部分へ返し、規則を複製しない。この開発の評価対象・版・未達は担当Issueに保持する。構文はskill-creatorのquick_validate.py、意味と通常利用の接続は独立した後続受入で確認する。
