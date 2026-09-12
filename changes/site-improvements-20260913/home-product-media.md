# ホームの商品画像利用条件（2026-09-13）

元の取得・商品同定・利用根拠は [official-media-sources.md](../wordpress-direct-publish-v1/official-media-sources.md) を参照。本書は今回のホーム利用条件の補足であり、元の承認済み snippet や比較記事の登録範囲を書き換えるものではない。

## 対象6商品と利用根拠

| 商品ID | 型番 | 利用根拠 |
| --- | --- | --- |
| PRD-PANASONIC-NP-TMLK1 | NP-TMLK1-K | 楽天生成HTML・下記楽天ルール |
| PRD-SIROCA-SS-MA251 | SS-MA251 | 楽天生成HTML・下記楽天ルール |
| PRD-PROTECA-AEROFLEX-DX2-01521 | 01521-09 | 楽天生成HTML・下記楽天ルール |
| PRD-SAMSONITE-C-LITE-CS2-09007 | CS2*09007 / 134679-1041 | 楽天生成HTML・下記楽天ルール |
| PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY | F155260 | 下記公式メディアキット・掲載ガイドライン |
| PRD-SWITCHBOT-K11-PRO | K11+ Pro | 楽天生成HTML・下記楽天ルール |

2026-09-13 に [楽天アフィリエイトのルール](https://affiliate.rakuten.co.jp/guides/rule/)、[アイロボット公式メディアキット](https://irobotjp.mediaroom.com/media-kits?item=28)、同キットの[掲載ガイドラインPDF](https://irobotjp.mediaroom.com/download/%E6%8E%B2%E8%BC%89%E3%82%AC%E3%82%A4%E3%83%89%E3%83%A9%E3%82%A4%E3%83%B3_Roomba_Mini+%281%29.pdf) を再読した。Mini のガイドラインに2記事だけへの利用制限は確認されず、元の文書・registry の掲載先は従来の実装対象だった。楽天についてもホーム除外を許諾条件とする記載は確認されなかった。今回の利用はユーザーの商品画像・リンク掲載依頼を受け、ホーム専用の明示設定として追加する。

楽天5商品は既存 registry の承認済み240px生成HTMLをそのまま使用する。a/img、画像URL、クリック先、rel、target、サイズを変更せず、300px版の縮小・切抜き・価格数値の付加を行わない。商品名に「（楽天市場）」を添え、広告案内はページ先頭の1か所に置く。

Mini は画像全体・比率・色を保持し、「アイロボット Roomba® Mini 掃除機＆床拭きロボット + AutoEmpty™ 充電ステーション」の正式名と公式素材への出典リンクを表示する。画像自身のリンクは実在する記事内位置 `/compact-robot-vacuum-shortlist/#product-robot-roomba-mini`。未照合の BERMAS・Anker 画像は対象外。

## 表示と計測の境界

純粋 helper は共有catalogの型番、画像レビュー、販売先同定、購入可能offer、原典payloadのhashを確認し、指定6商品だけを作成する。保存本文には安全なslotだけを入れ、元の楽天HTMLはPHPで投影する。ホームID15・front-page query・現在の投稿ID15・公開済みsnapshotと保存フィールドの一致・saved body hash・themeに結び付いたmetadata hash・6商品ID/型番・個別HTML hash・各slotが1個ずつ存在することを確認し、不一致時は投影しない。既存比較記事のkind、最大4商品、掲載先bindingは変更しない。既存のローカルプレビュー判定が成立し、本番 owner-direct class が存在しない場合だけ、再採番された page_on_front を使用する。この場合も query・現在投稿・snapshot の実ID、home slug、保存フィールド、本文hashの一致を必須とし、本番のID15制限は維持する。

ホーム画像には記事の計測属性・bindingを付けず、記事41/83/30のクリックイベントへ混ぜない。新しい計測を有効化せず、この画像経由の成果は未計測として扱う。現行analyticsコードを使うテストでは、6画像の通常/中ボタンクリックについて同意拒否・許可の両方で送信0を確認した。

局所検証は22 tests通過（PHP内21境界ケースを含む）、Ruff通過。本書作成時点では新ホームは未公開。生成物・統合プレビュー・本番反映の状態は親タスクの候補別結果で判断する。
