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
