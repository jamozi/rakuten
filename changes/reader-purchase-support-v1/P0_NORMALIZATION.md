# P0 購入経路の正常化（2026-09-10）

対象は投稿30・83・41のPilot。P1、投稿85/86の更新、全記事公開は未実施。
公開指示を受ける前のローカル実装・検証であり、P0全体の本番完了ではない。

## 根因と適用層

添付タスクの `src/purchase/`・`site/rebuild/` は現在のmainに存在しない。
対応する正本は `python/raos/domain/editorial/purchase_support.py`、
`python/raos/application/editorial/purchase_support.py`、本ディレクトリのカタログと
`scripts/build_reader_purchase_support_v1.py`。

- Data source: 新しい4比較記事は共通の商品・offerカタログを使う。旧記事85/19は公開本文を保持するpatch経路で、既存広告URLが別管理。記事の広告URLを見ただけでは新カタログの確認済みofferへ昇格できない。
- Resolver: `eligible_link` が保証の確認を購入リンクの条件にしていた。価格期限と送料の欠損は既に予算判定で独立していた。この性質を回帰テストで保持し、保証・仕様・設置条件をリンク停止理由から分離した。
- Generator: `add_compatibility_anchors` が消えた購入欄のIDまで本文末尾の空spanへ移した。ID存在だけの旧検査では商品との関係を検出できなかった。
- Tracking: 新しい4記事には4placementが存在するが、購入クリックにリンク目的と広告状態がなく、旧記事85は冒頭にfinal_summaryがある。
- WordPress: 購入欄・画像・計測の投影は承認済み本文とテーマruntimeのhashで限定される。この境界と停止スイッチ、同意、所有者除外を維持。
- Production verification: 既存 `scripts/raos_public_acceptance.py` を拡張。保存成功・HTTP200だけを購入経路成功にしない。

## 変更

既存offerへmerchant_url / affiliate_url / variant_id / verified_atを追加。
既存urlは互換入力として保持する。新resolverは承認済み発行URLをそのまま優先し、
未取得・利用権未確認では有効なmerchant URLを残す。公式仕様はproduct側のofficial_urlを保持する。
同じproduct・variant・sellerの重複登録を拒否する。ASPの正規化記録と編集確認票のURL照合も継続する。

identity / purchasability / affiliate / price / shipping / required_items / warranty /
spec / installationを独立して返す。価格状態は閲覧時のJSで期限を再計算する。
型番同定なし・variantなし・中古・売り切れでは購入CTAを出さない。

商品購入欄のlegacy IDは同じ商品の実section内にaliasを置き、本文内リンクはsectionへ直接向ける。
product_idの異なる遷移を生成時と公開HTML検査の両方で拒否する。
Pilotのクリックbindingにlink_purpose・affiliateを追加。旧8項目の固定snapshotも引き続き照合し、
同じoffer_clickに分類を追加する。公式仕様リンクはofficial_verifyとして識別し、offer_clickへ混ぜない。
GA4 outbound clickはoffer_clickと別イベント。同一Eventの二重処理とcollectorの二重登録を拒否する。

変更本文は30・83・41だけ。その他10件の購入支援runtime entryと本文を保持するため、
共有テーマをPilotへ反映しても対象外snapshotを失効させない。
本文、画像原文、runtime、テーマintegrityはowner generatorから再生成する。

## 変更ファイルと理由

| ファイル / 範囲 | 変更理由 |
| --- | --- |
| `python/raos/domain/editorial/purchase_support.py` | 発行済み広告・通常販売先の解決と9種類の状態を分離 |
| `python/raos/application/editorial/purchase_support.py` | 既存カタログ検証、商品アンカー、Pilotの10項目binding、価格状態の出力 |
| `python/raos/application/editorial/purchase_offer_import.py` | 既存ASP正規化入力と確認票に新フィールドを接続し、正式URLの完全一致を維持 |
| `changes/reader-purchase-support-v1/purchase-support.v1.json` | 既存6 offerのURL分離、確認したC-Liteの1 offer追加、Pilot対象の明示 |
| `scripts/raos_public_acceptance.py` | 既存匿名公開HTML検査へinventory、意味的アンカー、固定binding照合、SEO前後比較を追加 |
| テーマの `assets/purchase-analytics.js` / `inc/purchase-analytics.php` | 新旧bindingを検証し、既存同意・停止・重複防止の内側でイベントを分類 |
| テーマの `assets/purchase-support.js` | 価格期限だけの状態を閲覧時に再計算 |
| `scripts/build_st1704_self_hosted_theme.py` | 変更したテーマ資産のruntime revisionを更新 |
| `tests/purchase_support/test_purchase_paths.py` | URL選択・状態分離・アンカー・placement・公開検査CLIの失敗ケース |
| `tests/purchase_support/purchase_paths_browser.mjs` | 固定local WordPressでJS実行後のリンクと実アンカー移動を確認 |
| 既存purchase catalog / media testsとJS・PHP harness | 旧snapshot互換、広告属性、同一クリックと二重collector登録の回帰確認 |
| 投稿30・83・41の生成本文、テーマruntime / contract / manifest、build manifestと関連ledger | owner generatorによる上記変更の投影・integrity更新 |

## Before / After（本番Before、ローカルAfter）

| 代表箇所 | Before href / state | After href / state |
| --- | --- | --- |
| 83 C-Lite | 購入CTAなし / 販売先未確認 | https://www.samsonite.co.jp/samsonite/c-lite/spinner55exp/black/ss-134679-1041.html / 型番・ブラック・55cm照合済み、通常販売リンク。送料・必須費用は未確認 |
| 83 エアロフレックス「購入条件へ」 | #aeroflex-dx2-01521-purchase / 本文末尾の空span | #ps-seller-aeroflex-dx2-01521 / PRD-PROTECA-AEROFLEX-DX2-01521の実購入欄 |
| 83 FREQUENTER「購入条件へ」 | #frequenter-lieve-1-250-purchase / 本文末尾の空span | #ps-seller-frequenter-lieve-1-250 / 同商品の実確認欄。販売先同定未完のためCTAは追加しない |
| 30 K11+ Pro | https://www.switchbot.jp/products/switchbot-robot-vacuum-cleaner-k11-pro / 通常販売リンク | 同じhref / merchant_purchase・affiliate=false。保証等の一部UNKNOWNでもリンクを保持 |
| 41 SS-MA251 | https://store.siroca.jp/products/ss-mu251?variant=41121812643976 / 送料・必須品未確認 | 同じhref / merchant_purchase・送料と必須費用は独立UNKNOWN |

## 検証方法

Baselineの匿名HTMLと商品単位inventoryはローカル `output/purchase-p0/`。
正式な広告URLのopaque部分は最終報告・検査stdoutへ出力しない。

```sh
.venv/bin/python -m pytest -q tests/purchase_support tests/wordpress_public_acceptance
make generate
make fast
# 固定local WordPressのJS実行後・390pxと1440px・実アンカークリック
node tests/purchase_support/purchase_paths_browser.mjs <固定候補/browser-input.json> \
  changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/purchase-support.v1.json
# 公開後、匿名の完全HTTP応答を既存RAOSAnonymousPageBatchV1形式で取得して検査
python scripts/raos_public_acceptance.py --input <匿名公開応答.json> \
  --purchase-runtime <固定したpurchase-support.v1.json>
```

公開検査のinputは3記事の完全なhead/body、最終URL、HTTP status、headersを含める。
別ページのfragmentへ移動する既存リンクの確認には、その遷移先ページも同じbatchへ含める。
今回の3記事ではホームと食洗機の関連ガイドが該当する。未取得のままでは既存検査がINCOMPLETEを返す。
`purchase-runtime`は確認した候補の版を使用する。再生成した別snapshotで検査しない。
任意の `seo_baseline` を各observationに指定すればcanonical配列・robots配列・x_robots_tagを前後一致で検査する。
終了コード0のみ当該公開HTML検査のPASS。1は検出済み不具合、2は不足・未取得。
local結果を公開HTML PASSへ置き換えず、公開検査のFAIL/INCOMPLETEではPilot完了・横展開としない。
`--inventory-output <新規ファイル>` と `--purchase-catalog <確認済みカタログ>` で観測明細を保存できる。

## 実行結果と本番検証の区別

- 匿名公開Beforeを6記事取得し、186件の観測行を `output/purchase-p0/before/inventory-final.json` に保存。型番IDのない投稿86は表の実名だけを保存し、商品ID・販売先はUNKNOWNのまま。
- Before検査はFAIL。83の空spanへの購入遷移と85の冒頭placement不一致を検出。85の旧購入欄も新しいsemantic section契約には未適合であり、これだけから旧欄への遷移が空になるとは断定しない。別ページfragmentの未取得はINCOMPLETE要因として別記。
- `make setup` と `make generate`: PASS。生成対象79 ownerの更新と検査を実行。
- `.venv/bin/python -m pytest -q tests/purchase_support tests/wordpress_public_acceptance`: 105 passed（最終の公開検査追加前）。追加後の `tests/purchase_support/test_purchase_paths.py tests/wordpress_public_acceptance`: 52 passed。
- `make fast`の静的検査・生成物検査と並列Python検査: 21,817 passed、10 skipped、58 subtests passed。逐次検査とGitHub CIを含む最終結果は[PR #267](https://github.com/jamozi/rakuten/pull/267)へ記録。
- 固定候補の `direct preview`: PASS。3記事を390px / 1440pxで表示し、代表画面を確認。
- `purchase_paths_browser.mjs`: LOCAL_WORDPRESS PASS。6画面で購入アンカー計28回を実クリック。各画面幅で購入・画像リンク42 bindingのhref・属性・広告relが一致。
- ローカルWordPressの完全HTMLを固定期待値と照合: 3記事とも購入経路findings 0。これは本番公開後の検査結果ではない。
- 本番Beforeの3記事を新しい固定期待値と照合すると不一致を検出し、旧公開状態を新候補のPASSとしない。
- 関連fragment遷移先を含む10ページの匿名取得も実行し、上記不一致を検出。料金計算ガイドはHTMLだけでは `COST_INTERACTION_UNVERIFIED` となるため、公開後検査では実ブラウザーの計算・欠損入力確認も行う。
- 本文変更は3記事のみ。対象外10件のruntime entryがbase `1b3a027b` と完全一致することを確認。
- 本番反映・公開後のhref / rel / 商品binding / placement / anchor / disclosure / SEO前後照合は未実施。Pilot公開ゲートは未通過。

表示確認した固定候補は `c6c02879a6fa4baa3cb57280ece9b469a068e3d7c510edf1d23b9190e04f7cec`。
ローカル表示は `http://127.0.0.1:42033/`、候補と取得応答はlocal管理し、Gitへ入れない。
価格期限や本番preconditionが変わった場合は既存operatorの再確認条件に従う。

## 残る外部依存と公開境界

- K11+ Proの旧広告URLは正式発行・サイト利用権・遷移先variantを今回再確認できていない。画像用の正式コードをテキスト広告へ転用しない。通常リンクを維持し、広告リンクの正常化完了とはしない。
- ラクアmini colorの公式販売ページは再入荷通知のみ。mini Plusとは別商品。画像コードや仕様URLだけから在庫・注文可能を推測しない。
- SOLOTAの型番NP-TMLK1-Kに結び付く注文可能な販売先は未確定。NP-TSP1の停止中リンクを復活させない。
- ASP提携・正式URL取得と、本番GA4設定・DebugViewは別の外部作業。今回のcollector testsは実計測の証拠ではない。本番計測はOFFのまま。
- 本番反映は固定候補の表示確認後、この3記事と共有テーマに対する具体的な公開指示が必要。P1と全記事横展開はこのPilotの結果確認後。

販売先の確認元：
[C-Lite公式商品ページ](https://www.samsonite.co.jp/samsonite/c-lite/spinner55exp/black/ss-134679-1041.html)、
[ラクアmini color公式商品ページ](https://www.thanko.jp/view/item/000000004715)。
価格や在庫の観測日はそのofferの記録だけに適用し、他商品の確認日を書き換えない。
