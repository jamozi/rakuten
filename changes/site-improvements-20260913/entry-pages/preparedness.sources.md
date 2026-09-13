# ポータブル電源カテゴリ候補・統合メモ

状態：`LOCAL_DRAFT_AWAITING_USER_REVIEW`。2026-09-13作成。ユーザーによる見た目の確認は未完了。

## 対象と管理元

- 対応ページは **`/preparedness/` の既存固定ページ1件のみ**。本番IDは台帳上 **138**、共有ローカルWPの表示IDは **9**。ID 9を本番に使わない。
- 読み取った最新checkout：`/home/minami/rakuten/.worktrees/all-pages-20260913`。
- 本文owner：上記checkoutの `changes/wordpress-direct-publish-v1/articles/preparedness.html`。
- 台帳owner：同 `changes/wordpress-direct-publish-v1/articles.v1.json` の `article_key=preparedness`。
- 旧 `reader-sync/tools/hub_pages_20260912.py` にカテゴリ生成ロジックがあるが、今回の統合先は日常更新用の通常本文・台帳。古いハブ全体generatorを走らせて他ページを戻さない。
- 共有ローカル参照URL：<http://127.0.0.1:41398/preparedness/>。本文と台帳を読み取り照合した。
- MCP `wordpressEditor.raos_codex_site_status` の読取は成功。代替CMS操作なし。共有WordPress、DB、本番、Git branch/indexには書き込んでいない。

## 候補と取込方法

候補の基点：`/home/minami/rakuten/changes/site-improvements-20260913/page-drafts/power-category/`

1. `article.body.html` を、統合先checkoutの通常本文ownerに取り込む。WordPressのHTMLブロックコメントを含む。`metadata.json` のtitleは現状を維持し、excerptは更新案。
2. `power-category.proposed.css` を既存の子テーマCSSのownerへ統合する。本文の `.ks-power-category` と、それを含むページの見出し・余白に限定。生の page-id-9/138 に依存しない。CSSを記事本文内に直接埋め込まない。
3. `assets/power-capacity-{small,medium,large}-20260913.png` の3枚を統合担当の管理するローカルテーマ素材等へ取り込む。**本文の `src="assets/..."` は専用候補内の相対参照であり、そのままWPへ貼り付けない。** 実際に取り込んだ場所に合わせて3つのsrcを差し替える。既存メーカー商品画像は置換しない。
4. ローカルWPに統合した段階で対象ページを確認する。この担当では共有WPへのprepare/preview/importを実行していない。今回の表示証拠は、読み取ったWPの外枠に本文・専用CSSを載せた静的候補。
5. 新記事3本が別段階で作成・確認されるまで、容量カードへの記事リンクを追加しない。

取り込む成果物は本文、metadata、専用CSS、写真3枚、素材provenance、sources。`preview/` 以下のHTML全体やブラウザprofileはWP本文・テーマへ取り込まない。画像は元の1536×1024 PNGで、3枚計約6.2MiB。公開用の形式圧縮・URL割当は統合時に扱う。

## 容量区分の判断とリンクの状態

最新の確定方針どおり、入口は小容量・中容量・大容量の3つのみ。「使いたい機器から選ぶ」という別の同格分類は作っていない。場面と家電の例は各カードの補助説明に含めた。

| 容量入口 | 編集上の境界案 | 比較記事の状態 | カードのリンク |
| --- | --- | --- | --- |
| 小容量 | 500Wh未満 | `NOT_CREATED` | なし。リンク風ボタンもなし |
| 中容量 | 500Wh以上・1,000Wh未満 | `NOT_CREATED` | なし |
| 大容量 | 1,000Wh以上 | `NOT_CREATED` | なし |

新記事のURL・post ID・全比較対象：`UNKNOWN`。架空slugは発行していない。カード直下に「容量別の比較記事は準備中」と表示。容量境界はユーザー確定値ではなく、今回の編集提案。公称Whで区分し、拡張バッテリー追加後の容量による再分類やメーカー共通規格とは扱わない。

公式の288Wh、512Wh、768Wh、1,024Whという既存比較モデルの分布と、Anker・Jackeryの公式一覧を参考に500/1,000Whを区切りとした。Jackeryの「小型」一覧には1,024Whも入り、BLUETTIは768WhのAC70を「小型」と呼ぶため、メーカーのサイズ呼称とは区別する。

既存補助リンクは次の実在記事に限定する。容量帯全体の包括比較に名前を変えていない。

- `/portable-power-station-guide/`：既存post ID **28**。Anker Solix C300 / Jackery 500 New / BLUETTI AC70 / EcoFlow DELTA 3 Classicの4モデル。`PR・広告リンクあり`を維持。
- `/anker-solix-c300-c800-c1000-differences/`：既存post ID **29**。C300 / C800 Plus / C1000 / C1000 Gen 2の4モデル。`広告リンクなし`を維持。
- 計算例 `#ps-decision-steps`、双方の購入条件 `#ps-offers`、`/prepare-outage/`、編集・広告方針リンクを維持。この記事は既存個別記事の全文・比較基準を変更しない。

## 一次情報と主張の対応

確認日：**2026-09-13**。以下は公開Webの読取。価格・在庫・保証・寿命・充電速度・ソーラー対応を今回のカテゴリの推薦根拠にしていない。

| 出典 | 確認した範囲と使い方 |
| --- | --- |
| [Anker：選び方](https://www.ankerjapan.com/blogs/magazine/how-to-choose-potaden) | 容量Wh、定格出力W、起動電力、出力ポート、用途の考え方。資料中の「定格出力＝電力量」という表現は採用せず、WとWhを分離して自分の言葉で記述。用途別の消費電力・時間を固定値として転載しない。 |
| [Anker：モデル紹介](https://www.ankerjapan.com/blogs/magazine/power-recommend) | 小容量から大容量にわたる公式モデル構成の参照。メーカーのおすすめ順、最上級表現、販売条件による評価は採用しない。 |
| [Jackery：小型モデル一覧](https://www.jackery.jp/collections/small-portable-powerstations) | 比較一覧の99/256/288/512/1,024Whを確認。小型という呼称と本稿の容量区分を同一視しない。Explorer 100 Plusの出力欄のWh表記は出力定義に転載しない。 |
| [Anker Solix C300：A1722](https://www.ankerjapan.com/products/a1722) | 製品仕様欄：バッテリー容量288Wh、定格300W。C300 DCと混同しない。本文の区分根拠には288Whのみを使用。 |
| [Jackery 500 New](https://www.jackery.jp/products/explorer-500-new) | 製品ページ・一覧の512Wh/500W。容量区分の説明には512Whのみ。 |
| [BLUETTI AC70](https://www.bluetti.jp/products/bluetti-ac70) | バッテリー情報欄768Wh、AC合計1,000W。本文の区分根拠には768Whのみ。AC70Pへ転用しない。 |
| [EcoFlow DELTA 3 Classic](https://jp.ecoflow.com/products/delta-3-classic) | 日本向け製品ページの1,024Wh。DELTA 3/DELTA 3 Plus等の別variantに転用しない。 |
| [Anker：扇風機の使用時間](https://www.ankerjapan.com/blogs/magazine/power-electric-fan) | Whが蓄える電気の量で、消費電力と変換損失が使用時間に関わる点を参照。例の効率0.8を全機種共通の実効値や実測値にしない。 |

カードの場面・家電例は**編集上の想定**であり、当該容量帯の全製品で動くという主張ではない。容量別の持続時間、同時使用台数、家全体への給電、家電の動作試験はすべて `UNAVAILABLE`。家電の合計/起動電力・ポート・変換損失・温度の条件を短く表示した。大容量カードでも「冷蔵庫や炊飯器も候補に入れて考えたい人へ」とし、動作を断言しない。

隣接記事の担当へ渡す確認事項：AC70の公式ページ抽出では購入操作文言と「終売」の文言が共存した。表示状態の意味・現在の販売継続はこのカテゴリ担当では確定していない（`UNKNOWN`）。今回のカテゴリでは購入推奨・在庫ありを主張せず、既存4モデル記事の対象名を維持。次段階の製品選定時に実際の表示と機種ライフサイクルを確認する。

## 写真と権利

- 全3枚は、この担当で `image_gen` により2026-09-13に生成。ユーザーの匿名生成ライフスタイル画像の承認に基づく。
- 実在ポータブル電源本体、メーカー画像、ブランドロゴ、配線や稼働試験を描いていない。PC・スマホ、キャンプ、家の備えという想定場面。
- 生成AIイメージと動作非保証を本文の写真直下に表示し、altにも生成イメージと記載。
- ローカル素材の寸法、生成タスクID、hashは `assets/provenance.json`。raw promptやcredentialは保存していない。
- 本番media ID・公開URLは `UNAVAILABLE`。第三者のメーカー画像の利用権を推定していない。

## 表示確認と残る作業

- 確認候補：<http://127.0.0.1:41535/preview/>。ローカルサーバー稼働中のみ利用できる。
- `preview/index.html`：共有WPを読み取った外枠に候補本文を差し込んだ静的確認用。noindex/nofollow、スクリプト除去。ヘッダーの既存no-JSメニューを使う。
- `preview/browser-results.json`：1440/390/320pxで本文写真3枚読込、h1が1つ、容量見出し3つ、容量カードリンク0、重複IDなし、横はみ出しなし。出典折り畳みを開いた状態でもはみ出しなし。ローカル内部リンク10件がHTTP 200、3つのフラグメント到達先あり。ブラウザ実行エラーなし。
- `preview/1440-top.png` / `preview/1440.png` / `preview/390-top.png` / `preview/390.png`：PC・スマートフォン確認画像。`preview/320.png` と `preview/390-sources.png` も保存。
- `make fast`、本番反映・公開照合、ユーザーの見た目レビューは未実施。通常本文・CSSの専用ローカル候補作成のみのため、共有sourceの変更検証や全体testに合格したとは扱わない。
- 統合担当による本文/CSS/素材のローカル取込後の再確認、ユーザーのレビュー、容量別比較記事3本の別段階での作成が残る。公開承認はない。
