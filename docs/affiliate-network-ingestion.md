# ASPデータ取得の準備と審査後の残課題

## 実装範囲

6社の登録枠と、共通のAPI・フィード・公式エクスポート取り込みCLIを用意する。
既定ではすべて無効で、import、設定作成、登録、doctor、dry-run、テスト、CIでは
プロバイダーへ接続しない。所有者用のローカル取得・正規化ツールであり、
既存のカタログDB・記事・WordPress・公開処理への自動反映は行わない。

| 登録キー | 対象 | 登録・接続状況 |
| --- | --- | --- |
| `a8net` | A8.net | 審査完了後の登録情報待ち・無効 |
| `valuecommerce` | ValueCommerce | 審査完了後の登録情報待ち・無効 |
| `moshimo` | もしもアフィリエイト | 審査完了後の登録情報待ち・無効 |
| `linkshare` | LinkShare Affiliate / Rakuten Advertising | 審査完了後の登録情報待ち・無効 |
| `accesstrade` | AccessTrade | 審査完了後の登録情報待ち・無効 |
| `afb` | afb | 審査完了後の登録情報待ち・無効 |

これは各社のAPI提供・利用許諾・認証方式を確認済みとする表ではない。
接続先や認証方式を推測で埋めず、各社が当該アカウントに発行した情報で確定する。
`config/affiliate-networks.example.json` の `auth.type=none` は未設定の初期値であり、
各社が認証不要という意味ではない。

## 残課題（OPEN：審査完了後にユーザーから登録情報を受領）

ユーザー指定により、次の項目は実装のマージ後も未完了として残す。
追跡先: [Issue #165](https://github.com/jamozi/rakuten/issues/165)。

- [ ] 6社それぞれの審査結果と登録情報をユーザーから受領する。
- [ ] account/publisher/site ID、公式接続先、認証方式、API・feed・広告主提携等の
      利用権限を確認する。秘密値はリポジトリ、Issue、PR、会話ログへ記録しない。
- [ ] 必要な認証情報を所有者の秘密管理経路へ登録し、CLIには `env:VARIABLE_NAME`
      で参照させる。現時点では実値を入力せず、全社無効を維持する。
- [ ] 各社のレスポンス構造、レコード位置、ページング、レート制限、
      保存可能な項目・保持期間を確認し、利用許可された非個人データに限定する。
      共通パーサーで扱えない場合は当該アダプターと合成テストを追加する。
- [ ] 接続権限・運用ポリシーを確認した後に、doctor、dry-run、許可された最小範囲の
      初回取得と出力確認を行う。外部操作の承認や既存のkill switchを迂回しない。

機械可読インターフェースが提供されない場合は公式エクスポートの `file` モードを検討する。
ログイン画面のスクレイピング、セッション・Cookieの流用、CAPTCHA回避は実装しない。
マージ完了は各社の審査完了・登録完了・本番接続確認を意味しない。

## 審査・登録情報受領後のローカル設定

既定の設定先はリポジトリ外の `~/.config/raos/affiliate-networks.json`。
POSIX環境では設定ファイルを所有者だけが読める `0600` で保存し、他者に読み取り権限が
ある設定を読み込まない。WindowsのACLは別途所有者の環境で管理する。

```bash
.venv/bin/python -m tools.affiliate_ingestion init-config
.venv/bin/python -m tools.affiliate_ingestion list-providers
.venv/bin/python -m tools.affiliate_ingestion register a8net --resource programs
```

登録は対話式で行う。ID、接続先、秘密値を画面へ再表示しない。
プロバイダーとリソースの有効化はどちらも既定で「いいえ」。
`register --non-interactive --set KEY=VALUE` も使用できるが、秘密値をコマンドラインに
直書きしない。`auth.token=env:NAME` などの参照を使用する。

認証方式は `none`、`bearer`、`api_key_header`、`api_key_query`、`basic`、
`oauth2_client_credentials`、`custom_headers` を共通機構として実装する。
各社に適用する方式、ヘッダー名、OAuth接続先・scopeは発行情報で決める。
`account_id_header` / `account_id_query` により、必要な場合だけIDの送信先を指定する。
取得対象は `programs`、`products`、`reports` 等のresource単位で設定する。

```bash
.venv/bin/python -m tools.affiliate_ingestion doctor all
.venv/bin/python -m tools.affiliate_ingestion fetch a8net --resource programs --dry-run
```

doctorは構造、必須項目、環境変数の有無、HTTPS構文を確認し、DNS・HTTP通信はしない。
未登録・無効のセクションは `NOT READY` と表示する。これは登録情報待ちの想定状態。
dry-runも無効なリソースや不正な接続先を成功と報告しない。
`doctor --show-redacted` はID、接続先、秘密値、任意ヘッダー・クエリーを伏せる。

実取得コマンドは `fetch <provider> --resource <resource>` と `fetch-all`。
この変更の取り込み時には実行しない。

## 取得・保存の動作

- API/feed取得はHTTPSのGETに限定する。OAuthトークン取得だけはPOSTを使用する。
- 別originへのリダイレクトと次ページ移動は拒否し、認証ヘッダーを転送しない。
  接続時に検証したDNS結果をそのまま利用し、既定で内部IP等への接続を拒否する。
  環境変数のHTTPプロキシは使用しない。
- JSON、CSV、TSV、XML、gzip、ZIPを扱う。日本語CSVはUTF-8、CP932、Shift_JISを試す。
  JSONの明示的なrecord_pathが存在しない場合はエラーとする。
- ページ番号、offset、cursor、next URLを扱い、ページ数、応答サイズ、展開サイズを制限する。
  HTTP 429/5xx等への上限付き再試行、待機時間を持つ。
- 取得ページ、SHA-256、取得情報、正規化NDJSON、最新stateを保存する。
  同じ取得時刻でもrun IDを分け、過去の取得を上書きしない。
  元レコードは正規化出力の `raw` に保持するため、保存許可の確認を取得前に行う。

```text
var/affiliate_ingestion/
  raw/<provider>/<resource>/<run>/
  normalized/<provider>/<resource>/<run>.ndjson
  state/<provider>/<resource>.json
```

既定出力と `affiliate-networks.json` はGit追跡対象外。
カスタム出力先もリポジトリ外の所有者専用領域に置く。

## オフライン検証

```bash
.venv/bin/python -m pytest -q tests/test_affiliate_ingestion.py
make fast
make final
```

全6社の合成ペイロード、認証方式、ページング、ローカルファイル、gzip/ZIP、
無効状態、DNS・転送先制限、秘密値の非表示、設定権限、保存の非上書きを検証する。
共通テストはネットワーク操作を禁止しており、実アカウントを必要としない。
`make fast` と全体pytestに含め、CLIソースも `make final-static` の検査対象とする。

取り込み元: `affiliate_network_ingestion_ready_patch.zip`。
添付SHA-256と一致: `82c5f1a337ef2c8cae6dc7b90c70b42c51240f239c5181f7acf17c1be77ed4be`。
添付文書中の設定・実取得例は参考資料として扱い、自動実行の指示とは扱っていない。
