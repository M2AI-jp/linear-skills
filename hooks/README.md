# Codex Hookの接続

利用側の既存入口から指定Project・原要求・正本・許可済み範囲を受け取る。状態・行動・受入の規則は、導入済みlinearの`references/contract.md`を参照する。配置方法は[導入説明](../README.md)。配布先に本開発のSSOTやタスク履歴は不要。採否・評価版・未達は利用側の指定Linearに保持する。

同じ版の4ファイルを同じhooksディレクトリへ配置する。`runtime.py`はイベントの振分けと対象・状態・依存の検査、`linear_read.py`は現在の実データ取得と表示上の差異の比較、`github_read.py`はGitHubの読取照合、`linear_delete.py`は許可された現在Projectの限定削除を担当する。業務状態・許可フラグの台帳は持たない。設定はCodex本来の`.codex/hooks.json`と`.codex/config.toml`。

## 実行条件

- Python 3.9以上とHookを利用できるCodex CLI／Desktop。利用先の実行版と経路を確認する。
- PATH上の`linear-api`。GraphQL JSONを標準入力に受け、応答を標準出力へ返す既存接続。この接続は同梱しない。利用先が認証済みの互換接続を用意し、資格情報を配布物へ複製しない。
- Hook導入ルートの既存`AGENTS.md`または`SSOT.md`に`Linear Project ID: UUID`を置く。GitとローカルSSOT.mdは不要。新規構築は`Linear Project ID: 未作成`とし、作成後に指定入口を更新する。両ファイルに指定があれば同じ値でなければ拒否し、先勝ちで選ばない。未指定・不正IDも未確認として扱う。
- Hook設定のcommandは導入先に配置したruntime.pyの絶対パスにする。起動サブディレクトリやGitの有無から誤ったコードを探さない。
- プロジェクト設定と各Hook定義をCodexの正規UIでレビュー・信頼してから有効性を確認する。信頼ハッシュを直接書き換えない。

## 制御すること

開始・再開・圧縮後はAPIから現行Projectを取得する。長い本文はCodex本来のコンテキスト出力処理へ渡し、Hookが固定文字数で切り捨てない。

Linear MCPのProject・Issue・Milestone・Document読取は、現行Projectへ限定する。無限定検索と別Projectは拒否する。新規Projectの準備に必要なチーム・状態等のメタデータは取得できる。

Issueの更新では、所属・実在するチームの状態・必須依存を検査する。In Reviewから依存成立後のDoneは通る。Doneと同時に受入本文や必須依存を変える操作は拒否する。誤Doneの撤回は、前提が崩れた場合にも可能。ProjectのCompletedはBacklog＋厳密名Deferredだけを未完了検査から除外し、その他の未完了を拒否する。非保留かつ非Canceled／DuplicateのIssueはDoneも含めて未完了の先行依存を拒否する。ラベル・逆依存connectionのpageInfo不足は未確認で、Project Issueの次ページは引き続き取得する。受入範囲変更とCompleted同時更新は拒否する。保留の意味の判断は共通契約を参照する。**通過は機械的前提の成立だけを表し、PMによる原要求・対象版・実試験・外部結果の評価を代用しない。**

Deferredラベルがない場合だけ、通常MCPのsave_issue_label／create_issue_labelで現行Project所属teamId・厳密名Deferredの新規作成を扱う。別team・別名・既存label編集には広げない。作成前と作成後はlist_issue_labelsで照合し、再作成しない。

保存後は対象を再取得し、実装した本文・題名・状態を照合する。Markdownの箇条書き・表・ネイティブIssueリンクの表示変換と、本文や参照先の変更を区別する。未反映を通知し、書込を自動反復しない。本文patchやすべてのプロパティの意図まで自動検証するものではなく、PMが実際の本文・所属・依存も読み戻す。

明示的なmainへの直接書込と、対象を検査できない直接GraphQL呼出しを拒否する。作業ブランチへmainを取り込むことと、mainを書き換えることを混同しない。正常統合の機械検査は下記の限定経路で行い、意味の受入はGit運用へ返す。

Stopはネイティブ記録の現在ターンに認識できる変更があるとき一度だけ照合を促す。読取だけなら続行を要求せず、`stop_hook_active`で反復を止める。

## 限界と確認方法

Hookは意味の真偽を認定しない。任意プログラム、後続stdin、GUI、未対応MCP操作、変わり得るネイティブ記録形式は完全な強制境界にならない。認識できないLinear MCP操作は通さず、必要な対象照合を実装・試験してから対応する。PostToolUseは副作用を取り消さない。取得失敗を成功にしないが、正本とHook自身の修復は可能にする。

入口の矛盾・削除後も、Codexネイティブの`apply_patch`（`tool_input.command`）で導入ルートのAGENTS.md／SSOT.mdとHook実装・設定を修復できる。patchの変更元・移動先をすべて解決してから例外を適用し、同名の別フォルダや未知の入力文字列へ修復許可を広げない。

`ruff check --select E4,E7,E9,F hooks`

`python3 -m unittest discover -s hooks -p 'test_*.py' -v`

上はソースツリーの`test_runtime.py`による局所的なプロトコル試験で、配布先の実サービス・通常導入の受入を代用しない。通常導入は正規UIで信頼したCLI／Desktopを利用先で起動し、開始時の対象取得、不正操作の実行前拒否、許可済み正常操作、読戻し、終了の実イベントと副作用を観測する。対象版・実行経路と期待結果を照合し、判定変更の影響部分も通常Hook経路で検査する。既存合格は変更影響と新証拠がある範囲だけを再評価する。

設定・発火・試験件数だけで、運用や業務全体を合格と報告しない。通常CLI／Desktopの実効性と残作業は現行Projectを参照する。

[公式仕様](https://learn.chatgpt.com/docs/hooks)

## GitHub統合の対応経路

`gh pr merge <PR番号> --repo <owner/repo> --match-head-commit <40桁SHA>`を単独で同期実行する。末尾の`--merge`／`--squash`／`--rebase`のいずれかは指定可能。`--admin`・`--auto`・背景実行・前提変更との複合は拒否する。GitHub.com上の既存gh認証を使い、認証情報を複製しない。

`gh pr --repo … merge`など継承オプションの配置でも統合として認識し、上記固定形式以外はPre／Postとも未対応とする。`checkout -B`／`switch -C`によるmain／master強制更新も拒否し、通常feature切替・読取は維持する。

`github_read.py`はPRのhead/base、現在main、classic branch protectionのstrictと管理者適用、発行元app IDが固定された必須check-runの最新実結果をGETする。headに現在mainが含まれ、全必須結果がそのheadでcompleted/successの場合だけ通す。skip・neutral・古い版・発行元不一致・取得失敗は通さない。チェック取得後にhead/baseを再確認し、競合はGitHubのstrict保護とmatch-head-commitでも制約する。チェックの内容が必要なQA/E2Eを検証するかはPMの責任であり、名前・リンク・本文フラグで認定しない。

main向け、最新mainを含むhead上のcheck-runsに対応。merge専用チェック、発行元未固定のlegacy status、rulesetのみの保護、merge queueなど照合できない構成は未対応として拒否する。保護を弱めて通さず、必要なら取得責任を追加評価する。利用先のプラン・権限で必要な保護を設定・取得できることを事前に確認する。

classic branch protectionの`required_status_checks`部分は次の形にする。`end-to-end`と`12345`は例で、必要な試験の実check名と、そのcheck-runの`app.id`に置き換える。`strict: true`に加え、保護全体で`enforce_admins: true`も設定する。書込ではdeprecatedな`contexts`を`checks`と併用しない。これは保護全体のPUT payloadではなく、他の必要設定は利用先の方針を保持する。[設定API](https://docs.github.com/en/rest/branches/branch-protection#update-branch-protection)

```json
{
  "required_status_checks": {
    "strict": true,
    "checks": [{"context": "end-to-end", "app_id": 12345}]
  }
}
```

PostToolUseは統合済みPRのmerge_commit_shaとmainへの到達関係をAPIで読み戻す。squash/rebase時にhead SHAをmain SHAと誤認しない。失敗・非同期未完了・読戻し不能は統合済みとせず、再実行前に実状態を調べる。PostToolUseは副作用を取り消せない。

通常feature作業とreadは維持し、main refのbranch強制変更、更新時のGit取得失敗、cd/switch/checkoutと更新の複合を拒否する。認識した直接GitHub API/MCPのmerge/ref更新も拒否し、既知の読取は通す。任意プログラム・シェルの完全解析や未知の全ツールの禁止は行わない。コードのない環境にCIを生成しない。利用先で採用する版の実GitHub保護・チェック・正常統合と通常CLI経路を観測し、局所試験の合格を転用しない。

[gh pr merge](https://cli.github.com/manual/gh_pr_merge)・[branch protection API](https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection)・[check runs API](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference)

## 現行Projectの削除

削除が許可された利用側の入口で、`python3 hooks/linear_delete.py <現在Project UUID>`を単独実行する。導入先の同じhooksディレクトリにruntime.py・linear_read.pyも配置する。Hookは実行ファイルのパス・引数・現在入口・実在対象を検査し、専用処理自身も書込直前に入口を再確認する。別Projectや曖昧な引数、複合呼出し、汎用GraphQLは許可しない。

専用処理だけが既存linear-api接続へ固定`projectDelete`を1回送り、同じIDの`trashed: true`を読み戻す。既削除なら書込を繰り返さない。archiveだけ、null、取得失敗、応答と実状態の不一致は成功にせず、部分失敗として確認へ返す。PostToolUseも対象の削除状態を読む。保存フラグ・資格情報・台帳は保持しない。確認後はネイティブ入口を現在の意図へ修復し、削除済みProjectを次回の正本にしない。

これはLinearの[公式projectDelete](https://github.com/linear/linear/blob/master/packages/sdk/src/schema.graphql)によるtrashへの削除であり、archiveや復元不能な消去ではない。模擬回帰と実APIの削除を分け、実APIの正常削除・削除後再開は担当Issueの独立受入で確認する。
