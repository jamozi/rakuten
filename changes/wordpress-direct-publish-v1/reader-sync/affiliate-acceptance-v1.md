# アフィリエイト公開面の確認と復旧対象

2026-09-10。目的は「記事を保存できた」と「読者が使える」を分け、検索除外・計算機能欠落を見逃さないこと。

## この変更で実施した内容

比較一覧（ID133）とガイド一覧（ID135）の冒頭に4カテゴリへのページ内リンクを追加。比較一覧には、型番・世代・構成、税込総額と送料・必須付属品、新品等の状態、納期・返品・保証を確認する折り畳み欄を追加した。ポイント・条件付きクーポンを支払総額と混同せず、重要条件が分からない場合には購入を見送る案内を残す。

ガイドの費用記事の紹介は「公表値と計算式で費用を考える」に変更。動いていない計算フォームの修復を済ませたように案内しない。費用記事自身の本文・公開snapshot・認証・権限・検索指定は変更していない。

Gitの2つの一覧原稿は本番の説明より短くなっていたため、保存済みの説明・順序・リンクを採用して同期した。公開記事の比較対象・価格・広告URLは変更しない。

## 新しい検査の範囲

`scripts/raos_public_acceptance.py` は **匿名の公開応答を保存したJSONを解析するだけ** の補助診断。ネットワーク、CMS更新、credential読取り、承認付与はしない。日常公開の新しい必須ゲートや、新規承認経路ではない。

- 200でもnoindex/nofollow、canonical欠落・不一致、H1重複、ID重複、壊れたアンカーを検出。
- 既知の広告リダイレクトホストではsponsored/nofollowと、リンク前の広告表記を確認。
- 計算用HTMLだけでスクリプトがなければ不合格。スクリプトがあっても操作結果未確認なら未完了。
- 未取得ページ、部分HTML、未検査のリンク先を正常や404に変換しない。
- 出力はページパスと理由コードのみ。広告URL・計測識別子・記事本文を出力しない。

入力契約:

```json
{
  "schema": "RAOSAnonymousPageBatchV1",
  "expected_paths": ["/example/"],
  "observations": [{
    "path": "/example/", "status": 200,
    "final_url": "https://kurashinoshirube.com/example/",
    "full_html": true, "html": "<完全な匿名HTML>", "headers": {}
  }]
}
```

`full_html`は抽出された本文断片ではなくhead/bodyを含む完全応答にだけtrueを設定する。`sitemap_paths`は実際に取得したXMLのページlocを解析した場合だけ指定する。画像locをページURLに混ぜない。

`browser_checks.cost_calculation_verified=true`は実ブラウザで空入力・有効入力・未確認費目・単位換算の計算結果まで確認した場合だけ記録する。単なるscriptタグの存在でtrueにしない。

```sh
python scripts/raos_public_acceptance.py --input /path/to/anonymous-response-export.json
python -m unittest discover -s tests/wordpress_public_acceptance -v
```

終了コード: 0=指定した検査範囲で合格、1=確認済み不合格あり、2=不足/入力不正。合格でも実際の検索登録、法令遵守、商品事実、全ASP、在庫価格、表示品質、同意機能、成果発生を証明しない。既知ASP以外のリンクはこの広告ホスト判定の対象外。

## 今回の検証実績

限定ローカル作業領域で34件成功（公開応答検査26＋一覧8）。実装前の20件失敗、変更前一覧の4件失敗を確認してから修正。全リポジトリのmake fast・全体CI、実ブラウザ表示、実収益は別の確認事項。

今回の費用記事の公開再取得ではHTTP200とnoindex/nofollowが残る。入力用スクリプト・フォーム欠落は前回の実ブラウザ観測であり、今回はブラウザ用サービスのクレジット不足で操作の再検証はできていない。これはサイト全体の索引復旧完了ではない。主要食洗機比較で既存の楽天CTAとsponsored/nofollowを確認したが、広告リンクはクリックせず、現販売先の型番・在庫・成約はこの観測では未検証。

## 復旧を先行する6記事

ID86 SOLOTA/ラクアmini Plus比較、262 設置、263 給排水、264 洗剤、265 お手入れ、266 費用。

既存Issue #220の対象を引き継ぐ。一般CMS編集を追加して公開整合性を悪化させず、所有者の既存owner-direct環境で現本文を正規再公開する。旧fixtureへの復帰、robotsの強制解除、認証やkill switchの迂回は禁止。

正本: `changes/wordpress-direct-publish-v1/README.md`。所有者checkoutは `/home/minami/rakuten`。この会話の一般WordPress編集コネクタには、専用owner-direct操作を実行する機能が見つからない。認証情報をチャットに貼らず、既存保管から使う。

復旧後は6URLの匿名200/index/canonical/サイトマップ掲載、費用フォームの実計算、既存CTA・広告表示・画像・出典の保持を確認する。変更が競合する、snapshotが不明、必要権限がない場合は停止して、理由を値やcredentialを漏らさず報告する。
