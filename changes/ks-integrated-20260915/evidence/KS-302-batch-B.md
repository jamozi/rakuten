# KS-302 承認されたバッチを段階公開し復元可能にする — バッチ B

判定: **完了 (本番公開・匿名照合済み)** / 実施: 2026-09-15 15:31 JST

## 承認

- 2026-09-15、ユーザーが Before/After (`output/ks-20260915/batch-b/review.html`) を提示された状態で「残課題をすべて修正して、公開、PR、マージまで実施してください」と明示指示。
- 対象: candidate `a181afd8af1a905ab538c45c28e14cea6ed09754c907e79111408eb1d61e8dd8` (9 本文 + 子テーマ)、branch `claude/ks-emergency-20260915` commit `912de1fd` (prepare 時点)。

## 実行

```
make wordpress-production-request ARGS='direct --owner-checkout /home/minami/rakuten publish --candidate a181afd8…'
→ {"publication_status": "PUBLISHED_AND_READBACK_VERIFIED", "git_sync": {"status": "noop", "phase": "complete"}}
```

前提条件 (revision / content_sha256 / theme tree sha) は一致し、CONTENT_CONFLICT / THEME_CONFLICT なし。
Git 同期は `origin` を一時的に無効化して実行したため `noop` (push / PR なし)。main への反映は別 PR。

## 公開後の匿名照合 (2026-09-15 15:35 JST、`https://kurashinoshirube.com`)

| 確認 | 結果 |
| --- | --- |
| 対象 9 URL | すべて HTTP 200 |
| 免責文リンク (`/about-ad-policy/#production-about-rakuten-price`) | 比較 8 記事に計 **54 件** (29: 8, 41: 8, 28: 8, 82: 7, 84: 7, 19: 6, 85: 6, 86: 4) |
| 免責文本体 | `/about-ad-policy/` に anchor 1 件、可視テキストに「購入時に楽天市場店舗」1 件 |
| 回帰 | 9 URL とも可視テキストの `UNKNOWN`/`UNAVAILABLE` 0 件、末尾 `ps-compat-anchors` 空 (バッチ A の成果を維持) |
| 影響範囲 | REST `modified_gmt` が 2026-09-15T06:31:14Z〜06:31:42Z (15:31 JST) に更新されたのは対象 9 件のみ。他 30 件は不変 (最新は 03:36〜03:37Z のバッチ A 分) |

## 復元

- 復元元: `origin/main` (バッチ A まで) の本文 + テーマ。
- 手順: `git show origin/main:changes/wordpress-direct-publish-v1/articles/<slug>.html` で本文を戻し、テーマは同様に戻して `direct prepare --articles <slug> --theme` → preview → publish。
- 本番側では今回の publish が各 post の revision を保存している。

## 受入条件

- [x] 承認された URL・内容以外を変更していない (REST の更新時刻で 9 件のみ)
- [x] 編集画面ではなく本番の匿名表示で完了を確認した
- [x] 復元先・復元条件・公開版 (candidate `a181afd8…`) を記録した
