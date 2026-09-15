# KS-302 承認されたバッチを段階公開し復元可能にする — バッチ A

判定: **完了 (本番公開・匿名照合済み)** / 実施: 2026-09-15 12:36 JST

## 承認

- 2026-09-15、ユーザーが Before/After (`output/ks-20260915/batch-a/review.html`) を確認のうえ「バッチ A 公開して」と明示指示。
- 対象: candidate `6adf45e4c9388370c663cfc5a0765afd096589ecc59750029c6eac04022a4763` (13 本文 + 子テーマ)、branch `claude/ks-emergency-20260915` commit `28238ce9` (prepare 時点)。

## 実行

```
make wordpress-production-request ARGS='direct --owner-checkout /home/minami/rakuten publish --candidate 6adf45e4…'
→ {"publication_status": "PUBLISHED_AND_READBACK_VERIFIED", "git_sync": {"status": "noop", "phase": "complete", "publication": "ALREADY_COMPLETED_NO_REPUBLISH"}}
```

- 本番の前提条件 (revision / content_sha256 / theme tree sha) は一致し、CONTENT_CONFLICT / THEME_CONFLICT なし。
- Git 同期は `origin` を一時的に無効化した環境で実行し、checkpoint が branch HEAD と同一だったため `noop` (push / PR なし)。main への反映はユーザー指示により別途 PR で行う。

## 公開後の匿名照合 (2026-09-15 12:39 JST、`https://kurashinoshirube.com`)

| URL | 確認結果 |
| --- | --- |
| 13 URL すべて | HTTP 200、可視テキストの `UNKNOWN` / `UNAVAILABLE` **0 件**、末尾 `ps-compat-anchors` は空、CSS handles = editorial / editorial-v2 / purchase-support (入口ページは editorial のみ) |
| /roomba-mini-vs-switchbot-k11-pro/ | `保証：未確認` 3 件 (旧 `保証：UNKNOWN` 0) |
| /portable-power-station-guide/ | `幅20.0×奥行39.8×高さ28.3cm` 2 件、逆転表記 0 |
| /standard-dishwasher-comparison/ | `未確認（公表値を確認できず）` 9 件、旧表記 0 |
| /small-carry-on-suitcase-comparison/ | `調査日：2026年9月13日` 1 件、`本文候補作成` 0 |
| /anker-solix-c300-c800-c1000-differences/ | `#blk-anker-015-title` の到着先が `ps-choose` 先頭の alias (末尾 compat なし) |
| /large-dishwasher-comparison/ | `<h1>` 1 件 (テーマのタイトルのみ) |
| /cleaning/ | 記事 30 / 85 へのリンク各 1 件 |

注 (2026-09-15 追記、W2B・未公開): 記事 29 の nav は判断 11 (KS-139) で「購入費用と販売先へ」→ `#blk-anker-007-title` (`ps-offers` 先頭の alias) に変える。上の `#blk-anker-015-title` の照合はバッチ A 公開時点のもので、W2B 公開後に再照合する。

REST `modified_gmt` が 2026-09-15T03:36:19Z〜03:37:01Z に更新された 13 件 = 対象と一致 (19, 28, 29, 41, 82, 84, 85, 86, 131, 266, 550, 551, 553)。対象外の 26 件は未変更。

## 復元

- 復元元: branch `codex/all-pages-improvements-20260913` (`c506e75c`) の本文 + テーマ (2026-09-13 公開版)。
- 手順: `git show c506e75c:changes/wordpress-direct-publish-v1/articles/<slug>.html` で対象本文を戻し、テーマは `git checkout c506e75c -- changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child` → `direct prepare --articles <slug> --theme` → preview → publish。
- 本番側では今回の publish が各 post の revision を保存している (WP の Revisions で内容確認は可。復元操作は上記経路で行う)。

## 受入条件

- [x] 承認された URL・内容以外を変更していない (REST の更新時刻で 13 件のみ)
- [x] 編集画面ではなく本番の匿名表示で完了を確認した
- [x] 復元先 (`c506e75c`)・復元条件・公開版 (candidate `6adf45e4…`) を記録した
