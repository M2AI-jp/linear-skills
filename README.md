# Linear skills

指定したLinear Projectの計画・実行・訂正・保守を、Codexと通常のツールで進める3つのスキルです。コード、資料、外部サービス、人への引継ぎを扱います。

| スキル | 役割 |
|---|---|
| [linear](skills/linear/SKILL.md) | 対象・正本・依頼から必要なRefresh／PMを選ぶ入口 |
| [linear-refresh](skills/linear-refresh/SKILL.md) | 原要求と指定実態から計画を構築・再整理 |
| [linear-pm](skills/linear-pm/SKILL.md) | 現在計画から実行・評価・訂正・保守・再開 |

状態と受入の規則は[共通契約](skills/linear/references/contract.md)が所有します。Hookは同梱せず、起動・実行・完了評価に必要ありません。外部結果と必要な受入はCodexが確認します。

## 導入と利用

1. 操作するProject、原要求・正本、許可された範囲を特定し、通常のLinear MCP接続を用意します。Git／GitHubはコードやリポジトリを扱う場合だけ必要です。
2. 3つのスキルフォルダを、利用先の`.agents/skills/`へ兄弟フォルダとして配置します。`references/`と`agents/openai.yaml`を含む全体を同じ版で配置し、同名の重複導入を避けます。
3. 利用先のAGENTS.mdに、その利用先のProject、正本、実際のlinear/SKILL.mdへの参照と呼出しを記載します。開発用のルートAGENTS.mdとSSOT.mdはコピーしません。
4. `$linear`を明示するか、設定したAGENTSの入口から開始します。「現状を説明して」は読取と回答、「計画を整理して実行して」はRefresh→PM、「現在計画から続けて」はPMが担当します。3スキルの`allow_implicit_invocation: false`は維持します。
5. 最初は指定Projectの読取で接続を確認し、許可された対象で実行・訂正・読戻し・再開を確認します。配置や構文合格だけでは業務で有効と認定しません。

Hook用Python、linear-api、隔離判定CLI、Hookの信頼設定は不要です。既存のこのパッケージのHookを撤去する場合は、Linear用イベント定義と専用ファイルだけを除き、他用途のHookや設定は保持します。

## 配布と受入

配布対象は3つの完全なスキルフォルダとこのREADMEです。個人用tools、資格情報、開発用AGENTS／SSOT、セッション履歴を含めません。対象と認証は利用先が提供します。

通常の利用から、計画の妥当性、実行した結果、状態訂正、Doneを維持する保守、部分反映からの重複なし再開を確認します。スキル自体の動作と業務の外部成果は別々に評価します。未実施の導入経路は未確認のまま残します。

Hookは将来必要と判断した場合の補強に限り、現在の開発・完成・導入条件へ戻しません。
