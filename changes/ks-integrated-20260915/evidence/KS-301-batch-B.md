# KS-301 公開バッチごとの回帰・出典・動作レビュー — バッチ B

対象タスク: KS-019 (検証・テスト追加、本文変更なし) / KS-006・KS-020 の免責文 (楽天ウェブサービス規則)
実施: 2026-09-15 / branch `claude/ks-emergency-20260915` (commit `912de1fd` + 補助 `cd754a2b`)

## 対象と影響 URL

9 本文 + 子テーマ (投影 `purchase-support.v1.json` と runtime hash の再束縛):
`/about-ad-policy/` (ID 10) と、offer パネルを持つ比較 8 記事 (29, 19, 82, 41, 84, 28, 85, 86)。
新規 5 記事・手順記事は `comparison_rows` / guide 形式で `ps-price-date` 行を持たないため差分なし。

## 差分レビュー

- 運営・広告方針: 「広告・アフィリエイト」節に `id="production-about-rakuten-price"` の段落を 1 つ追加 (RWS ヘルプの定型免責文 + サイト名 + 24 時間表示方針の説明)。既存文は不変。
- 比較 8 記事: 各 offer の「販売条件確認：<日時>／<費目範囲>」行の末尾に「／価格・販売可能情報の注意」リンク (`/about-ad-policy/#production-about-rakuten-price`) を追加。数値・出典・相対評価・売り場・表示期限・アンカーは不変。
- テーマ: CSS/JS 不変。投影 hash と theme revision のみ再束縛。
- 可視テキスト差分: `output/ks-20260915/batch-b/*.text.diff` (Before = `origin/main` = バッチ A 公開後)。追加行のみ、削除なし。内部語 0。

## 生成・回帰

| 検査 | 結果 |
| --- | --- |
| `make generate` ×2 | `RAOS_STATUS_V2 status=PASS`、2 回目に差分なし (`IDEMPOTENT_OK`)、`THEME_HASH_OK` |
| pytest `tests/purchase_support` 全体 + `site_editorial_pages` + `wordpress_public_acceptance` + `st1704/test_self_hosted_editorial_theme.py` | 初回 `365 passed, 11 failed` — 失敗 11 件はすべて Docker 内 PHP を使う harness で、Docker Desktop 停止が原因。Docker 復旧後に同 5 ファイルを再実行し **168 passed** (失敗 0) |
| KS-019 テスト `test_ks_offer_state_consistency.py` | 6 passed |
| KS-008/011 テスト `test_ks_emergency_20260915.py` | 上記 365 に含まれ PASS (fragment リンクの解決先 `#production-about-rakuten-price` を含む) |

## 候補と preview

- candidate `a181afd8af1a905ab538c45c28e14cea6ed09754c907e79111408eb1d61e8dd8` (`direct prepare --articles <9> --theme`, `publication_ready: true`)
- `direct preview`: **status PASS, failures []**、11 surface × 2 幅 = 22 枚。ローカル URL `http://127.0.0.1:42429/`
- After preview の確認: 記事 85 にリンク 6 件、記事 28 に 8 件、`/about-ad-policy/` に anchor 1 件、CSS handles 3 本。本番 (Before) には 0 件。

## Before / After

`output/ks-20260915/batch-b/review.html` — Before = 本番 (バッチ A 公開後、匿名取得)、After = 候補 preview。9 記事 × 390/1440px × before/after = 36 枚 + テキスト差分 9 本。

## 受入条件

- [x] 選択バッチ内で未解消の誤購入・安全・プライバシーの重大問題 0 件 (KS-019 の 3 ケースを検証)
- [x] 添付や前回報告だけを完了根拠にしていない (テスト + preview + 本番との差分)
- [x] 変更不要の項目 (KS-019 本文) にも現行版の確認証拠がある
