---
name: raos-wordpress-workflow
description: RAOSのWordPress記事・固定ページ・ホーム・テーマ・表示pluginの編集、local表示確認、公開準備、承認済み反映や通信断からの再開に使う。WordPressに影響しないコード修正や、表示・公開を伴わない比較レビューだけでは使わない。
---

# WordPress workflow

## Input and references

依頼された段階、対象記事・投稿ID・共有変更、tracked source、既存候補と検査レポートを特定する。
実値・承認状態が不明なら作らない。既存候補は上書きしない。

- [段階・準備・失効・再開の正本](../../../docs/runbooks/wordpress-verified-incremental.md)
- [local preview](../../../changes/wordpress-local-preview-v1/README.md)
- [bounded MCP](../../../changes/wordpress-mcp-v1/README.md)
- 記事品質の判断が必要な時だけ[editorial review](../raos-editorial-review/SKILL.md)

## Procedure

1. 対応能力のある`wordpressEditor` / `wordpressDeployment`でread-only statusを実呼出しする。
   能力が使えなければMCP list/statusで診断し、理由と必要な代替を示す。optional tool不在と障害を区別する。
2. runbookの該当段階だけ読む。既存prepareレポートの対象・失敗・期限から再開地点を決める。
3. `make wordpress-production-request`のplan/prepareと既存local previewを使う。
   文章・表示はtracked sourceで修正し、依頼範囲の検査とURL・viewport画像を確認する。
4. 提案・反映は依頼された段階と既存の独立監査・CI・wp-admin承認等を満たす時だけ進む。
   各段階の期限・precondition・idempotency・kill switchはrunbookと実装に従う。
5. 通信断ではoperation status/recoveryとreadbackを使い、同じ作用を推測で再送しない。

## Validation and output

有効な同一入力の結果は元の検査日時で再利用し、変更・失効した単位を再検査する。
prepare失敗はlocalで修正を続ける。失効承認を更新したことにして提案・適用しない。
自己承認、汎用CMS迂回、gate有効化、任意command/PHP/SQL/URL実行は行わない。

対象と到達段階、確認URL、実行/再利用した検査、スクリーンショット保存先、外部実行の有無、
残る条件を返す。未実施の表示検査や本番照合を合格と呼ばない。
