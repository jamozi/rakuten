# 既存記事の段階公開

`verified-incremental` は既存記事の一部と、明示した共通変更だけを扱う公開方式です。
通常 API リンクの `standard-api` を指定し、計測は OFF のままにします。
引数なしは読み取り専用の計画表示です。対象は明示指定し、自動で全件へ広げません。
既存の承認待ち候補は元の形式とハッシュのまま扱います。

## 対象と証跡

- 既存記事 ID・slug・URL を維持します。新規投稿・固定ページは作成しません。
- 比較に残す商品と、写真・購入リンクを掲載する商品は別集合です。
  未確認の商用要素はブロックごと除外し、理由を manifest に残します。
  写真の空枠やメーカーリンクへの購入ボタン代替は使いません。
- 購入リンクがない記事の収益機能は `NOT_INCLUDED` です。検証済みの件数へ
  加算しません。同一商品の API URL を複数箇所に使うことはできます。
- 本文・公式出典・対象商品・掲載位置・共通成果物の正確な集合とハッシュを、
  生成、監査、提案、再開、適用、本番照合で再検証します。

公式情報は実際に再取得して locator と本文を照合します。日付やハッシュだけを
更新して確認済みにはしません。楽天の資格情報、API 応答、画像、公開バックアップは
保存済み checkout `/home/minami/rakuten` の private 保存先に置きます。
実行するコードと商品契約は現在の作業 checkout を使い、秘密情報をコピーしません。

## 準備とローカル確認

記事本文・テーマはローカルのtracked sourceで作成・確認し、確定した候補の本文・ファイルを
そのまま本番へ適用します。本番用に文章を書き直す工程は設けません。ローカル管理画面だけに
保存した編集は公開元にならないため、残す変更はtracked sourceへ反映してprepareします。
未選択記事はMCP snapshotの内容を保持し、選択記事も確認後に変われば候補の照合で検出します。

通常のローカル起動は本番と同じ通常APIリンク・計測OFF・圧縮JavaScriptを使います。
`make wordpress-preview-environment`は稼働中WebコンテナのWordPress/PHP、テーマ、Yoastの実値を
読み取ります。prepareの既存レポートの`environment`には本番snapshotとの一致・相違・
明示したテーマ変更・未取得を分けて記録します。旧snapshotにPHP情報がなければ未取得とし、
承認待ちsnapshotを書き換えません。親テーマの本番版、全plugin一覧、CDNや一般表示設定など
MCP未取得の値まで一致したとは扱いません。ローカルURL、noindex、メール・外部通信の停止、
ローカル専用アカウントとデータは意図的な差分として維持します。

1. bounded WordPress MCP から実際の公開内容を取得します。
   `scripts/raos_wordpress_incremental_snapshot.py` は固定の既存14ページを対象とし、
   公開日時・分類は公開 REST 応答との照合結果も区別して保存します。
2. 次の共通入口で対象を確定し、準備します。`plan` は書き込みや生成を行いません。
   出典（記事の根拠と規約等の補助資料）、投稿ID、対象範囲、共有変更、公開用本文を
   提案と同じ関数で事前検証します。生成は依存順に一度行い、テーマ刻印を途中へ組み込みます。
   ZIP作成は公開処理側です。すでに登録した候補をprepareで上書きしません。

```bash
make wordpress-production-request                       # read-only plan
make wordpress-production-request ARGS='plan --articles <slug> --snapshot-name <name> --json'
make wordpress-production-request ARGS='prepare --articles <slug> --snapshot-name <name>'
# 明示した共有変更だけ追加: --include-theme / --update-policies all
# 同じ引数での再開は有効な既存候補と結果を使う
make wordpress-production-request ARGS='plan --candidate <private-candidate> --json'
```

3. 準備処理は共通プランナーの静的検査・関連テスト・生成物検査を`fast --critical`で実行し、
   ローカルWordPressを起動します。必要なら同期し、対象記事、ホーム、関連一覧、内部リンク
   利用先を選択して検査・撮影します。共有表示変更では全体を選びます。
   `make final` は任意の全体診断です。5コマンド連続実行は監査の条件ではありません。
4. 機能検査と撮影は独立ブラウザコンテキストで並列実行します。既定はCPU数と4の小さい方、
   `prepare --workers N` または `RAOS_WORDPRESS_BROWSER_WORKERS=N` で調整できます。
   viewportは360/390/768/1440pxと200%文字拡大です。画面数の固定値ではなく選択集合を照合します。
   Lighthouseはブラウザ作業終了後に各対象3回を直列測定し、従来の中央値基準を維持します。
5. URL・スクリーンショットを確認します。進捗は
   `output/publication/release-preparation.v2.json` の対象・チェック・残課題・次処理を読みます。
   元のテスト出力は`output/publication/checks/`、表示原本は
   `output/playwright/local-preview.audit.v1.json`（内部schemaはV1/V2）、画像は
   `output/playwright/local-preview/`、所要時間は`output/playwright/local-preview.run-summary.v2.json`です。
   結果ファイル・本文・テーマ・画像・表示設定・ツール入力・WordPress内の状態と期限を
   照合できる場合だけ再利用します。成功日時を書き直しません。

対象確定後の任意の文章・デザイン改善は次回更新へ回し、今回は対象内の不具合を修正します。
修正後は影響する検査を実行します。公開処理の変更だけで表示入力が変わらない場合は撮影を再利用できます。
表示検査の期限は2時間、監査は24時間、適用用証跡は15分です。失効した単位だけ更新し、
未変更の検査や担当者を一律に作り直しません。バックアップの実際の復元・照合は引き続き必要です。

## 監査対象と短命の公開証跡を分ける

`scripts/raos_wordpress_incremental_candidate.py` の現在の準備経路は、商用要素を
除いた候補を作成します。この候補を作っただけでは監査・収益検証・公開は未完了です。

候補 manifest は同じ成果物を2巡監査するための不変の対象です。有効期間は最長24時間、
かつ選定出典の最短有効期限までです。これは公開権限や15分の反映用証跡ではありません。
実装担当とは別の Codex による実際の監査を2巡行い、修正があれば影響する検査と監査を
差分確認します。各担当は自分の観察を記録し、最終候補のハッシュに結び付けます。
2巡で同じ有効な自動検査原本を参照できます。過去の検査出力を点検したことと再実行は区別します。

実読者調査は未実施の後日確認項目です。Codex による評価で代用しません。
連絡先の所有者確認と実送受信試験も区別します。監査報告の詳細な形式は
[監査インターフェース](../verified-incremental-audit-v1.md) を参照してください。

公開直前は、現在の出典・商品・成果物・ローカル検査・本番保存内容を再検証したうえで、
最長15分の activation を作ります。商品／出典は24時間の期限を維持し、最短の期限を
採用します。再開で期限を自動延長しません。失効した対象に新しい適用を行いません。

## 提案、所有者承認、照合

Site Kit を保持して既存 DNS 事前参照を除去する移行は、candidate 準備時だけ
`--runtime-transition sitekit-dns-prefetch-removal-v1` と `--include-theme` を
明示します。省略時は従来の strict 検査です。旧／新テーマ、除去関数を含むファイル、
対象14 URLごとの既存1件が manifest と監査に拘束されます。提案・適用前に旧テーマの
参照が残る状態と、適用後の0件必須を区別し、この移行条件も所有者へ提示します。
他のスクリプト、Cookie、参照先、HTTP Link は許容しません。新テーマ適用済みの
再開と最終照合に例外はなく、DNS通信ゼロの証拠とも扱いません。

実行入口は `scripts/raos_wordpress_publication_request.py`（Makefileと同一）です。
新規候補はV2監査を使い、2巡の独立レビュー後に次へ進みます。

```bash
make wordpress-production-request ARGS='propose --candidate <private-candidate> --preview-fixture <private-preview> --implementation-execution-id <id>'
# wp-adminの別人による所有者承認後のみ
make wordpress-production-request ARGS='apply --candidate <private-candidate> --preview-fixture <private-preview> --implementation-execution-id <id>'
make wordpress-production-request ARGS='readback --candidate <private-candidate> --preview-fixture <private-preview>'
```

旧候補は既存のV1監査・承認内容を保持します。互換入口では
`--publication-profile verified-incremental --link-mode standard-api --quality-audit-mode codex-owner`
と従来の`--incremental-stage`等を明示します。全件公開の旧方式も
`--publication-profile full-portfolio`を明示して利用でき、既存の条件を維持します。
`--base`を変更した場合は、prepareとpropose/applyで同じ値を指定します。

ローカル検査と必須 CI 合格後のコードから提案を作り、対象ハッシュを所有者へ示します。
本番連携プラグイン初回更新は既存の wp-admin 手順で所有者が実施します。
所有者の具体的な wp-admin 承認と単回リースがなければ適用しません。
Codex の監査結果や会話上の包括的な依頼を、この承認の代わりにはしません。
登録・再開・適用・本番照合では、既存 batch status GET が返す各提案の
`proposal_bindings`（種類、idempotency key、変更前後のハッシュ、既存投稿ID・種別）を
公開候補へ照合します。このサーバー側の不変の情報がない旧応答では段階公開を拒否します。
保存済み envelope の日時を変更してハッシュを再計算しても、登録時の key と一致しません。
従来の全件公開では追加情報のない旧応答との互換性を維持します。

通信断時は既存 operation の状態を確認します。`operation-status` は指定1件の状態を
取得し、公開・適用・復旧・後処理を起動しません。ただし既存サーバーの期限整合処理で
失効状態と失効リースが更新される場合があります。無条件の再送は行いません。

適用後は対象本文・URL・SEO・画像・リンク・テーマを照合し、未更新ページと対象外の
公開内容が維持されたことも確認します。本番照合が成功した batch だけを公開済みとし、
改善中・保留・収益機能未導入の範囲を分けて報告します。PR のマージやローカル成功を
本番公開と呼びません。収益、検索順位、実読者評価、法令適合そのものは保証しません。
