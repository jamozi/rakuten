---
name: raos-wordpress-workflow
description: RAOSのWordPress記事・ページ・テーマの編集、表示確認、公開、再開に使う。WordPressに影響しないコード修正や比較レビューだけには使わない。
---

# WordPress workflow

依頼と既存候補から方式を選び、該当する参照だけを読む。

- 通常の記事・ページ・子テーマ更新は [日常更新](references/everyday.md) と
  [簡易公開](../../../changes/wordpress-direct-publish-v1/README.md) の `owner-direct-v1`。
- 既存の `verified-incremental` 候補の再開を明示された場合だけ [旧候補の再開](references/legacy.md)。
- 記事の選定や根拠のレビューも必要な場合は [編集レビュー](../raos-editorial-review/SKILL.md)。

ユーザーがローカル確認した対象へ「公開して」と指示したら、反映・照合・Git同期へ進む。
日常更新に独立監査、2巡レビュー、監査レポート、wp-admin再承認を追加しない。
previewを公開承認へ置換せず、旧候補を新方式へ自動移行しない。

実行能力・公開状態は現在のread-only statusで確認する。対応するMCP能力があれば先に実呼出しし、
不能時はlist/statusで診断して限定operatorへ切り替える理由を示す。接続失敗だけでローカル準備を止めない。
対象snapshot、競合検出、冪等性、限定権限、停止スイッチ、反映照合を維持する。
公開結果、Git同期結果、未実行の操作を簡潔に返す。
