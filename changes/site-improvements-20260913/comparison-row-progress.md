# 比較14記事：共通商品行の実装結果

確認 2026-09-13T06:57:15.879754+00:00。source `fface1a6e90b711941b605e635ce9228f0f1b538`、共有候補 `498e64af203150fd2de62ab22ea36505aa25c8f49ce40d86cb21a308640c90e3`。ローカル実装・表示確認済み。本番未公開。

商品名・実写真・仕様・確認日時付き参考価格・発行済み購入リンクを同じ行に配置。スマートフォンでは商品列を固定。了承済みコンパクトの本文と価格JSを維持。

| 記事 | 主／補足行 | 写真 | 発行購入リンク | 状態 |
| --- | ---: | ---: | ---: | --- |
| [タンク式食洗機4モデルを1〜2人暮らし向けに比較](http://127.0.0.1:41398/countertop-dishwasher-for-small-households/) | 4／0 | 4 | 4 | 実装・表示確認済み |
| [30L以上・3kg以下の機内持ち込みスーツケース4モデルを比較](http://127.0.0.1:41398/lightweight-carry-on-suitcase-under-3kg/) | 4／0 | 4 | 4 | 実装・表示確認済み |
| [省スペースのロボット掃除機を条件で絞る](http://127.0.0.1:41398/compact-robot-vacuum-shortlist/) | 4／0 | 4 | 4 | 実装・表示確認済み |
| [停電対策のポータブル電源4モデル比較｜容量・出力・重さで選ぶ](http://127.0.0.1:41398/portable-power-station-guide/) | 4／0 | 4 | 4 | 実装・表示確認済み |
| [エースの機内持ち込みスーツケース3モデル比較｜軽さ・容量・開き方](http://127.0.0.1:41398/carry-on-suitcase-comparison/) | 3／0 | 3 | 3 | 実装・表示確認済み |
| [100席未満の国内線向け機内持ち込みスーツケース4モデル比較](http://127.0.0.1:41398/carry-on-suitcase-under-100-seats/) | 4／0 | 3 | 3 | 画像待ち：60524（新仕様・USBポートなし） |
| [前開き・ストッパー付き機内持ち込みスーツケース4モデル比較](http://127.0.0.1:41398/front-open-carry-on-suitcase-with-stopper/) | 4／0 | 3 | 3 | 画像待ち：INV50 |
| [Roomba MiniとK11+ Pro｜台の寸法と手入れで比較](http://127.0.0.1:41398/roomba-mini-vs-switchbot-k11-pro/) | 2／1 | 3 | 3 | 実装・表示確認済み |
| [SOLOTAとラクアmini Plus｜大きさ・食器量・乾燥方式](http://127.0.0.1:41398/solota-vs-rakua-mini-plus/) | 2／0 | 2 | 2 | 実装・表示確認済み |
| [Anker Solix 4モデルの違い｜容量・出力・重量で選ぶ](http://127.0.0.1:41398/anker-solix-c300-c800-c1000-differences/) | 4／0 | 4 | 4 | 実装・表示確認済み |
| [コンパクト食洗機を比較｜少量の食器に合う小型機を選ぶ](http://127.0.0.1:41398/compact-dishwasher-comparison/) | 4／0 | 4 | 4 | 実装・表示確認済み |
| [標準容量の食洗機比較｜16〜28点の選び方](http://127.0.0.1:41398/standard-dishwasher-comparison/) | 13／0 | 12 | 13 | 画像待ち：STTDWADW |
| [大容量の卓上食洗機比較｜40点モデルの給水・置き場](http://127.0.0.1:41398/large-dishwasher-comparison/) | 4／2 | 6 | 6 | 実装・表示確認済み |
| [小型・機内持ち込みスーツケース比較｜軽さ・開き方・移動で選ぶ](http://127.0.0.1:41398/small-carry-on-suitcase-comparison/) | 12／0 | 10 | 10 | 画像待ち：82353704, INV50 |

71商品行・66写真行。発行済み購入リンク67行、残る4行は対象商品の公式リンク。価格は確認後24時間以内かつ提供元期限内の本体参考価格のみ。欠損費目から総額を作らず、JavaScript無効時に数値を表示しない。

## 残る画像4機種

- **60524（新仕様・USBポートなし）**：旧仕様とUSBなし仕様の同一性を解消できず。確認済み公式リンクを保持。
- **INV50**：INV50とINV50Gの販売素材が混在。対象INV50の公式リンクを保持。
- **STTDWADW**：白STTDWADWの発行画像はNO IMAGE、別売場は404。取得済み販売リンクと参考価格を保持。
- **82353704**：82353704・アイボリー・EAN4003743040278の利用可能な実写真と発行購入リンクが未取得。公式リンクを保持。

上記は同一型番・色・構成の発行済み画像HTML、または掲載許可のある実写真が必要。画像不足を完了扱いしない。

## 検証

- 共通基盤：`make fast BASE=3fdfe3e3` PASS（4,651並列＋298 serial）。その前の全体実行で見つかった3件は修正し、28件の関連再検査と差分make fastを通過。
- 最後の標準食洗機画像URL修正：生成8 owners PASS、共通商品行12 tests PASS。テーマの照合用hashもowner generatorから更新し、依存生成とテーマ・媒体103 testsを通過。
- 共有WordPress：14記事×5幅＝70表示、CTAと商品・snapshot・URLの対応、画像読込、内部リンクとアンカー、表の固定列、JavaScript無効時の価格非表示を確認。標準・小型スーツケースはキーボードと文字200%も確認。
- 39本文＋テーマの owner-direct preview PASS。公開や本番反映照合は行っていない。

[機械可読結果](comparison-row-progress.v1.json)／[新規記事の手順とひな型](../reader-purchase-support-v1/comparison-rows.md)。元136項目の外部検証待ちと、7手順記事の旧残件は別管理。

進捗Excel：`/mnt/c/Users/naoki/Downloads/kurashinoshirube_all_pages_improvements_20260913_comparison_rows_progress.xlsx`。136 IDの一致と元Excelの未変更を確認。
