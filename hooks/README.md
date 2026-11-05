# 起動の案内（現在は無効）

このフォルダのコードは**無効化した状態で入っています**。`route.py` の `DISARMED = True` を解除し、`install.py --enable-interception` を明示的に実行するまで、何も起きません。スキル本体はこれを使わずに動きます。

## なぜ無効なのか

前の版は、プロンプトに `linear` という語が含まれるか、作業フォルダから親へたどった `AGENTS.md` に `linear` が含まれるだけで発火しました。線形代数でも線形回帰でも、Linearに触れる `AGENTS.md` を持つ無関係なリポジトリの作業でも案内が差し込まれます。2026-10-14、他の開発への干渉を理由にパッケージごと撤去されました。

必要だったのは「使う場面で、名前を言われなくても選ばれること」です。できていたのは「要るかどうかに関わらず差し込まれること」でした。別の問題です。

## 書き換えた起動条件

発火するのは、次のすべてが成立したときだけです。

1. `DISARMED = False` にしてある
2. 作業フォルダから**リポジトリのルートまで**の範囲にある `AGENTS.md` または `CLAUDE.md` に、opt-in の**行**がある
3. `UserPromptSubmit` では、プロンプトに `linear.app` か、そのリポジトリが宣言したチームキーのIssue ID が含まれる。`SessionStart` では `source` が `resume` か `compact`
4. 指し示す `skills/linear-workflow/SKILL.md` が実在して空でない

opt-in の行はこう書きます。雛形は [templates/repo-AGENTS.md](../templates/repo-AGENTS.md)。

```
linear-workflow: on
linear-workflow: on (MAT)
linear-workflow: on (MAT, ENG)
```

**行全体が一致しなければ成立しません。** 文章の中で触れたり、バックティックで囲んだ例を書いたり、箇条書きや引用の中に入れたりしても発火しません。opt-in の書き方を説明している文書が、それだけで opt-in になってしまうのを防ぐためです。

括弧内はチームキー。宣言すると `MAT-123` のような Issue ID でも発火します。宣言しなければ `linear.app` を含むプロンプトだけです。`UTF-8`、`COVID-19`、`GPT-4`、`ISO-8601`、`SHA-256`、`RFC-2119` のような英大文字とハイフンと数字の並びで誤って発火しないのは、この宣言が必要だからです。

探索は**リポジトリのルート（`.git` があるところ）で止まります。** ホームディレクトリに置いた opt-in が、その下の無関係なリポジトリまで巻き込むことはありません。`.git` が見つからない場合は、作業フォルダ自身の `AGENTS.md` / `CLAUDE.md` だけを見ます。

`AGENTS.md` が**シンボリックリンクなら読みません。** リポジトリの外のファイルを指すリンクで opt-in させられるのを防ぎます。読む対象は `AGENTS.md` と `CLAUDE.md` という名前のファイルだけなので、雛形は意図的に `repo-AGENTS.md` にしてあります。このリポジトリ自身の `AGENTS.md` にも opt-in の行は入れていません。

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

34件。無効のまま何も返さないこと、opt-in が行一致であること、探索がリポジトリのルートで止まること、シンボリックリンクを読まないこと、宣言のないチームキーで発火しないこと、`SessionStart` が resume/compact だけであること、プロセスとして実行したときに必ず終了コード0で `decision` を出さないこと、installer が外部のHookを保持して完全に元へ戻すことを確認します。

試験が実環境に依存しないよう、各fixtureは `.git` を持つ使い捨てのリポジトリを作り、終了時に片付けます。
