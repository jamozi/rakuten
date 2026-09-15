# 本番 39 ページ横断検査 (2026-09-15)

バッチ A・B 公開後に、公開中の全 39 URL を匿名取得して一括検査した。
スクリプト: セッション scratchpad `prod_audit.py` (HTTP / 可視テキストの禁止語 / 末尾 compat アンカー / 未解決 fragment / canonical / noindex / 本文 h1 / 広告表示 / `rel="sponsored"` / 楽天クレジット)。

## 結果

| 検査 | 結果 |
| --- | --- |
| HTTP | 39/39 が 200 |
| 可視テキストの内部語 (`UNKNOWN`/`UNAVAILABLE`/`SOLD_OUT`/`PREORDER`/`newPurchaseSku` ほか) | **1 件** (下記 A) — 他 38 ページは 0 |
| 末尾 `ps-compat-anchors` の裸 id | 0 件 (バッチ A の成果を維持) |
| 未解決の内部 fragment リンク | 0 件 |
| canonical | 39/39 が自身の URL |
| 意図しない noindex | 0 件 |
| 広告リンクを持つページ | 15 ページ。すべて広告表示あり、`rel="sponsored"` の欠落 0 件 |
| 楽天 API クレジット | **15 ページ中 2 ページのみ** (下記 B) |
| `h1` | 各ページ 1 件 (テーマがタイトルを描画。本文側の重複なし) |

## 検出 A — 記事 549 の抜粋に制作途中の文言 (KS-008 の残り)

`articles.v1.json` の `compact-dishwasher-comparison` の抜粋が
「小型の食洗機を容量、設置寸法、給水方法と手入れで比較します。**比較対象の範囲はレビュー中です。**」で、
本番では `meta name="description"` / `og:description` / `twitter:description` / JSON-LD `description` / 記事冒頭の standfirst の 5 箇所に出ていた。

バッチ A の KS-008 検査は**本文 HTML だけ**を走査していたため見逃した。台帳の抜粋は本文と別の入力である。

- 修正: 抜粋を記事の実内容に沿う表現へ差し替え (SOLOTA・ラクアmini/Plus/color の 4 モデル、食器量・開扉時の奥行・乾燥方式・毎日の手間)。
- 再発防止: `test_ledger_titles_and_excerpts_have_no_internal_tokens` — 台帳 39 件の `title` / `excerpt` を内部語と制作途中語 (レビュー中・執筆中・作成中・検討中・仮題 ほか) で走査。
- 全 39 件の抜粋を同じ条件で再走査し、他に該当なしを確認。

## 検出 B — 楽天 API クレジットの欠落 (KS-006 の残り)

楽天ウェブサービス由来の商品画像を表示しているのは 15 ページだが、クレジット
「商品画像と商品情報の取得に Rakuten Developers API を利用しています（Supported by Rakuten Developers）」が出ていたのは
`/lightweight-carry-on-suitcase-under-3kg/` と `/compact-robot-vacuum-shortlist/` の **2 ページのみ**。残り 13 ページで欠落。

原因: `purchase_support.py` の `RAKUTEN_CREDIT` は `ps-products` グリッド経路の `media_shown` フラグでのみ付与されていた。
`comparison_rows` 経路 (`bind_comparison_rows`) と guide 経路は同じ `ps-product-media` プレースホルダを出してテーマが写真を差し込むが、クレジットを付けていなかった。

- 修正: `ensure_rakuten_credit()` を追加し、経路によらず**プレースホルダの有無**を基準に正規化 (`ps-evidence` / `guide-evidence` セクションの直前、無ければ末尾)。再生成で 15/15 に付与。
- 再発防止: `test_rakuten_media_pages_carry_the_api_credit` (欠落を禁止) と `test_api_credit_only_where_media_is_shown` (API 未使用ページへの表示を禁止) の両方向。
- 出典: [クレジット表記ガイドライン](https://webservice.rakuten.co.jp/guide/credit)、[利用規約 第13条](https://webservice.rakuten.co.jp/guide/rule)。

## 併せて確認した画像要件 (KS-006 項目 1・2)

楽天商品画像は `figure.ps-product-image.ps-rakuten-product-photo` に入り、CSS は
`.ps-rakuten-product-photo img { object-fit: contain }` / `.raos-rakuten-product-photo img { object-fit: contain }` /
`.raos-rakuten-image-300 img { object-fit: contain }`。**切り抜き (`cover`) は適用されていない**。
`cover` を使っているのはサイト自身の編集用画像 (`ks-home-mood`, `ks-feature-image`, `ks-recent-image`, `km-hero-image`) のみ。
画像への文字入れ・一部切り取りはなく、ガイドラインの「サイズ変更・周辺部分への加工は可、文字入れ・切り取りは不可」に適合。

## 判断

A・B はいずれも読者に見える実害があり、編集判断を要さず機械的に直せるため、バッチ C として修正・公開する。
