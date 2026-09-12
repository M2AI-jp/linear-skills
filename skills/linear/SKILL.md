---
name: linear
description: 明示的なLinear利用または導入済み対象の入口から、計画の構築・再整理をlinear-refreshへ、実行・訂正・再開をlinear-pmへつなぐ。
---

# Linear

利用側の既存入口とユーザー指示から、対象Projectまたは新規作成の意図、原要求・正本、今回の責任範囲・既存の許可を受け取り、[共通運用契約](references/contract.md)を参照して呼出先へ渡す。既知の対象・許可は再質問せず、不明な業務判断だけを確認する。他Projectを探索して補完しない。

- 新規計画の構築・既存実態の整理 → [linear-refresh](../linear-refresh/SKILL.md)を呼ぶ。
- 現在の計画から実行・訂正・再開 → [linear-pm](../linear-pm/SKILL.md)を呼ぶ。
- 計画の構築・再整理から実行まで求められた場合 → [linear-refresh](../linear-refresh/SKILL.md)の出力を[linear-pm](../linear-pm/SKILL.md)へ渡す。

呼出先が利用可能か確認し、未導入なら接続不足を明示する。状態規則は共通契約に従う。
