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
販売先の現況照合と最終テーマ公開・Gitの結果は最終回答に記載する。

## 残件と検証範囲

11一覧・目的別ページはmeta descriptionが未設定。旧ショートコード本文への厳密な
hub照合を現在のHTMLが満たさず、Yoastにも説明がない。これらのIDは現行owner-directの
許可対象外（130,132,133,134,135,137,139,140,141,143,144）。権限を拡張・迂回していない。
本件の6記事のdescriptionは公開後に復旧済み。

一般CMSによる公開本文の再編集はsnapshotの照合を再び失敗させ得る。
今後もtracked patch → owner-direct prepare/preview/publishを使用する。
本番raw本文・opaque購入URL・認証情報はGitへ保存しない。
