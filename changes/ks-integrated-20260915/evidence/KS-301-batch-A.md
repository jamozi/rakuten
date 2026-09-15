# KS-301 公開バッチごとの回帰・出典・動作レビュー — バッチ A

対象タスク: KS-007 / KS-008 / KS-011 / KS-109 (+ KS-001/002 の前提確認)
実施: 2026-09-15 / branch `claude/ks-emergency-20260915` (commit `28238ce9`)

## 対象と影響 URL

13 本文 + 子テーマ (`purchase-support.v1.json` 投影と runtime hash の再束縛):
記事 29, 19, 82, 41, 266, 84, 551, 28, 85, 553, 86, 550 と固定ページ 131 (`/cleaning/`)。
依存タスク KS-001 / KS-002 は完了 (`evidence/KS-001.md`, `KS-002.md`)。

## 差分レビュー

- 数値・出典: DELTA 3 Classic の寸法 (記事 28) のみ変更。仕様表の出典 (公式仕様、確認 2026-09-11) と一致させた。他の数値・売り場・表示期限は不変。
- 相対評価: 変更なし。
- アンカー: 49 件の旧 id を現行 section の alias に移し、末尾 compat ブロックは全記事で空。記事 29 の `#blk-anker-015-title` は `ps-choose` 先頭へ到達。
- 可視テキスト: 内部語 (`UNKNOWN` / `UNAVAILABLE` / `本文候補作成`) 0 件。data-* 属性の機械状態は不変。
- テーマ: CSS/JS の内容変更なし。`KURASHINOSHIRUBE_PURCHASE_RUNTIME_SHA256` と theme runtime revision を投影に合わせて再束縛 (`build_st1704_self_hosted_theme.py --generate`、2026-09-13 と同じ手順)。
  初回候補 `1608e6cf…` は再束縛前だったため purchase-support / editorial-v2 CSS が読み込まれず、390px で計算機がはみ出した (FAIL)。再束縛後の候補で解消。

## 生成・回帰

| 検査 | 結果 |
| --- | --- |
| `make generate` ×2 (owner 83) | `RAOS_GENERATE status=PASS`、2 回目に差分なし (`IDEMPOTENT_OK`) |
| pytest (`test_ks_emergency_20260915`, `purchase_support` 4 suite, `site_editorial_pages`, `wordpress_public_acceptance`, `st1704/test_self_hosted_editorial_theme`) | **197 passed, 18 subtests passed** |
| `make fast BASE=codex/all-pages-improvements-20260913` | 結果は末尾に追記 |

## 候補と preview

- candidate `6adf45e4c9388370c663cfc5a0765afd096589ecc59750029c6eac04022a4763` (`direct prepare --articles <13> --theme`, `publication_ready: true`)
- `direct preview`: **status PASS, failures []**、15 surface × 2 幅 = 30 枚。ローカル URL `http://127.0.0.1:42429/`。
- After preview の確認 (匿名取得): `保証：UNKNOWN` 0、`未確認（UNAVAILABLE）` 0、`本文候補作成` 0、`幅39.8×奥行20.0` 0 (正順 2)、記事 551 の h1 1 件 (テーマのタイトルのみ)、
  `/cleaning/` に記事 30・85 リンク各 1、末尾 compat 空、CSS handles = editorial / editorial-v2 / purchase-support。

## Before / After (ユーザー確認用)

`output/ks-20260915/batch-a/index.md` — Before = 稼働中の本番相当 preview (127.0.0.1:41398)、After = candidate の screenshots、可視テキスト unified diff 13 本。

## 異常系

- 同意・計測: テーマ JS 不変。KS-003 で本番 4 状態を実測済み。
- JS 無効: alias span は静的 HTML。compat 廃止で JS 依存なし。
- 画像失敗: preview の `broken-image` 検査 0 件。

## 受入条件

- [x] 選択バッチ内で未解消の誤購入・安全・プライバシーの重大問題 0 件
- [x] 添付や前回報告だけを完了根拠にしていない (本番取得 + preview + テスト)
- [x] 変更不要の項目 (KS-007 の SOLOTA / NP-TSP1) にも現行版の確認証拠がある

## 追記 (make fast / Before-After)

- `make fast BASE=codex/all-pages-improvements-20260913` (worktree に `.venv` / `node_modules` を用意して全件計画で実行): **fast exit=0**。
  pytest 全件 `21996 passed, 7 skipped, 157 subtests passed` (10:55)、serial `2042 passed`、DB/Storage partition `349 passed` / `91 passed`、Node `4 passed`、PHP 構文 OK。
  1 回目の実行は Before/After スクリーンショット取得と並走中に `build_st1002_public_article_renderer` の check が失敗したが、単独再実行と 2 回目の `make fast` では再現せず (同 check PASS)。
- Before/After: `output/ks-20260915/batch-a/` に 13 記事 × 2 幅 × before/after = 52 枚 + テキスト差分 13 本 + `index.md` / `review.html`。Before 取得は `PASS` (HTTP 200、失敗なし)。
