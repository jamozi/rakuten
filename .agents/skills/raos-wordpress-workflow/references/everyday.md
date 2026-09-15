# 日常のWordPress更新

商品比較子記事の新規作成・更新では[共通の商品行形式](../../../../changes/reader-purchase-support-v1/comparison-rows.md)を使う。
画像・仕様・参考価格・正規リンクを同じ商品行へ結合し、カテゴリ固有の比較軸は入力データに置く。
画像・価格・リンクの処理や期限判定を記事ごとに作らない。ホーム・カテゴリ等の入口は対象外。

1. `make wordpress-production-request ARGS='direct status'`で限定公開能力を実確認する。
   worktreeでは`direct --owner-checkout /home/minami/rakuten status`のように所有者の保管先を指定し、
   初回設定した認証を使う。記事source・候補・Git保存先は作業中のworktreeのままにする。
   未設定でもlocal作成・prepare・previewは続ける。旧operatorのread-only statusで接続と未設定を区別する。
2. 記事台帳と通常のtracked本文・子テーマsourceを編集する。出典・商品同定・日本語・広告表示を
   作成時に守る。旧記事の取り込みは`direct import-existing`を使い、生成fixtureを編集元にしない。
3. `direct prepare --articles <keys> [--theme]`、`direct preview --candidate <id>`を続けて実行する。
   対象だけをGitへ保存し、固定した本文・テーマをlocal WordPressで確認する。URLと画像を示す。
4. その対象への公開指示があれば`direct publish --candidate <id>`を実行する。
   変更した対象は新候補として扱う。独立監査、性能測定、全件検査、復元演習、PR/CI待ちは追加しない。
5. 通信断では同じ候補のstatusを確認して再開する。Git同期失敗は`direct sync --candidate <id>`で再開し、
   再公開しない。公開結果・Git同期結果・残る操作を簡潔に返す。

初回の本番plugin更新・権限設定は、更新物とlocal検証を完成させてから具体的な操作の承認を得る。
対象snapshot、競合検出、冪等性、限定権限、停止スイッチ、反映照合は維持する。


対象記事の基本確認、テーマ変更時の構文検査と代表画面のPC・スマートフォン確認を行う。
独立監査、2巡レビュー、全件検査、全画面撮影、Lighthouse、復元演習、PR/CI待ちを日常公開の条件にしない。
公開機構・認証・共通基盤自体の開発では、通常の関連回帰テストと必須CIを適用する。
