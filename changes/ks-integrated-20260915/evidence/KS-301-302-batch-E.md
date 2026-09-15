# KS-301 / KS-302 — バッチ E (楽天商品画像の代替テキスト / KS-115 導入文)

対象タスク: KS-018 (具体作業 4: 代替テキスト) / KS-115 (バッチ D の残り)
実施: 2026-09-15 / 公開した commit は branch `claude/ks-batch-d-20260915` の `defaf4ef` (`ad002aa2` + テーマ再刻印の修正)。main へは branch `claude/ks-batch-e-20260915` に cherry-pick (`22d28bfb` / `ceba6f2f`) して載せる。公開 commit との tree 差分は main 側のバッチ D 証跡 2 ファイルだけ

## 修正前の本番実測 (2026-09-15 16:33 JST 匿名取得)

| 確認 | 結果 |
| --- | --- |
| 楽天商品画像を出すページ | 15 |
| 画像 (`<img>` で `image.rakuten.co.jp`) | 126 枚 |
| 代替テキストが一律「楽天市場の商品 の商品画像（楽天市場）」 | **126 枚 (100%)** |
| 代替テキストに商品名がある | 0 枚 |
| `/comfortable-travel/` 導入文 | 「階段・車内・**保安検査**・宿・帰路の荷物で考えます。」(バッチ D で表の行を「小型機の便」に変えたため、表の場面と食い違う) |

ページ別: 記事 19 (6) / 82 (8) / 83 (8) / 84 (8) / 41 (8) / 86 (4) / 263 (5) / 30 (6) / 85 (3) / 28 (8) / 29 (8) / 549 (11) / 550 (17) / 551 (10) / 553 (16)。

## 原因

テーマ `kurashinoshirube_rakuten_image_subject()` は代替テキストの主語を次の順で決める:
1. 画像を含む open な `figure` の `aria-label="<名前>の商品画像"`
2. 開いている `<article class="ps-product">` の `<h3>` + `<p class="ps-model">`
3. 後続 `figcaption` の「画像：楽天市場（<店舗名>）」
4. いずれも無ければ「楽天市場の商品」

描画器 `render_product_media()` の楽天 figure には `aria-label` が無く、比較表・ガイド形式の figcaption は「SS-M171／メタリックウォームグレー・本体単体（広告）」形式で 3 の正規表現に一致しない。
このため全画像が 4 に落ちていた。商品カード形式の記事 83・30 も本番では一律表記だった (2 の条件にも一致していない)。

## 変更

| 項目 | 内容 |
| --- | --- |
| 描画器 | `purchase_support.py` に `product_image_label()` を追加し、楽天 figure に `aria-label="<ラベル>の商品画像"` を付与。テーマ側は無変更 (既存の優先順位 1 がそのまま効く) |
| ラベル規則 | catalog の商品名。**型番が名前に含まれない場合だけ** `exact_model` を追記。楽天画像を持つ 53 商品中 48 商品は名前に型番を含み、追記は 5 商品 (ラクアmini color、Anker Solix C300 / C800 Plus / C1000 / C1000 Gen 2)。バッチ D で直した二重表記 (KS-132) を代替テキストで再発させないため |
| 安全性 | 53 商品のラベルに `<` `>` `"` を含むもの 0、150 字超 0 (テーマの `is_clean_text` は 160 字まで・タグ不可) |
| KS-115 | 同じ場面の列挙が 3 か所の**入力**に残っていたため、すべて「階段・車内・小型機の便・宿・帰路の荷物で考えます。」に揃えた: `site-improvements-20260913/entry-pages.v1.json` の `description` (本文の導入文 `ks-directory-lead` の元)、`wordpress-direct-publish-v1/articles.v1.json` の抜粋 (meta description / og:description の元)、`editorial-portfolio-v3/reader-experience.v1.json` の `description` (ナビゲーション文言の元)。`site_editorial_pages.py` の辞書も同文に更新 (こちらは `registry-updates.json` の元で、本文には効かない)。履歴記録の `progress-evidence.v1.json` は当時の記述のまま残す |

## 途中の失敗と対処

1. **最初の KS-115 修正は効かなかった**。`site_editorial_pages.py` の辞書だけを変えたが、本文の導入文は `entry-pages.v1.json` から作られており、生成物に「保安検査」が残った (ゲートのスキャンで検出: 「保安検査」1 件・「小型機の便・宿」0 件)。ゲートを commit 前に停止し、入力 3 か所を直して再実行した。
2. **再実行の commit `ad002aa2` で st1704 のテスト 93 件が失敗した** (CLI 63・reader hub 20 エラー・theme 3・theme fixes 3・release contract 2・runtime integrity 2)。代表メッセージ: テーマのソース指紋 `8ef5a875…` ≠ 実行時リビジョン `eb83b134…`、`SELF_HOSTED_EDITORIAL_THEME_INVALID`、reader hub が `reader_navigation` を読めず null (ナビゲーション JSON 自体はキーを持つので整合性検査に弾かれた結果)。
   原因: 上流入力を変えたため、テーマ生成器の後に走る `make generate` がテーマ指紋の入力を書き換え、刻印済みリビジョンが古くなった (バッチ D はテーマより上流を変えなかったので起きなかった)。
   対処: 「`make generate` → テーマ `--generate` → `--check` → `make generate` (冪等確認) → `--check`」で整合させ、全テスト・lint の合格を条件に修正 commit を追加した。
3. **ゲートがテスト失敗のまま commit と候補作成 (`15725baa…`) まで進んだ**。`pytest | tail -3` の終了コードが `tail` のものだったため。**この候補は公開していない**。ゲートを修正し、テスト・lint の失敗、冪等性・テーマ hash の不一致で commit 前に止まるようにした。
4. 途中で実行中のゲートを止める際、コマンド行の部分一致で停止対象を選んだため自分自身のシェルに一致し、ゲート本体を止められなかった。以後は実行ファイルと第 1 引数の完全一致で選ぶ。

## 再発防止テスト

- `test_rakuten_product_photos_carry_an_identifying_label` — テーマ投影の全楽天 figure がラベルを持ち、型番を重複しない。**修正前の投影データで失敗することを確認済み**
- `test_product_image_label_adds_the_model_only_when_missing` — 型番あり / なし / KS-132 型 (`01521` と `01521-09`) の 3 ケース
- `tests/st1704/test_site_audit_theme_fixes.py::test_comparison_row_photo_alt_uses_the_figure_label_not_the_generic_fallback` — 「（広告）」形式の figcaption でも figure のラベルから商品名の代替テキストが出ることを PHP harness で固定

## KS-301 検査

全段階を「失敗したら commit 前に停止」する条件で実行した (commit `defaf4ef`)。

| 段階 | 結果 |
| --- | --- |
| テーマ再刻印 | `SELF_HOSTED_EDITORIAL_THEME_GENERATED revision=17607e22…` |
| テーマ整合 `--check` (再刻印直後 / `make generate` 後 / 冪等確認後の 3 回) | 3 回とも `SELF_HOSTED_EDITORIAL_THEME_OK sha256=b503bc57…` |
| `make generate` ×2 | 2 回とも `RAOS_STATUS_V2 status=PASS`、2 回目で差分なし (`IDEMPOTENT_OK`)、テーマ hash 一致 (`THEME_HASH_OK`) |
| pytest (purchase_support / site_editorial_pages / wordpress_public_acceptance / st1704 / wordpress_reader_navigation_v3 / wordpress_local_preview) | `2176 passed, 1 skipped, 102 subtests passed in 190.98s` |
| ruff | `All checks passed!` |
| 候補作成 | candidate `c9a8e8aa6934c075a6b755f3c674c24d58b584a0a8d07611beb1e2734184a09a` (17 文書 + テーマ、`publication_ready: true`、元 commit `defaf4ef`) |
| preview (使い捨て WordPress) | `status: PASS`、failures 0、URL 19 (対象 17 文書 + ホーム + 投稿一覧)、スクリーンショット 38 |

対象 17 文書: 記事 19 / 28 / 29 / 30 / 41 / 82 / 83 / 84 / 85 / 86 / 263 / 549 / 550 / 551 / 553 と固定ページ 132 (`/comfortable-travel/`)・139 (`/purposes/`)。
`/purposes/` は目的カードの説明文が同じ導入文を使うため、「保安検査」→「小型機の便」の 1 か所だけが変わった。

## KS-302 公開と照合

公開: 2026-09-15 16:56:06〜16:57:01 JST (`modified_gmt` 07:56:06Z〜07:57:01Z)、`PUBLISHED_AND_READBACK_VERIFIED`。Git 同期は `noop` (公開後に main へ PR で反映)。

### 匿名照合 (2026-09-15 16:57 JST、公開前 16:54 JST の同じ検査と比較)

| 確認 | 公開前 | 公開後 |
| --- | --- | --- |
| 楽天商品画像を出すページ / 画像 | 15 / 126 | 15 / 126 |
| 代替テキストが一律「楽天市場の商品」 | 126 | **0** |
| 代替テキスト内の型番重複 | 0 | 0 |
| 商品カード形式 (記事 83 / 30) の一律表記 | 8 / 6 | 0 / 0 |
| `/comfortable-travel/` 本文の「保安検査」/「小型機の便・宿」 | 1 / 0 | **0 / 1** |
| 同 meta description・og:description | 「…車内・保安検査・宿…」 | 「階段・車内・小型機の便・宿・帰路の荷物で考えます。」 |
| `/purposes/` 目的カードの「保安検査」/「小型機の便・宿」 | 1 / 0 | **0 / 1** |
| 内部語 (状態コード・`newPurchaseSku`・レビュー中・本文候補) | 0 | 0 |
| `articleSection: null` / 章番号の残存 | 0 / 0 | 0 / 0 |
| 楽天クレジット | 15 / 15 | 15 / 15 |
| 楽天価格の免責文リンク | 54 | 54 |
| 07:55Z 以降に更新された文書 | 0 | **17** (候補の対象 17 文書と一致、それ以外の更新なし) |

公開後の代替テキスト例:
- 記事 550 `/standard-dishwasher-comparison/`: 「シロカ 食器洗い乾燥機 SS-M171 の商品画像（楽天市場）」
- 記事 83 `/lightweight-carry-on-suitcase-under-3kg/`: 「PROTECA エアロフレックスDX2 01521 の商品画像（楽天市場）」(型番の二重表記なし)
- 記事 30 `/compact-robot-vacuum-shortlist/`: 「SwitchBot（スイッチボット）ロボット掃除機 K11+ Pro の商品画像（楽天市場）」

照合は、記事・固定ページ 39 件の匿名 HTML 取得と REST API の `modified_gmt` で行った。
