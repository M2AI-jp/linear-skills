# 起動の案内（現在は無効）

このフォルダのコードは**無効化した状態で入っています**。`route.py` の `DISARMED = True` を解除し、`install.py --enable-interception` を明示的に実行するまで、何も起きません。スキル本体はこれを使わずに動きます。

## なぜ無効なのか

前の版は、プロンプトに `linear` という語が含まれるか、作業フォルダから親へたどった `AGENTS.md` に `linear` が含まれるだけで発火しました。線形代数でも線形回帰でも、Linearに触れる `AGENTS.md` を持つ無関係なリポジトリの作業でも案内が差し込まれます。2026-10-14、他の開発への干渉を理由にパッケージごと撤去されました。

必要だったのは「使う場面で、名前を言われなくても選ばれること」です。できていたのは「要るかどうかに関わらず差し込まれること」でした。別の問題です。

## 書き換えた起動条件

発火するのは、次のすべてが成立したときだけです。

1. `DISARMED = False` にしてある
2. 作業フォルダか、その祖先の `AGENTS.md` / `CLAUDE.md` に、文字列 `linear-workflow` が書かれている（リポジトリ側の明示的なopt-in）
3. `UserPromptSubmit` では、プロンプトに `linear.app` またはIssue IDの形（`MAT-123`）が含まれる。`SessionStart` では `source` が `resume` か `compact`
4. 指し示す `skills/linear-workflow/SKILL.md` が実在して空でない

リポジトリが自分で名乗らない限り発火しません。入力装置はリポジトリごとに用意する、という元の考え方をそのまま条件にしています。

## できること・できないこと

できるのは、入口のパスを1行案内することだけです。Linearを更新せず、ツールや終了を拒否せず、入力を書き換えず、LLMやMCPを呼ばず、外部通信をしません。失敗・設定なし・入力不足のときは空出力で終了コード0です。Python 3の標準ライブラリだけを使います。

案内が出たことは、スキルが使われたことの証明ではありません。実際に使ったかどうかは実行記録で確かめます。

## 有効にする場合

```sh
python3 -c "import pathlib,re; p=pathlib.Path('route.py'); p.write_text(p.read_text().replace('DISARMED = True','DISARMED = False'))"
```

```sh
python3 install.py --enable-interception
```

導入先を変えるなら `--config-dir` と `--skills-root` を渡します。installerは既存Hookを保持し、自分が所有する2イベントのhandlerだけを置換します。元の `hooks.json` はバックアップへ退避します。

**導入だけではHookは信頼されません。** Codexの `/hooks` 画面で生成された定義とコードを確認し、信頼を設定してください。定義を更新したら再確認が必要です。installerは trust、config.toml、features を変更しません。

## 戻す

```sh
python3 install.py --remove
```

削除に `--enable-interception` は不要です。他のHookは残し、自分が所有するhandlerだけ取り除きます。

## 試験

```sh
python3 -m unittest discover -s hooks
```

無効のまま何も返さないこと、有効にしたときopt-inが必須であること、`linear algebra` で発火しないこと、`SessionStart` が resume/compact だけであること、installerが明示フラグなしでは何も書かないことを確認します。
