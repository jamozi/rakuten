# KS-301 / KS-302 — バッチ D (残り 67 タスク監査で本番に実在した 9 件)

実施: 2026-09-15 / branch `claude/ks-batch-d-20260915`
検出の経緯: 並列監査ワークフロー `ks-remaining-audit` (16 群・67 タスク、「解消済み」主張は反証担当が独立に検証、統合担当が sandbox で修正を試行) と、Claude による本番の独立実測。

## 本番で実測した不備 (修正前、2026-09-15 16:30 JST 匿名取得)

| ID | 不備 | 本番の実測 |
| --- | --- | --- |
| KS-133 / KS-008 | 記事 82 に内部フィールド名 `newPurchaseSku` が露出 | `/carry-on-suitcase-under-100-seats/` の可視テキストに 3 件 (「…newPurchaseSkuというフィールド名を新品の根拠にしない。」) |
| KS-110 | 入口ページが広告ありの記事を「広告リンクなし」と表示 (誤った広告非表示の申告) | `/preparedness/` に「広告リンクなし」1 件。到着先の記事 29 には楽天アフィリエイトリンク 16 件 |
| KS-132 | 型番の二重連結 | `/lightweight-carry-on-suitcase-under-3kg/` に `0152101521-09` / `CS2*09007CS2*09007` / `QJ6-68002QJ6-68002` / `1-2501-250` 各 1 件 (商品名と正規型番 `exact_model` の区切りなし連結) |
| KS-009 / KS-134 | 候補数と一致しない相対表現 | 4 商品の `/front-open-carry-on-suitcase-with-stopper/` に「3モデルで最軽量」1 件 (同じ固定文を 3 商品の記事 19 と共用) |
| KS-129 | JSON-LD の `articleSection` が null | `/roomba-mini-vs-switchbot-k11-pro/` 等で `"articleSection":null` (テーマが存在しないキー `category_label` を参照。binding の実キーは `section`) |
| KS-137 | 章番号の残存 | 記事 85 に「09　アプリとWi-Fi」 (公開 39 本文で唯一の `section-number`) |
| KS-119 | 実在しないフッターラベルを名指し | プライバシーポリシーが「Cookie・個人情報の取り扱い」と記載、実ラベルは「Cookie設定を変更」 |
| KS-117 / KS-118 | 方針本文の期限後文言が実装と不一致 | 方針は「再確認中」のみ、実装は「販売条件の表示期限切れ。」/「販売条件を再確認中。」/「価格は販売先で確認」の 3 分岐 |
| KS-115 | 目的ページの行が到着記事と不一致 | `/comfortable-travel/` の「保安検査」行の到着先 `/carry-on-suitcase-under-100-seats/` に「保安検査」0 件 |

## 見逃しの原因 (KS-008 の検査欠陥)

バッチ A で追加した `INTERNAL_TOKENS` は `\b(?:…|newPurchaseSku)\b` だった。Python の `\b` は日本語文字も単語文字として扱うため、
「newPurchaseSku**という**」のように日本語が隣接すると一致しない。バッチ A の本文検査も、本番横断検査 (`evidence/production-audit-20260915.md`) も同じ正規表現を使っていたため、同じ盲点を共有していた。
→ ASCII 境界 `(?<![A-Za-z0-9_])…(?![A-Za-z0-9_])` に修正し、日本語隣接ケースのテストを追加。

## 変更 (正本のみ。生成物は再生成)

| ID | 正本 | 変更 |
| --- | --- | --- |
| KS-133 | `purchase-support.v1.json` (3 offer の `condition_note`) | 「newPurchaseSkuというフィールド名を」→「販売先の内部項目名を」。確認状態 (新品の明示なし) は不変 |
| KS-110 | `site-improvements-20260913/entry-pages/preparedness.html` | 記事 29 のバッジを「PR・広告リンクあり」(記事 28 と同形) |
| KS-132 | `reader-purchase-support-v1/articles/lightweight-carry-on-suitcase-under-3kg.html` | 二重連結 4 件を「商品名 + 正規型番」に。出典リストの統合 (了承範囲に触れる) は含めない |
| KS-009 / KS-134 | `purchase-support.v1.json` | 「3モデルで最軽量の本体を求める人」→「比較した候補の中で最軽量の本体を求める人」(3 商品・4 商品の両記事で正しい) |
| KS-129 | テーマ `functions.php` | `$binding['category_label']` → `$binding['section']` |
| KS-137 | `roomba-mini-vs-switchbot-k11-pro.html` | 残存する章番号 1 行を削除 |
| KS-119 | `privacy-policy.html` | ラベルを実表記「Cookie設定を変更」に |
| KS-117 / KS-118 | `comparison-policy.html` / `about-ad-policy.html` | 期限後文言を実装の 3 分岐を名指す文に |
| KS-115 | `python/raos/application/editorial/site_editorial_pages.py` | 「保安検査／取り出す順番と便の規定」→「小型機の便／各辺・3辺合計・重量・個数の条件」、リンク文言「小型機の寸法条件」 |

## 再発防止テスト (`tests/purchase_support/test_ks_emergency_20260915.py`)

- `test_internal_token_pattern_matches_japanese_neighbours` — 日本語隣接の内部語を検出、ASCII 隣接の別識別子は許容
- `test_section_numbers_do_not_reach_published_bodies` — 公開本文に `section-number` 0 件
- `test_relative_claims_match_the_article_candidate_count` — 「NモデルでM最…」の N が記事の掲載商品数と一致
- 修正前の生成物に対してこの 3 件が **失敗し、検出内容が上表の本番不備と一致** することを確認してから再生成した (内部語 3 件 / 章番号 1 件 / 「3モデル」expected 4)

## 監査で「今回は実施しない」と判断したもの

- 了承済み構成を覆すもの (KS-016 / KS-101 / KS-107 / KS-108 / KS-121 / KS-138 の一部)
- 記事内容の執筆・取捨が要るもの (編集判断 16 件)
- 提携・計測の外部作用 (オーナー承認 9 件)
- 新規 5 記事 (549〜553) の一覧・新着への登録 (KS-012/013/101〜106)。publisher の対象同一性検査と全 39 ページ再生成に関わるため、登録機構を先に 1 つ決める必要がある

## KS-301 検査

| 検査 | 結果 |
| --- | --- |
| 再生成 | `build_reader_purchase_support_v1` → `build_site_editorial_pages` → `build_st1704_self_hosted_theme --generate` → `make generate` ×2。2 回目に差分なし (`IDEMPOTENT_OK`)、`THEME_HASH_OK` |
| 生成物の不備スキャン | `newPurchaseSku` 0 本 / `section-number` 0 本 / 「3モデルで最軽量」0 本 / preparedness「広告リンクなし」0 件 / 記事 83 の二重連結 0 件 |
| pytest (`purchase_support`, `site_editorial_pages`, `wordpress_public_acceptance`, `st1704`, `wordpress_reader_navigation_v3`, `wordpress_local_preview`) | **2173 passed, 1 skipped, 102 subtests passed** |
| ruff (`python scripts tests tools/affiliate_ingestion`) | All checks passed |
| candidate | `db7367e840c0a683cea3301283c8f6c1c1f6dff9a39081d8f20f69c2ef1e2dd5` (`direct prepare --articles <変更本文> --theme`) |
| `direct preview` | **status PASS, failures []**、12 surface × 2 幅 = 24 枚 |

## KS-302 公開と照合

- candidate `db7367e840c0a683cea3301283c8f6c1c1f6dff9a39081d8f20f69c2ef1e2dd5`
- `direct publish` → `PUBLISHED_AND_READBACK_VERIFIED`、`git_sync: noop` (push/PR なし。main へは本 PR)
- 本番の匿名照合 (2026-09-15 16:29 JST):

| ID | 本番 (公開後) |
| --- | --- |
| KS-133 | `/carry-on-suitcase-under-100-seats/` の `newPurchaseSku` **0 件** (公開前 3)、新表現「販売先の内部項目名を新品の根拠にしない」3 件 |
| KS-110 | `/preparedness/` の「広告リンクなし」**0 件**、「PR・広告リンクあり」2 件 (記事 28・29) |
| KS-132 | 記事 83 の二重連結 4 種すべて **0 件**、「01521（型番 01521-09）」1 件 |
| KS-009 / KS-134 | 記事 84 の「3モデルで最軽量」**0 件**、「比較した候補の中で最軽量」1 件 |
| KS-137 | 記事 85 の「09　アプリとWi-Fi」**0 件** |
| KS-119 | プライバシーポリシーの「Cookie・個人情報の取り扱い」**0 件**、「Cookie設定を変更」2 件 |
| KS-117 / KS-118 | 比較方針・運営方針に「販売条件の表示期限切れ。」各 1 件、旧「再確認中」単独の文 0 件 |
| KS-115 | 表の行は「小型機の便／各辺・3辺合計・重量・個数の条件」に更新 (到着先の記事 82 は「3辺合計」15 件・「重量」19 件で行の答えと一致)。**ただしページ冒頭の導入文「階段・車内・保安検査・宿・帰路…」が残り、表の場面と食い違う**。次バッチ (E) で導入文を「小型機の便」に揃える |
| KS-129 | 全 39 ページで `"articleSection":null` **0 件** |

全 39 ページの回帰 (修正後の ASCII 境界の正規表現で走査):

| 確認 | 結果 |
| --- | --- |
| 可視テキストの内部語 | **0 件** (旧 `\b` 版で見逃していたものを含めて再走査) |
| 章番号 `section-number` | 0 件 |
| 楽天画像ページのクレジット (バッチ C) | 15/15 を維持 |
| 免責文リンク (バッチ B) | 54 件を維持 |
| 影響範囲 | `modified_gmt` が 2026-09-15T07:27:43Z〜07:28:13Z に更新されたのは 10 文書で、変更本文 10 件と完全一致 (対象外の更新 0、漏れ 0) |

## 復元

復元元は main (`7e402880`、バッチ C まで) の本文とテーマ。`git show 7e402880:changes/wordpress-direct-publish-v1/articles/<slug>.html` で戻し、同じ prepare → preview → publish 経路で再公開する。

## 受入条件

- [x] 承認された URL・内容以外を変更していない (REST の更新時刻で 10 件のみ)
- [x] 本番の匿名表示で完了を確認した (KS-115 の導入文の残りは次バッチで対応と明記)
- [x] 復元先・復元条件・公開版 (candidate `db7367e8…`) を記録した
