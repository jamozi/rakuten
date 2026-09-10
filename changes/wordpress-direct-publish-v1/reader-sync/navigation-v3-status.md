# 共通入口・画像カードの反映と残る公開阻害（2026-09-10）

## 基準と反映済み範囲

PR #254（画像と静的一覧）、#255（最新本文パッチ）、#256（共通入口と新原稿）はマージ済み。今回の追補は #256 のmain 1e010fb4434dc2aafe6bf2d1018b9b0181804848 を基準とする。以前の「Git統合が未完了」「カテゴリ画像が未反映」という記録を現状として引き継がない。

- ホーム15: 「選び方の3ステップ」「商品別に選び方を見る」から /categories/ へ進む共通入口に修正。WPWriter部分更新成功に加え、匿名公開HTML（HTTP200）で新見出し・リンク・3ステップを確認。
- カテゴリ一覧130: 最初の全文置換2回は403で失敗したため停止。その後、既存の各カードへの画像追加4件、カード配置のinline grid指定1件、AI画像注記1件の通常の部分編集が成功した。認証・セキュリティ設定は変更していない。
- categories.html は、最初の全面改稿案ではなく上記部分編集後の保存本文を再取得して同期した。元の説明文・4カテゴリ・4/7/2/2記事の案内・関連する一覧リンクを保持する。画像はWordPressに取り込み済みの762×506の編集イメージ。掲載商品写真・設置例・性能検証ではない。
- 既存15記事の再保存、テーマ、認証、公開スナップショット、robotsの強制変更、ファイアウォール停止は行っていない。

## 検証結果と限界

`python -m unittest discover -s tests/wordpress_reader_navigation_v3 -v` を、取得した編集元と新規テストだけを置いたローカル作業領域で実行。部分編集後の最終HTMLでも7件成功。画像4枚・カテゴリ到達・重複ID・AI注記・編集元のレスポンシブ指定・外部リンク追加なし・共通入口とホームの画像/購入前確認を検査した。ホーム原本はGit blob 9e52b1bf6bd116cc722add5b0d536355c8a97d92と一致を確認してから1箇所だけ変更した。

サイト全体のmake fast、全31ページのブラウザ検証、現コミットCIと同じ範囲の検査ではない。カテゴリ一覧の390/1440px同時ブラウザ検査はタイムアウトしたため、全端末表示を合格と記録しない。旧コミットのCI成功は追補コミットへ流用しない。

## P0: 正常公開記事のnoindexと費用フォーム欠落

匿名公開の再取得で次を実測した。

| URL | HTTP | robots | 追加観測 |
| --- | --- | --- | --- |
| /solota-vs-rakua-mini-plus/ (86) | 200 | noindex, nofollow | 著者メタがシステムアカウント表記 |
| /dishwasher-running-cost/ (266) | 200 | noindex, nofollow | ブラウザ上で費用計算JS・入力欄がない |

266の実ブラウザDOMでは `script[src*='local-running-cost']` はfalse、main内inputは0、費用計算フォームなし。H1は1、390pxでclientWidth/scrollWidthとも390。見切れがないことと機能が動くことを区別する。262〜265は過去の検査で同じnoindex兆候があったが、今回の個別再実査は未実行。

テーマfunctions.phpの `kurashinoshirube_filter_robots` は、direct記事で `kurashinoshirube_direct_article_snapshot` がnullならnoindexを返す。`kurashinoshirube_public_article_identity` は一覧表示・著者メタ・食洗機費用計算JSの読込みにも使われる。本文・タイトルの更新に対して承認済み公開状態が追従していない可能性が高いが、private snapshotの不一致フィールドは未確定。問題は既存Issue #220へ実測値と受入条件を追記した。

### 正規経路での復旧手順

1. 所有者の物理checkoutで現在mainと対象投稿をread-only確認。対象候補は86、262〜266。その他はrobots等を実測し必要な対象だけに限定。
2. 既存owner-direct-v1のstatus/documentで権限と最新本文を取得し、post ID・slug・商品構成・出典日・featured imageを照合する。未取得・権限外なら停止。
3. articles.v1.jsonのpatch_sourceから現在本文をprepareし、候補の内容・画像・購入リンクをpreview。確認した候補のみ、今回の具体的な対象更新の範囲でpublishする。
4. 保存本文readbackに加え、匿名公開HTTPのrobots、canonical、著者、公開一覧、必要なCSS/JSを確認する。266は実際のフォーム入力と有限な入力例、空欄・不正値の扱いまで確認し、欠測をゼロ円にしない。

```sh
python scripts/raos_wordpress_direct_publish.py status
python scripts/raos_wordpress_direct_publish.py prepare --articles solota-vs-rakua-mini-plus,dishwasher-installation-measurement,dishwasher-water-supply-methods,dishwasher-detergent-guide,dishwasher-cleaning-guide,dishwasher-running-cost
# candidate-idはprepareが実際に返した値だけを使う。
python scripts/raos_wordpress_direct_publish.py preview --candidate <candidate-id>
python scripts/raos_wordpress_direct_publish.py publish --candidate <candidate-id>
```

この会話の接続ツールには限定operatorの実行経路が見つからず、ローカル環境のリポジトリ取得もDNS失敗した。そのため上記正規再公開は未実行。robotsだけの強制index化、古いfixtureへの巻き戻し、承認hashの捏造、汎用CMSによる承認境界の迂回はしない。

## 全文保存403の扱い

部分編集成功は全文保存403の原因解明を意味しない。レート制限・WAFルール・ホスト制限のどれかは未確定。必要になった時点で所有者側ログの時刻・ルート・ルールIDを確認し、正規コネクタの必要操作だけに限定して対応する。/wp-json全体の開放や保護機能の恒久停止は行わない。
