# 最新本文を保持する読者導線パッチの統合

2026-09-10。画像更新コミット57b6c784のホーム・全カテゴリ・一覧HTML、画像台帳、表示CSS、既存検査はそのまま保持し、公開パイプラインと15記事分の限定編集を追補した。並行作業を旧HTMLで上書きしていない。

## 実装

articles.v1.json は31対象（ホーム1、カテゴリ4、横断・目的別一覧11、記事15）を既存IDで管理する。各行は body_source（静的HTML）か patch_source（最新本文への限定編集）の片方のみ。画像更新側のページタイトルと編集元は維持。記事ではtitle/excerpt/media_idsを固定せず、最新baselineを継承して、追加されたfeatured imageなどを空値で消さない。featured imageフィールド自体の保持・復元はWordPressで別途確認する。

prepare は従来の限定operatorでstatus/documentを読み、id・slug・post_type・publish状態を照合する。最新本文が読めなければPATCH_BASELINE_REQUIREDで停止。JSONをHTMLとして送らず、旧fixtureも使わない。

raos_reader_live_patch.py は商品ID集合、対象見出し、記事キーを照合し、既存の詳細な冒頭・関連記事欄を保持する。欠落した近道の補充と明示的neutral画像の除去に限定する。外部リンクの開始タグ（href/rel/data含む）、確認済み商品画像、商品ID、確認日の文字列は編集前後で同一であることを検査する。新しい外部購入リンク・価格・実機性能は作らない。

合成本文はowner-privateな候補ディレクトリのbodies/へ600権限で凍結し、候補とbody_sha256に結び付ける。既存プレビューもこのハッシュを照合する。公開前確認、限定権限、明示的公開、precondition、kill switch、idempotency、rollback、readbackは維持する。公開権限の拡張や別経路の自動公開は行わない。

## 表示とバックアップの範囲

パッチで扱う既存読者コンポーネントには限定的なinline styleを持たせ、既存のinline宣言を優先する。並行作業側の画像付きページHTMLとCSSは変更しないため、サイト全体のCSSやテーマ配布を完全統合したという意味ではない。

これは最新本文を読み取って編集する仕組みであり、本番全記事の全文をGitにバックアップしたものではない。公開本文・アフィリエイトURLはGitへコピーしない。旧article-fragments.v1.jsonは履歴として非公開権限・未接続のまま維持する。旧5断片ではなく、現在の実行用*.patch.jsonを使う。別の商品構成へ移行する場合は、根拠を確認したうえで対象レシピを再編集する。

## 検証

新規tests/wordpress_reader_completeは隔離ローカル作業領域で37件成功。架空データとread-only operatorスタブで、保護対象保持、異なる対象の拒否、本文凍結・改変検出、プレビュー接続、31ID・15記事の導線を検査した。並行作業の画像付きHTMLの全件検証とフルcheckoutのmake fast/全体CIは最新コミットで別途確認する。未実行をPASSにしない。

```sh
python -m unittest discover -s tests/wordpress_reader_complete -v
python -m unittest discover -s tests/wordpress_reader_live_sync -v
python -m unittest discover -s tests/wordpress_reader_visuals -v
```

本番記事・画像・仕様の全端末検証や、価格・在庫・性能の全面再調査を終えた記録ではない。公開後の実データと現head CIを照合してから完了範囲を判断する。
