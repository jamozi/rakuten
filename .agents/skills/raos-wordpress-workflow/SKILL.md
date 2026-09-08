---
name: raos-wordpress-workflow
description: RAOSのWordPress記事・固定ページ・ホーム・テーマ・表示pluginの編集、local表示確認、公開準備、承認済み反映や通信断からの再開に使う。WordPressに影響しないコード修正や、表示・公開を伴わない比較レビューだけでは使わない。
---

# WordPress workflow

通常の記事作成・更新・子テーマ変更は[簡易公開](../../../changes/wordpress-direct-publish-v1/README.md)の
`owner-direct-v1`を使う。ユーザーがローカル確認した対象へ「公開して」と指示したら、その1回で
反映・照合・Git同期へ進む。独立監査、2巡レビュー、監査レポート、wp-admin再承認を追加しない。
以下の旧runbook手順は、既存の`verified-incremental`候補の再開を明示された場合だけ適用する。

## Everyday procedure

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

## Legacy candidate input and references

依頼された段階、対象記事・投稿ID・共有変更、tracked source、既存候補と検査レポートを特定する。
実値・承認状態が不明なら作らない。既存候補は上書きしない。

- [段階・準備・失効・再開の正本](../../../docs/runbooks/wordpress-verified-incremental.md)
- [local preview](../../../changes/wordpress-local-preview-v1/README.md)
- [bounded MCP](../../../changes/wordpress-mcp-v1/README.md)
- 記事品質の判断が必要な時だけ[editorial review](../raos-editorial-review/SKILL.md)

## Legacy procedure

1. 対応能力のある`wordpressEditor` / `wordpressDeployment`でread-only statusを実呼出しする。
   能力が使えなければMCP list/statusで診断し、理由と必要な代替を示す。optional tool不在と障害を区別する。
2. runbookの該当段階だけ読む。既存prepareレポートの対象・失敗・期限から再開地点を決める。
3. `make wordpress-production-request`のplan/prepareと既存local previewを使う。
   文章・表示はtracked sourceで修正し、依頼範囲の検査とURL・viewport画像を確認する。
4. 提案・反映は依頼された段階と既存の独立監査・CI・wp-admin承認等を満たす時だけ進む。
   各段階の期限・precondition・idempotency・kill switchはrunbookと実装に従う。
5. 通信断ではoperation status/recoveryとreadbackを使い、同じ作用を推測で再送しない。

## Legacy validation and output

有効な同一入力の結果は元の検査日時で再利用し、変更・失効した単位を再検査する。
prepare失敗はlocalで修正を続ける。失効承認を更新したことにして提案・適用しない。
自己承認、汎用CMS迂回、gate有効化、任意command/PHP/SQL/URL実行は行わない。

対象と到達段階、確認URL、実行/再利用した検査、スクリーンショット保存先、外部実行の有無、
残る条件を返す。未実施の表示検査や本番照合を合格と呼ばない。
