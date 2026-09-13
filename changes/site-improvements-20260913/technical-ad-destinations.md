# Q07 有限の最終到達確認（追補）

2026-09-13 JST。ユーザー承認済みの読み取りによる到達確認として、候補2のruntime bindingに実際に許可された26固有URLを各1回だけ要求した。ログイン、フォーム送信、カート、購入、再読込は行っていない。広告URL、リダイレクト途中のURL、クエリ値は保存しない。詳細は [到達証跡](technical-ad-destinations.json)。

対象候補: `0c240d945aba1d4659ecb64be0ec85c93a4ea515b2e7af84f22e29bc8d244766`。runtime hashはJSONに記録。runtimeのaffiliateフィールドは文字列であり、26件の内訳は **trueが16広告URL、falseが10通常URL**。26件すべてを広告と数えない。withheldとなった旧素材のURLは含まない。

26件中25件HTTP200、Samsonite通常公式1件が406。広告16件はすべて楽天の最終商品ページへ到達した。各サイズの画像広告はURL自体が異なるためそれぞれ1回ずつ確認。同じmerchant pathへ到達することも確認した。HTTP成功だけでは選択済み色・構成・注文可能性・成果計上を証明しない。

| 対象 | 実際の最終ホスト/パス | 一致した内容・残る条件 |
| --- | --- | --- |
| SOLOTA画像2件 | item.rakuten.co.jp/emedama/4550719155769/ | NP-TMLK1-K、ブラック、カメラのキタムラを題名で確認。現在の注文可能性は未確認 |
| SOLOTA通常1件 | item.rakuten.co.jp/panasonic-store/np-tml1-w/ | 公式店、NP-TML1/TMLK1の2色選択ページ。NP-TMLK1-K記載はあるが初期選択色を確定しない |
| siroca画像2件 | item.rakuten.co.jp/siroca/ss-ma251/ | SS-MA251、シルバー、シロカ公式ストアを題名で確認 |
| siroca通常1件 | store.siroca.jp/products/ss-mu251 | SS-MU251/SS-MA251合同商品ページ。選択構成は別途確認 |
| Aeroflex画像2件 | item.rakuten.co.jp/ace-store/01521/ | エアロフレックスDX2、35L、01521、公式店を題名で確認。suffix09の選択色は未確認 |
| Aeroflex通常1件 | store.ace.jp/shop/g/g01521-09/ | 01521・09グレー×ホワイトを題名で確認 |
| C-Lite画像2件 | item.rakuten.co.jp/samsonite/cs2-007/ | シーライトCS2スピナー55エキスパンダブル36/42L、公式店を題名で確認。exact variant CS2*09007 / 134679-1041は未確認 |
| C-Lite通常1件 | www.samsonite.co.jp/samsonite/c-lite/spinner55exp/black/ss-134679-1041.html | 406。販売終了・欠品とは判断しない |
| Mini通常1件 | store.irobot-jp.com/item/F155260.html | Mini+AutoEmptyを題名、F155260を本文で確認 |
| K11画像2件 | item.rakuten.co.jp/r-kojima/0810224630279/ | K11+Pro、W3004100、アイボリー、コジマを題名で確認。空白の有無によるliteral比較失敗はモデル相違ではない |
| K11通常1件 | www.switchbot.jp/products/switchbot-robot-vacuum-cleaner-k11-pro | K11+ Proを確認 |
| C300通常1件 | www.ankerjapan.com/products/a1722 | C300 Portable Power Station、A17225Z1本文記載を確認。停止済みの広告画像は対象外 |
| Jackery画像2件/通常1件 | item.rakuten.co.jp/jackery-japan/n-p-400200-bkor-jk2/ / www.jackery.jp/products/explorer-500-new | 500 New・512Wh・500W・Jackeryを確認。タイトルの期間限定価格をcatalogへ転記しない |
| AC70画像2件/通常1件 | item.rakuten.co.jp/bluettijapan/bluettijapan_ac70/ / www.bluetti.jp/products/bluetti-ac70 | AC70・BLUETTIを確認。タイトルのクーポン価格を現行価格として採用しない |
| DELTA画像2件/通常1件 | item.rakuten.co.jp/ecmaison/compass1782726434/ / jp.ecoflow.com/products/delta-3-classic | DELTA 3 CLASSIC。楽天側題名は新品・株式会社ECメゾン・**1年保証**。公式販売の保証と同一条件だと扱わない |

判定: **有限到達確認は実施済み（広告16件到達、通常9件到達/1件取得不能）。全色・構成・販売状態の一致は部分確認**。在庫・選択variant・保証適用可否・成果承認は未確認のまま。画像提供元リンクは購入条件を全面検証したリンクと同一扱いにしない。手元の広告URLを変更していない。

この追補はtechnical-external-verification.mdの初回「広告クリック未実施」時点の記述を更新する。初回通常31商品の確認と、今回runtime26リンクの確認は別集合である。
