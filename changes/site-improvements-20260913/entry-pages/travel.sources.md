# /travel/ カテゴリ候補 — 統合用メモ

更新日：2026-09-13。状態：ユーザーレビューの容量・泊数・機内持ち込み分類と表示削除の指示を反映したローカル候補。再確認待ち。

## 成果物と対象

対象 `/travel/`。ローカル ID **6**、本番 registry ID **142**。環境と slug で対象照合する。

- `body.html`、`travel-category.css`、`assets/travel-*.png`、`assets/manifest.json`。
- プレビューは同じ `http://127.0.0.1:43037/preview.html`。`preview.html` を更新済み。
- PC / スマートフォン画像は `preview/desktop-1440.png`、`preview/mobile-390.png`。容量カードの確認画像は `preview/capacity-cards-1440.png`、`preview/capacity-cards-390.png`。
- 個別6記事の新設は行わない。未作成記事を待たずカテゴリを先に確認する依頼。
- 編集はこの専有ディレクトリのみ。共有 WordPress / DB / 正規テーマ / Git / 本番は変更していない。

## 最終の6入口

| 入口 | 容量・泊数の表示 | リンク先・範囲 |
| --- | --- | --- |
| 小型（機内持ち込み） | 目安：50L未満／1〜3泊 | `/carry-on-suitcase-comparison/`、エース3モデル／通常時・国内100席以上向け |
| 中型 | 目安：50L以上・80L未満／3〜7泊 | リンクなし、比較記事は準備中 |
| 大型 | 目安：80L以上／7泊〜 | リンクなし、比較記事は準備中 |
| 軽さ重視 | 30L以上・本体3kg以下の4モデル | `/lightweight-carry-on-suitcase-under-3kg/` |
| 出し入れ重視 | 前開き・ストッパー付きの4モデル | `/front-open-carry-on-suitcase-with-stopper/` |
| 移動のしやすさ重視 | 比較記事は準備中 | リンクなし |

容量区分の境界は50Lと80L。小数の容量も重複や抜けなく扱う。**ただし小型の入口は容量だけで決める分類ではなく、利用便の機内持ち込み条件への適合も必要**。50L未満なら必ず持ち込めるという主張はしていない。小型全般・全メーカーを網羅した比較とも表現していない。

## 容量・泊数の根拠と編集判断

2026-09-13 に確認した一次情報：

- [エース公式・選び方](https://store.ace.jp/shop/pages/travel-info.aspx) は容量帯を49Lまで、79Lまで、その上の複数区分で案内し、季節や荷物量の個人差を説明している。これを3入口にまとめ、50L未満 / 50L以上80L未満 / 80L以上とした。
- [エース公式の容量別案内](https://store.ace.jp/shop/r/rsuitcase_ssp/?filtercode13=1&filtercode9=79) は29Lまでを1〜2泊、30〜49Lを2〜3泊、50〜59Lを3〜5泊、60〜79Lを5〜7泊、80〜99Lを7〜10泊、100L以上を10泊以上として案内している。
- [80〜99Lの公式案内](https://store.ace.jp/shop/r/r10nights/?filtercode13=1) でも7〜10泊の目安を確認した。

これを編集上まとめ、小型1〜3泊、中型3〜7泊、大型7泊以上を目安とした。日数と泊数を混同せず、泊数が明記された公式の容量別案内を採用。3泊・7泊は荷物量によって隣接区分の双方が候補になる目安であり、泊数で排他的に振り分けるルールではない。本文には「容量・泊数は当サイトの目安です。季節や荷物の量で変わります」と記載。メーカー共通の S/M/L 規格とは表現しない。

## 小型3モデルの外寸照合

公式製品ページと既存リンク先記事を2026-09-13に照合。以下は車輪・持ち手を含む通常時の外寸。

| 製品・公式仕様 | 容量 | H×W×D | 本体重量 | 拡張時 |
| --- | --- | --- | --- | --- |
| [クレスタ06316](https://store.ace.jp/shop/g/g06316-01/) | 34L | 55×35×25cm、合計115cm | 3.2kg | 39L、奥行29cm・合計119cm |
| [ディフェレンス05721](https://store.ace.jp/shop/g/g05721-04) | 32L | 55×36×24cm、合計115cm | 3.5kg | 38L、奥行27cm・合計118cm |
| [マックスパス4 01471](https://store.ace.jp/shop/g/g01471-02) | 40L | 50×40×25cm、合計115cm | 3.6kg | 公式仕様・機能一覧で拡張の記載を確認できず |

[ANA国内線公式](https://www.ana.co.jp/ja/jp/guide/boarding-procedures/baggage/domestic/carry-rule/) の100席以上は各辺55×40×25cm以内かつ合計115cm以内、機内持ち込み手荷物1個と身の回り品1個の総重量10kg以内。[ANA国際線公式](https://www.ana.co.jp/ja/jp/guide/boarding-procedures/baggage/international/carry-rule/) でも同じ外寸・合計重量の条件を確認。寸法には車輪・持ち手を含み、他社運航便は運航会社のルールによる。

3モデルの通常時外寸はこの基準に適合する。重量条件は本体だけでなく中の荷物と身の回り品を含むため、実際の搭乗可否は未確定。クレスタとディフェレンスの拡張時は上記外寸基準を超える。100席未満や別会社のより小さい条件、すべての国際線に適合するとはしない。カードを「通常時・国内100席以上向け」と限定し、冒頭に「機内持ち込みの外寸・重量・個数の条件は、航空会社・便によって異なります。車輪・持ち手を含めて確認し、拡張時は別に確かめましょう。」と記載。

[JAL国内線](https://www.jal.co.jp/jp/ja/dom/baggage/inflight/) / [JAL国際線](https://www.jal.co.jp/jp/ja/inter/baggage/inflight/) の公式ページも参照。数値照合はテキストで確認できたANAの上記正規ページに基づく。

## ユーザー指定による表示削除

- カテゴリ内の「リンク先にPR・広告あり」を削除。リンク先の比較記事の広告表示やサイト共通機構は変更していない。このカテゴリに直接のアフィリエイトリンクを新設していない。
- カテゴリ内のAI画像に関する可視注記を削除。同義の注記を移動・再掲していない。内部の画像生成来歴は次項とmanifestに保持。
- 独立した「飛行機に乗るなら」ブロックを削除。関連する `/carry-on-suitcase-under-100-seats/` への導線は折りたたみ内の比較表・購入条件リンクも含め、このカテゴリから除去。記事自体は変更・削除していない。
- これらの表示要素に属した `ks-visual-travel`、`travel-axes`、`travel-axes-title` の3アンカーは削除指示に伴い終了。他の既存7アンカーは保持。
- 「使いやすさから選ぶ」の3分類・写真・比較範囲・URLは維持。既存3記事の `#ps-specs` / `#ps-offers`、`/comfortable-travel/`、編集・広告方針のリンクも維持。

## 画像の内部来歴

6点は本タスクで OpenAI imagegen により新規生成した匿名の編集イメージ。外部メーカー写真の流用はない。写真中の製品にブランド・型番を割り当てていない。掲載モデルの実写、容量・縮尺比較、実測性能の証拠には使わない。画像内容・altは今回変更していない。

各1448×1086 PNG、合計約13.2MB。元ファイル、寸法、SHA-256は `assets/manifest.json`。確認用原本で配信用最適化は未実施。統合側で配信サイズ・形式を整え、配信ファイルの来歴とURLを記録する。

## 統合経路

参照 checkout：`/home/minami/rakuten/.worktrees/all-pages-20260913`。実際のローカル `wp:post-content` に本文が現れることを初稿時に確認済み。H1はテンプレートが出すため候補本文に重複させない。

本文owner：`scripts/build_site_editorial_pages.py` → `python/raos/application/editorial/site_editorial_pages.py` の travel分岐 → `changes/wordpress-direct-publish-v1/articles/travel.html`。

1. `body.html` の最新候補を通常 source へ移し、生成済みHTMLの直接修正を避ける。
2. 画像を正規資産へ収録し、相対 `assets/travel-*.png` を正規URLへ差し替える。
3. `travel-category.css` を表示側ownerへ統合。すべて `#ks-travel-guide` 内限定。
4. owner generatorで更新し、正規WordPressのKSES・表示確認を実行する。

## 確認と未実行の境界

今回の最新確認は `evidence/capacity-review-checks.json` と容量カードのPC/スマートフォン画像を参照。初稿の `evidence/browser-layout-checks.json`、`evidence/static-checks.json`、`evidence/local-link-checks.json` は初稿時点の記録で、削除済みブロック・リンクを含む旧状態の件数を示す。

同一URLの専用プレビューは公開ローカルHTMLの殻と候補本文の合成。共通CSS等は `127.0.0.1:41398` に依存し、 `/wp-includes/` は専用サーバーから読み取り専用で仲介する。正規WordPressへの本文反映、配信画像最適化、統合後のKSES、ユーザー再確認、本番反映はこのタスクでは未実行。

再生成は `python3 preview/build_preview.py`。サーバーを再起動する場合は `python3 preview/serve_preview.py` が空きポートのURLを表示する。現在のサーバーは43037で継続中。
