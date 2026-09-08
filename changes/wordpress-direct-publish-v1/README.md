# WordPressの簡易公開

日常の操作は **Codexで作成 → ローカル確認 →「公開して」** です。
記事の新規作成・更新と`kurashinoshirube-child`の変更に対応します。
独立監査、2巡レビュー、監査報告書、wp-admin再承認、公開前のPR/CI待ちは不要です。

## 編集から公開まで

記事台帳は`articles.v1.json`、通常の本文は`articles/`で管理します。
台帳に記事キー、new/existing、投稿種別、slug、タイトル、抜粋、本文sourceを指定します。
未取得の本番IDは作りません。本文はWordPress block markupです。
商品同定・一次情報・鮮度・比較範囲・広告表示は作成時の要件です。
価格や料率を商品選定の加点要素にしません。

既存記事の初回取り込みは、現在のtracked本文を編集可能なsourceへコピーします。
本番から本文を作り直す処理ではありません。旧fixtureを直接編集しません。

```sh
make wordpress-production-request ARGS='direct import-existing'
make wordpress-production-request ARGS='direct prepare --articles <article-key>'
# 共有テーマの変更を含む場合は --theme を追加
make wordpress-production-request ARGS='direct preview --candidate <candidate-id>'
# ローカルURL・確認画像を見たユーザーの、この候補への公開指示後に実行
make wordpress-production-request ARGS='direct publish --candidate <candidate-id>'
```

Codexが上の内部操作を行います。利用者はGitや候補ファイルを操作する必要がありません。
記事とテーマはprepareで固定され、確認した版をそのまま公開します。後から本文・対象・テーマが
変わった場合は、新しい候補を確認します。previewの成功だけでは公開しません。
記事だけを公開する場合は、表示に使うローカルテーマが本番と一致することも確認します。
未反映のテーマ変更がある場合は`--theme`を含め、その版も一緒に確認します。

## 毎回行う確認

- 記事：対象ページを390px・1440pxで表示し、本文・画像・購入リンク・広告表示の基本を確認します。
- テーマ：構文とホーム・記事・一覧の代表画面を確認します。
- 本番反映：限定権限、変更前のrevision、直前状態の保存、冪等性、反映結果を自動確認します。

全ページ撮影、Lighthouse、全体テスト、復元演習を毎回の条件にしません。
同じ固定入力・表示runtime・保存画像なら、元の確認日時の結果を再利用します。
公開機構・認証・共通基盤を開発する際の回帰テストと必須CIは別に実行します。

## Gitと中断からの再開

prepareは対象sourceだけを独立したGit indexでcommitします。現在のHEAD・index・無関係な変更を
変更しません。本番照合後に専用branchをpushし、PRを作成してCI成功後にmergeします。
公開はGit同期の完了を待ちません。同期に失敗しても記事を再公開しません。

```sh
make wordpress-production-request ARGS='direct status --candidate <candidate-id>'
make wordpress-production-request ARGS='direct publish --candidate <candidate-id>'
make wordpress-production-request ARGS='direct sync --candidate <candidate-id>'
```

候補ごとのprivate journalに操作IDと現在の状態を記録します。通信結果が不明なときは同じ操作を
照合して再開します。新規投稿は同じ記事キーから重複作成しません。本番で他者が変更していた場合は
上書きせず停止します。公開済み・復旧中・競合・Git同期待ちを区別し、未確認を成功としません。

## 初回だけ行う本番切替

1. localの実装・回帰テスト・使い捨てWordPressでの公開と復旧確認を完了し、plugin更新物を提示します。
2. その具体的な更新物のインストールと限定権限設定について、所有者の承認を得ます。
3. 所有者が管理画面で専用publisherと対象を設定します。既存記事は登録した対象、新規記事は
   この連携が作成した記事だけを継続更新できます。子テーマは固定slugに限定します。
4. 専用Application Passwordを既存の安全な保管手段で設定し、`direct status`で実接続を確認します。

権限は初期OFFで、既存のeditor/operatorをアップグレード時に自動昇格させません。
停止スイッチ・権限取消・対象制限は本番側で適用します。plugin管理・DB migration・計測設定・
任意PHP/SQL・データ削除は日常公開権限に含みません。
旧承認待ち候補は元の方式のまま扱い、簡易公開へ黙って移しません。

設定画面は「ツール → RAOS Codex proposals」の「Owner-direct-v1 publishing」です。
専用アカウントのroleは`raos_codex_owner_direct_publisher`とし、
`Dedicated publisher user ID`に指定します。新規記事を使う場合は
`Allow new posts created and owned by this publisher`を有効にします。
既存対象には`article_key`・`post_id`・`post_type`・`slug`を設定します。
`Enable owner-direct-v1`と`Save delegation`で保存します。
専用Application Passwordの名称は`RAOS Codex Owner Direct Publisher`です。

```sh
# 承認済みの初回設定時のみ。パスワードは非表示の端末入力で保存し、会話には貼らない
.venv/bin/python scripts/store_wordpress_mcp_credential.py --purpose owner_direct_publisher
make wordpress-production-request ARGS='direct status'
```

認証の初回保存は所有者のcheckout `/home/minami/rakuten`で行います。別のworktreeからは、
`direct --owner-checkout /home/minami/rakuten prepare ...`のように全操作で同じ保管先を指定できます。
本文・固定候補・Git履歴は作業中のworktreeを使い、認証を複製しません。

ローカル表示にはDockerと、`make setup`で導入したPlaywrightのChromiumを使います。
初回だけブラウザーが未導入なら`node node_modules/playwright/cli.js install chromium`を実行します。

本書は通常の記事・子テーマ公開について旧公開runbookと独立監査規定を置き換えます。
不変baselineを変更せず、読者向けの正確性・内部情報の非公開を維持します。
