# F: 公開側・外部到達確認（2026-09-13 JST）

対象は編集前の本番34 URLと、公開REST・実リンクから得た自動生成URL。read-only GETのみ。本番変更、広告リダイレクトへのクリック、購入・計測イベント送信、認証情報・個人情報取得は行っていない。検索テストの語句・URLクエリ値は証跡に保持しない。ローカル候補の合格やGoogleの登録・リッチリザルト採用を意味しない。

詳細証跡: [公開34ページと自動生成URL](technical-public-verification.json)、[31商品の公式到達先](technical-official-destinations.json)。製品内容の照合根拠は [catalog research](research-catalog.md) を併読する。

## Q04: 分類・自動生成ページ

公開REST `/wp-json/wp/v2/posts` と `/pages` を `id,link,categories,tags` 等の必要項目だけに限定して取得。15投稿・19固定ページで34 URL、すべてHTTP200。タグRESTは空配列。分類は category5「暮らしの道具」15件、category1 `uncategorized` 0件。15投稿はすべてcategory5、タグなし。

| 編集ハブ（固定ページ） | 対象投稿ID | WP分類との関係 |
| --- | --- | --- |
| /travel/ | 19,82,83,84 | 全てcategory5。スーツケース4記事の編集入口 |
| /kitchen/ | 41,86,262,263,264,265,266 | 全てcategory5。比較2・ガイド5の編集入口 |
| /cleaning/ | 30,85 | 全てcategory5。掃除機2記事の編集入口 |
| /preparedness/ | 28,29 | 全てcategory5。電源2記事の編集入口 |

4ハブは4個のWPカテゴリではない。既存のカテゴリURL2件はともに301→`/updates/`→200、最終canonicalも更新一覧。重複した一覧を残す必要性や分類分割の新要件は今回の観測から出ていない。index方針を変更しなかった。

| 実確認対象 | 結果・戻り先 | 限界 |
| --- | --- | --- |
| カテゴリ2件 | 実RESTリンクからGET、301→updates、index/follow | 過去被リンクやGoogle登録状況は未取得 |
| タグ | 公開REST0件 | 実在URLがないため架空タグを作って試していない |
| 著者 | 34ページに著者アーカイブリンクなし。公開users RESTを `link` のみに限定して要求したが401 rest_forbidden | 実在著者URL未取得。推測slugや非公開ユーザー情報は使わず、動作未確認 |
| 添付5件 | 公開media RESTの `id,link` から取得。5件すべて301→対応する公開png/webp→200 | 画像ファイルにHTML robots metaはない。画像インデックスの状態は未取得 |
| 検索（該当あり） | 200、noindex/follow。食洗機比較・ガイドへの実リンクあり | Google検索での登録可否は未取得 |
| 検索（該当なし） | 200、noindex/follow。「一致する記事はありません」、短い語句での再検索案内、再検索フォーム、ホームへ戻るリンク | テスト用語句は証跡から省略 |
| ページ送り | 実際の検索結果内で発見した `/page/2/`（検索条件付き）をGET、200、noindex/follow、再検索フォームあり | クエリを省略した記録URL単独の結果を検証したという意味ではない |
| 存在しないURL | 実HTTP404、noindex/nofollow。再検索とホーム、カテゴリ、4ハブへのリンクあり | 無制限な未知URL網羅ではない |

通常34 URLは全件index/follow。これはmeta robotsの観測で、Googleの実インデックス登録ではない。カテゴリ転送・検索noindex・添付転送は既存動作であり今回新しく設定していない。

判定: **実在取得対象は確認済み、著者はUNAVAILABLE**。4ハブと分類の対応、検索/404の戻り先は確認できた。実在しないタグ、取得不能な著者を成功扱いにしない。

## Q05: JSON-LDの内容

34ページの最終HTTPレスポンス中の全 `application/ld+json` を再帰解析し、Yoast・テーマ・本文の混在を含めて型と内容を検査。

- 全34ページでJSON構文エラーなし。
- 15投稿それぞれにArticleが1件。全15件のheadlineは可視H1と一致、Article.urlは取得最終URLと一致。
- datePublished/dateModifiedのUTC時刻を、可視`time[datetime]`のタイムゾーン付き時刻と比較。全15件とも同じ瞬間を表す。
- 本番dateModifiedは2026-09-12 UTC / 2026-09-13 JSTの保存日時。本文中の仕様確認日・編集履歴には9/10–9/12など別日付がある。両者を「全商品を9/13に再調査した」証拠としない。今回候補はroot/entry_pagesが編集日と確認日を分離するため、候補の最終表示は別途確認が必要。
- 34ページ全体にProduct、Review、AggregateRating、Offerは出ていない。したがって現在価格・レビュー点数・実機評価を構造化データで捏造している出力は今回の取得内では検出なし。
- Breadcrumbの実対象を抽出。例えばランニングコスト記事はHome→kitchen→当該記事。4ハブを親にする経路が存在し、単一WPカテゴリの名前へ一律に寄せた出力ではない。
- 型はArticle/WebPage/AboutPage/CollectionPage/BreadcrumbList/WebSite/Organization/ImageObject等。商品写真ではない編集画像のImageObjectをProduct型と混同しない。

判定: **本番34 URLの上記意味照合はPASS（限定範囲）**。Google Rich Results Test、Search Console、ローカル候補全34URLの最終出力はこの証跡に含まない。構文成功だけを内容一致と扱っていない。

## Q07: 公式到達先と広告最終遷移

catalog31商品の `official_url` を各1回GET（最大並列4、商品ごとの到達先とレスポンス題名を保存）。広告URLへはアクセスしておらず、広告URLの無改変性・型番照合の既存証跡を置き換えない。

- 29/31はHTTP200。取得後の正規到達パスを証跡に保持。クエリ値は保存しない。
- Samsonite C-LiteはHTTP406。取得経路の制限であり販売終了・在庫切れではない。
- American Tourister Applite 4はTLS検証エラー。証明書検証を無効化して迂回していない。購入不可とは判断しない。
- INV50は今回の直接GETで200。前段のweb取得失敗は一時的な取得経路の問題だった可能性があるが、200だけでPC収納寸法・開口構造・在庫の確認済みに変更しない。
- ace05721/01471等は末尾スラッシュを正規化する到達先、Mini Slimは商品カテゴリ配下への到達を記録。型番・色・構成の根拠はcatalogとresearch-catalog.mdにある個別一次資料の照合を使う。
- miniPlusの通知表示、Anker型番・世代・ポート、BERMAS60524新旧商品差などの個別確認はresearch-catalog.mdに記録。HTTP成功をその色・構成の注文可能状態としない。

判定: **直接公式URLの到達は29確認/2UNAVAILABLE。全広告・画像リンクの最終商品/色/構成/状態/販売店一致は未完了**。ASP規約・許可された検証方法の確認なしに大量リダイレクトアクセスを行わない。成果計上・承認率は遷移成功から推定しない。必要な次の確認は、既存広告URLを所有者が許可された方法で個別に照合し、最終型番・選択variant・ショップ・状態を記録すること。

## 計測の取得可否

現セッションのツールメタデータをmeasurement/metrics/analytics/aggregate/GA4/GSC/Search Consoleで確認。WordPress Editorの共通説明にはaggregate-only measurement readsがあるが、実際の公開ツール一覧に計測aggregateを読む呼出しが存在しない。非公開endpointやrawイベントへの迂回はしない。

- GSC aggregate: **UNAVAILABLE（callable aggregate toolなし）**。
- GA4 aggregate: **UNAVAILABLE（callable aggregate toolなし）**。
- ASP承認成果/確定報酬aggregate: **UNAVAILABLE（callable aggregate toolなし）**。

0件・0円・未接続・正常計測のどれにも置換していない。Google側の実登録、計測疎通、成果承認は未確認のまま。

## 後続の有限QA・候補2確認

初回記録後、明示された読み取り到達確認の範囲でruntimeの26固有URLを各1回確認した。内訳は広告16・通常10で、広告16は最終楽天商品ページへHTTP200。全variant/注文可能性の確定とはしない。[有限到達確認の追補](technical-ad-destinations.md) を参照。

候補2 `0c240d945aba1d4659ecb64be0ec85c93a4ea515b2e7af84f22e29bc8d244766` の15記事の意味照合も実施した。[候補2の結果](technical-local-semantics.md) は当該候補だけに有効で、本番や後続候補の自動PASSではない。
