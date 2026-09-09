# 共通入口の修正と残る公開阻害（2026-09-10）

## 確認した基準

main 0fc11b58481feb813aa9d7e5f45f7f3c61b1d077。PR #254（画像と静的一覧）、#255（最新本文パッチ）はマージ済み。以前の「Git統合が未完了」という報告を引き継がない。

## この差分

- home.html: 共通案内の見出しを「選び方の3ステップ」、リンク先を /categories/、ラベルを「商品別に選び方を見る」に限定変更。元の画像・記事・購入前確認を保持。変更前のローカル取得内容はGit blob 9e52b1bf6bd116cc722add5b0d536355c8a97d92と照合した。
- categories.html: 公開済みのAI編集イメージ4枚を再利用する画像カード、4カテゴリへの入口、各4/7/2/2記事と購入前確認への案内。モバイルの折返しと画像比率は編集元のinline styleで保持。実物・性能検証の画像と誤認しない注記を維持。
- 新規7テスト: 同一サイトの画像4枚、カテゴリ到達、重複IDなし、画像注記、編集元のレイアウト、外部リンク追加なし、ホーム共通入口と写真・購入前確認の保持。限定したローカル作業領域で実行し7件成功。元のホームでは新テスト1件の失敗も確認。全リポジトリのmake fast、全ページブラウザ検証ではない。

## WordPressの実結果を区別する

- ホーム15: WPWriterの部分更新成功（1か所）。
- カテゴリ一覧130: 新画像カード版の全文保存は2回とも403のHTMLブロック応答で失敗。再送を停止。Gitの新原稿は未反映候補であり、本番がこの版になったと扱わない。従来の4カテゴリへの一覧は保持されている。
- 本差分では既存15記事の再保存、テーマ、認証、公開スナップショット、robots強制上書き、ファイアウォール停止を行わない。

## P0: 正常公開記事のnoindexと機能不整合

現地再取得で /solota-vs-rakua-mini-plus/ はHTTP 200だが robots=noindex,nofollow、著者メタはシステムアカウント名だった。過去の検査では食洗機5ガイド262〜266にも同じ兆候があるが、この記録時点の全5件再検査は未了。読者用の本文・内部リンクを保存できたことは、正規公開状態が有効なことを意味しない。

テーマ functions.php の kurashinoshirube_filter_robots は、direct記事で kurashinoshirube_direct_article_snapshot がnullならnoindexを返す。public_article_identityも一覧表示・著者メタ・食洗機費用計算JSの読込みに使われる。したがって本文更新後の承認済み状態との不整合を疑う。実際のprivate snapshot値は取得せず、個別の不一致フィールドは未確定。

復旧は既存owner-direct-v1経路で行う。検索制限を無条件に外したり、古いfixtureで本文を戻したり、承認hashを手動で捏造しない。

1. 所有者の物理checkoutで現mainと対象投稿をread-onlyで確認。対象候補は86、262、263、264、265、266。その他はrobots等を実測して必要な対象だけに限定。
2. 既存CLIのstatus/documentで対象権限と最新本文を取得し、post ID・slug・商品構成・出典日・featured imageを照合する。権限外や未取得なら停止。
3. articles.v1.jsonのpatch_sourceを使って現在本文から候補をprepare。CLI例は下記。生成候補の内容・既存画像・購入リンクをpreviewで確認してから、今回の明示された対象更新の範囲内でpublishする。
4. 保存本文のreadbackだけでなく、同じURLの匿名公開HTMLでrobots、canonical、著者表示、必要なCSS/JS、費用フォームの有限な入力例と未入力時の挙動を確認する。失敗時は復旧完了としない。

```sh
python scripts/raos_wordpress_direct_publish.py status
python scripts/raos_wordpress_direct_publish.py prepare --articles solota-vs-rakua-mini-plus,dishwasher-installation-measurement,dishwasher-water-supply-methods,dishwasher-detergent-guide,dishwasher-cleaning-guide,dishwasher-running-cost
# candidate-idはprepareが実際に返した値のみ使用する。
python scripts/raos_wordpress_direct_publish.py preview --candidate <candidate-id>
python scripts/raos_wordpress_direct_publish.py publish --candidate <candidate-id>
```

この会話の接続ツールには上記限定operatorの実行経路が見つからず、ローカル環境からのリポジトリ取得もDNS失敗した。そのため正規経路の再公開は未実行。WordPress.comや汎用CMSを使ってこの境界を迂回しない。

## P1: 全文保存403

ホームの小さな更新は通る一方、130の全文保存はブロックされた。これだけではレート制限・WAFルール・ホスト側制限のどれかを確定できない。サイト所有者側のセキュリティログで該当時刻・ルート・ルールIDを確認し、正規コネクタの当該操作に限った対応を行う。/wp-json全体の開放や保護機能の恒久停止はしない。解消後はcategoriesの既存ID130へ候補を適用し、公開HTMLの4画像・4リンク・モバイル表示を確認する。
