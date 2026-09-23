# Linear の入口を案内する Hook

本体の受入・導入後に追加する、Python 3 標準ライブラリだけの起動補助です。`route.py` は会話ログ、Linear API、状態キャッシュを使いません。入力か作業フォルダの `AGENTS.md` に Linear の文脈があれば、スキルの入口と適用条件を短く追加します。実際のスキル使用はモデルの実行記録で確認します。

| イベント | 案内する条件 |
|---|---|
| `UserPromptSubmit` | 入力に Linear / linear.app がある、または作業フォルダから親へたどった AGENTS.md に Linear の参照がある |
| `SessionStart` | source が resume / compact で、同じフォルダ条件が成立する |

ユーザー・AGENTS・所有 Issue の OFF と指定された有効版を優先します。ON への切替、業務更新、ツール拒否、入力書換え、Stop 継続、LLM/MCP 呼出し、外部通信は行いません。読取だけなら回答で終了し、適用外ならスキルを使わないよう案内します。

入力と各読取ファイルは最大 64 KiB。欠損・破損・過大入力・異常パス・symlinkループ・範囲外イベントは空出力、終了コード 0 です。出力は公式の `hookSpecificOutput.additionalContext` のみ。Hook 定義の timeout は 3 秒です。Python 自体が起動できない等の環境障害は Codex 側で扱われるため、正常動作を保証するものではありません。

## 導入

3 スキルを先に配置してから、このフォルダで実行します。

```sh
python3 install.py
```

既定では `~/.codex/skills/linear/SKILL.md` を確認し、`~/.codex/linear-harness/<SHA256>/route.py` に配置します。生成コマンドは実行に使った Python のパスを使用します。別の配置は明示できます。

```sh
python3 install.py --config-dir /path/to/codex-config --skills-root /path/to/skills
```

installer は既存 Hook を保持し、自己所有の 2 イベントの handler だけ置換します。元の `hooks.json` を `hooks.json.backup-<SHA256>` に保持し、検証後に一時ファイルから設定を置換します。破損設定・未知の構造・書込先ファイルの symlink は説明付きで失敗し、現在の設定を書き換えません。基準ディレクトリと読取用の通常 symlink は正規化して扱います。同じ設定なら保存せず、配置済みコードの欠損だけ復元します。旧版コード・バックアップは保持します。

**導入だけでは Hook は信頼されません。Codex の正規 `/hooks` 画面で生成された定義とコードを確認し、信頼を設定してください。** 定義の更新時も再確認が必要です。installer は trust、config.toml、requirements.toml、features を変更しません。プロジェクト等で Hook が無効なら、その設定が優先されます。

参照: [Codex Hooks の公式仕様](https://learn.chatgpt.com/docs/hooks)。非管理 Hook の信頼確認、複数設定の合成、追加 context 形式はこの仕様に従います。

## 取り外し・復帰

```sh
python3 install.py --remove
```

独自配置なら同じ `--config-dir` を渡します。他の Hook を残し自己所有 handler だけ取り除きます。スキルと旧版コードは削除しません。過去版へ戻す場合はその版の installer を実行し、定義を `/hooks` で再確認します。バックアップ全体の復元は他の変更も戻すため自動では行いません。

## 試験

配布ルートから:

```sh
python3 -m unittest discover -s hooks -v
```

単体試験は文脈選択、読取の異常、非ブロック出力形式、既存 Hook 保持、冪等導入・更新・除去を確認します。Codex の実イベントでの起動・スキル使用の証拠とは別です。実経路では通常依頼、読取だけ、OFF、適用外、再開、入口欠損と復帰を確認してください。
