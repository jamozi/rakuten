# 統合改善タスク (KS-xxx) 実施記録 — 2026-09-15 緊急修復バッチ

入力: `tmp/20260915/kurashinoshirube_integrated_tasks_20260914.{md,xlsx,zip}` (80 タスク、2026-09-14 作成)。
Excel (`統合タスク管理.xlsx`) が運用台帳。この directory は着手したタスクの現行照合・差分・検証証拠を残す。
状態の一次情報は `status.v1.json`、タスクごとの証拠は `evidence/KS-xxx.md`。

## 前提 (KS-001 / KS-002 で確定)

- 本番の実体は branch `codex/all-pages-improvements-20260913` (2026-09-13 公開、`changes/site-improvements-20260913/publication-result.v1.json`)。
  作業 branch `claude/ks-emergency-20260915` はそこから派生し、`origin/main` (#282) を merge 済み。main への PR は別タスク。
- 本文の正本は `changes/wordpress-direct-publish-v1/articles.v1.json` + `articles/*.html`。購入判断 19 本文と入口 4 ページは生成物で、
  元 (`changes/reader-purchase-support-v1/`, `changes/site-improvements-20260913/entry-pages/`) と描画器 (`python/raos/application/editorial/`) を直す。
- 公開は owner-direct-v1 (`make wordpress-production-request ARGS='direct --owner-checkout /home/minami/rakuten …'`)。
  各バッチは KS-301 (回帰テスト + preview) → ユーザーの Before/After 確認 → KS-302 (「公開して」の明示指示) の順。

## このバッチで扱うタスク

| タスク | 判定 | 概要 |
| --- | --- | --- |
| KS-001 | 完了 (検証) | 本番 sitemap/REST は 20 記事 + 19 固定ページ = 39、ID は公開記録と一致 |
| KS-002 | 完了 (検証) | 責務 → 実ファイル → 生成器 → 反映経路を `evidence/KS-002.md` に確定 |
| KS-007 | 完了 (公開済み) | DELTA 3 Classic の幅・奥行逆転が記事 28 の結論カード・仕様欄に残存 → 元本文と catalog を修正。SOLOTA / NP-TSP1 は解消済み |
| KS-008 | 完了 (公開済み) | 可視テキストの `保証：UNKNOWN` / `未確認（UNKNOWN）` / `未確認（UNAVAILABLE）` / `本文候補作成` を読者向け日本語へ。再発防止テスト追加 |
| KS-011 | 完了 (公開済み) | 末尾 `ps-compat-anchors` の裸 id 49 件を現行 section への alias に移行。記事 551 の本文 h1 重複を解消 |
| KS-019 | 次バッチ | 描画器の状態別文言は既存。冒頭/比較表/詳細の一致検査と価格再取得はバッチ B |
| KS-109 | 完了 (公開済み) | /cleaning/ 上部に記事 30・85 へのリンク 2 本 (2026-09-15 ユーザー決定: 削除済み節は復活させない) |

`output/ks-20260915/` (Git 管理外) に Before/After の画像とテキスト差分を置く (`scripts/ks_before_after.py`)。
