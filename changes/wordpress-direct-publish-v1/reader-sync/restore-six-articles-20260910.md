# 食洗機6記事の正規公開復旧 — 2026-09-10

## 根因と適用

一般CMS編集後の保存本文と公開snapshotの不一致で、公開identityの照合が失敗していた。
5ガイドは前回のowner-direct公開記録との比較で `block_markup` と `media_ids` の差分を確認。
86の過去snapshotフィールド単位の差分は未取得。6記事とも匿名noindex/nofollow、canonical欠落、
サイトマップ除外を再現し、費用記事はidentity不成立のため既存計算JSが読み込まれていなかった。

最新mainのpatch_source対応には、Git checkpointが `.patch.json` と専用patch engineを
許可しない接続漏れがあった。限定したパスだけを許可し、隣接する任意JSON/Pythonは禁止した。
さらに86の既存 `overflow-x:auto` と生成するCSSがWordPressの `wp_kses_post` で変換され、
公開提案を拒否されていた。スクロールを `overflow:auto` にし、未対応CSSと末尾セミコロンを
生成しないようにした。robots・canonical・snapshot検証の条件は変更していない。

6記事candidate: `fc25725ef3dccb2bcbed4042ef5417ee0e99098f8ee53da590de6cc3095a902a`。
owner-directで6件を一括適用し `PUBLISHED_AND_READBACK_VERIFIED`。
最初のcandidateはHTML検査で適用前に拒否され、公開成功には数えていない。

- 86 `solota-vs-rakua-mini-plus`
- 262 `dishwasher-installation-measurement`
- 263 `dishwasher-water-supply-methods`
- 264 `dishwasher-detergent-guide`
- 265 `dishwasher-cleaning-guide`
- 266 `dishwasher-running-cost`

5ガイドの本文は同一。86はCSS属性のみ。全6件の本文テキスト、リンク・画像、タイトル、抜粋、
分類、画像IDを保持。編集元は現在本文へのtracked patchであり、旧fixtureへ戻していない。
公開前にローカルWordPressのKSESで全6本文が変換なしになることも確認した。

## 本番で確認した結果

全6URL: HTTP200、index/follow、自己参照canonical、H1一つ、重複IDなし。
post-sitemap.xmlは9件から15件になり、6記事すべてをURLのlocとして確認。
検索エンジンによる実際の登録・検索順位・成果・利益は未確認。

費用計算は本番Chromiumで22項目成功。NP-TMLK1-Kの公式値230Wh・2.5Lを使用し、
試験入力30.7円/kWh、262円/m³、洗剤2.1円/回、月30回で9.82円/回、294.48円/月。
0.23kWh・0.0025m³への換算、空欄、明示的0、未確認の消費量、負値・非数・非整数、
キーボード、クリア、再読込、JavaScriptなし、390/1440pxと文字200%を確認。
入力操作中のリクエスト0、DOMStorageイベント0、保存状態の変化なし、再読込で入力消去。
公表値の一次情報: https://panasonic.jp/dish/products/NP-TMLK1/spec.html
これらの単価は試験入力であり、家庭の料金や請求総額を主張しない。

31ページ（ホーム、4カテゴリ、15記事、11一覧・目的別ページ）とリンク先35ページを取得。
966リンク出現を照合しHTTP404なし。記事・カテゴリの本文アンカー欠落なし。
共通フッターのCookieリンクだけが実ブラウザでも無反応だったため、テーマの限定filterで
プライバシーポリシーへの実リンクと正確なラベルに変更。CookieYes用classは保持し、
同意値・計測設定・cookie・通信処理は変更しない。

既知ASPの40 CTAすべてでsponsored/nofollowとCTAより前の広告表示を確認。
購入リンクが存在しない記事・機種を低評価に変更していない。報酬率・取扱有無による順位変更なし。
販売先20件（記事別の重複を含む）のうち、NP-TSP1の1件でHTTP404を別の取得方法でも再現。
残る19件はHTTP200と販売ページtitleの型番一致を確認した。在庫・価格・選択中の色やセットは未確認。
41 `countertop-dishwasher-for-small-households` の該当2 CTAのみ停止案内へ変更し、
商品評価・仕様・順位・メーカー出典は保持した。その他38 CTAのURL/追跡属性は保持した。
owner-direct反映・照合済みの追加候補は `e65d2a2322e8c10de3a3de03ccee6df3236142736131af045e77048990f4c040`。

本番共通テーマcandidate `099c2e6e98e59b757892affad8b9b6b28e6b4d4800a8d3b2894cfcf3014bcdb9` は
反映・照合済み。Cookieリンク修正後の1,072内部リンク出現、35リンク先で404/アンカー欠落0。

既存の外部商品画像を持つ記事のpreviewは、確認済みthumbnail.image.rakuten.co.jp画像だけを
candidateの非公開領域へ保存し、ハッシュを表示runtimeへ束縛する。ブラウザの外部通信は遮断したまま
保存した画像で応答する。折りたたみ内の遅延画像も展開し、デコード後に検査する。
画像URL・画像本体・追跡値をGitへ追加しない。

ローカル全件経路は21,633 passed / 10 failed / 7 skipped / 58 subtests。
検査中のテーマrevision更新で旧revisionを捕捉した10失敗は、最終版の該当3ファイル再検査で
321 passed。最終の対象テストは127 passed / 30 subtests passed、Ruffも成功。
required CIは統合PR #259の最終headで確認する。
旧失敗を後の成功でPASSへ書き換えない。

最終本番確認では31ページ×390/1440pxの62画面でHTTP、H1、横はみ出し、画像読込、
本文アンカー、JavaScriptエラー、旧Cookieリンクの検査に失敗なし。
再実行した費用計算22項目もPASS。残る38 affiliate CTAはrel適正、販売先19件は
HTTP200とtitleの型番一致。広告表示はCTAより前に存在する。

## 残件と検証範囲

11一覧・目的別ページはmeta descriptionが未設定。旧ショートコード本文への厳密な
hub照合を現在のHTMLが満たさず、Yoastにも説明がない。これらのIDは現行owner-directの
許可対象外（130,132,133,134,135,137,139,140,141,143,144）。権限を拡張・迂回していない。
本件の6記事のdescriptionは公開後に復旧済み。

一般CMSによる公開本文の再編集はsnapshotの照合を再び失敗させ得る。
今後もtracked patch → owner-direct prepare/preview/publishを使用する。
本番raw本文・opaque購入URL・認証情報はGitへ保存しない。
