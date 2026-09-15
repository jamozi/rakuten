# 全34ページ改善（2026-09-13）

所有者が採用した全136項目の改善。詳細と受入条件は [監査原文](audit-source.md) の各IDを参照する。
現在の色・許諾済み画像・URL/ID/既存アンカーを維持し、価格は確認後24時間以内かつ提供元の期限内だけ補助表示する。
元Excelは変更せず、対応結果と実施した証拠を別の進捗版にまとめる。未実行を完了にしない。

## 実装と正本

| 範囲 | 正本と変更 |
| --- | --- |
| A/B/C | `changes/reader-purchase-support-v1/purchase-support.v1.json` の31商品・10比較。6記事を保存本文から通常の本文テンプレートへ移行 |
| B/F | `purchase_support.py` とテーマの `purchase-support.js`。静的販売価格を除去し、期限・欠損費目・型番・広告属性を検証 |
| D | `site_guide_improvements.py` と共通商品データ。5手順記事、現行4機種と旧機種の分離、図・材質表・具体的清掃手順・入力不要の費用例 |
| E | `site_editorial_pages.py` と `entry-pages.v1.json`。ホーム、カテゴリ、目的、記事一覧の役割・実質更新日・件数・広告表示を生成 |
| F | `site_improvements_audit.mjs` と `site_improvements_progress.py`。34ページ確認、元Excelを保持した136項目の進捗版 |

共通仕様: 商品の主比較と補足構成を分離。既存4比較/16商品を10比較へ明示拡張し、任意商品を自動公開しない。
価格確認と編集更新の日時を分離。未知費目は0にしない。広告の有無・報酬を推薦に使わない。
公開日・実質更新日は確認できる出典に基づく。運営者情報は既に公開されている範囲に限定する。

## 完了境界

ローカル変更・検証・固定候補を提示してから、対象候補への具体的な公開指示を受けてowner-direct-v1で反映する。
外部計測の新規有効化、メールやメーカー問い合わせの送信はこの計画の実装指示から実行権限を推定しない。
GSC/GA4/ASPやメール到達の外部証拠が未取得なら、その状態と次の操作を明記する。

## 作業記録

- 基点: `4daadd611`。作業場所: `.worktrees/all-pages-20260913`、branch `codex/all-pages-improvements-20260913`。
- 初期確認: owner-directの34対象とテーマ1.6.0をread-only確認。既存purchase policy/catalogテスト32件PASS。
- 保存本文・商品データ・手順・入口を統合し、実際のWordPress描画経路で確認。最新の食洗機カテゴリ候補は `kitchen-preview.md`、以前の全体検証範囲は `verification.md`、項目別の実装と未解決条件は `progress-evidence.v1.json` を参照。
