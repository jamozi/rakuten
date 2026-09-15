# 楽天価格の再取得: owner-private overlay と publisher 注入の契約（KS-020 / KS-304）

- 対象コード
  - domain: `python/raos/domain/editorial/rakuten_price_refresh.py`（純関数。ファイル・通信・時計・認証値に触れない）
  - adapter: `python/raos/adapters/rakuten_price_refresh_client.py`（唯一の通信、認証ファイルの読み取り、0600 の保存、tracked file の走査）
  - CLI: `scripts/raos_rakuten_price_refresh.py`（`plan` / `fetch` / `apply` / `gate` / `purge-expired` / `resolve-incident`）
  - publisher 組み込み: `scripts/raos_wordpress_price_overlay.py`（`scripts/raos_wordpress_direct_publish.py` の `prepare` / `publish` に明示の `--price-overlay-run` / `--price-overlay-purge` を足す）
  - WordPress plugin 側の保存の redact: `changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/includes/class-raos-codex-mcp-owner-direct.php` の `redact_price_overlay_copies()`（§10.1-3。ソースのみ、未デプロイ）
  - テスト: `tests/purchase_support/test_rakuten_price_refresh.py`、`tests/purchase_support/test_rakuten_price_overlay_publish.py`、`tests/wordpress_mcp_v1/php/owner_direct_overlay_redaction_harness.php`（fixture はすべて合成値。WordPress は offline の fake、plugin は PHP の shim）
- 現状（2026-09-16、バッチ G）: publisher への組み込み（§6〜§8）、candidate ディレクトリの purge、テーマの税別表示、`SOLD_OUT_WITH_CTA`、plugin 側の保存の redact（ソース。本文の行・undo option・テーマ release 行）、値が残る限り run を解除しない判定（§5）、値の配信中（owner checkout を基準に判定）のフラグ無し prepare / publish / 状態表示の拒否（§8）を実装しました。**初回の実値公開の前提条件として §10.1-3（plugin のデプロイ、WordPress のリビジョンとページキャッシュの実測、preview のデータベースの後始末、plugin に残る hash についてのオーナー決定 §1-5）が残っています。**それを満たすまで値を公開しません。
- フラグを付けない `prepare` / `publish` の挙動は、値の配信中でなければ変わりません（配信中の拒否は §8）。
  - テスト `test_flag_free_prepare_and_publish_match_the_pre_batch_g_publisher` は、バッチ G 直前の main の commit `2fac0278b3b64b46545389c083f3fcedaf5e0199`（#289）から `git archive` で取り出した publisher と、作業ツリーの publisher に同じ fixture で prepare・publish させます。candidate.json、candidate ディレクトリ、WordPress への呼び出し、journal、標準出力が一致することを確かめます。
  - origin/main ではなく commit を固定する理由: バッチ G を merge すると origin/main 自身がフラグを持つので、比較が自分自身との比較になり、「バッチ G 以前である」ことの検査も main で失敗するためです。
  - その commit が無い clone では、shallow clone なら skip、それ以外は失敗にします（CI は fetch-depth 0）。

## 1. オーナー決定（計画より優先）

1. 楽天 API の価格・販売可能情報は、git 管理のファイルに書かず、push もしません。git の本文とカタログは価格なしのまま保ちます。
2. API 値は owner checkout の `.secrets/rakuten-price-refresh/<run_id>/` に置きます（ディレクトリ 0700、ファイル 0600、git 管理外）。`observed_at` と `cache_expires_at`（24 時間以内）を必ず付けます。カタログへ反映する promote 段はありません。
3. publisher は WordPress へ送る直前に overlay を本文へ注入し、期限前に価格なしの本文を送り直して消します（purge 公開）。
4. オーナーの 1 回の承認で「fetch・公開・期限前の purge 公開」を 1 組として行います。定期実行と自動公開はしません。
5. **OWNER DECISION REQUIRED（未決定）**: sha256 hashes of injected documents/themes remain in plugin proposal rows and undo options after purge; either the owner accepts this (hashes are not prices, but can be brute-forced) or a row/option deletion step must be designed before the first real publish.
   - 残る場所: proposal 行の `before_sha256` / `after_sha256` 列（本文行・テーマ release 行）、本文行の payload の `block_markup: sha256:<注入本文の sha256>` と `price_overlay_redaction.sides.*.block_markup_sha256`、undo option の `applied_document.content_sha256` など（§10.1-3）。
   - 決まるまで値を公開しません（§10.1-3 の残る作業 4）。WordPress DB の hash 列を残す設計は変えていません。`run_status()`（§5）はこの項目を理由に解除も判定の変更もしません。

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

- 同じ理由で、price-recoverable な hash は標準出力にも出しません（端末やエージェントの記録は 24 時間を超えて残るため）。
  - price overlay の candidate は handle で名指しします（§8）。
  - 値の配信中（§8。owner checkout か ROOT に、公開の記録があり purge 公開もオーナーの incident 記録も無い run、または承認記録が読めない run がある間）は、`status`（`--candidate` なし）が WordPress を呼ばず `{"price_overlay_live": [<run_id>...], "status": "REDACTED_PRICE_OVERLAY_LIVE"}` だけを出します。
    - フラグ無し candidate の `status --candidate` は、64 桁 hex を含む文字列と `runtime_revision` / `plugin_runtime_revision` を、どの深さでも `REDACTED_PRICE_OVERLAY_LIVE` に置き換えます（`theme` 配下を含む）。
    - deployment operator の CLI と MCP bridge、編集用 MCP（`wordpressEditor`）の launcher、公開ページの readback、匿名の監査・ブラウザ計測も、WordPress に届く操作をすべて拒否します（§8 の表）。
  - 同じ間、フラグを付けない `prepare` を拒否します（§8。baseline に配信中の注入本文や注入テーマの tree hash が入り、id とディレクトリを出力するため）。
- WordPress 側では、owner-direct plugin がテーマ release 行の payload にある注入テーマの hash を伏せます（§10.1-3）。行の `before_sha256` / `after_sha256` 列には残ります。purge 後も残る hash の扱いはオーナー決定待ちです（§1-5）。

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
  - 書く時点: gate と注入の再導出を通した後、**WordPress への最初の書き込みの直前**（予約）。書き込みが失敗して rollback されても、承認は使用済みです（別の candidate での再公開は新しい承認が要ります）。同じ candidate の再開（resume）は通します。
  - 書く内容: candidate_id、article_keys、注入後本文の sha256、runtime sha256、`purge_publish_due_by` = overlay の `cache_expires_at`、git の `source_sha256`、`readback_verified_at`（readback と注入後 hash の照合が通った時刻。通るまで null）。
  - 2 回目は `APPROVAL_PUBLISH_ALREADY_USED`、残りが 2 時間未満なら `OVERLAY_VALUE_EXPIRING` です。publisher は、使用済みの承認を WordPress への最初の呼び出しより前に拒否します。
- purge 公開時: `record_purge_publish()` で `purge_publish` を 1 回だけ書き、期限前に済んだかを `before_expiry` に残します。publisher は purge 用 candidate の元になった価格なし candidate の id（`base_candidate_id`）も書きます（live の注入後本文を baseline に持つため、価格と同じ扱い）。
  - `wordpress_redaction`: batch の finalize で plugin が返した保存の redact の結果（`COMPLETE` / `INCOMPLETE`。返さない plugin では `NOT_REPORTED`）。§10.1-3 の確認に使います。
  - purge 公開が readback・記録・git 同期まで済むと、publisher は purge 用 candidate のディレクトリを削除し、`sweep_local_copies()`（§5）でこの run のローカル複製をすべて消してから、`redact_purge_candidates()` で `purge_publish.candidate_id`・`base_candidate_id`・`prepared_candidates.PURGE` を `PURGED` にします（`purge-expired` が先に走っていた場合も同じ）。
- `prepared_candidates`（任意）: `prepare` が作った candidate の id を `PUBLISH` / `PURGE` ごとに書きます。publisher は id を出力せず、`price-overlay:<run_id>:publish|purge` の handle を出し、`preview` / `publish` / `status` / `sync` の `--candidate` はこの handle をここから引きます（§8）。
- `purge-expired` は、公開の記録から注入後の hash を消します（`redact_approval()`。`purge_publish.candidate_id`・`base_candidate_id`・`prepared_candidates` の id も `PURGED` にします）。
- `incident-resolution.v1.json`（`resolve-incident`）と `plugin-cleanup.v1.json`（`resolve-incident` / `confirm-plugin-cleanup`）は、値も hash も持ちません。run_id・結果の種類・確認文・時刻だけを 0600 で書きます。

## 5. コマンドと応答の判定

```
plan          --catalog <catalog.json> --output <plan.json>                        # オフライン
fetch         --owner-checkout /home/minami/rakuten --plan <plan.json> --owner-approved-run <run_id> [--max-requests 60]
apply         --owner-checkout /home/minami/rakuten --run-id <run_id> --plan <plan.json> [--now ISO]
gate          --owner-checkout /home/minami/rakuten --run-id <run_id> --repository <worktree> --body <key>=<path> ... [--now ISO]
purge-expired --owner-checkout /home/minami/rakuten [--run-id <run_id>] [--include-unexpired] [--now ISO]
resolve-incident --owner-checkout /home/minami/rakuten --run-id <run_id> --owner-confirmed-price-free <run_id> --owner-confirmed-plugin-cleanup PLUGIN_COPIES_REMOVED:<run_id> --resolution WORDPRESS_RESTORED_OUTSIDE_PUBLISHER|WORDPRESS_POSTS_WITHDRAWN [--now ISO]   # オーナーだけが使う
confirm-plugin-cleanup --owner-checkout /home/minami/rakuten --run-id <run_id> --owner-confirmed-plugin-cleanup PLUGIN_COPIES_REMOVED:<run_id> [--now ISO]   # オーナーだけが使う
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
- **書き込みの途中で止まった場合**: 置き換え書き込みは `<file>.tmp` を作ってから rename します。`.tmp` が残っていると、次の置き換え書き込みは次のように扱います。
  - 60 秒（`STALE_TMP_SECONDS`）より新しい: 並行する書き込みの可能性があるので `PRIVATE_TMP_BUSY` で拒否します（時間をおいた再実行で解消）。
  - それより古い、所有者本人の 0600 の通常ファイル: 中断の残りとして削除してから書きます。注入後の hash を持ちうるので、rename で採用はしません。
  - symlink、通常ファイルでない、mode や所有者が違う: `PRIVATE_PATH_UNSAFE`。
  - purge 済みの run のディレクトリに `.tmp` が残る間は `REDACTION_PENDING` です。`purge-expired` が古いものを削除します（`stale_tmp_files_deleted`）。
- **出力**: 件数、状態別の集計、offer_id、期限だけです。価格は出しません。
- **`--now`**: 時計を先へ進めることにだけ使えます（実際の時刻との大きい方を採用）。過去の時刻を渡して期限検査を避けることはできません。
- **期限切れ run の放置防止**: 期限を過ぎて purge されていない run（記録が壊れて期限が読めない run を含む）があると、`fetch` は `EXPIRED_RUN_NOT_PURGED` で拒否し、`gate` も同じ code で拒否します。定期実行はしないため、これが 24 時間の保持上限を運用で守らせる仕組みです。
  - ローカルの値を消した run で、承認記録（`approval.v1.json`）が無い・読めない（symlink、JSON でない、オブジェクトでない）場合は `UNDATED` です。承認記録は fetch の通信前に作られるので、無ければ公開と purge の義務を確かめられません。
  - `purge-expired` でローカルの値を消した run が purge 済み（`PURGED`）になるのは、次の**すべて**を満たすときだけです（`run_status()`、上から順に判定）。1 つでも欠ければ、`fetch` と `gate` は `EXPIRED_RUN_NOT_PURGED` で拒否を続けます。
    1. 公開の記録が無い、または purge 公開の記録かオーナーの incident 記録がある。欠ければ `PUBLISHED_NOT_PURGED`。
    2. 承認記録に price-recoverable な id・hash が残っていない。残れば `REDACTION_PENDING`。
    3. run ディレクトリに `.tmp` が残っていない。残れば `REDACTION_PENDING`。
    4. ローカル複製の走査（`local_copies()`）が何も見つけない。見つければ `REDACTION_PENDING`。
    5. 公開の記録がある run では、承認記録の `purge_publish.wordpress_redaction` が `COMPLETE`、またはオーナーの plugin 後始末の記録（`plugin-cleanup.v1.json`）がある。欠ければ `WORDPRESS_REDACTION_UNCONFIRMED`。
  - **ローカル複製の走査**（`sweep_local_copies()` が削除し、`local_copies()` が検出する）
    - 対象
      - owner checkout の `.secrets/wordpress-mcp/owner-direct-v1/<candidate_id>/` の全ファイル（`candidate.json` / `journal.json` / `preview.json` のほか `bodies/`・`theme/`・`*.tmp` など。一致すればディレクトリごと削除）と、承認記録にある id の candidate ディレクトリ（中身にかかわらず削除）
      - 同じ場所の `.staging-*`（注入 candidate の書き出しが中断して残るもの。記録に無い注入後の hash しか持たないことがあるので、中身にかかわらずディレクトリごと削除）
      - `.secrets/wordpress-direct-preview/` の凍結テーマ `theme-<tree>`（中の 1 ファイルでも一致すればディレクトリごと）と、`fixtures/` 以下のファイル
    - 探すもの: 承認記録にある candidate id、run の目印 `data-ps-overlay-run="<run_id>"`、値を持つ entry の観測時刻・期限・`response_row_sha256`、承認記録に残る注入後の hash（生の形と JSON エスケープ形）。
    - これで見つかる例: 値の公開中にフラグ無しで prepare した candidate（baseline に注入本文）、値を持つ preview の凍結テーマと fixture。
    - 注入テーマの凍結コピーは目印を持たず、注入後の hash でしか見つかりません。そのため `purge-expired`・purge 公開・`resolve-incident` は、承認記録の hash を redact する**前に**走査します。
    - candidate の置き場や preview ディレクトリ（またはその中の途中のパス）が symlink なら `PRIVATE_PATH_UNSAFE` で止まり、何も消しません（run は `UNDATED`）。`delete_preview_copy()` は `theme-*` 1 段か `fixtures/` 以下だけを受け付け、`..` を含むパスを拒否します。
    - 走査しないもの: `.secrets` 外のコピー、ほかの clone・worktree、preview のデータベース（§10.1-3）、上記以外の `.secrets` 内のファイル。worktree の `.secrets` へ複製が入る経路は、配信中のフラグ無し prepare / publish の拒否（§8、owner checkout を基準に判定）で塞いでいます。
  - `purge-expired` の報告（`result`）: `PURGED` / `ALREADY_PURGED` のほか、残っている条件に応じて `PURGE_PUBLISH_MISSING`（上の 1）、`REDACTION_PENDING`（2〜4。通常は同じ実行で解消）、`WORDPRESS_REDACTION_UNCONFIRMED`（5）、承認記録が無い・読めない `UNDATED` を返します。`candidate_directories_deleted`・`preview_copies_deleted`・`stale_tmp_files_deleted` も出します。
  - **`PUBLISHED_NOT_PURGED` の解除**は次のどちらかだけです。
    - purge 公開を記録する（期限後でも可。§8-5）。完了時に purge candidate・ローカル複製・id も消えます。
    - オーナーが `resolve-incident` で記録する。purge 公開はできないが、WordPress が値を配信していないことをオーナーが確かめた場合です（手作業で価格なしに戻した `WORDPRESS_RESTORED_OUTSIDE_PUBLISHER`、記事を非公開にした `WORDPRESS_POSTS_WITHDRAWN`）。
      - `--owner-confirmed-price-free` に同じ run_id が要ります（`OWNER_CONFIRMATION_REQUIRED`）。状態が `PUBLISHED_NOT_PURGED` の run にしか書けません（`INCIDENT_RESOLUTION_NOT_APPLICABLE`）。
      - plugin の redact は purge 公開の finalize でしか動きません。この経路では、plugin の proposal 行・undo option・テーマ release 行から注入本文と注入テーマの hash を手作業で消したうえで、`--owner-confirmed-plugin-cleanup PLUGIN_COPIES_REMOVED:<run_id>` をちょうどこの文で渡します（違えば `PLUGIN_CLEANUP_CONFIRMATION_REQUIRED`）。
      - 記録の前にローカル複製の走査（削除）を行い、なお残れば `LOCAL_COPIES_REMAIN` で記録しません。
      - 記録は `plugin-cleanup.v1.json`（理由 `INCIDENT_RESOLUTION`）と `incident-resolution.v1.json` です。どちらかが壊れていれば、run は `UNDATED` として拒否を続けます。
  - **`WORDPRESS_REDACTION_UNCONFIRMED` の解除**: purge 公開の finalize で plugin が `COMPLETE` を返さなかった（`INCOMPLETE` / `NOT_REPORTED`）run です。オーナーが plugin の保存（§10.1-3）を手作業で消し、`purge-expired` の後に `confirm-plugin-cleanup --owner-confirmed-plugin-cleanup PLUGIN_COPIES_REMOVED:<run_id>` で記録します。
    - この状態の run にしか書けません（`PLUGIN_CLEANUP_CONFIRMATION_NOT_APPLICABLE`）。確認文が違えば `PLUGIN_CLEANUP_CONFIRMATION_REQUIRED` です。
    - 記録の理由は `WORDPRESS_REDACTION_INCOMPLETE` / `WORDPRESS_REDACTION_NOT_REPORTED` です。
  - `REDACTION_PENDING` は通常残りません。残るのは、消す途中で止まった場合（ディレクトリ削除後、redact 前）や、purge 済みの run の複製が後から現れた場合で、次の `purge-expired` が削除し redact します。

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
- `data-ps-tax-included` の表示分け（バッチ G で実装）: theme の `purchase-support.js` は `data-ps-tax-included="false"` の価格を「本体税別：N円（税別のため小計・総額に含めません）」と表示し、「税込」とは書きません。小計・購入総額・予算判定には含めません（状態は `INCOMPLETE`、予算は `UNKNOWN`）。属性が無い既存の手動観測は従来どおり「本体税込」です。
- gate は、税別の価格を持つ overlay を、**送るテーマの `purchase-support.js` がこの表示分けを持つ場合だけ**通します（`theme_labels_tax_excluded()`。持たなければ `TAX_EXCLUDED_PRICE_UNSUPPORTED`）。

### 6.2 参考価格 `<p class="ps-reference-price" role="status">`

- overlay に `reference_price` がある offer だけが対象です。次のどちらかの位置に、`data-ps-reference-price="<canonical JSON を HTML エスケープ>"` と `data-ps-overlay-run="<run_id>"` を付けます。
  1. 明示の目印: `data-ps-reference-offer="<offer_id>"` を持つ placeholder。
  2. 現行の比較行: `価格は販売先で確認</p>` の直後に、`<p><a class="ps-offer-link" … data-raos-offer-id="<offer_id>"` が続く placeholder。
- バッチ G の判断: renderer に 1 の目印は**追加しません**（静的出力は不変）。2 の隣接形で注入先が一意に決まり、隣接しない placeholder には注入しない（価格なしのまま）ので、目印は必須ではありません。2026-09-16 時点の `wordpress-direct-publish-v1/articles` では、参考価格の placeholder はすべて手動観測の `data-ps-reference-price` を持つか、比較行で CTA に隣接しています。
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
4. **テーマの fingerprint**: `build_st1704_self_hosted_theme.py` の `_fingerprint_from_payloads()` は `assets/purchase-support.v1.json` と `functions.php` を入力に含みます。注入後の payload で revision を計算し直し、生成器（`render_theme_stamp_payloads()`）が同じ値を書くテーマ内の場所をすべて置き換えます: `functions.php` の `KURASHINOSHIRUBE_THEME_RUNTIME_REVISION` と `KURASHINOSHIRUBE_THEME_SOURCE_FINGERPRINT`、`assets/theme.css` と `assets/editorial-v2.css` の revision sentinel、`raos-assets.v1.json` の `theme_runtime_revision` / `theme_source_fingerprint`、`theme-contract.v1.json` の `runtime_evidence.revision` / `source_fingerprint`。
   - 前提の検査: git 側で、注入する slug の runtime `body_sha256` が価格なし本文と一致し（`RUNTIME_BODY_UNBOUND`）、`PHP_INTEGRITY_BINDINGS` の定数がすべて payload と一致し（`THEME_BINDING_STALE`）、revision が fingerprint と一致すること（`THEME_STAMP_STALE`）。置換後に旧 revision がテーマ内に 1 つでも残れば `THEME_STAMP_INCOMPLETE`。
5. **パッケージ**: `package_theme(root, paths, commit, payloads)` に、注入後の runtime と functions.php を差し替えた `payloads` を渡します。
   - `theme.zip` と `descriptor.file_manifest_sha256` は candidate ディレクトリにだけ置きます。
   - `sources` / `source_sha256` は git のバイト列のままです。
6. **candidate と照合**
   - `articles[i].document.block_markup` は注入後の本文です。
   - `candidate_id = sha256(encoded(candidate))`、`content_after_sha256(document, post_id)`、proposal の `after_sha256` はすべて注入後の document から計算します。
   - `readback()` は注入後の document と、注入後の `file_manifest_sha256`（`THEME_READBACK_MISMATCH`）で照合します。
7. **git に書かないもの**: 上の 1〜6 の値（価格入りバイト列の hash）はすべて、journal と candidate（.secrets 内）にだけ置きます。`sync_git()` が push するのは checkpoint の commit（価格なしのソース）だけです。

## 8. 公開と purge の順序

publisher のコマンド（`--owner-checkout` は既存どおり。値を扱うのはフラグを付けたときだけ）:

```
prepare --articles <keys> --theme --price-overlay-run <run_id>     # checkpoint（価格なし）→ gate → 注入 → §7 → 注入 candidate
preview --candidate price-overlay:<run_id>:publish
publish --candidate price-overlay:<run_id>:publish --price-overlay-run <run_id>    # 再 gate・注入の再導出 → 承認の予約 → 書き込み → readback → 注入後 hash の照合
prepare --articles <keys> --theme --price-overlay-purge <run_id>   # 同じ記事キー・同じ source_sha256 の価格なし candidate
preview --candidate price-overlay:<run_id>:purge
publish --candidate price-overlay:<run_id>:purge --price-overlay-purge <run_id>  # readback → price_free_violations → record_purge_publish → 注入 candidate の削除 → purge candidate の削除と id の redact
```

- `--price-overlay-run` と `--price-overlay-purge` は `--theme` 必須、affiliate 系の引数・patch 行とは併用できません（`PRICE_OVERLAY_THEME_REQUIRED` / `PRICE_OVERLAY_AFFILIATE_UNSUPPORTED` / `PRICE_OVERLAY_PATCH_SOURCE_UNSUPPORTED`）。
- 注入 candidate の publish はフラグが無いと `PRICE_OVERLAY_FLAG_REQUIRED`、価格なし candidate にフラグを付けると `PRICE_OVERLAY_CANDIDATE_UNBOUND`、run や種別が違えば `PRICE_OVERLAY_RUN_MISMATCH` です。
- 何も注入されない overlay（本文に値を持つ offer が無い）は `PRICE_OVERLAY_NOTHING_INJECTED` で、承認を消費しません。
- **値の配信中のフラグ無しコマンド**: 公開の記録があり purge 公開もオーナーの incident 記録も無い run、または承認記録が読めない run（`live_run_ids()`）がある間は、フラグを付けない `prepare` と `publish` を、記事や `--theme` の有無にかかわらずすべて `PRICE_OVERLAY_LIVE` で拒否します。
  - 判定する場所: 検証済みの `--owner-checkout`、固定の `OWNER_CHECKOUT`（`/home/minami/rakuten`）、publisher の ROOT、それぞれの `.secrets/rakuten-price-refresh`。`--owner-checkout` が無い場合や ROOT と違う場合（worktree から実行する通常の形）も `OWNER_CHECKOUT` を見ます。
  - run ディレクトリが symlink かディレクトリでない場合は `PRICE_OVERLAY_PRIVATE_PATH_UNSAFE`、owner checkout が不正なら `PRICE_OVERLAY_OWNER_CHECKOUT_INVALID` で拒否します（安全側）。
  - WordPress への呼び出し、checkpoint の commit、candidate ディレクトリ、publish の lock と journal より前に拒否します。
  - 理由: prepare は baseline に配信中の注入本文（または注入テーマの tree hash）を入れ、その candidate の id とディレクトリを出力します。publish は記録の無い書き込みで配信中の run の purge 公開の前提を崩します。
  - `--price-overlay-run` / `--price-overlay-purge` の prepare と publish はこの検査を通りません（purge は配信中の記事に対して行うもの）。別の run が配信中のときの run 付き prepare は §10.1-11 を見てください。
  - 同じ間、`status`（`--candidate` なし）は WordPress を呼ばず `{"price_overlay_live": [...], "status": "REDACTED_PRICE_OVERLAY_LIVE"}` だけを出し、フラグ無し candidate の `status --candidate` は hash と revision を伏せます（§3）。
  - `scripts/raos_wordpress_deployment_operator.py` の CLI も、同じ判定で WordPress に届くコマンドを**すべて**拒否します。配信中なら `WORDPRESS_MCP_PRICE_OVERLAY_LIVE`、run の状態が読めなければ `WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID` です。
    - 判定は、ローカルだけで完結するコマンドの許可リスト（`PRICE_OVERLAY_LOCAL_COMMANDS`）で行います。今は `price-overlay-live-check` だけです。
    - リストに無いコマンドはすべて拒否します。読み取り系、`owner-direct-*`（`ensure-draft` / `content-propose` / `theme-propose-candidate` / `authorize` / `apply` / `finish` を含む）、`theme-propose-release`、`release-wait-and-apply`、`plugin-propose-change`、`plugin-apply-change`、`operation-recover` が対象です。後から足したコマンドも、リストに加えない限り拒否します。
    - 理由: 読み取りは注入本文や注入テーマの tree hash を出力します。提案の作成は、その hash を WordPress の新しい行に保存します（purge の対象外）。authorize と apply は、記録の無い書き込みになります。
    - 拒否は CLI の入口（`main()`）だけで行います。publisher 内部の呼び出し（purge 公開の publish と、それが使う status）は `run()` を直接呼ぶので影響しません。
  - MCP bridge（`packages/wordpress-mcp-bridge/src/index.ts`）は、どの tool でも、先に `price-overlay-live-check` を実行します。応答が `{"price_overlay_live": false}` と完全に一致したときだけ、本来のコマンドを operator に渡します。
    - 終了コードが 0 以外なら、そのコード（`WORDPRESS_MCP_PRICE_OVERLAY_LIVE` など）を返します。
    - 終了コードが 0 でも応答が違えば、`WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID` を返します。
    - operator 側の拒否と二重になります。
  - **編集用 MCP（`wordpressEditor`）**: launcher（`scripts/raos_wordpress_editor_mcp_launcher.mjs`）が、proxy を起動する前と、**client → proxy の各メッセージの前**、および **proxy → client の各応答の前**に、同じ `price-overlay-live-check` を実行します（`scripts/raos_price_overlay_live_check.mjs`）。
    - 起動時に拒否されると、proxy は起動せず、資格情報も読みません（終了コード 69、stderr に判定コード）。
    - 配信中に届いたメッセージは proxy に渡さず、`id` を持つ要求には JSON-RPC error（`message` は判定コード）を返します。応答側も同じで、配信中は proxy の応答を client に渡しません。
    - 理由: `content-get` / `content-list` は配信中の注入本文と `content_sha256` を返し、`site-status` は注入テーマの `runtime_revision` を返します。`content-propose-release` と `publication-batch-register` は、その hash を WordPress の新しい行に保存します（purge の対象外）。
    - 判定は 1 メッセージずつ順番に行います。proxy は長時間動くので、起動時の 1 回だけでは足りません。
  - **ほかの経路も同じ判定で拒否します**（共有の実装: `python/raos/adapters/price_overlay_live_guard.py`、Node は `scripts/raos_price_overlay_live_check.mjs`）。判定する場所は同じ 3 つの checkout（呼び出し側の owner checkout、固定の `OWNER_CHECKOUT`、実行中のリポジトリ）です。

| 経路 | 実装 | 配信中の動作 |
| --- | --- | --- |
| `wordpressEditor` MCP（launcher → proxy） | `scripts/raos_wordpress_editor_mcp_launcher.mjs` | 起動・各メッセージ・各応答で拒否 |
| `wordpressDeployment` MCP（bridge → operator） | `packages/wordpress-mcp-bridge/src/index.ts` + operator `main()` | 全 tool・全コマンドを拒否 |
| publisher のフラグ無し `prepare` / `publish` / `preview` / `sync` / `status --candidate` | `scripts/raos_wordpress_direct_publish.py` | `PRICE_OVERLAY_LIVE`（`status`（`--candidate` なし）は WordPress を呼ばず marker のみ） |
| 直接の editor MCP クライアント（legacy full-portfolio・verified-incremental・snapshot・reader hubs） | `EditorMcpClient`（`raos_wordpress_publication_request.py`）の生成時と毎要求 | `RAOS_WORDPRESS_REQUEST_PRICE_OVERLAY_LIVE` |
| 公開ページ・stylesheet の readback（Basic 認証の有無を問わない） | 同上（`_public_page_evidence` / `_fetch_public_stylesheet_sentinels`） | 同上 |
| deployment bridge の呼び出し側 | 同上（`_deployment_mcp_call`） | 同上（bridge・operator と三重） |
| SEO 監査の匿名 GET（body hash を証跡に残す） | `scripts/raos_wordpress_seo_audit.py` の `BoundedHttpsTransport.get`（`raos_wordpress_runtime_audit.py` / `raos_wordpress_incremental_seo_audit.py` もこれを使う） | `PRICE_OVERLAY_LIVE` |
| full redesign の匿名 capture（body 全文と hash を保存） | `scripts/prepare_full_redesign_audit_packet.py` の `_capture_public` | 同上 |
| RAOS v2 の匿名 capture（body hash を出力・保存） | `scripts/validate_raos_v2_successor.py` の `_fetch` | `RAOS_V2_PRICE_OVERLAY_LIVE` |
| harness の `inventory --wordpress-status`（実 MCP を起動） | `scripts/codex_harness.py` の `wordpress_status` | server を起動せず `REFUSED` 行 |
| candidate preview の単体 CLI | `scripts/raos_wordpress_direct_preview.py` の `main`（フラグ無し candidate のみ） | `DIRECT_PREVIEW_PRICE_OVERLAY_LIVE` |
| ST-1506 / ST-1704v2 / ST-1703 / ST-1704 pilot の CLI（`raos-bounded-operator`・`wp/v2`） | 各 CLI の `_price_overlay_live()`（operator の check を子プロセスで実行） | `<CLI>_PRICE_OVERLAY_LIVE`（終了コード 69） |
| 匿名のブラウザ計測（`ks_before_capture` / `ks_public_performance_probe` / `ks_viewport_matrix` / `site_improvements_audit` / `site_improvements_consent_lab` / `npm run wordpress:ui:check`） | `scripts/raos_price_overlay_live_check.mjs`（127.0.0.1 の origin は対象外） | 判定コードで終了 69（ブラウザを起動しない） |

- **拒否しない経路**（構造上、値も価格復元可能な hash も扱わないもの）
  - `--price-overlay-run` / `--price-overlay-purge` を付けた `prepare` / `publish`、およびその candidate の `preview` / `status` / `sync`（run に束縛された正規の経路。§10.1-11 は別）。
  - ローカルだけの経路: `make wordpress-preview-*`（docker。seed は価格なしの materialized fixture）、`tests/wordpress_mcp_v1/e2e`（使い捨ての docker）、`raos_wordpress_local_restore.py` / `raos_wordpress_scratch_restore.py` / `raos_wordpress_scratch_theme_restore.py`（ローカルのファイル操作と `theme_package()` だけ）、`store_wordpress_mcp_credential.py`（書き込みのみ）。
  - kurashinoshirube.com に接続しない経路: Google（GSC / GA4）、楽天 API（価格取得そのもの。§5 の保存規則で守る）、ASP の API、WordPress.com（別サイトの下書き）、`raos_wordpress_baseline_media.py`（楽天のサムネイルのみ）、`raos_public_acceptance.py`（入力は既存の匿名 export で、自分では取得しない）。
  - 127.0.0.1 の origin を指定したブラウザ計測（ローカル preview の観測）。
- **run の保存場所の固定**: `scripts/raos_rakuten_price_refresh.py` の `--owner-checkout` を取るコマンドは、固定の `OWNER_CHECKOUT`（`/home/minami/rakuten`、publisher・operator と同じ値）以外を `OWNER_CHECKOUT_NOT_PINNED` で拒否します。対象は `fetch` / `apply` / `gate` / `purge-expired` / `resolve-incident` / `confirm-plugin-cleanup` です。
  - worktree の ROOT やほかの clone を指定した場合も、保存を開く前（資格情報の読み込み、承認記録の作成、run ディレクトリの作成より前）に拒否します。
  - これで、publisher と operator が見ない場所に run が作られることはありません。
- **run 付きコマンドの実行場所の固定**: publisher の run 付き `prepare` / `publish` と、price overlay の handle を使う `preview` / `status` / `sync` は、ROOT が固定の `OWNER_CHECKOUT` でなければ `PRICE_OVERLAY_OWNER_CHECKOUT_REQUIRED` で拒否します（承認記録を開く前）。
  - 理由: 承認記録は owner checkout にしかなく、注入 candidate のローカル複製の走査（§5）も owner checkout の candidate ディレクトリしか見ません。worktree から実行すると、purge が届かない場所に注入バイト列を作ってしまいます。
- **run ディレクトリの安全性**: `.secrets/rakuten-price-refresh` 直下に symlink やディレクトリでない entry があると、`live_run_ids()` は `PRIVATE_PATH_UNSAFE` で拒否します（operator では `WORDPRESS_MCP_PRICE_OVERLAY_STATE_INVALID`、publisher では `PRICE_OVERLAY_PRIVATE_PATH_UNSAFE`）。読めない run を「配信していない」と扱わないためです。
- 出力に candidate id を出しません。注入 candidate の id は注入後本文の hash、purge candidate の id は live の注入後本文を baseline に持つ candidate の hash で、どちらも価格を総当たりで復元できるためです。
  - `prepare` は id を承認記録の `prepared_candidates` にだけ書き、`{"candidate": "price-overlay:<run_id>:<mode>", "candidate_id": "REDACTED_PRICE_OVERLAY", ...}` を出します。candidate ディレクトリのパスも出しません。
  - `preview` / `publish` / `status` / `sync` は price overlay の candidate について、handle、`REDACTED_PRICE_OVERLAY`、mode・run_id、状態（`publication_ready` / `publication_status` / `status` / `result_code`）、`git_sync.status` だけを出します（preview の runtime hash や journal の proposal id・receipt は出さない。`preview.json` と `journal.json` には従来どおり書く）。
  - handle の形が違えば `PRICE_OVERLAY_CANDIDATE_HANDLE_INVALID`、承認記録に id が無い（purge 公開の後など）と `PRICE_OVERLAY_CANDIDATE_HANDLE_UNKNOWN` で、WordPress を呼ぶ前に拒否します。
  - 証跡（KS-020.md など）には run_id と結果コードだけを写します。

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
   - candidate ディレクトリ（`.secrets/wordpress-mcp/owner-direct-v1/<candidate_id>/`）: 注入後本文・runtime・theme.zip・manifest・journal を持つので、ディレクトリごと削除します。
     - purge 公開の成功時: publisher が注入 candidate、purge 用の元 candidate（`base_candidate_id`）、preview が凍結した注入テーマの複製（`.secrets/wordpress-direct-preview/theme-<tree>`）を削除し、git 同期の後に purge 用 candidate 自身（baseline に live の注入後本文を持つ）と、§5 の走査で見つかるこの run のローカル複製をすべて削除して、その id を承認記録から消します（§4）。readback で価格なしを確かめられなかった purge 公開は、再試行のために candidate を残します。
     - `purge-expired`: §5 のローカル複製の走査で、承認記録にある candidate（公開・purge 公開・`base_candidate_id`・`prepared_candidates`）、この run の目印・観測時刻・注入後 hash が残る candidate（値の公開中に別途 prepare した candidate など）、preview の凍結テーマと fixture を削除します（`candidate_directories_deleted`・`preview_copies_deleted`）。
   - 引数なしの `purge-expired` は、期限を過ぎた全 run を掃除します。
7. 公開後の確認
   - ブラウザで JS を実行した後の状態を照合します（静的 HTML の `data-ps-price-state` は CURRENT にならない）。
   - WordPress のリビジョンとページキャッシュに注入本文が残らないかを確認します。**これは初回の実値公開の前提条件です**（未実測）。リビジョンが残る設定なら、purge 公開と同じ期限までに注入本文のリビジョンを削除する手順を先に用意し、用意できるまで値を公開しません。
   - 承認記録の `purge_publish.wordpress_redaction` が `COMPLETE` であることを確かめます（§10.1-3）。`INCOMPLETE` / `NOT_REPORTED` なら、plugin の保存に注入本文が残っています。その run は `WORDPRESS_REDACTION_UNCONFIRMED` として `fetch` と `gate` を拒否し続け、オーナーが手作業で消して `confirm-plugin-cleanup` で記録するまで解除されません（§5）。

## 9. gate の拒否条件（`gate()`）

| code | 内容 |
| --- | --- |
| `OVERLAY_INVALID` | 構造の不正、24 時間を超える窓、状態と値の組の不整合 |
| `OVERLAY_VALUE_EXPIRING` | 値を持つ entry の残りが 2 時間未満 |
| `OVERLAY_VALUE_OLDER_THAN_24H` / `OVERLAY_OBSERVED_IN_FUTURE` | 観測から 24 時間を超えた / 観測時刻が未来 |
| `TAX_INCLUDED_MISSING` | `price_yen` があるのに `tax_included` が bool でない |
| `IDENTITY_MISMATCH_WITH_CTA` | IDENTITY_MISMATCH の offer に、送る本文の `ps-offer-link` CTA、または同じ商品ページへのリンクが残っている |
| `CTA_TARGET_MISMATCH` / `CTA_TARGET_UNVERIFIED` | 値を持つ offer の CTA が overlay の `item_url` 以外を指す / 本文にその offer の CTA が無く照合できない（plan 作成後のカタログ変更対策） |
| `SOLD_OUT_WITH_CTA` | `SOLD_OUT` または `NOT_FOUND_PENDING` の offer に、送る本文の `ps-offer-link` CTA、または同じ商品ページへのリンクが残っている（注入は CTA を消さないため。UI は変えない）。CTA が無ければ `CTA_TARGET_UNVERIFIED` にもしない |
| `TAX_EXCLUDED_PRICE_UNSUPPORTED` | `tax_included=false` の価格で、送るテーマの `purchase-support.js` が税別表示を持たない（CLI の `gate` は `--repository` のテーマ JS を、publisher は checkpoint のテーマ JS を渡す） |
| `GIT_TRACKED_OVERLAY_VALUE` | tracked file（作業ツリーと index）か、ignore されていない未追跡ファイルに overlay の値がある（下記） |
| `BODY_NOT_PRICE_FREE` / `BODY_ALREADY_INJECTED` | 送る本文が価格なしでない / 注入済み |
| `RAKUTEN_CREDIT_MISSING` | 値を注入する本文の `ps-media-credit` 段落に、`https://developers.rakuten.com/` への「Supported by Rakuten Developers」リンクが無い |
| `RAKUTEN_PRICE_DISCLAIMER_MISSING` | 値を注入する販売先ブロックの `ps-price-date` 段落（または本文全体）に免責文へのリンクが無い（§2.1） |
| `EXPIRED_RUN_NOT_PURGED` | 別の run が期限切れのまま purge されていない（§5 の `PUBLISHED_NOT_PURGED` / `REDACTION_PENDING` / `WORDPRESS_REDACTION_UNCONFIRMED` / `UNDATED` を含む） |
| `APPROVAL_MISSING` / `APPROVAL_RUN_MISMATCH` / `APPROVAL_PLAN_MISMATCH` / `APPROVAL_PUBLISH_ALREADY_USED` | 承認の 1 組が無い / 一致しない / 公開済み |
| `BODIES_REQUIRED` | 本文が 1 件も渡されていない |

publisher は、gate の拒否を `RAOS_WORDPRESS_DIRECT_PRICE_OVERLAY_GATE_REFUSED:<code,...>` として返し、ほかの domain の拒否も `RAOS_WORDPRESS_DIRECT_PRICE_OVERLAY_<code>` で返します。publisher の gate は、下記の走査に加えて **checkpoint の commit** も `scan_revision_for_overlay()`（完全一致と文脈一致）で走査します。

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

1. ~~**publisher 組み込み**~~ **済（2026-09-16、バッチ G）**: `prepare` / `publish` の `--price-overlay-run` / `--price-overlay-purge`（§8）。checkpoint 後の注入、§7 の再計算（private の candidate だけ）、公開直前の再 gate と注入の再導出、承認の予約、readback と注入後 hash の照合、purge 公開の記録。テスト: `test_rakuten_price_overlay_publish.py`（git の全 ref・index・作業ツリー・checkpoint commit に値が無いこと、checkpoint commit に入った値を gate が拒否すること、hash の整合、公開直前の注入の再導出 `INJECTION_MISMATCH`、prepare 後に現れた漏出と `EXPIRED_RUN_NOT_PURGED` の再 gate、readback、purge 公開の書き込み前検査 `PURGE_SOURCE_DRIFT` / `PURGE_BODY_NOT_PRICE_FREE` と readback、期限切れと期限間近の再開、承認の再利用を WordPress の呼び出し 0 件で拒否すること、origin/main の publisher とのフラグ無しの一致、出力に candidate id を出さないこと）。
2. ~~**candidate ディレクトリと journal の purge**~~ **済（2026-09-16）**: §8-5・§8-6 のとおり、purge 公開の成功時と `purge-expired` で candidate ディレクトリ（journal を含む）を削除します。残る限界:
   - purge 公開をせず `purge-expired` だけを実行しても、WordPress 上の値は消えません（期限前の purge 公開は運用で行う）。その run は `PURGE_PUBLISH_MISSING` と報告され、`PUBLISHED_NOT_PURGED` として `fetch` / `gate` を拒否し続けます。解除は purge 公開の記録（期限後でも可。完了時に purge candidate と id も消える）か、オーナーの `resolve-incident`（plugin の後始末の確認とローカル複製の走査を含む）だけです（§5）。
   - preview のローカル WordPress（docker のデータベース）に取り込まれた注入後本文は消しません（§10.1-3 の残る作業 3）。
   - ローカル複製の走査（§5）が見るのは、owner checkout の candidate ディレクトリ（全ファイルと `.staging-*`）と、preview の凍結テーマ・fixture だけです。`.secrets` 外のコピー、ほかの clone・worktree の `.secrets`、preview のデータベースは対象外です。worktree から実行した publisher が配信中の値を複製する経路は、§8 の拒否（owner checkout を基準に判定）で塞いでいます。
   - purge 用 candidate は、公開時と同じ `source_sha256` を要求します（`PURGE_SOURCE_DRIFT`）。公開後に git の本文を変えた場合は、checkpoint の内容に戻してから purge します。
3. **WordPress 側に残る注入本文**（一部実装、未解決。**初回の実値公開の前提条件**）
   - **実装済み（plugin ソースのみ、未デプロイ）**: owner-direct plugin は、proposal 行の `payload.before` / `payload.after`（公開時は `after`、purge 公開時は `before` が注入本文）と、option `raos_codex_owner_direct_undo_<proposal_id>`（`applied_document`・`public_before`）に注入本文を保存します。purge 公開の batch を finalize したとき（rollback できなくなった時点）、`RAOS_Codex_MCP_Owner_Direct::redact_price_overlay_copies()` がこれらを redact します。
     - purge 公開の判定: 行の `before` 本文に `data-ps-overlay-run="<run_id>"` があり、`after` 本文に無いこと。
     - 対象: 同じ投稿の owner-direct の CONTENT_RELEASE 行のうち、その run の目印を持つ本文。`block_markup` を `sha256:<本文の sha256>` に置き換え、`payload.price_overlay_redaction`（run_id と面ごとの sha256）を足します。undo option の同じ本文も置き換えます。別の run・別の投稿の本文は変えません。
     - 状態が APPLIED / FAILED / EXPIRED の行だけを書き換えます。PENDING / MANUAL_REQUIRED / APPROVED / APPLYING の行は書き換えず、結果を `INCOMPLETE` にします。すべて済めば `COMPLETE` です。
     - proposal の完全性検査（`validate_proposal_integrity()`）は、終了状態の owner-direct 行で、redact 記録と `sha256:` の本文が一致する面に限り、記録済みの文書 hash を使います。記録と食い違う行や、終了状態でない行は従来どおり hash 不一致で拒否します。
     - 結果は finalize の応答 `price_overlay_redaction` に入り、publisher が承認記録の `purge_publish.wordpress_redaction` に残します（§4）。
     - **テーマ release 行**: purge 公開の batch にある THEME_RELEASE 行の置き換え前の tree（= 注入テーマの tree hash）を手がかりにします。同じ publisher の THEME_RELEASE 行のうち、その tree を `before_sha256` / `after_sha256` 列に持つ行の payload を書き換えます。
       - 伏せる値: その tree の面の `before_tree_sha256` / `after_tree_sha256`。注入テーマを入れた行（after 側）では、`code_package.file_manifest_sha256` と、`file_manifest` のうち `assets/purchase-support.v1.json`・`functions.php` の `sha256` も伏せます。
       - どれも `REDACTED_PRICE_OVERLAY` にし、`price_overlay_redaction`（`runs`・`tree_sides`・`manifest_paths`）を足します。件数は結果の `theme_proposals` です。
       - 終了状態でない行は書き換えず、結果を `INCOMPLETE` にします（本文の行と同じ）。
       - 完全性検査は、終了状態の owner-direct の THEME_RELEASE 行で、記録が伏せた面・項目とちょうど一致する場合に限り、伏せた tree hash を行の列の値に戻して検査します。記録と印が食い違う行、終了状態でない行、本文用の形の記録は拒否します。
       - 行の `before_sha256` / `after_sha256` 列は変えません（batch の照合に使うため）。注入テーマの tree hash は WordPress のデータベースの列に残り、§3 と同じく price-recoverable です。
     - テスト（PHP harness）
       - `finish_owner_direct_batch()` の finalize を実際に通します。応答の `price_overlay_redaction`、本文の行・undo option・両方のテーマ行の書き換え、無関係なテーマ行が変わらないこと、完了記録の保存を確かめます。呼び出しを `null` に置き換える変異で失敗することを確認済みです。
       - 配信中の本文変更（before と after の両方に目印。同じ run・別の run）を purge と見なさないことを確かめます。「after に目印が無い」条件を外す変異で失敗することを確認済みです。
       - テーマ行の UPDATE が失敗した finalize: 結果は `INCOMPLETE`、`theme_proposals` は増えず、finish の `price_overlay_redaction` は `COMPLETE` になりません。
       - テーマ行の記録の改ざん（tree_sides と印の食い違い、before 側だけの行の manifest の印、空の runs、不正な run id、余分なキー、本文行・plugin 行に付けたテーマ形の記録）と、終了状態でない行の拒否を確かめます。別の作成者の batch 行を手がかりにしないことも確かめます。harness は PHP の Warning / Notice を例外にします。
     - 残す hash: 行の `before_sha256` / `after_sha256` 列には元から注入後文書の hash があるため、本文の sha256 を残しても復元の手がかりは増えません。これらの hash も価格を総当たりで復元できる点は §3 と同じで、WordPress のデータベース内に残ります。**purge 後も残るこの hash の扱いは §1-5 のオーナー決定待ちです（下の残る作業 4）。**
     - テスト: `tests/wordpress_mcp_v1/php/owner_direct_overlay_redaction_harness.php`（`test_owner_direct_server.py` から実行）。
     - plugin の `RUNTIME_REVISION` は変えていません。変えると、デプロイ前の本番に対する既存の公開要求（`EXPECTED_PLUGIN_RUNTIME_REVISION`）がすべて止まるためです。デプロイ済みかは revision では判別できず、下の確認で見ます。
   - **初回の実値公開までに残る作業**（満たすまで値を公開しない）
     1. **plugin のデプロイ（オーナー）**: この redact を含む plugin を本番に入れます。確認は 2 段です。
        - 初回の実値公開の前: 本番の plugin ファイルが `changes/wordpress-mcp-v1/runtime-manifest.v1.json` の `plugin.file_manifest_sha256` と一致すること（revision は変えていないので、revision では判別できません）。
        - 初回の purge 公開の後: 承認記録の `purge_publish.wordpress_redaction` が `COMPLETE` であること。`INCOMPLETE` / `NOT_REPORTED` なら、同じ期限内に plugin の proposal 行・undo option の注入本文とテーマ release 行の注入テーマ hash を手作業で消し、`confirm-plugin-cleanup` で記録します（記録するまで run は `WORDPRESS_REDACTION_UNCONFIRMED`、§5）。
     2. **WordPress の投稿リビジョンとページキャッシュの実測**: purge 公開の後に、`wp_posts` のリビジョン行（`post_type=revision`）と、ページキャッシュ・CDN に注入本文が残るかを実測します。残る設定なら、purge 公開と同じ期限までに消す手順（リビジョンの削除、キャッシュの purge）を先に用意します（§8-7）。plugin の redact はリビジョンとキャッシュを対象にしていません。
     3. **preview のデータベースの後始末**: 注入 candidate の preview は、注入後本文をローカルの WordPress（docker のデータベース）に取り込みます。purge 公開も `purge-expired` もこれを消しません。値を含む preview の後、同じ 24 時間以内にローカル環境を作り直す（またはデータベースを消す）手順を決めます。
     4. **OWNER DECISION REQUIRED: plugin に残る hash（§1-5）**: sha256 hashes of injected documents/themes remain in plugin proposal rows and undo options after purge; either the owner accepts this (hashes are not prices, but can be brute-forced) or a row/option deletion step must be designed before the first real publish.
        - 決まるまで値を公開しません。`run_status()` の判定（§5）は今のままで、この項目を理由に run を解除しません。
   - 参考（値は含まない）: purge 公開のテーマ release は、置き換え前のテーマ（注入後 runtime JSON を含む）を plugin の `operation-<proposal_id>/before` に一時保存します。runtime JSON にあるのは注入後本文の sha256 だけで、価格そのものはありません。plugin の redact はこの一時保存を対象にしません。
4. ~~**税別価格の表示（theme JS）**~~ **済（2026-09-16）**: §6.1 のとおり、JS は税別価格を「本体税別」と表示し、合計に含めません。gate は送るテーマ JS が表示分けを持つときだけ税別価格を通します。renderer の `data-ps-reference-offer` 目印は不要と判断し、追加していません（§6.2）。
5. ~~**SOLD_OUT と CTA**~~ **済（2026-09-16）**: gate に `SOLD_OUT_WITH_CTA` を追加しました（`SOLD_OUT` と `NOT_FOUND_PENDING`。UI は変えない）。CTA を残したまま売り切れ・未発見の状態を注入する公開は拒否され、カタログ側で CTA を外してから再度 plan・fetch します。
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
   - 価格更新 CLI の `--owner-checkout` は `/home/minami/rakuten` に固定しています（§8、ほかは `OWNER_CHECKOUT_NOT_PINNED`）。そのうえで、絶対パス・symlink でない・`.secrets` ディレクトリを持つ checkout であることを要求します。`--repository` は固定していません。
   - 文脈一致の限界は §10.2-1 を見てください。
8. **`hits=1` の曖昧さ**
   - 要求は `hits=1` なので、応答の行は 1 件までです。`classify_observation()` の `MULTIPLE_ROWS`（items が 1 件でない）は、実際には発火しません。
   - 同じ itemCode に複数の行があっても検出できません。`hits=2` にして `MULTIPLE_ROWS` を生かすかは未判断です。
9. **標準出力と証跡**
   - `apply` の出力には、`status_counts`（SOLD_OUT などの状態別件数）と `purge_publish_due_by` が含まれます。価格は出しません。
   - 対象の offer が 1 件だと、件数から販売可能情報が分かります。
   - 証跡（KS-020.md など）には、run_id と結果コードだけを写します。
10. **テストの穴**: ~~`.secrets/rakuten-price-refresh` 経路の symlink 拒否には専用テストがありません~~ **済（2026-09-16）**: run ディレクトリが symlink・ファイルの場合の `PRIVATE_PATH_UNSAFE` を `test_rakuten_price_refresh.py` と `test_price_overlay_live_paths.py` で確かめます。gate 側の `EXPIRED_RUN_NOT_PURGED` は、CLI の `gate` と publisher の gate の両方でテスト済みです（2026-09-16）。
    - purge 公開の書き込み前検査（`Binding._check_purge()`）の本文側には 2 つの条件があります。
      - 「文書が checkpoint の本文と違う」: フラグ無しで作った candidate では `body_file` が checkpoint のコピー（`sources/…`）そのものなので、先に `load_candidate()` が `SNAPSHOT_DRIFT` で拒否し、この条件には届きません。多重防御として残し、テストは `SNAPSHOT_DRIFT` を確かめます。
      - `price_free_violations()`: 本文・sources・作業ツリーを一貫して注入本文にした candidate を `PURGE_BODY_NOT_PRICE_FREE` で拒否します（テスト済み）。
11. **別の run の配信中の run 付き prepare（未対応）**: `--price-overlay-run` の prepare は §8 の配信中の検査を通りません。
    - 別の run が配信中の記事・テーマに対して新しい run を prepare すると、price-free の base candidate の baseline に配信中の注入本文が入ります。
    - その candidate は目印を持つので、配信中の run の purge 公開か `purge-expired` の走査で削除されます。
    - 拒否するかはオーナー判断です。

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
