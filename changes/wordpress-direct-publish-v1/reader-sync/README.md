# 読者導線と画像の公開ソース（2026-09-10）

## 今回更新した範囲

ホーム、4カテゴリ、11横断・目的別一覧を `../articles/*.html` に保存し、`../articles.v1.json` の既存WordPressページIDへ接続した。動的shortcodeだけの一覧が公開側で「現在、条件に合う公開記事はありません」と返すケースを確認したため、掲載対象を明示した編集可能HTMLへ置換する。実際に存在する15記事へのリンクを使い、未公開記事を作らない。

4カテゴリは条件整理→記事選択→購入前確認の3入口を持つ。掲載記事数は旅行4・食洗機7・掃除機2・電源2。本文と出典の確認日を区別し、在庫・実機性能・全市場網羅を推測で追加しない。

`visual-assets.v1.json` はWordPressへ取り込んだ4枚のAI編集イメージの台帳。商品写真、測定・性能根拠、設置図には使用しない。幅・高さは実際の762×506ピクセル。1536×1024の生成シートから切り出し、拡大処理はしていない。sha256とbytesは取り込み前のローカルWebPに対する記録。ユーザー指定はImages 2.5だが、生成ツールは実行モデル名を返しておらずモデル選択を確認したとは記録しない。

ホームの4カテゴリ画像カードと8か所のテーマ別イメージを更新し、4カテゴリの導入画像も公開。既存15記事には台帳の画像をWordPressのfeatured imageとして設定した。これは本文の個別商品画像ではない。画像はWordPressのuploadsへ保存済みで、一時転送用の共有先に依存しない。一時署名URL・認証情報はGitへ保存しない。

## 公開処理と安全境界

この差分は公開権限・kill switch・認証・比較商品レジストリを変更しない。日常公開は既存owner-direct-v1のpreview/precondition/readbackを維持する。ページIDを台帳に書くことは実行主体の権限拡大ではない。対象権限のないページを別経路で自動公開しない。

食洗機5ガイドは既存投稿262〜266への紐付けを保持。`media_ids`の空配列を固定せず、既存prepareのbaseline継承に委ねる。thumbnailの保持・復元は別途WordPressのfeatured imageフィールドを実読して確認すること。

## 残っている境界（完了扱いにしない）

`article-fragments.v1.json` は前回取得した5記事の断片であり、引き続き CAPTURED_NOT_WIRED_TO_PUBLICATION / publication_authority=false。今回の15記事の全文ソース同期を示すものではない。特にSOLOTA記事はその後公式仕様の比較へ改訂されており、古い断片を自動再挿入しない。Gitの旧比較fixtureと本番の比較対象は異なるため、公開前に最新の本文・型番・構成と照合する。

`visual-layout.css` と `additional-css.css` は、本番Additional CSSへ適用した表示ルールの保管。テーマ配布物への自動統合・展開を完了した記録ではない。既存のAdditional CSS全体を置換しない。HTMLソースは公開と同じ導線を持つ編集版で、一部の繰り返す説明・inline styleを整理している。保存本文のバイト単位バックアップとは呼ばない。

## 実施した検証

- 新規 `tests/wordpress_reader_visuals`：ファイル未作成で失敗を確認後、10テスト成功。4画像、15記事対応、同一ホスト、寸法、画像と性能根拠の分離、重複ID、同一ページリンク、ホーム購入前確認を検査。
- 本番ホームの遠隔ブラウザ実測：1440px viewportでclientWidth/scrollWidthとも1425px、390px viewportでとも375px。H1は両方1個。4画像のnaturalWidth/Heightは762/506、画像ロード失敗なし。home-purchase-checkが存在。
- 旅行カテゴリの公開HTMLをHTTP 200で再取得し、生成画像・AI表示・4記事リンクを確認。
- サイト全30ページのクロールは取得上限/429により完走していない。全記事のリンク・全端末・アクセシビリティ・性能が合格したとは記録しない。
- GitHubの現在headでの必須CIはPRのcheck runで別に確認。旧コミットの成功を流用しない。

```sh
python -m unittest discover -s tests/wordpress_reader_visuals -v
python -m unittest discover -s tests/wordpress_reader_live_sync -v
```
