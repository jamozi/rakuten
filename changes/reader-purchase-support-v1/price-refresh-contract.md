# 楽天価格の再取得: owner-private overlay と publisher 注入の契約（KS-020 / KS-304）

- 対象コード
  - domain: `python/raos/domain/editorial/rakuten_price_refresh.py`（純関数。ファイル・通信・時計・認証値に触れない）
  - adapter: `python/raos/adapters/rakuten_price_refresh_client.py`（唯一の通信、認証ファイルの読み取り、0600 の保存、tracked file の走査）
  - CLI: `scripts/raos_rakuten_price_refresh.py`（`plan` / `fetch` / `apply` / `gate` / `purge-expired`）
  - テスト: `tests/purchase_support/test_rakuten_price_refresh.py`（fixture はすべて合成値）
- 現状: publisher（`scripts/raos_wordpress_direct_publish.py`）への組み込みは**未実装**です。別バッチの merge 後に、§6〜§8 のとおり実装します。それまで `fetch` は実行できますが、公開はできません。

## 1. オーナー決定（計画より優先）

1. 楽天 API の価格・販売可能情報は、git 管理のファイルに書かず、push もしません。git の本文とカタログは価格なしのまま保ちます。
2. API 値は owner checkout の `.secrets/rakuten-price-refresh/<run_id>/` に置きます（ディレクトリ 0700、ファイル 0600、git 管理外）。`observed_at` と `cache_expires_at`（24 時間以内）を必ず付けます。カタログへ反映する promote 段はありません。
3. publisher は WordPress へ送る直前に overlay を本文へ注入し、期限前に価格なしの本文を送り直して消します（purge 公開）。
4. オーナーの 1 回の承認で「fetch・公開・期限前の purge 公開」を 1 組として行います。定期実行と自動公開はしません。

## 2. 公式仕様の確認（2026-09-15 取得）

| 資料 | URL | 取得時刻 (UTC) | raw sha256 |
| --- | --- | --- | --- |
| 楽天市場商品検索 API（version 2026-07-01） | https://webservice.rakuten.co.jp/documentation/ichiba-item-search | 2026-09-15T11:22:53Z | `cb7f998dc88820ecdb063ecd1c1cd371207b585e387a7f7edacddd92fdb2740d` |
| 楽天ウェブサービス規約（日本語・正文） | https://webservice.rakuten.co.jp/guide/rule（`/locale/ja` 経由） | 2026-09-15T11:29:43Z | `6fa97dc0136e8fa2bfa636a7c9f034c9b46a1160c35a5af147d2bb5d973a5fa0` |
| 同（英語・参考訳） | https://webservice.rakuten.co.jp/guide/rule | 2026-09-15T11:22:53Z | `621461ebd277cde7943fec4f7abcad6d9b168797fe01cbfbc512652c29c0ccf4` |
| クレジット表示 | https://webservice.rakuten.co.jp/guide/credit | 2026-09-15T11:22:53Z | `7b3b4d2ade62b6f6b36e34e959b9d068b2f97e52f7dba7b7690ceef912b26784` |
| RWS ヘルプ 900001974343（キャッシュ期間） | https://webservice.faq.rakuten.net/hc/ja/articles/900001974343 | 2026-09-15T11:23:58Z / 12:00:25Z に HTML を匿名取得すると HTTP 403 | — |
| 同（Help Center API、同じ記事の JSON） | https://webservice.faq.rakuten.net/api/v2/help_center/ja/articles/900001974343.json | 2026-09-15T12:03:10Z（HTTP 200、記事 `updated_at` 2024-04-01T01:12:52Z） | `6c3471d3c05931a86e228187b4dc14276a9e80f1fccc606015bc1831c35eedb6`。本文は KS-006 #8 の記録と一致 |

ドキュメントから確認した要求形式と、実装での使い方:

- **エンドポイント**: `https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701`。旧版として 2026-04-01 が並記されています。
- **認証**
  - `applicationId` はクエリで送ります（必須、access key と組）。
  - `accessKey` は入力ヘッダー表に【NEW】として載っており、「header or query parameter」のどちらでも可です。実装は**ヘッダー**で送り、URL に載せません。
  - `affiliateId` は任意です。実装は送りません（`affiliateUrl` も要求しません）。
- **実装が送るパラメーター**（`request_path()`）
  - `itemCode=<shop>:<item>`: ドキュメントの形式は "shop:1234"。
  - `hits=1`: 1〜30。
  - `availability=0`: 0 = 全商品、1 = 購入可能な商品のみ（既定値）。売り切れも返させるため 0 にします。
  - `format=json`
  - `formatVersion=2`: `items[0].itemName` の形になります。
  - `elements=itemCode,itemName,itemUrl,shopCode,itemPrice,itemPriceMin1,itemPriceMax1,itemPriceMin3,itemPriceMax3,availability,taxFlag,postageFlag`: カンマ区切りで、指定したフィールドだけが返ります。
- **出力の意味**
  - `availability`: 0 = 在庫なし、1 = 在庫あり
  - `taxFlag`: 0 = 税込、1 = 税別
  - `postageFlag`: 0 = 送料込み、1 = 送料別
  - `itemPriceMin3` / `itemPriceMax3`: 購入可能な価格の最小・最大
  - `itemPriceMin1` / `itemPriceMax1`: 購入できないものも含む全商品の価格の最小・最大（"All item price min/max"）。SKU を表す出力フィールドはありません（識別安全レビューで 2026-09-15 に同じ公式ページを再確認）。
  - SKU（色・構成）単位の価格や在庫の出力項目はありません。
- **エラー**（ドキュメントの表）

  | HTTP | error | 実装での扱い |
  | --- | --- | --- |
  | 400 | `wrong_parameter` | 実行を中止 |
  | 404 | `not_found` | `NOT_FOUND_PENDING` |
  | 429 | `too_many_requests` | `REQUEST_FAILED`（本文を保存しない） |
  | 500 | `system_error` | `REQUEST_FAILED` |
  | 503 | `service_unavailable` | `REQUEST_FAILED` |

  401 / 403 は表にありませんが、認証の拒否として実行を中止します。
- **アクセス頻度**: 数値の上限は書かれていません。「同一 URL への短時間の大量アクセスは一定時間応答しなくなる」とあるため、1.1 秒以上の間隔を空けます。

規約（日本語正文、2012-06-28 改定版を 2026-09-15 に取得）で効く条文:

- **第10条1項(7)**: 「ウェブサービスおよびアプリケーションを通じて得た情報（商品情報、ユーザの情報を含むがこれに限られない）に関し、当社が別途定める目的以外に使用し、または当社が別途定める以外の複製または改変をすること」
- **第10条1項(9)**: 「不特定または多数人と情報を共有することを可能にする場所にウェブサービスを通じて得た情報またはアプリケーションを保管すること」
- **第1条2項（英語参考訳）**: 商品情報には product names, store names, URLs, images, product descriptions, prices が含まれる、と定義しています。
- **RWS ヘルプ 900001974343（上表の API 経由で本文を再確認、KS-006 #8 と同文）**
  - (1) キャッシュ上限: 「商品の価格情報、および販売可能情報：24時間」「その他の情報：3か月間」。さらに「当社はいつでも上記の当社の知的財産を削除するようデベロッパーに指示することができ、デベロッパーは、かかる指示をただちに遵守する」。
  - (2) 価格・販売可能情報を表示する場合は、少なくとも 1 週間に 1 回、API から新たに取得した情報に刷新して再表示する。
  - (3) 1 時間に 1 回以上更新しない場合は、価格・在庫情報に隣接した位置に更新時刻・日時を記載し、次の免責事項を**隣接して掲載するかハイパーリンク等で掲載**する: 「このサイトで掲載されている情報は、●●（サイト名）の作成者により運営されています。価格、販売可能情報は、変更される場合があります。購入時に楽天市場店舗（www.rakuten.co.jp）に表示されている価格が、その商品の販売に適用されます。」

### 2.1 表示義務の引き継ぎ（注入する本文ごとに gate が検査）

| 義務 | 根拠 | この契約での満たし方 | gate |
| --- | --- | --- | --- |
| 更新日時の隣接表示 | ヘルプ (3) | `ps-price-date` の `<time>` を `observed_at` に書き換える（§6.1） | 見つからなければ注入が `BODY_PRICE_DATE_MISSING` |
| 免責事項（隣接またはリンク） | ヘルプ (3) | 値を注入する販売先ブロックの `ps-price-date` 段落に `href="/about-ad-policy/#production-about-rakuten-price"` があること（定型文は /about-ad-policy/ に掲載済み、KS-006）。2026-09-15 時点の `wordpress-direct-publish-v1/articles` の販売先ブロック 54/54 が満たす | `RAKUTEN_PRICE_DISCLAIMER_MISSING` |
| クレジット | 規約第13条、クレジット表示ガイド（テキスト版は `<a href="https://developers.rakuten.com/" target="_blank">Supported by Rakuten Developers</a>` を「提供された HTML のまま」使う） | 本文の `ps-media-credit` 段落に、`https://developers.rakuten.com/` への「Supported by Rakuten Developers」リンクがあること | `RAKUTEN_CREDIT_MISSING` |
| 週 1 回以上の刷新 | ヘルプ (2) | 値は 24 時間以内に purge 公開で消えるため、表示が 1 週間続くことはない | — |
| 削除指示への即時対応 | ヘルプ (1) | 楽天から指示があれば、承認済みの run について期限を待たず purge 公開（§8-5）と `purge-expired --run-id <run_id> --include-unexpired` を行う | — |

- 未解決: 現行のクレジットは `target="_blank"` と snippet のコメント行を省いています（KS-006 で適合と判定済みの既存表示）。「HTML をそのまま使う」との差をどう扱うかはオーナー判断で、この契約では変えません。

## 3. フィールドごとの保存規則（git に置いてよいか）

原則: **API 応答から得た値は、どれも git に置きません**（第10条(9)。GitHub は共有可能な場所にあたる）。git に置いてよいのは、編集者が API を使わずに決めた値だけです。

| フィールド | 出どころ | git | 規則 |
| --- | --- | --- | --- |
| `offer_id`, `product_id`, `exact_model`, `variant`, `variant_id`, `seller`, `seller_id` | 既存カタログ（編集判断、ブラウザ観測） | 可 | 変更しない |
| `merchant_url` / `item_url`（`https://item.rakuten.co.jp/<shop>/<item>/`） | 編集者が選んだリンク先 | 可 | canonical 形は merchant_url のクエリを除いたもの。**API の itemUrl で上書きしない**（照合に使うだけ） |
| `item_code`（`<shop>:<item>`）、`shop_code` | merchant_url のパスから導出 | 可 | API の itemCode / shopCode とは比較だけ。不一致でも binding を API 値へ直さない（IDENTITY_MISMATCH にする） |
| `sku_variant_id` | merchant_url の `variantId` | 可 | URL から導出する |
| `multi_sku`, `multi_sku_reasons` | 編集判断（URL・variant 文言・型番表記） | 可 | 安全側にだけ変更できる。`variantId` があるなら必ず true |
| `required_title_tokens`, `forbidden_title_tokens` | 型番（メーカー資料由来）と編集上の禁止語 | 可 | 商品名（itemName）から語を抜き出して足さない |
| `seller_shop_consistent` | seller_id と shop の比較 | 可 | — |
| `jan` | — | 対象外 | plan に持たない。メーカー資料で確認した JAN だけを別途の編集記録に置ける。API 由来の JAN は置かない |
| `itemName`, `shopName`, `itemUrl`（応答値） | API | **不可** | raw 応答（.secrets）にだけ残し、24 時間で purge |
| `itemPrice`, `itemPriceMin1/Max1/Min3/Max3` → `price_yen`, `reference_price.amount_yen` | API | **不可** | overlay のみ |
| `taxFlag` → `tax_included`、`postageFlag` → `postage_included` | API | **不可** | overlay のみ |
| `availability` → `state`（AVAILABLE / SOLD_OUT）、`status` | API | **不可** | 販売可能情報として overlay のみ。ハブページの販売状態（`hub_sales_record`）は git のカタログからしか描画しない |
| `observed_at`, `cache_expires_at`, `response_row_sha256` | API 取得に付随 | **不可** | overlay のみ。gate の漏出検査の目印にもなる |
| 注入後本文の `body_sha256`、注入後 runtime JSON の sha256、`KURASHINOSHIRUBE_PURCHASE_RUNTIME_SHA256`、テーマ fingerprint、`file_manifest_sha256` | 価格入りバイト列の hash | **不可** | 価格なし本文は公開されているので、候補価格を総当たりすれば hash から価格を復元できる。hash も価格と同じ扱いにする |
| `run_id`、承認の有無、purge 済みかどうか | 運用記録 | 可 | 証跡（KS-020.md など）に書いてよい。値・hash・時刻は書かない |

`validate_plan()` は plan に API 値のキー（`API_VALUE_KEYS`）があると拒否します。plan は git に置けます。

## 4. 実行単位と承認の記録

1 回の承認は、次の 1 組です。

1. `fetch`: 1 回
2. 注入した本文の公開: 1 回
3. 期限前の purge 公開: 1 回

- 記録は `.secrets/rakuten-price-refresh/<run_id>/approval.v1.json`（`RAOS_RAKUTEN_PRICE_REFRESH_APPROVAL_V1`）です。
- 作成
  - `fetch --owner-approved-run <run_id>` が、**通信の前に**作ります。
  - 記録する項目: `plan_sha256`、`approved_at`、`fetch_deadline`（= approved_at + 24h）、`scope=["fetch","publish","purge_publish_before_expiry"]`。
- `run_id` の規則
  - 形式は `[a-z0-9][a-z0-9-]{7,63}`。
  - 既存の run ディレクトリがあれば `RUN_ALREADY_EXISTS` で拒否します（承認の使い回しを防ぐ）。
- 公開時: publisher が `record_publish()` で `publish` を 1 回だけ書きます。
  - 書く内容: candidate_id、article_keys、注入後本文の sha256、runtime sha256、`purge_publish_due_by` = overlay の `cache_expires_at`。
  - 2 回目は `APPROVAL_PUBLISH_ALREADY_USED`、残りが 2 時間未満なら `OVERLAY_VALUE_EXPIRING` です。
- purge 公開時: `record_purge_publish()` で `purge_publish` を 1 回だけ書き、期限前に済んだかを `before_expiry` に残します。
- `purge-expired` は、公開の記録から注入後の hash を消します（`redact_approval()`）。

## 5. コマンドと応答の判定

```
plan          --catalog <catalog.json> --output <plan.json>                        # オフライン
fetch         --owner-checkout /home/minami/rakuten --plan <plan.json> --owner-approved-run <run_id> [--max-requests 60]
apply         --owner-checkout /home/minami/rakuten --run-id <run_id> --plan <plan.json> [--now ISO]
gate          --owner-checkout /home/minami/rakuten --run-id <run_id> --repository <worktree> --body <key>=<path> ... [--now ISO]
purge-expired --owner-checkout /home/minami/rakuten [--run-id <run_id>] [--include-unexpired] [--now ISO]
```

- **認証**
  - 読むのは `.secrets/rakuten-owner-local/credentials.v1.json` だけです（所有者本人、0600、4KB 以下、`profile=OWNER_LOCAL_RAKUTEN_PRODUCTION_API`）。
  - 使うキーは `application_id` / `access_key` です。`affiliate_id` は使いません。
  - 値は標準出力・エラー・例外文・repr のどこにも出しません。
- **fetch の安全策**
  - TLS 1.2 以上、証明書とホスト名を検証します。
  - リダイレクト（3xx か Location ヘッダー）は中止します。
  - 本文は 4MB を上限にします。
  - 応答本文かヘッダーに認証値（URL エンコード形を含む）が現れたら中止します。
  - 要求の間隔は 1.1 秒以上です。
  - 200 以外の応答本文は保存しません。
- **保存先の検査**: 書き込み先ごとに `git check-ignore` で ignore 済みか、`git ls-files` で未追跡かを確かめ、満たさなければ `PRIVATE_PATH_NOT_GIT_IGNORED` で拒否します。
- **出力**: 件数、状態別の集計、offer_id、期限だけです。価格は出しません。
- **`--now`**: 時計を先へ進めることにだけ使えます（実際の時刻との大きい方を採用）。過去の時刻を渡して期限検査を避けることはできません。
- **期限切れ run の放置防止**: 期限を過ぎて purge されていない run（記録が壊れて期限が読めない run を含む）があると、`fetch` は `EXPIRED_RUN_NOT_PURGED` で拒否し、`gate` も同じ code で拒否します。定期実行はしないため、これが 24 時間の保持上限を運用で守らせる仕組みです。

判定（`classify_observation()`。上から順に評価します）:

| 条件 | status | price / tax | state | CTA |
| --- | --- | --- | --- | --- |
| HTTP 400 | 実行中止 `RAKUTEN_WRONG_PARAMETER` | — | — | — |
| HTTP 401 / 403 | 実行中止 `RAKUTEN_AUTH_REJECTED` | — | — | — |
| HTTP 404、または 200 で items が 0 件 | `NOT_FOUND_PENDING` | なし | UNKNOWN | 変更しない（identity_verified もそのまま。再照合キューへ） |
| HTTP 429 / 5xx / 通信失敗 / 本文の不正 | `REQUEST_FAILED` | なし | 書かない | 変更しない |
| items が 2 件以上、itemCode・shopCode・canonical itemUrl・必須トークン・禁止トークンのどれかが不一致、seller_id が URL の店舗と一致しない（`SELLER_SHOP_INCONSISTENT`）、または title の色が編集上の色と別の色だけ（`TITLE_COLOR_CONFLICT`） | `IDENTITY_MISMATCH` | なし | 書かない | 注入では変えない。**CTA（class なしのリンクを含む）が残る本文は gate で拒否** |
| `multi_sku=true`、title が他の色も並べる（`TITLE_LISTS_OTHER_COLORS`）、全N色・カラー選択など（`TITLE_MULTI_VARIANT`）、×2・2台組など（`TITLE_QUANTITY_PACK`）、または `itemPriceMin3 == itemPriceMax3 == itemPrice` と `itemPriceMin1 == itemPriceMax1 == itemPrice` のどちらかを満たさない | `MULTI_SKU_NO_PRICE` | なし | UNKNOWN | 変更しない |
| `availability == 0` | `SOLD_OUT` | なし | SOLD_OUT | 変更しない（§10.1-5） |
| それ以外 | `MATCHED` | `price_yen=itemPrice`、`tax_included=(taxFlag==0)`、`postage_included=(postageFlag==0)` | AVAILABLE | 変更しない |

- `MATCHED` かつ `taxFlag==0` で、variant_id がある場合だけ `reference_price`（`RAOS_REFERENCE_PRICE_V1`）を overlay 内に作ります。
  - `evidence_sha256=response_row_sha256`
  - `checked_at=observed_at`
  - `valid_until=cache_expires_at`
- **識別の補足**（API に SKU フィールドが無いため、上の表の判定は title と価格幅からの推定です）
  - 型番トークンの `+` は区切りでなく型番の一部です。`K11+ Pro` は `K11 Pro` に、`SYN-100A` は `SYN-100A+` に一致しません。
  - 数字だけで 5 桁未満、または英数字 4 文字未満のトークンは弱すぎるため、plan で `TITLE_TOKEN_TOO_WEAK` として除外し、`validate_plan` も `PLAN_TITLE_TOKEN_WEAK` で拒否します。
  - 色は片仮名・英単語・白/黒の単独語だけを title から拾います（`グレード`・`ブラックフライデー`・`面白い` は色にしません）。
  - 残る限界: 同じ価格の色違いを 1 ページで売り、title に色を書かない店舗は検出できません。`(W)` のような色記号だけの違いも拾いません。editor が単一 SKU と確かめた offer 以外は `multi_sku=true` にしてください。
- overlay の各 entry は plan の `item_url`（編集上の値）を持ちます。gate は、値を持つ offer の CTA が同じ商品ページ（直接 URL か `hb.afl` の `pc`）を指すことを確かめます。
- すべての entry で `cache_expires_at = observed_at + 24h`（`validate_overlay()` は 24 時間を超える窓を拒否）。
- `apply` は、観測から 24 時間以上たった raw を拒否します（`OBSERVATION_OUTSIDE_CACHE_WINDOW`）。承認時と異なる plan も拒否します（`APPROVAL_PLAN_MISMATCH`）。

## 6. publisher の注入手順（`inject_body()` が参照実装）

注入は、`prepare` が checkpoint を作り `CHECKPOINT_SOURCE_MISMATCH` の検査を通した**後**に行います。

- `sources`、`source_sha256`、checkpoint の commit には、git の価格なしバイト列だけを入れます。
- 注入後の本文・runtime・テーマは candidate ディレクトリ（`.secrets/wordpress-mcp/owner-direct-v1/<candidate_id>/`）の中にだけ置きます。

### 6.1 販売先パネル `<div class="ps-seller" data-ps-offer="<offer_id>" ...>`

overlay に値を持つ entry（`carries_values()`: price / tax / state / reference のどれかが非 null）ごとに、同じ offer_id を持つすべての開始タグへ次を設定します。

| 属性 | 値 | 条件 |
| --- | --- | --- |
| `data-ps-checked-at` | `observed_at` | 常に |
| `data-ps-valid-until` | `cache_expires_at` | 常に |
| `data-ps-state` | overlay の `state` | 常に |
| `data-ps-purchasability-state` | overlay の `state` | 属性がある場合（normalization 有効な記事） |
| `data-ps-price-yen` | `price_yen` | MATCHED のみ。**価格なし本文に既にあれば `BODY_PRICE_CONFLICT` で中止** |
| `data-ps-tax-included` | `true` / `false` | MATCHED のみ |
| `data-ps-price-source` | `<API_VERSION_ID>`（`rakuten_ws_item_search_` に版の日付） | 常に |
| `data-ps-overlay-run` | `<run_id>` | 常に |

- 同じブロック内の `<p class="ps-price-date">販売条件確認：<time datetime="…">…</time>` は、`datetime` を `observed_at` に、表示を「YYYY年M月D日 HH:MM（日本時間）」に置き換えます。RWS の「更新日時を隣接表示」を満たすためで、見つからなければ `BODY_PRICE_DATE_MISSING` で中止します。
- `data-ps-price-state` は変えません。静的 HTML は CURRENT を出さず、閲覧時の時計（theme JS）が `min(valid_until, checked_at + 24h)` で判定します。
- **読める金額は静的 HTML に書きません。** 金額の文字列は、JS が有効期限内に限り表示します。
- CTA（`<a class="ps-offer-link">`）とリンク系の属性は変えません。
- `data-ps-tax-included` の表示分けは、バッチ G の JS 変更が前提です。それまでの JS は `price_yen` を「本体税込」と表示するので、**税別（false）の offer を含む overlay は、G の merge まで公開しません**。

### 6.2 参考価格 `<p class="ps-reference-price" role="status">`

- overlay に `reference_price` がある offer だけが対象です。次のどちらかの位置に、`data-ps-reference-price="<canonical JSON を HTML エスケープ>"` と `data-ps-overlay-run="<run_id>"` を付けます。
  1. 明示の目印: `data-ps-reference-offer="<offer_id>"` を持つ placeholder（バッチ G で renderer に追加する推奨形）。
  2. 現行の比較行: `価格は販売先で確認</p>` の直後に、`<p><a class="ps-offer-link" … data-raos-offer-id="<offer_id>"` が続く placeholder。
- canonical JSON は `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))` で、purchase-support の `canonical()` と同じです。
- JSON は `raos.domain.editorial.purchase_support.reference_price()` と theme JS の `referencePricePresentation()` の検査を通る形です（テストで確認済み）。
- 既に `data-ps-reference-price`（手動観測）を持つ placeholder には注入しません。

### 6.3 注入しないもの

- `IDENTITY_MISMATCH` と `REQUEST_FAILED` の offer（値を持たない）
- 本文の自由文、ハブページ（`build_site_editorial_pages.py` の出力）、og / JSON-LD、抜粋
- 二重注入: 注入済みの目印がある本文は `BODY_ALREADY_INJECTED` で拒否します。

## 7. 注入後の hash の再計算

1. **本文**: `body_sha256 = sha256(injected_body.encode("utf-8"))`。build の `sha256(outputs[slug].encode())`、および `inc/purchase-support.php` の `hash('sha256', $snapshot['block_markup'])` と同じです。
2. **runtime JSON**: `inject_runtime(git_runtime_bytes, {slug: injected_body})`
   - 入力が `json.dumps(runtime, ensure_ascii=False, indent=2) + "\n"` と一致しなければ `RUNTIME_NOT_CANONICAL` で拒否します（リポジトリの実ファイルで round-trip を確認済み）。
   - 注入した slug の `body_sha256` だけを置き換え、同じ直列化で再出力します。戻り値は `(bytes, sha256)` です。
   - 注入しない記事の `body_sha256` は git の値のままです。20 件の上限で分けて公開する場合も、runtime は全記事分を 1 つにまとめて束縛します（§2.2）。
3. **PHP 定数**: `rebind_runtime_constant(functions_php, runtime_sha256)` で `const KURASHINOSHIRUBE_PURCHASE_RUNTIME_SHA256 = '<hex>';` をちょうど 1 か所だけ置き換えます。
4. **テーマの fingerprint**: `build_st1704_self_hosted_theme.py` の `_fingerprint_from_payloads()` は `assets/purchase-support.v1.json` と `functions.php` を入力に含みます。注入後の payload で `KURASHINOSHIRUBE_THEME_SOURCE_FINGERPRINT` と `KURASHINOSHIRUBE_THEME_RUNTIME_REVISION` を計算し直します（あの生成器が正規化するのはこの 2 定数だけ）。
5. **パッケージ**: `package_theme(root, paths, commit, payloads)` に、注入後の runtime と functions.php を差し替えた `payloads` を渡します。
   - `theme.zip` と `descriptor.file_manifest_sha256` は candidate ディレクトリにだけ置きます。
   - `sources` / `source_sha256` は git のバイト列のままです。
6. **candidate と照合**
   - `articles[i].document.block_markup` は注入後の本文です。
   - `candidate_id = sha256(encoded(candidate))`、`content_after_sha256(document, post_id)`、proposal の `after_sha256` はすべて注入後の document から計算します。
   - `readback()` は注入後の document と、注入後の `file_manifest_sha256`（`THEME_READBACK_MISMATCH`）で照合します。
7. **git に書かないもの**: 上の 1〜6 の値（価格入りバイト列の hash）はすべて、journal と candidate（.secrets 内）にだけ置きます。`sync_git()` が push するのは checkpoint の commit（価格なしのソース）だけです。

## 8. 公開と purge の順序

1. `plan` → Before/After 用の差分を確認する（値は .secrets の overlay から読み、画面キャプチャを git に置かない）。
2. オーナーが `<run_id>` を承認する → `fetch --owner-approved-run <run_id>` → `apply`
3. `build_reader_purchase_support_v1.py` など、git の価格なしソースを生成して `--check` → `prepare --articles … --theme`（checkpoint は価格なし）
4. `gate` → 注入 → §7 の再計算 → preview → `publish` → readback → `record_publish()`
   - gate は公開の直前に実行します。
   - 公開と readback は、残り 2 時間より前に終えます。
5. **purge 公開**
   - 価格なしの本文と、git の runtime / テーマ（checkpoint のバイト列そのもの）で、同じ記事キーを `prepare --theme` → `publish` します。
   - 開始期限は `purge_publish_due_by` の 2 時間前です。
   - readback 後、公開本文に対して `price_free_violations(body, overlay)` が空であることを確認し、`record_purge_publish()` を書きます。
   - purge 公開には新しい承認を要りません（同じ `<run_id>` の範囲）。値を持たないので gate の期限検査は対象外です。
6. `purge-expired --run-id <run_id>`
   - `--include-unexpired` を付けると、purge 公開の直後に期限を待たず消せます。
   - raw 応答を削除し、overlay を `RAOS_RAKUTEN_PRICE_OVERLAY_PURGED_V1`（offer_id と purged_at だけ）に置き換え、承認記録から注入後の hash（candidate_id、本文、runtime）を消します。
   - overlay や承認記録が壊れていて期限が読めない run は、期限を待たずに消します（保持は安全側に倒す）。
   - **publisher 組み込みの必須条件**: candidate ディレクトリ（`.secrets/wordpress-mcp/owner-direct-v1/<candidate_id>/`）の注入後本文・runtime・theme.zip・manifest、および journal に残る注入後の hash も、同じ期限までに削除または `PURGED` に置き換えます。この CLI はまだそれらを消しません。
   - 引数なしの `purge-expired` は、期限を過ぎた全 run を掃除します。
7. 公開後の確認
   - ブラウザで JS を実行した後の状態を照合します（静的 HTML の `data-ps-price-state` は CURRENT にならない）。
   - WordPress のリビジョンとページキャッシュに注入本文が残らないかを確認します。**これは初回の実値公開の前提条件です**（未実測）。リビジョンが残る設定なら、purge 公開と同じ期限までに注入本文のリビジョンを削除する手順を先に用意し、用意できるまで値を公開しません。

## 9. gate の拒否条件（`gate()`）

| code | 内容 |
| --- | --- |
| `OVERLAY_INVALID` | 構造の不正、24 時間を超える窓、状態と値の組の不整合 |
| `OVERLAY_VALUE_EXPIRING` | 値を持つ entry の残りが 2 時間未満 |
| `OVERLAY_VALUE_OLDER_THAN_24H` / `OVERLAY_OBSERVED_IN_FUTURE` | 観測から 24 時間を超えた / 観測時刻が未来 |
| `TAX_INCLUDED_MISSING` | `price_yen` があるのに `tax_included` が bool でない |
| `IDENTITY_MISMATCH_WITH_CTA` | IDENTITY_MISMATCH の offer に、送る本文の `ps-offer-link` CTA、または同じ商品ページへのリンクが残っている |
| `CTA_TARGET_MISMATCH` / `CTA_TARGET_UNVERIFIED` | 値を持つ offer の CTA が overlay の `item_url` 以外を指す / 本文にその offer の CTA が無く照合できない（plan 作成後のカタログ変更対策） |
| `TAX_EXCLUDED_PRICE_UNSUPPORTED` | `tax_included=false` の価格。テーマが税別表示を区別できるまで（バッチ G）は公開しない |
| `GIT_TRACKED_OVERLAY_VALUE` | tracked file（作業ツリーと index）か、ignore されていない未追跡ファイルに overlay の値がある（下記） |
| `BODY_NOT_PRICE_FREE` / `BODY_ALREADY_INJECTED` | 送る本文が価格なしでない / 注入済み |
| `RAKUTEN_CREDIT_MISSING` | 値を注入する本文の `ps-media-credit` 段落に、`https://developers.rakuten.com/` への「Supported by Rakuten Developers」リンクが無い |
| `RAKUTEN_PRICE_DISCLAIMER_MISSING` | 値を注入する販売先ブロックの `ps-price-date` 段落（または本文全体）に免責文へのリンクが無い（§2.1） |
| `EXPIRED_RUN_NOT_PURGED` | 別の run が期限切れのまま purge されていない |
| `APPROVAL_MISSING` / `APPROVAL_RUN_MISMATCH` / `APPROVAL_PLAN_MISMATCH` / `APPROVAL_PUBLISH_ALREADY_USED` | 承認の 1 組が無い / 一致しない / 公開済み |
| `BODIES_REQUIRED` | 本文が 1 件も渡されていない |

漏出の走査（`scan_repository_for_overlay()`）は、`--owner-checkout`（publisher が commit する場所）と `--repository` の両方に対して、`git grep --untracked`、`git grep --cached`、およびどの remote にも無い commit（`git rev-list HEAD --not --remotes`、完全一致のみ）で次を探します。

- **完全一致**
  - `data-ps-overlay-run="<run_id>"`
  - 値を持つ entry の `observed_at` / `cache_expires_at` / `response_row_sha256`
  - 公開記録に残る candidate_id・注入後本文・runtime の sha256（`status.v1.json` など tracked の記録に candidate_id を書く既存の運用があるため、値を注入した公開の candidate_id は git に書かない）
- **文脈一致**（候補価格の数字だけでは誤検出するため、場所を限定する）
  - 同じ `data-ps-offer` の販売先タグにある `data-ps-price-yen="<price_yen>"`
  - JSON 内で同じ `offer_id` を持つオブジェクトの `price_yen`

## 10. 未解決・公開前に必要なこと

2026-09-15 のレビュー（RWS 適合と保持、識別の安全、テスト品質の 3 観点）で出た major のうち、コードとテストで直したものは §5・§8・§9 に反映済みです。ここに書くのは、コードで直していない設計上の限界と、初回の実値公開までに必要な作業です。

### 10.1 公開前に必要なこと（満たすまで値を公開しない）

1. **publisher 組み込み**: `prepare` / `publish` への組み込み（§6〜§8）は未実装です。それまで `fetch` は実行できますが、公開はできません。
2. **candidate ディレクトリと journal の purge**
   - `purge-expired` が消すのは、`.secrets/rakuten-price-refresh/<run_id>/` の raw 応答と overlay、承認記録の注入後 hash だけです。
   - candidate ディレクトリ（`.secrets/wordpress-mcp/owner-direct-v1/<candidate_id>/`）の注入後本文・runtime・theme.zip・manifest と、journal に残る注入後 hash は消しません。
   - 同じ期限までに削除するか `PURGED` に置き換える処理を、publisher 組み込みで実装します（§8-6）。
3. **WordPress のリビジョンとページキャッシュ**
   - purge 公開の後も注入本文が残るかは、未実測です。
   - 実測し、残る設定なら同じ期限までに消す手順を先に用意します（§8-7）。
4. **税別価格の表示（theme JS）**
   - 現行の JS は `price_yen` を「本体税込」と表示します。
   - `data-ps-tax-included` の表示分けが入るまで、gate は税別価格を `TAX_EXCLUDED_PRICE_UNSUPPORTED` で拒否します。
   - JS の表示分けと、renderer の `data-ps-reference-offer` 目印（§6.2）は、どちらも未実装です。
5. **SOLD_OUT と CTA**
   - 注入は CTA を消しません。現行の renderer は SOLD_OUT の offer に CTA を出さないので、注入した本文と食い違います。
   - 「JS が売り切れ表示中の CTA を補助表示にする」か「gate に `SOLD_OUT_WITH_CTA` を足す」かを決めます。
   - 現状はどちらも未実装で、gate は SOLD_OUT の offer に残る CTA を拒否しません。
6. **`multi_sku=false` の offer の単一 SKU 確認**
   - API に SKU 単位の出力が無いため、§5 の判定は title と価格幅からの推定です。次の 2 つは MATCHED になり、別の色の価格や販売可能情報が付きえます。
     - 同じ価格の色違いを 1 ページで売り、title に色を書かない（または編集上の色だけを書く）商品ページ
     - `(W)` / `(K)` のような括弧内の色記号だけの違い。`_model_tokens()` が型番の括弧部分を落とすため、`SYN-100A(W)` の plan は title `シンセ SYN-100A(K)` にも一致します。
   - 初回 fetch の承認前に、plan で `multi_sku=false` の各 offer が単一 SKU ページかを編集者が確かめます。確かめられないものは `true` にします。
7. **漏出走査の範囲**
   - `scan_repository_for_overlay()` が見るのは、`--owner-checkout` と `--repository` の次の範囲だけです。
     - 作業ツリー（ignore されていない未追跡ファイルを含む）
     - index
     - `HEAD` から辿れて、どの remote にも無い commit
   - 次は走査しません。ここに漏出があると、別の操作で push されえます。
     - `HEAD` 以外のローカル branch、`refs/stash`、reflog
     - 上の 2 つ以外の clone・worktree
     - ignore 済みのファイル
   - `--owner-checkout` は `/home/minami/rakuten` に固定していません。要求するのは、絶対パス・symlink でない・`.secrets` ディレクトリを持つ checkout であることだけです。
   - 文脈一致の限界は §10.2-1 を見てください。
8. **`hits=1` の曖昧さ**
   - 要求は `hits=1` なので、応答の行は 1 件までです。`classify_observation()` の `MULTIPLE_ROWS`（items が 1 件でない）は、実際には発火しません。
   - 同じ itemCode に複数の行があっても検出できません。`hits=2` にして `MULTIPLE_ROWS` を生かすかは未判断です。
9. **標準出力と証跡**
   - `apply` の出力には、`status_counts`（SOLD_OUT などの状態別件数）と `purge_publish_due_by` が含まれます。価格は出しません。
   - 対象の offer が 1 件だと、件数から販売可能情報が分かります。
   - 証跡（KS-020.md など）には、run_id と結果コードだけを写します。
10. **テストの穴（minor）**: 次の 2 つには専用テストがありません。
    - gate 側の `EXPIRED_RUN_NOT_PURGED`（fetch 側はテスト済み）
    - `.secrets/rakuten-price-refresh` 経路の symlink 拒否

### 10.2 前提と既知の限界

1. **文脈一致の限界**
   - 文脈一致は `price_yen` だけを見ます。カタログの `reference_price.amount_yen` や `state` へ API 値を書き写し、時刻も書き換えた場合は検出できません（手動観測の値と区別できないため）。レビューで防ぎます。
   - 逆に、tracked のカタログにある手動観測の `price_yen` が API 値と同じ金額だと、`PRICE_JSON_FIELD` で gate が拒否します（安全側の誤検出）。
2. **楽天 offer の条件**: 楽天 offer の多くは `condition=UNKNOWN` です。MATCHED でも販売先欄に金額は出ず、出るのは参考価格だけです。
3. **RWS ヘルプ 900001974343**
   - HTML を匿名で取得すると 403 でした。
   - 本文は Help Center API から取得しました（§2 の表）。24 時間・3 か月・週 1 回刷新の条文は、KS-006 #8 の記録と一致しています。
4. **初期値の multi_sku 判定**
   - 根拠: variantId、共通販売ページの文言、色コード、複数型番、商品 ID と異なる SKU ID。
   - 安全側に倒した結果、実カタログの多くの offer は価格を上書きしません。
   - 個別に単一 SKU と確かめた場合だけ、plan を編集して false にします（variantId 付きは不可、§10.1-6）。
5. **クレジット表示**: 既存の表示とガイドの snippet の差は、§2.1 の「未解決」のとおりオーナー判断です。この契約では変えません。
