# 候補2のJSON-LD意味照合・画像保留

確認日: 2026-09-13 JST。対象origin `http://127.0.0.1:41398`。対象候補は `0c240d945aba1d4659ecb64be0ec85c93a4ea515b2e7af84f22e29bc8d244766` のみ。後続候補や本番反映を自動的に合格扱いにしない。

[15記事の実取得結果](technical-local-semantics.json) に可視H1、time datetime、Articleの公開日・更新日・URL、画像数を保持した。

- 全15記事HTTP200。JSON-LD内Articleは各1件、headlineは可視H1と一致。
- 全15記事のdatePublished/dateModifiedは日付精度で、可視timeの同じ日付と一致。時刻精度の情報があるとは主張しない。dateModifiedは2026-09-13、仕様確認日を全て更新日に塗り替えていない。
- Article.urlはローカルの対象origin＋記事pathと一致。
- Product、Offer、Review、AggregateRatingの出力なし。
- ID82（BERMAS60524を含む比較）、ID29（Anker4モデル）の画像は0件。保留対象の商品画像は表示されていない。
- 商品figure数:41=2、83=2、30=2、28=3、85=2。19/82/84/86/29とガイド5件は0。ID28の3枚はAnker C300を含まない既存許可対象。

判定: 上記の**ローカル意味照合と画像保留はPASS**。rootの34画面幅確認とは別の検証であり、Googleの登録・成果計測・本番公開の証明ではない。

## 方針

2026-09-16 追記。ここは方針の記録で、上の観測記録（2026-09-13 のローカル照合）とは別のもの。観測の結果として読まない。公開本文（/comparison-policy/）は変えていない。

### 採用しない構造化データ

テーマ（functions.php の JSON-LD 出力）は、次の型を出さない。

| 型 | 採用しない理由 | 根拠 |
|---|---|---|
| Product | 複数の商品を比べる記事に、Product Snippet 用の Markup を出さない。 | POL-CONT-027（docs/upstream/key_documents/RAOS_06_editorial_policy_catalog_v0.1.yaml） |
| Offer | 価格は販売先ごとに確認日時付きで JS（purchase-support.js）が補助表示する。キャッシュされる HTML と構造化データには価格を固定せず、存在しない Offer も補完しない。 | POL-CONT-026、purchase_support.py のコメント「Cacheable HTML never contains a price amount」 |
| Review | 実機を使っていない記事では、レビュー系の構造化データを出さない。楽天の評価も転用しない。 | POL-CONT-026、POL-CONT-029、/comparison-policy/ の「構造化データ」節 |
| AggregateRating | 楽天の平均評価・件数から作らない。レビュー件数や星評価を独自に集計した順位も載せない。 | POL-CONT-029、/comparison-policy/ の「構造化データ」節 |
| FAQPage | 本文に FAQ を載せても、FAQPage の JSON-LD は生成しない。 | POL-CONT-028 |
| ItemList | OWNER_DECISION_PENDING（一覧ページで使わない理由はオーナーが決める。未記入のまま扱う） | 社内ルールなし（OWNER_DECISION_PENDING） |

### 方針ページのパンくず（KS-029-b3）

about-ad-policy、comparison-policy、privacy-policy の 3 ページには、本文に見えるパンくずが無い。見える本文と構造化データを一致させるため、テーマはこの 3 ページで BreadcrumbList を出さず、WebPage（about-ad-policy は AboutPage）の breadcrumb も出さない。記事とハブのページは、これまでどおり BreadcrumbList を出す。

採らなかった案: 3 ページの本文の先頭に見えるパンくずを足す案。3 ページは会話レビュー台帳で未レビューのため、本文の見た目を変えるこの案は採らなかった。
