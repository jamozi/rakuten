# 購入判断支援の実装・確認記録

2026-09-10。対象13ページの通常編集元、共通データ、表示、計測経路を実装した。本番公開・GA4設定変更・メーカーへの問い合わせ送信は実行していない。

## 固定候補と表示

- owner-direct候補: `4ce7b07c64ce69651d233a2833524321ed13d27e014d01d10a90413b36a98d27`
- source SHA-256: `ce6652efcfbd78820383515e1f242484e177c1e41184ef8b61d96b8a9cffec1b`
- preview runtime SHA-256: `564e7c2f6a77d74174035619956b8128edda922077e9c7199f23c3d8e9e7a7b7`
- theme fingerprint: `0d71ff107c056641bc1e3ad8369dbf9f10eb838f939aa4625d7426eae1a5cf78`
- local preview: **PASS**（2026-09-10 12:28 JST）。対象13ページとホーム・一覧、390px/1440px、30画面。画像切れなどの検出エラー0。
- WordPress保存処理: 現行13本文が実 `wp_kses_post` とバイト単位で一致。画像原文は承認済みpublic runtimeから保存後の表示時に投影する。カテゴリの既存編集イメージ・説明は保持し、ローカルpreviewでは登録済みURLとSHA-256が一致する画像だけを固定して表示する。
- 現在の元チェックアウト `/home/minami/rakuten` の作業中ファイルは保持した。2026-09-10 12時台の本番read-only再取得でも13本文に追加更新なし。最新main `d2a643b8` の公開機構・素材・ASP準備を統合し、対象外の台帳・ホーム・記事を保持した。

ローカルで [食洗機比較](http://127.0.0.1:41851/countertop-dishwasher-for-small-households/)、[予算の絞り込み](http://127.0.0.1:41851/portable-power-station-guide/)、[設置寸法の照合](http://127.0.0.1:41851/dishwasher-installation-measurement/) を確認できる。ローカル環境を停止するとこれらのURLは利用できない。

## 操作・境界の確認

最終候補に対するローカルChromium操作確認は **PASS**（2026-09-10 12:29 JST）。PC/スマートフォン幅で次を確認した。実端末での確認・所有者の操作確認とは区別する。

- 用途・予算入力、購入総額の境界、不正な負数入力、未確認費目と予算超過の区別。
- 2商品選択・差分表示・解除、購入案内行の保持、キーボード操作と比較表の横スクロール。
- 食洗機4候補の20リンクと到着先アンカー、費用計算の該当機種選択、既存6機種を含む8機種の選択肢。
- 4候補×9項目の設置測定入力と条件不一致の表示。安全な設置を保証する表示は行わない。
- 文字を200%相当に拡大して本文が画面から横にはみ出さないこと。PC/スマートフォンで商品写真・理由・関連案内を目視確認。
- JavaScript無効時も4比較記事で各4候補・比較・購入案内を読め、16商品の写真が表示されること。
- 既定OFFの最終候補からGoogleへのリクエスト0、JavaScript実行エラー0。

関連テストは広告条件と推薦の分離、価格の期限・費目欠損・型番/コース照合、許諾画像の原文とsnapshot、同意前/拒否/撤回/所有者除外/二重送信/通信失敗、Googleのクリックと閲覧の別report・登録済みjob境界・混在行の扱い、owner-directの対象限定を検証する。実PostgreSQLで別reportの取り込みと再実行、未登録・誤ったreportの拒否を確認した。

`make setup`、`make generate`、theme source check は **PASS**。関連83テストが成功。初回の全体検証で見つかった7失敗は、カテゴリ画像の保持・ビルダー互換構文・旧テスト前提を修正し、該当17テストの再実行で解消した。過去の完了記録は書き換えていない。最終 `make fast` の再実行と必須CIの結果は統合PRの検証欄に記録する。ローカル証跡は `.local/purchase-support/` に保存し、秘密情報を含む公開操作用ディレクトリをGitへ登録しない。

## 未完了事項と公開条件

- 所有者の3課題は [評価記録](evaluation.v1.json) の `PENDING` のまま。エージェントによる操作を所有者確認や実読者調査として記録しない。実端末は `NOT_TESTED`。
- 16商品枠すべてに購入先または調査管理がある。公式販売ページ6件、調査課題24件。写真リンクの販売条件を確認済みとみなさない。不足条件・調査先・次回日・見送り条件は共通データに保持する。
- 固定ページ3・10・120・136は未委任のため、この候補は `publication_ready=false`。[対象限定の追加案](owner-delegation-additions.v1.json) を用意した。権限追加後は現状を読み直して候補を固定し、対象候補への公開指示後に反映・照合する。
- GA4プロパティは `UNKNOWN`、計測は `OFF`。所有者から既存プロパティの識別情報を確認後、[有効化手順](ga4-activation.md) に沿って具体的な設定対象を確定する。本番DebugView・実受信・除外フィルターの確認は未実施。将来のプライバシー文案は今回の公開候補に混ぜていない。
- 運営時間・GA4セッション・ASP確定成果・未帰属成果は未計測のためNULL。計測欠損をゼロへ変換せず、対象範囲のそろわない「確定報酬/1,000セッション」は算出しない。前後差から因果効果を断定しない。

## 目的起点設計R2.1（2026-09-12）の保全記録

比較41の主表を判断軸に絞り、条件つきの値を同じ型番の常時表示領域へ移した一次回の対象差分。新しい正本や全記事の原文複製ではなく、旧位置→新位置の対応だけを記録する。CP41-03（NP-TSP1の「売り切れです。」）は現行の生成本文に旧文が0件のため置換対象なし。rendererのSOLD_OUT用文言だけ将来のために更新した。

| product_id | exact_model | source_fact_locator | value_and_unit | qualifier_or_condition | source_reference | checked_at | prior_state | old_location | new_location | reason_for_change | verified_in_generated_output |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PRD-PANASONIC-NP-TMLK1 | NP-TMLK1-K | facts[label=公表使用水量（条件は機種別）] / 既存公開記事の比較表に紐づく公式仕様 | 約2.5L | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://panasonic.jp/dish/products/NP-TMLK1/spec.html | 2026-08-23 | PRESERVED | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-PANASONIC-NP-TMLK1 | NP-TMLK1-K | facts[label=開扉時の寸法] / SOLOTA NP-TMLK1 の設置例 | 開扉時の奥行は485mm。設置案内では蛇口までの奥行502mm、高さ490mmの確保を案内しています。 | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://panasonic.jp/dish/installation.html | 2026-09-10 | KNOWN | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-PANASONIC-NP-TMLK1 | NP-TMLK1-K | facts[label=必要な余白] / SOLOTA の設置例・熱源との距離 | 背面にはホース外径17mm分の空間が必要です。上部の蒸気を遮らず、熱源から150mm以上離します。設置例の総高さと、本体上の余白を混同しないでください。 | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://panasonic.jp/dish/installation.html | 2026-09-10 | KNOWN | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-PANASONIC-NP-TMLK1 | NP-TMLK1-K | facts[label=給水方式] ← guide_facts[field=water_supply] / p.6 タンク給水 | 着脱タンクへ手動給水 | guide_facts.water_supply の記述から方式名だけを短縮。数値・条件は追加していない | https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/000/379/872/000000000379872/np-tml1.pdf | 2026-09-10 | KNOWN | guide_facts（給排水ガイドの根拠） | 主表 `.ps-comparison` の行「給水方式」 | 比較の判断軸として給水方式を主表へ追加（同じ出典・確認日・状態を継承） | tests/purchase_support/test_purpose_delta.py::test_water_supply_rows_only_where_the_guide_fact_names_the_method |
| PRD-PANASONIC-NP-TMLK1 | NP-TMLK1-K | products.caution | 本体奥行225mmと、扉を開けたときの奥行485mmは別の値です。着脱タンクを出し入れする動線、周囲の余白、電源は別に確認してください。 | 本体寸法と開扉時・余白の読み分け。数値は既存factの値のみを参照 | 既存facts（開扉時の寸法・必要な余白）の出典 | 既存factsの確認日を継承 | 既存fieldを更新（従来はrendererで未使用） | catalog内のみ（未表示） | 商品カード `.ps-product-caution` と販売枠 `#ps-seller-*`、`#ps-installation-context` の一覧 | 詳細を閉領域だけに置かず、直接流入でも必要な限界が読めるようにする | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-THANKO-RAKUA-MINI-COLOR | TDWS25SBL / TDWS25SRD | facts[label=公表使用水量（条件は機種別）] / 既存公開記事の比較表に紐づく公式仕様 | 3.2L | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://www.thanko.jp/view/item/000000004715 | 2026-08-23 | PRESERVED | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-THANKO-RAKUA-MINI-COLOR | TDWS25SBL / TDWS25SRD | facts[label=開扉時の寸法] / 仕様・開扉時奥行 | 扉を開けたときの奥行は594mmです。 | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://www.thanko.jp/view/item/000000004715 | 2026-09-10 | KNOWN | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-THANKO-RAKUA-MINI-COLOR | TDWS25SBL / TDWS25SRD | facts[label=必要な余白] / 説明書 p.10–12 設置 | 上方500mm、背面50mm、左右それぞれ50mm以上を空け、熱源から150mm以上離します。 | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://www.data.thanko.jp/download/manual/tdws25s_man_web_01.pdf | 2026-09-10 | KNOWN | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-THANKO-RAKUA-MINI-COLOR | TDWS25SBL / TDWS25SRD | facts[label=給水方式] ← guide_facts[field=water_supply] / 説明書 p.15 電源を入れる・タンクに給水する | 上部からカップで給水（付属カップ1.8L） | guide_facts.water_supply の記述から方式名だけを短縮。数値・条件は追加していない | https://www.data.thanko.jp/download/manual/tdws25s_man_web_01.pdf | 2026-09-10 | KNOWN | guide_facts（給排水ガイドの根拠） | 主表 `.ps-comparison` の行「給水方式」 | 比較の判断軸として給水方式を主表へ追加（同じ出典・確認日・状態を継承） | tests/purchase_support/test_purpose_delta.py::test_water_supply_rows_only_where_the_guide_fact_names_the_method |
| PRD-THANKO-RAKUA-MINI-COLOR | TDWS25SBL / TDWS25SRD | products.caution | 本体幅308mmだけで設置可とは判断できません。上からカップで給水する空間、扉を開けたときの奥行594mm、周囲の余白の条件があります。 | 本体寸法と開扉時・余白の読み分け。数値は既存factの値のみを参照 | 既存facts（開扉時の寸法・必要な余白）の出典 | 既存factsの確認日を継承 | 既存fieldを更新（従来はrendererで未使用） | catalog内のみ（未表示） | 商品カード `.ps-product-caution` と販売枠 `#ps-seller-*`、`#ps-installation-context` の一覧 | 詳細を閉領域だけに置かず、直接流入でも必要な限界が読めるようにする | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-SIROCA-SS-MA251 | SS-MA251 | facts[label=公表使用水量（条件は機種別）] / 既存公開記事の比較表に紐づく公式仕様 | 約6L | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://www.siroca.co.jp/product/dishwasher_advance/ | 2026-08-23 | PRESERVED | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-SIROCA-SS-MA251 | SS-MA251 | facts[label=開扉時の寸法] / 説明書 p.21–22 設置 | 開扉時の最大奥行は、今回確認できた一次資料では未確認です。販売元・メーカーに照会するまで、第三者の数値で設置を確定しません。 | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://www.siroca.co.jp/im/ss-ma251.pdf | 2026-09-10 | UNKNOWN | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-SIROCA-SS-MA251 | SS-MA251 | facts[label=必要な余白] / 説明書 p.21–22 設置 | 上方700mm、背面60mm、左右それぞれ50mm以上を空け、熱源から150mm以上離します。 | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://www.siroca.co.jp/im/ss-ma251.pdf | 2026-09-10 | KNOWN | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-SIROCA-SS-MA251 | SS-MA251 | facts[label=給水方式] ← guide_facts[field=water_supply] / 説明書 p.12 給水する | タンク給水／分岐水栓（適合確認が別途必要） | guide_facts.water_supply の記述から方式名だけを短縮。数値・条件は追加していない | https://www.siroca.co.jp/im/ss-ma251.pdf | 2026-09-10 | KNOWN | guide_facts（給排水ガイドの根拠） | 主表 `.ps-comparison` の行「給水方式」 | 比較の判断軸として給水方式を主表へ追加（同じ出典・確認日・状態を継承） | tests/purchase_support/test_purpose_delta.py::test_water_supply_rows_only_where_the_guide_fact_names_the_method |
| PRD-SIROCA-SS-MA251 | SS-MA251 | products.caution | 給水2WAYは、自宅の水栓に無条件で適合するという意味ではありません。本体寸法、開扉時の寸法、背面の余白は分けて確認してください。 | 本体寸法と開扉時・余白の読み分け。数値は既存factの値のみを参照 | 既存facts（開扉時の寸法・必要な余白）の出典 | 既存factsの確認日を継承 | 既存fieldを更新（従来はrendererで未使用） | catalog内のみ（未表示） | 商品カード `.ps-product-caution` と販売枠 `#ps-seller-*`、`#ps-installation-context` の一覧 | 詳細を閉領域だけに置かず、直接流入でも必要な限界が読めるようにする | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-PANASONIC-NP-TSP1 | NP-TSP1-W | facts[label=公表使用水量（条件は機種別）] / 既存公開記事の比較表に紐づく公式仕様 | 約9L | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://panasonic.jp/dish/products/NP-TSP1/spec.html | 2026-08-23 | PRESERVED | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-PANASONIC-NP-TSP1 | NP-TSP1-W | facts[label=開扉時の寸法] / ドア開放時寸法 | 開扉時の奥行は386mm、高さは712mm。扉の途中の軌跡や必要な空間も確認します。 | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://panasonic.jp/dish/products/NP-TSP1/spec.html | 2026-09-10 | KNOWN | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-PANASONIC-NP-TSP1 | NP-TSP1-W | facts[label=必要な余白] / NP-TSP1 サポート確認先 | この型番に適用できる上・左右・背面の必要余白は追加確認中です。後継のNP-TSP2の条件へ置き換えません。 | 公表条件つき。同一コース・同一食器量の実測比較ではない | https://panasonic.jp/dish/products/NP-TSP1/spec.html | 2026-09-10 | UNKNOWN | 主表 `.ps-comparison` の行 | `#ps-installation-context` の詳細表 `.ps-installation-details`（常時表示、確認元・確認日つき） | 主表を判断軸3+給水方式に短縮し、長い条件つきの値を同じ型番の常時表示領域へ移動 | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-PANASONIC-NP-TSP1 | NP-TSP1-W | facts[label=給水方式] ← guide_facts[field=water_supply] / 公式FAQ：タンクへの給水／NP-TSP1 | タンク給水／分岐水栓（給水方式ごとの条件あり） | guide_facts.water_supply の記述から方式名だけを短縮。数値・条件は追加していない | https://jpn.faq.panasonic.com/app/answers/detail/a_id/17176 | 2026-09-10 | KNOWN | guide_facts（給排水ガイドの根拠） | 主表 `.ps-comparison` の行「給水方式」 | 比較の判断軸として給水方式を主表へ追加（同じ出典・確認日・状態を継承） | tests/purchase_support/test_purpose_delta.py::test_water_supply_rows_only_where_the_guide_fact_names_the_method |
| PRD-PANASONIC-NP-TSP1 | NP-TSP1-W | products.caution | 上方へ動く扉の最大高さ712mmと、周囲の余白は分けて確認してください。1店舗の過去の売り切れを、市場全体の販売終了とは扱いません。 | 本体寸法と開扉時・余白の読み分け。数値は既存factの値のみを参照 | 既存facts（開扉時の寸法・必要な余白）の出典 | 既存factsの確認日を継承 | 既存fieldを更新（従来はrendererで未使用） | catalog内のみ（未表示） | 商品カード `.ps-product-caution` と販売枠 `#ps-seller-*`、`#ps-installation-context` の一覧 | 詳細を閉領域だけに置かず、直接流入でも必要な限界が読めるようにする | tests/purchase_support/test_purpose_delta.py::test_moved_facts_keep_value_state_and_source_in_open_detail_table |
| PRD-THANKO-RAKUA-MINI-COLOR | TDWS25SBL / TDWS25SRD | research_issues[manufacturer_inquiry 通常洗浄コースのWh].alternative | （文面。値なし） | 電気代未算定と設置根拠の分離 | 既存research_issueのtarget_url | 既存next_check_onを維持 | DRAFT_NOT_SENT（変更なし） | 旧文「回答までは対象項目を未確認として扱い、その条件での設置や費用を確定しません。」 | 新文「1回の消費電力量が未確認のため、電気代は算定していません。…設置条件は…別に確認します。」（41と5ガイドに反映） | CP41-02。電気代未算定を設置の確認済み根拠の無効化に読ませない（AC12） | tests/purchase_support/test_purpose_delta.py::test_electricity_note_does_not_void_installation_evidence |

## 販売経路の棚卸し（FD-05、2026-09-12）

比較41と83の現在本文が投影する販売先を、通常リンク・広告文面・広告画像に分けて記録する。本文の非広告リンクだけを見て収益化ゼロと判定しない。価格鮮度（RECHECK_REQUIRED）・注文可能性・広告権限・商品同一性は別の判定で、価格未確認だけで正しい通常リンクを外さず、広告未契約を商品の不向き理由にしない。新しいaffiliate parameterや仮URLは追加していない。ASP各社の提携状態は既存準備文書のまま未接続。

| post_id | product | exact_model | kind | seller | url_host | variant_or_note | identity | state | checked_at | rights | handling |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 41 | SOLOTA | NP-TMLK1-K | 通常 | Panasonic Store Plus 楽天市場店 | item.rakuten.co.jp | 商品ページ np-tml1-w（同定済み） | True | AVAILABLE | 2026-09-10T14:23:58.738Z | affiliate=False／link_basis=メーカー運営店の商品ページへの通常リンク。広告用URLや計測パラメーターは使用しない。 | 価格は確認時点。現在総額は断定しない |
| 41 | SOLOTA | NP-TMLK1-K | 広告画像 | 画像提供元（楽天） | hb.afl.rakuten.co.jp | 画像リンク先の構成・送料・保証は未確認 | 画像の同定は登録素材のSHA-256 | RUNTIME_BINDING | 公開時snapshotに固定 | advertiser/link_usage は既存確認票で管理 | 画像リンクを価格・保証の確認と扱わない |
| 41 | ラクアmini color | TDWS25SBL / TDWS25SRD | 通常（未確認） | 販売先未確認 |  |  |  | NO_OFFER |  | 調査課題で管理 | 候補の評価は販売先の有無に依存しない |
| 41 | ラクアmini color | TDWS25SBL / TDWS25SRD | 広告画像 | 画像提供元（楽天） | hb.afl.rakuten.co.jp | 画像リンク先の構成・送料・保証は未確認 | 画像の同定は登録素材のSHA-256 | RUNTIME_BINDING | 公開時snapshotに固定 | advertiser/link_usage は既存確認票で管理 | 画像リンクを価格・保証の確認と扱わない |
| 41 | SS-MA251 | SS-MA251 | 通常 | シロカ公式通販 | store.siroca.jp | SS-MA251 シルバー・オートオープン・新品 | True | AVAILABLE | 2026-09-10T01:43:25+00:00 | affiliate=False／link_basis=公式販売ページへの通常リンク。広告素材・計測パラメーターは使用しない。 | 価格は確認時点。現在総額は断定しない |
| 41 | SS-MA251 | SS-MA251 | 広告画像 | 画像提供元（楽天） | hb.afl.rakuten.co.jp | 画像リンク先の構成・送料・保証は未確認 | 画像の同定は登録素材のSHA-256 | RUNTIME_BINDING | 公開時snapshotに固定 | advertiser/link_usage は既存確認票で管理 | 画像リンクを価格・保証の確認と扱わない |
| 41 | NP-TSP1 | NP-TSP1-W | 通常 | Panasonic Store Plus 楽天市場店 | item.rakuten.co.jp | 商品ページ np-tsp1-w（同定済み） | True | SOLD_OUT | 2026-09-10T14:18:06.011Z | affiliate=False／link_basis=メーカー運営店の商品ページへの通常リンク。広告用URLや計測パラメーターは使用しない。 | 確認時は売り切れ。1店舗の売り切れを市場全体の販売終了とは扱わない |
| 41 | NP-TSP1 | NP-TSP1-W | 広告画像 | 画像提供元（楽天） | hb.afl.rakuten.co.jp | 画像リンク先の構成・送料・保証は未確認 | 画像の同定は登録素材のSHA-256 | RUNTIME_BINDING | 公開時snapshotに固定 | advertiser/link_usage は既存確認票で管理 | 画像リンクを価格・保証の確認と扱わない |
| 83 | エアロフレックスDX2 01521 | 01521-09 | 通常 | エース公式通販 | store.ace.jp | 01521-09 グレー×ホワイト・35L・新品 | True | AVAILABLE | 2026-09-10T01:43:25+00:00 | affiliate=False／link_basis=公式販売ページへの通常リンク。広告素材・計測パラメーターは使用しない。 | 価格は確認時点。現在総額は断定しない |
| 83 | エアロフレックスDX2 01521 | 01521-09 | 広告画像 | 画像提供元（楽天） | hb.afl.rakuten.co.jp | 画像リンク先の構成・送料・保証は未確認 | 画像の同定は登録素材のSHA-256 | RUNTIME_BINDING | 公開時snapshotに固定 | advertiser/link_usage は既存確認票で管理 | 画像リンクを価格・保証の確認と扱わない |
| 83 | C-Lite CS2*09007 | CS2*09007 / 134679-1041 | 通常 | サムソナイト公式ストア | www.samsonite.co.jp | CS2*09007 / 134679-1041 ブラック・55cm・36L（拡張時42L）・新品 | True | AVAILABLE | 2026-09-10T05:46:00+00:00 | affiliate=False／link_basis=公式商品ページのSKU CS2*09007、ブラック、55cm、在庫あり表示とカート欄を確認。通常リンク。 | 価格は確認時点。現在総額は断定しない |
| 83 | C-Lite CS2*09007 | CS2*09007 / 134679-1041 | 広告画像 | 画像提供元（楽天） | hb.afl.rakuten.co.jp | 画像リンク先の構成・送料・保証は未確認 | 画像の同定は登録素材のSHA-256 | RUNTIME_BINDING | 公開時snapshotに固定 | advertiser/link_usage は既存確認票で管理 | 画像リンクを価格・保証の確認と扱わない |
| 83 | APPLITE 4.0 QJ6-68002 | QJ6-68002 | 通常（未確認） | 販売先未確認 |  |  |  | NO_OFFER |  | 調査課題で管理 | 候補の評価は販売先の有無に依存しない |
| 83 | APPLITE 4.0 QJ6-68002 | QJ6-68002 | 広告画像 | 画像提供元（楽天） | hb.afl.rakuten.co.jp | 画像リンク先の構成・送料・保証は未確認 | 画像の同定は登録素材のSHA-256 | RUNTIME_BINDING | 公開時snapshotに固定 | advertiser/link_usage は既存確認票で管理 | 画像リンクを価格・保証の確認と扱わない |
| 83 | FREQUENTER LIEVE 1-250 | 1-250 | 通常（未確認） | 販売先未確認 |  |  |  | NO_OFFER |  | 調査課題で管理 | 候補の評価は販売先の有無に依存しない |
| 83 | FREQUENTER LIEVE 1-250 | 1-250 | 広告画像 | 画像提供元（楽天） | hb.afl.rakuten.co.jp | 画像リンク先の構成・送料・保証は未確認 | 画像の同定は登録素材のSHA-256 | RUNTIME_BINDING | 公開時snapshotに固定 | advertiser/link_usage は既存確認票で管理 | 画像リンクを価格・保証の確認と扱わない |

## 全ページ監査（2026-09-12）の修正記録（WS-B: 生成記事13本）

renderer（`python/raos/application/editorial/purchase_support.py`）、カタログ、費用profile、編集元13本を更新し、`scripts/build_reader_purchase_support_v1.py` で再生成した。価格の表示期限は生成時刻（`datetime.now(timezone.utc)`）で判定し、`--check` は同日中のみ再現する。

- 期限判定: `valid_until` と `checked_at`+24h の早い方を過ぎた offer は価格を表示せず「販売条件の期限切れ・再確認中（確認日／期限）」を表示、`data-ps-price-state="EXPIRED"`。「次回確認」は `valid_until` 翌日以降の未来日を自動表示。
- 商品画像（楽天広告リンク）は、型番照合済みで注文可能な販売先がある候補にだけ投影する（41: SOLOTA・SS-MA251、83: エアロフレックスDX2・C-Lite、30: K11+ Pro、28: 4候補）。それ以外は「商品写真：販売先を照合できるまで未掲載。」の1行。画像リンクbindingは30→18。
- 外部購入CTAは商品カード末尾と販売先パネルの2箇所（結論・比較表は `#ps-seller-…` への内部リンク）。
- 販売先へのリンク数: 41=10（文字CTA4＋画像2サイズ×2＋確認元1）、83=8、30=6、28=16（文字CTA8＋画像2サイズ×4。4候補すべて販売先照合済みのため「合計≤10」は未達。240px版はtheme CSSで非表示）。

### 2026-09-12 に確認した外部情報

| 確認先 | 方法 | 結果 |
|---|---|---|
| https://www.thanko.jp/view/item/000000004715 | WebFetch 10:38Z | TDWS25SBL（ミスティーブルー）／TDWS25SRD（クラシックローズ）、税込36,800円、保証24か月、2色とも「再入荷(予約開始)通知」。offer `thanko-tdws25s` を SOLD_OUT 相当で追加 |
| https://store.siroca.jp/products/ss-mu251?variant=41121812643976 | WebFetch 10:38Z ＋ 商品データ（.js）10:59Z | 「オートオープンタイプ/シルバー(SS-MA251) / 通常商品」が選択済み、税込59,800円、available=true。CB-20 の型番選択注記を追加し確認日時を更新 |
| https://www.samsonite.co.jp/samsonite/c-lite/spinner55exp/black/ss-134679-1041.html | WebFetch 10:38Z | SKU CS2*09007、134679=スタイル・末尾=色。134679-1549はミッドナイトブルー、-1041はブラック。税込83,600円・在庫あり。83の旧型番注記を「同じスタイルの色違い」に |
| https://www.jackery.jp/products/explorer-500-new（.json/.js 商品データ） | curl 10:44Z/10:59Z | 本体のみ 価格59,800円＝比較価格（値引きなし）、available=true。セール価格47,840円は9月10日で終了と扱い、通常価格に更新。HTMLページの価格表示はWebFetchで取得不可 |
| https://panasonic.jp/dish/installation.html | WebFetch | SOLOTAは上方「できるだけあける」、左右の数値記載なし。41・262に「上・左右の必要余白は公式資料で未確認」を明記 |
| np-tsp1.pdf（取扱説明書） | curl＋pypdf（scratchpad） | p.2 長期間使わないときは電源プラグを抜く、p.11 残さいフィルター週に1回・本体月に1回・庫内月に2〜3回、p.12 タンク、p.15 離隔 上方11.5cm・側方0.5cm・後方0.5cm |
| https://jpn.faq.panasonic.com/app/answers/detail/p/1776/a_id/11545/ ほか | WebFetch | 庫内の水抜きは「乾燥」のみ運転（卓上型共通）。26688で庫内お手入れ月2〜3回（NP-TSP1明記） |
| np-tml1.pdf・tdws25s_man_web_01.pdf | pypdf | 本文テキストを抽出できず（フォント埋め込み／画像）。SOLOTAの保管前手順、mini colorの長期不使用手順は「未確認」 |
| https://www.americantourister.jp/（トップ・APPLITE） | WebFetch | サーバー証明書の検証に失敗し取得不可。samsonite.co.jp の検索にもAPPLITEなし。URLは維持し文言を読者向けに変更 |
| https://www.data.thanko.jp/download/manual/tk-mdw22{w,b}_man_web_01.pdf | curl -I | 200（旧 data.thanko.jp は302）。registry の出典URLを更新 |
| item.rakuten.co.jp/panasonic-store/{np-tml1-w,np-tsp1-w} | WebFetch | 価格・在庫の文字列を抽出できず。既存offerは確認日のまま（期限切れ表示） |

未確認のまま残した項目: SOLOTA上・左右余白（数値）、SOLOTA保管前手順、mini color長期不使用手順・洗剤種別・試験条件の洗剤量、SS-MA251試験条件の洗剤量、APPLITE現行販売条件、NP-TSP1再入荷、SOLOTA/NP-TSP1楽天店の現在価格。
