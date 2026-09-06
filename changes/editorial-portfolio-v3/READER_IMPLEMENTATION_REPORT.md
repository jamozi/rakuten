# 暮らしのしるべ 読者体験改善・実装報告

対象は追跡済み10記事、WordPress子テーマ、共通表示モデル、専用ローカルWordPressです。公開サイトの投稿・URLは変更していません。白・紺と明朝見出しを維持しました。

統合レビュー: [PR #187](https://github.com/jamozi/rakuten/pull/187)。基盤の[PR #177](https://github.com/jamozi/rakuten/pull/177)はマージ済みです。#178〜186は実装の区切りを確認するためのドラフトで、最終統合は#187にまとめています。

## 実装範囲とタスクID

| タスク | 結果 |
| --- | --- |
| RX-000〜004 | 編集元・生成経路・公開境界を整理。変更前を保存。型番・出典・日付・画像・CTA・比較適格性の純粋な検証を追加 |
| UI-001〜007、QA-001 | 仮画像と枠、装飾改行を除去。本文800px／比較1200px／モバイル余白16px。最新カードを単一リンクと同じ行高へ統一。5幅・拡大文字・キーボード・アクセシビリティ検査 |
| DS-001〜012 | 30秒結論、3条件、判断表、差分仕様表、商品ごとの適合・妥協点、証拠パネル、UNKNOWN、購入前確認、段階CTA、文脈リンク、承認アセット、共通カードを追加 |
| HOME-001〜009 | 指定のHeroコピー、悩み→カテゴリ→まず読む→最近更新→方針の順序。計測根拠のない「人気」は不使用。承認写真がないため画像なしで成立するレイアウト |
| DW-001・003〜010 | 食洗機4候補とSOLOTA状態確認を代表実装。公式claimから本体寸法図4点、確認できる2点のみ扉開放時奥行を表示。容量の仮定場面と日々の作業を説明 |
| DW-002 | 新規SOLOTA比較記事は必須仕様・販売状態・保証・構成の欠損により生成停止。状態確認記事を維持 |
| DW-011 | ローカル表示と適格性の検査完了。実読者の理解テストは未実施 |
| ART-001〜004・006〜008 | V3への任意のreader_experience追加、旧データのフォールバック、shortlist／comparison／model_difference／status_checkを現行記事で使用。主要見出し7〜9以内を原則とし、証拠と選定過程を末尾へ整理 |
| ART-005 | safety_ruleの検証・表示モジュールを用意。規定主体、確認日、最終判断者、例外、公式参照が必要。該当する新規記事は作成していない |
| MIG-001〜005・007〜009 | 電源7候補、食洗機4候補、掃除機4候補、Anker4モデル、エース3モデル、Roomba2製品、SOLOTA状態確認を移行。タイトル・対象数・出典・確認日を保全 |
| MIG-006 | スーツケース3記事の追跡済みの場面説明を保持して整理。30L・3kg以下は5モデルを維持。総重量の計算例は仮定として表示 |
| MIG-010 | 権利不明画像・仮画像を非表示。商品写真と記事ごとのアイキャッチ、追加の構造図は承認アセット・根拠整備後の残件 |
| HUB-001〜005 | 15の独立ハブをローカル固定ページとして追加。カテゴリ・目的・記事数・主分類を同じレジストリから生成。存在する記事だけを文脈リンクに使用。既存slug・canonicalと旧ホームのアンカーを保全 |
| QA-002〜004 | 6問／ホーム5秒／記事30秒の手順と空の記録様式を用意。参加者0人、回答率未測定 |
| QA-005〜006 | 計測は未実装・無効。人の検証結果がないためコピーや順序の追加実験を開始していない。データ欠損と次の検証順を記録 |

最初の10タスクを表示基盤として実装した後、ホームと記事を段階的に移行しました。最終検査で見つかったモバイル仕様表の旧CSSによる非表示も修正し、表の存在・読み上げ構造・スクロール操作を追加検査しています。

## 確認URLと表示記録

ローカル環境: **http://127.0.0.1:21924/**。検査は本番公開の承認ではありません。

- 食洗機4候補: http://127.0.0.1:21924/local-preview-countertop-dishwasher-for-small-households/
- SOLOTA状態確認: http://127.0.0.1:21924/local-preview-solota-vs-rakua-mini-plus/
- カテゴリ: http://127.0.0.1:21924/categories/
- 悩み・目的: http://127.0.0.1:21924/purposes/
- 記事ごとのURLと全対象は `generated/wordpress-audit-inventory.v3.json` を参照。

`output/playwright/reader-experience/` 以下にHTML・スクリーンショット・検査記録を保存しています。これらはGit管理外のローカル成果物です。

| 保存先 | 内容 |
| --- | --- |
| `before/` | 改修前のホーム＋10記事、360/390/768/1024/1440px、55条件。公開MCP取得結果とは別のローカル基準 |
| `first-ten/` | 初期の表示基盤の比較記録 |
| `components-final/`、`home-hubs-final/`、`dishwasher/` | 共通部品・ホーム・食洗機の区切りごとの記録 |
| `power-cleaning/`、`model-differences/`、`roomba/`、`lightweight-luggage/`、`front-open/` | 1〜2記事ずつの移行確認 |
| `final-all/manifest.json` | 41ページ×5幅=205条件。通常／200%文字、見出し、表、カード、アクセシビリティ、40の内部リンクを確認。失敗0件 |
| `final-dishwasher/manifest.json` | 最終の食事場面・日々の作業の追記後、食洗機を5幅で再確認。失敗0件 |
| `review/` | ホーム・食洗機の画面、モバイル仕様表、実際のアクセシビリティツリーと矢印キー操作 |

既存の `make wordpress-preview-check` も26ページ×5幅の130条件とLighthouseで成功しました。156枚の表示・200%文字の記録とURLは `output/playwright/local-preview.run-summary.v2.json`、画像は `output/playwright/local-preview/` にあります。

表示の主要な差は、仮画像と調査過程を先頭から取り除き、候補・条件・妥協点を先に読めること、本文と比較表に異なる幅を使うこと、スマートフォンで判断表をカード、仕様表を表内スクロールとして読めることです。詳細証拠は元の出典IDへ直接移動して開けます。

## 自動検査

- `make fast BASE=origin/main` で静的検査、型検査、生成物の整合検査を実行。全体テストは19,847件成功、34件skip、旧ナビ・旧CSSの期待値による3件の失敗を確認した。
- 失敗した3件を先に修正・再検査。JavaScriptなしのナビを独立ページへ移動する検査に変更し、項目数・画面条件はデータから確認する。表示の要件を緩めて合格させていない。
- readerの振る舞い検査では、出典リンク・元の日付・商品集合の保持、未検証offerの非表示、画像のAPI証拠と利用承認の両方、UNKNOWN、欠損値、2/4/5/7商品、状態確認記事の比較化禁止、未実機体験の断定と明示的な未確認説明の区別を確認する。
- 通常検査とCIの最終結果は統合PRのチェック・説明に記録する。PHP CLIや専用PostgreSQL 18.4がないローカルskipは合格として数えない。CIのPHP 7.4・Storage・Databaseは別の実行結果で確認する。
- ローカルUI検査もCIも、本番承認や実読者の理解度の実測ではない。

## 残件と次の順序

1. 5人以上の実読者テストを実施し、5/6問以上を回答できた割合80%以上を目標に評価する。依頼送信は実行していない。`READER_VALIDATION.md` と空のCSVを使用する。
2. SOLOTA NP-TMLK1-K／ラクアmini Plus TK-MDW22Bの必須データを揃える。別型番の仕様は転用しない。欠損の詳細は `READER_DATA_GAPS.md`。比較記事はそれまで生成しない。
3. 商品写真・編集写真の利用根拠を承認し、意味のある構造図・記事別ビジュアルを追加する。未承認時は現在の画像なし表示を維持する。
4. 未制作の設置測定・給水方式・洗剤・手入れ・費用の記事を根拠整備後に作る。制作前のリンクは追加しない。
5. 人の検証結果に基づいてP1/P2の修正を優先し、その後に必要最小限の任意計測の項目・保存期間・オプトアウトを設計する。有効化は別の承認対象。

本番送付・公開、本番下書き更新、provider request、資格情報操作、追跡計測の有効化は**未実施**。MCP、別人承認、proposal、hash/precondition、kill switch、default-offの境界を維持しています。

## 変更ファイル

主な実装は次の編集元にあります。最終差分の全ファイルは統合PRで確認できます。

| 責務 | ファイル |
| --- | --- |
| データと任意スキーマ | `reader-experience.v1.json`、`python/raos/application/editorial/editorial_portfolio_v3.py` |
| 純粋な表示適格性 | `python/raos/application/editorial/reader_experience_v1.py` |
| 共通HTMLと移行 | `python/raos/application/editorial/reader_html.py`、`reader_components.py`、`reader_experience_projection.py` |
| 編集元・公開候補との共有 | `scripts/raos_editorial_portfolio_v2.py`、`scripts/raos_wordpress_incremental_candidate.py` |
| V3とハブの生成 | `scripts/build_editorial_portfolio_v3.py`、`scripts/build_editorial_v3_theme_navigation.py` |
| WordPress表示 | `changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/` の `functions.php`、`theme.json`、`templates/`、`parts/`、`assets/theme.css`、`assets/editorial-v2.css`、`assets/editorial-navigation.js` |
| テーマの生成・実行境界 | `scripts/build_st1704_self_hosted_theme.py`、既存runtime manifestのownerとHTTPS adapter |
| ローカル固定ページ | `changes/wordpress-local-preview-v1/seed.php` |
| 検査 | `tests/wordpress_local_preview/test_reader_experience.py`、既存テーマ・ナビ・source・viewportの関連テスト、`browser/reader_experience_audit.mjs`、`browser/wordpress_local_preview_audit.function.js` |
| 調査・未実施事項 | 本書、`READER_EXPERIENCE.md`、`READER_VALIDATION.md`、`READER_DATA_GAPS.md`、`reader-comprehension-results.csv` |

前半5記事の生成HTMLを直接編集せず、後半5記事の追跡済みHTMLも編集元として保持しています。生成JSON・CSSのrevision・runtime manifestは、それぞれのownerから更新しています。
