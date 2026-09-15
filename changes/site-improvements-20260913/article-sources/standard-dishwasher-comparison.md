# 標準容量食洗機：根拠と候補範囲

- 調査日：2026-09-13 JST。寸法不一致の最終実読は11:12:27〜11:12:38 JST（`dimension-source-check.json`）。その他の資料もこのタスクで実読した。
- URL案（統合担当と合意）：`/standard-dishwasher-comparison/`。新規ページ。WordPress IDはUNKNOWN・未取得。
- 容量帯（統合担当の2026-09-13指示）：コンパクト12点以下、標準13〜29点、大容量30点以上。本サイトの入口分類であり、メーカー共通規格や本体の小ささを保証しない。
- 標準の今回の掲載：16〜28点の13機種。公式現行一覧12機種と、製品ページ・説明書を読めたAINX AX-S7。全市場網羅とはしていない。在庫・生産継続を一覧掲載から推定していない。
- 公式一次情報を使用。広告条件・楽天取扱・販売可能性は仕様評価や掲載順の加点に使っていない。
- 下位詳細比較：既存 `/countertop-dishwasher-for-small-households/`（ID41）を保持。改題・置換はしない。

## 現行の候補一覧

`candidate-data.json` に型番、容量、W×D×H、本体込み開扉奥行、給水・乾燥、水量・電力量・洗剤、根拠キー、確認状態を記録。nullはUNKNOWN/UNAVAILABLEで、0を意味しない。

| 型番・仕様の対象 | 点数 | 掲載と識別 | 主な根拠・読んだ箇所 |
| --- | ---: | --- | --- |
| SS-M171 | 16 | シロカ現行一覧。PDW-M151と予約/付属品を分離 | [ベーシック製品ページ](https://www.siroca.co.jp/product/dishwasher_basic/)、[説明書](https://www.siroca.co.jp/im/ss-m171.pdf) p.29仕様、p.31保証 |
| PDW-M151 | 16 | オンラインストア限定。予約なし。付属品欄に給水ホースなし | 同ベーシック製品ページ、[現行比較](https://www.siroca.co.jp/product/dishwasher/) 予約・給水・容量・皿サイズ。保証は他型番から転用せずUNKNOWN |
| SS-MA251（シルバーW/S） | 16 | オートオープン型。温風なし | [アドバンス製品](https://www.siroca.co.jp/product/dishwasher_advance/)、[説明書](https://www.siroca.co.jp/im/ss-ma251.pdf) p.11皿、p.13乾燥、p.17〜20清掃、p.21離隔、p.29仕様、p.31保証 |
| SS-MU251（ホワイトW/W） | 16 | UV型。MA251の自動開扉を転用しない | 同アドバンス製品、[説明書](https://www.siroca.co.jp/im/ss-mu251.pdf) p.29仕様、p.31保証。現行比較表の温風×・オートオープン×・UV○ |
| STTDWADW・白・本体単体 | 16 | JAN4562331784470。公式の17点という見出しは箸類込み。標準収納容量16点を採用 | [ラクア公式](https://www.thanko.jp/view/item/000000003491) 仕様・型番/JAN・保証・白本体のカート表示。セットや旧黒色を同一variantにしない |
| AX-S7 | 16 | JAN4582519730051。製品掲載あり、購入可能状態はUNAVAILABLE | [AINX製品](https://ainx.info/dishwasher_uv) SPEC・説明書リンク、[リンク先PDF](https://peraichi.com/user_files/download/46d94f95-5e75-4a0c-a608-5380f2b944c5) p.7洗剤と16〜17点の並べ方、p.23仕様の標準16点/4.8L/温風。正式仕様16点を表に使用 |
| DWS-33B(W) | 18 | [東芝現行一覧](https://www.toshiba-lifestyle.com/jp/dish-drye/) 掲載 | [DWS-33B仕様](https://www.toshiba-lifestyle.com/jp/dish-drye/dws-33b/) 寸法/仕様と注3：27cm皿を入れると16点。4.5gは試験条件。開扉奥行と個別保証はUNKNOWN |
| NP-TCR5-W | 18 | [パナソニック現行比較](https://panasonic.jp/dish/comparison.html) 掲載 | [個別仕様](https://panasonic.jp/dish/products/NP-TCR5/spec.html) 容量/水量/電力量/寸法、[製品ページ](https://panasonic.jp/dish/products/NP-TCR5.html) 24cm皿・注2の洗剤4g |
| TKDWSLHWH・白・本体単体 | 21 | JAN4580060599820。ファミリースリム | [公式製品](https://www.thanko.jp/view/item/000000004559) 仕様のW370 D510 H452、開扉830mm。26cm皿は上部トレイ取り外し。10g/ジェル推奨、12か月保証。本体のカート表示を確認 |
| NP-TSK2-W/-C | 24 | 色違いを同一仕様の行で比較。TSP系と混同しない | [仕様](https://panasonic.jp/dish/products/NP-TSK2/spec.html) 8L・670Wh・433mm/612mm、[収納例](https://panasonic.jp/dish/products/NP-TSK2.html) 食器12点とフライパン全長45cm/径26cm/高さ6.5cm以下。食器24点＋鍋とはしていない |
| NP-TSP1-W | 24 | 公式比較表に載る従来機。終売とは断定しない | [個別仕様](https://panasonic.jp/dish/products/NP-TSP1/spec.html) 9L（タンク）/670Wh、寸法は下記CONFLICT。在庫・納期・洗剤量は今回未確定 |
| TKDWWDHWH・白・本体単体 | 28 | JAN4580060599455。ファミリーワイド | [公式製品](https://www.thanko.jp/view/item/000000004557) 仕様W548 D360 H496・開扉730mm、28cm皿は上部トレイ取り外し、5.2L/10g/ジェル推奨/12か月保証。本体のカート表示を確認 |
| ADW-M28B(W)/(H) | 28 | [AQUA現行一覧](https://aqua-has.com/dishwasher/) 掲載、[2026-05-13発売資料](https://aqua-has.com/wp-content/uploads/2026/05/ADW-L40B_M28B_pressrelease.pdf) | [仕様](https://aqua-has.com/product/m28b/)、[説明書](https://aqua-has.com/wp-content/uploads/2026/05/ADW-M28B_manual.pdf)、[カタログ](https://aqua-has.com/wp-content/uploads/2026/04/adw_l40b_%EF%BD%8D28b_webc.pdf) |

## 大きさ・収納の補足

- シロカの[据え付けFAQ](https://www.siroca.co.jp/support/食器洗い乾燥機：据え付けについて)をHTTPで実読。SS-MA251/MU251/M171/PDW-M151はドアを開いた奥行76.0cm。底の脚の寸法を本体寸法に使っていない。上面70cm以上/側面5cm以上/背面6cm以上は本体からの余白。SS-MA251説明書p.21の図も目視した。設置面から70cmではない。
- AQUA説明書p.8：本体上面30cm、側面10cm、後面10cm以上。カタログ2頁下部寸法図で取出しに必要な奥行83cm、設置に必要な高さ75.2cmを目視。本文は本体幅37cmだけで置けるとはしない。
- AQUA説明書p.14/30：箸立て/小物入れを取り外して28点。p.15の標準大皿の並べ方は直径23cm以下・高さ2.5cm以下。メーカーの最大収納径と同一だとはしていない。p.15には鍋や深い食器が上段への水流を遮る場合の注意がある。鍋と28点の同時収納を約束していない。
- サンコーの「最大皿径」と「標準点数」は別の条件。ラックやトレイを外す大皿の例を通常の満載点数へ足さない。STTDWADWの26cmはかご基準の有効高さで、大皿径と書き換えていない。
- AINX取説は画像PDF。p.7/p.23をレンダリングし目視済み。p.7には16〜17点、p.23仕様は16点。標準仕様16点を採用し、1点多いことを優位性にしていない。最大大皿径はUNKNOWN。

## NP-TSP1の開扉寸法：CONFLICT

同じ2026-09-13のHTTP200で以下を実読。JSONは寸法部分と応答hashだけを残し、画面に個人情報や認証情報はない。

| 実読日時（JST） | 正確なURL/箇所 | 表記と軸 |
| --- | --- | --- |
| 11:12:27.996777 | https://panasonic.jp/dish/comparison.html / NP-TSP1列・本体外形寸法 | 幅×奥行×高さ。550 × 341〈433〉 × 600〈712〉mm。〈〉はドア開閉時の最大寸法と説明 |
| 11:12:35.326313 | https://panasonic.jp/dish/products/NP-TSP1/spec.html / 本体外形寸法・注6 | 幅550 × 高さ600〈712〉 × 奥行341〈上386,下362〉mm。〈〉はドア開閉時の最大寸法 |
| 11:12:38.558755 | https://panasonic.jp/dish/products/NP-TSK2/spec.html / 本体外形寸法・注8 | 別機種。幅550 × 奥行290〈上433,下362〉 × 高さ500〈612〉mm |

- 比較表のNP-TSP2列も奥行341〈433〉/高さ600〈712〉だが、2026年新機種の数値を2021年NP-TSP1へ移さない。
- 386/433の差を「上扉か下扉か」「本体を含むか」「扉の軌跡か」の違いと推定して解消していない。メーカーの解説が未確認のため、NP-TSP1開扉奥行はnull/未確定。
- 個別specの上386/下362も、比較表の433も、いずれも本体奥行へもう一度足す値として扱わない。
- 既存ID41の入力・表示や採寸ガイドへの影響を統合担当に通知済み。今回の担当は既存記事や共有catalogを変更していない。

## 給水・維持費・保証

- 分岐水栓/タンク両対応の現行候補を掲載。外部容器の自動給水を標準装備として確認できた標準帯機種は今回なし。STTDWADW公式に「本体＋自動給水ポンプセット」があるため、別売オプションの存在としてのみ案内。ポンプの型番・全条件・費用を捏造しない。
- MAXZEN JDW03BS01は外部タンク機だが生産完了。容量帯に合うからと現行候補へ復活させない。
- 消費電力Wは1回の電力量kWhに換算していない。シロカ、東芝、サンコー、AINXは今回のkWh欄UNAVAILABLE。実運転時間から最大電力を掛けていない。
- NP-TCR5は標準コースの600Wh/9L。NP-TSK2は汚れレベル2の670Wh/8L。NP-TSP1は標準食器点数の670Wh/9L（タンク）。AQUAは標準/温風乾燥の530Wh/4.5L（タンク）。各社の食器量・試験条件は違うため、電力量の小ささを洗浄効率の順位にしない。
- AQUA分岐水栓時の電力量は製品仕様表560Wh、カタログ2頁注8では660Whと差がある。本文には一致するタンク値530Whだけを載せ、分岐側の電力量は使わない。水量は分岐6Lと明記。
- 洗剤量の4g/4.5g/5gなど試験条件と、説明書の標準量をラベルで分離。AINX量とNP-TSP1量はUNKNOWN。ジェル推奨はサンコー2ファミリー機種の仕様注記、液体推奨はAINX説明書p.7。
- 清掃：SS-MA251取説p.17は残さいフィルターとメッシュトレイを毎回、p.18〜20はノズル/庫内。AQUA取説p.23〜25はフィルター・ノズル・本体。機種個別の月次回数を他型番に転用していない。
- 保証：シロカ3機種の取説p.31、AQUA取説p.32、サンコー各仕様欄、AINX SPECを実読。確認できた対象にだけ1年/12か月と表示。PDW/東芝/パナソニックは今回の個別保証UNKNOWN。保証優劣の推薦には使わない。
- リコール・長期修理実績・独立実機性能は今回未検証。該当なし・安全性検証済みとしない。購入前の型番照合と通常の編集確認は統合側で実施する。

## 発売予定・除外・確認できなかった範囲

- NP-TSP2：[パナソニック公式発表](https://news.panasonic.com/jp/topics/206815)は2026年9月中旬より発売予定。9月13日に発売済みとは扱わない。ショップの9月18日表記は本稿の根拠に採用せず、発売確認後の更新対象。
- DWS-33A：DWS-33B公式ページの関連商品で在庫限り。現行の同等比較に混在させず旧型枠へ。
- [MAXZENカテゴリ](https://maxzen.jp/product-category/dishwasher/)：JDW03BS01/JDW03BS01-SV/JDW03BS02-Gは生産完了。JDW03BS01個別ページの15点を読めても現行と判定しない。
- [アイリスオーヤマ](https://www.irisohyama.co.jp/products/electrical-appliances/cooking-appliances/other-cooking-appliances/dishwasher/dishwasher)：ISHT-5000-W/KISHT-5000-Wは15点・生産終了。
- [AQUA生産終了一覧](https://aqua-has.com/dishwasher/old-dishwasher/)：ADW-GM3は30点で標準帯外かつ生産終了。
- AINX製品ページにある[公式販売先](https://ainx.stores.jp/items/60c5e3a9d7e1d80d839c2202)は403・ロボット検証画面。制限を迂回しない。商品の在庫/生産終了を403から推定しない。
- 東芝取扱説明書入口は利用条件同意のページ。自動同意操作はせず、一般公開の仕様ページを使用。未確認の開扉寸法・保証を補完しない。
- シロカFAQとAINX PDFはweb工具の安全判定/取得に失敗したため、同じ公開公式URLをHTTP取得して内容確認。AINXの販売先アクセス制限は別であり、こちらは解消していない。

## 写真と図

- `assets/standard-dishes.webp`：最新worktreeの `changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/kitchen-capacity-standard-20260913.webp` の生成済み食器イメージを改変なしでコピー。
- 原画像生成記録：最新worktree `changes/site-improvements-20260913/kitchen-capacity-images.v1.json`。tool=image_gen.imagegen、900×600、SHA256 `6c1c766e69b7e39634f0363e087f255ed21ede528ce3d505a3c0eb5b03027a37`。原図と本候補の表示を目視確認。
- 本タスクのユーザー指示にある生成の暮らしイメージ許可の範囲で、記事の導入写真として提案。既存category用のallowed_uses/registryは触らず、統合時にこの新記事への画像使用を明示登録する。既存制限を自動解除していない。
- 型番・文字の焼き込みなし。食洗機の実機写真・実測収納量の証拠として扱わない。写真のすぐ下にAIの暮らしイメージである旨を表示。
- 本体形状比較は編集部作成のHTML/CSS模式図。幅55/42/37cm・奥行29/44/51cmを共通縮尺で表し、壁・扉の必要寸法を含めないと明記。機種外観は再現していない。
- メーカー写真の転載権利を新たに確認できていないため不使用。既存の楽天画像slotを無断で新slugへ拡張しない。
- `research/*.png` は説明書/カタログのローカル読解用スクリーンショット。記事素材・再利用許諾済み画像ではない。公開・WordPress取り込み・共有themeへのコピー対象外。

## 実行済み確認と残る条件

- `validation.json`：単体プレビューの1366/390/320px。画像読込、横はみ出し0、h1一つ、重複IDなし、欠落アンカーなし、アコーディオン開閉・展開時の390px幅、ページJavaScriptエラー0。
- 1366px全体と390pxの寸法図を目視。スマホの機種比較は縦並び。実WordPress描画ではなく単体HTMLとしての確認。
- 共有WordPress/DBへの書込、共有catalog/registry/generator/theme更新、Git stage/commit/branch操作、production/write/publicationは未実行。
- 統合ownerでの取り込み、相対画像URLの解決、記事の登録、ローカルWordPressのPC/スマートフォン確認、ユーザーレビューは残る。ユーザーのレビュー完了をこの技術確認で代替しない。

## 2026-09-16 W3 変更（承認済みレイアウト。オーナーのBefore/After確認前、公開は未承認）

- KS-015/017：テーマで非表示だった `p.std-scroll-hint`（#std-daily、#std-more）の2件を削除。大容量の非表示の案内と同じ扱いにそろえた。
- KS-026：本文末尾の訂正依頼の連絡先1行はレンダラーが付ける。履歴の項目は追加していない。
