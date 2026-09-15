# KS-301 / KS-302 — バッチ C (本番横断検査で検出した 2 件の修正)

対象タスク: KS-006 (楽天 API クレジットの欠落) / KS-008 (記事 549 の抜粋の制作途中文言)
実施: 2026-09-15 / branch `claude/ks-batch-b-20260915` (commit `51f389d5`)
検出の経緯: `evidence/production-audit-20260915.md` (バッチ A・B 公開後の 39 ページ横断検査)

## 対象

13 本文 + 子テーマ。記事 19, 28, 29, 41, 82, 84, 85, 86, 263, 549, 550, 551, 553。
`/about-ad-policy/` は本文変更なし (バッチ B で免責文を追加済み)。

## 変更

| 項目 | 内容 |
| --- | --- |
| クレジット正規化 | `purchase_support.py` に `ensure_rakuten_credit()` を追加。`data-ps-media-product` プレースホルダを持つ本文に `ps-media-credit` が無ければ、`ps-evidence` / `guide-evidence` セクションの直前 (無ければ末尾) にクレジットを挿入。`ps-products` グリッド経路だけが付与していた漏れを経路非依存にした |
| 抜粋 | `articles.v1.json` の `compact-dishwasher-comparison` の抜粋から「比較対象の範囲はレビュー中です。」を削除し、記事の実内容 (SOLOTA・ラクアmini/Plus/color の 4 モデル、食器量・開扉時の奥行・乾燥方式・毎日の手間) に沿う表現へ差し替え |
| 再発防止テスト | `test_ledger_titles_and_excerpts_have_no_internal_tokens` (台帳の title/excerpt を走査) / `test_rakuten_media_pages_carry_the_api_credit` (欠落を禁止) / `test_api_credit_only_where_media_is_shown` (過剰表示を禁止) |

## KS-301 検査

| 検査 | 結果 |
| --- | --- |
| `make generate` ×2 | `RAOS_STATUS_V2 status=PASS`、2 回目に差分なし (`IDEMPOTENT_OK`)、`THEME_HASH_OK` |
| クレジット網羅 | プレースホルダを持つ本文 15 / クレジットを持つ本文 15 |
| pytest (`purchase_support`, `site_editorial_pages`, `wordpress_public_acceptance`, `st1704`, `wordpress_reader_navigation_v3`) | **1418 passed, 102 subtests passed** |
| `make check BASE=origin/main` | exit 0 (ruff / mypy / eslint / PHP 構文。`scripts/ks_render_review.py` の E741 を修正後) |
| `direct preview` | **status PASS, failures []**、15 surface × 2 幅 = 30 枚 |

## KS-302 公開と照合

- candidate `382d985d07ca23badc322ee7c754542d97b9559efa4e0fa72ef0a941bfe0b136`
- `direct publish` → `PUBLISHED_AND_READBACK_VERIFIED`、`git_sync: noop` (push/PR なし)
- 本番の匿名照合 (2026-09-15 16:10 JST):

| 確認 | 結果 |
| --- | --- |
| HTTP | 39/39 が 200 |
| 楽天画像を表示するページ | 15。**うちクレジットあり 15** (公開前は 2) |
| 画像が無いのにクレジットがあるページ | 0 |
| 「レビュー中」の残存 | 0 (公開前は記事 549 の 5 箇所) |
| 記事 549 の抜粋 (REST) | 「少量向けの小型食洗機4モデルを、洗える食器の量・扉を開けた奥行・乾燥方式・毎日の手間で比較します。SOLOTAとラクアmini系の違いを整理します。」 |
| 免責文リンク (バッチ B の成果) | 54 件を維持 |
| 影響範囲 | `modified_gmt` が 2026-09-15T07:07:34Z〜07:08:16Z に更新されたのは対象 13 件のみ。他 26 件は不変 |

## 復元

復元元は `origin/main` + バッチ B の本文。`git show <commit>:changes/wordpress-direct-publish-v1/articles/<slug>.html` で戻し、同じ prepare → preview → publish 経路で再公開する。

## 受入条件

- [x] 承認された URL・内容以外を変更していない (REST の更新時刻で 13 件のみ)
- [x] 本番の匿名表示で完了を確認した
- [x] 復元先・復元条件・公開版 (candidate `382d985d…`) を記録した
