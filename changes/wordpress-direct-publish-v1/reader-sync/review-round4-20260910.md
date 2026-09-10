# 公開31ページ再点検とホームの導線修正

確認日：2026-09-10（日本時間）。Gitベース：c17d5f1346fb9e0ff5dbf89282d03b2eae1fc30f。

## 今回の本番変更

ホーム（投稿ID15）だけを、取得済み本文への5つの厳密な部分置換で更新した。元の画像12箇所、広告表示、購入前確認、4カテゴリ・商品比較への既存リンクは保持。

1. cluster-mobility をスーツケースの画像カードに復旧。
2. cluster-home を食洗機・掃除機カード列の先頭（食洗機カード）に復旧。既存の「家事」パンくずが参照する共通位置であり、掃除機専用カテゴリへの直接リンクとは別。
3. cluster-ready をポータブル電源の画像カードに復旧。
4. FEATURE先頭カードの行き先を、省スペースから家事時短の目的別ページへ変更。
5. 同カードを「家事を減らす道具／洗い物と床掃除。任せたい作業から選ぶ。」へ変更。

旧3アンカーを参照していたのは、スーツケース4記事、食洗機主比較・掃除機2記事、電源2記事の計9記事。記事本文や承認スナップショットを更新せず、ホームに実際の移動先を戻した。

## 実取得の結果

既知の31URL（ホーム1、4カテゴリ、横断・目的別一覧11、公開記事15）を匿名HTTP GETで取得し、HTMLParserで解析。外部販売先・購入リンクを踏んでいない。これは実ブラウザの全画面表示検査ではない。

- 31/31がHTTP 200。取得失敗を成功扱いしていない。
- 31/31のH1は1個。重複IDは検出なし。
- 31ページに「現在、条件に合う公開記事はありません」の空一覧表示なし。
- 25ページはindex/followと自己canonicalを出力。
- 下記6記事はnoindex/nofollow、canonicalなし。
- post-sitemap.xmlには9投稿URLを掲載。下記6記事は掲載なし。画像のimage:locは投稿数に数えていない。
- 食洗機費用記事はHTMLにlocal-running-costのscriptなし、main内inputなし。現在の入力式計算機は動作確認済みと扱わない。
- 31URLの範囲内で検出した壊れたページ内参照は、上述の旧ホーム3アンカーを参照する9件。変更後の公開HTMLで3つのidと正しいカテゴリリンクの存在を再取得して確認。

### 検索除外指定が残る6記事（今回未復旧）

| 投稿ID | パス |
|---|---|
| 86 | /solota-vs-rakua-mini-plus/ |
| 262 | /dishwasher-installation-measurement/ |
| 263 | /dishwasher-water-supply-methods/ |
| 264 | /dishwasher-detergent-guide/ |
| 265 | /dishwasher-cleaning-guide/ |
| 266 | /dishwasher-running-cost/ |

以前の2記事の個別確認より影響範囲が広い。テーマの既存direct snapshot／public identity照合と整合する症状だが、非公開メタデータの不一致項目を今回直接確認したわけではない。原因はこの段階では仮説。robotsだけの強制解除、別経路の強制公開、旧fixtureへの巻き戻しは行っていない。

正規復旧は既存owner-directの最新本文取得→対象とsnapshot確認→preview→明示した対象のpublish→匿名HTML／費用フォーム確認が必要。現在利用できるWordPress本文編集操作で、その承認メタデータまで整合させられるとは確認できていない。記事6件への追加の直接編集を避けた。

## その他の確認範囲

/about/は/about-ad-policy/へ転送され200。比較・編集方針も200。31対象外の/privacy-policy/は追加取得がタイムアウトしたため、この試行では状態未確認。404や不通とは断定しない。価格・在庫・商品仕様・性能・法令適合・検索登録の実績は今回の検証に含めない。

## ローカル検証

取得したhome.html原本はGit blob 309d434033524b3a4fe245e818d41e644db0dbc5と一致。編集後はc477d72e0dba2bcb1c94ca3f6f2d5b65d2dc2e80。

`python -m unittest discover -s tests/wordpress_reader_navigation_v3 -p test_legacy_home_routes.py -v`

追加8テストを限定したローカル作業領域で実行。変更前は欠落アンカー3箇所とFEATURE重複で失敗、変更後は全8テスト成功。フルcheckoutのmake fast、全体CI、全31ページの実端末レイアウト合格を意味しない。現コミットCIはGitHubで別確認する。
