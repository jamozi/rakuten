# 暮らしのしるべ 比較記事テンプレート

## 1. デザイン意図

比較記事を「おすすめ順に眺めるページ」ではなく、読者が自分の条件と根拠を照合するための編集ページとして設計する。

- SAKIDORI系の記事で一般的な、多数の商品画像・ランキング・複数モールCTAを連続させる密度は採用しない。
- 色数を抑え、明朝見出し、広い余白、細い罫線で落ち着きと信頼感をつくる。
- 「総合1位」ではなく「条件別の第一候補」とする。
- 編集判断、確認済み事実、購買導線を別の視覚レイヤーに分ける。
- 不明値は空欄やゼロで置き換えず、「未確認（一次情報なし）」として表示する。
- 商品カードのCTAは楽天市場への1ボタンに絞り、直前に価格・在庫の注意を置く。

## 2. Figma取り込み

対象ファイル:

- `kurashinoshirube-comparison-template-desktop.svg` — 1440 × 5660
- `kurashinoshirube-comparison-template-mobile.svg` — 390 × 7780

SVGをFigmaへドラッグして配置する。主要セクションは次のIDでグループ化済み。

1. `Header`
2. `Hero`
3. `Disclosure`
4. `DecisionSummary`
5. `IntendedReader`
6. `Methodology`
7. `ComparisonTable` / `ComparisonCards`
8. `ProductCards`
9. `SelectionRationale`
10. `Caution`
11. `Sources`
12. `Footer`

取り込み後は、各セクションを縦Auto Layoutへ変換し、本文幅をDesktop 1000px、Mobile 350pxで固定する。商品カードだけを再利用コンポーネント化し、`Priority=Portable | Capacity` のバリアントまたはテキストプロパティで運用する。

## 3. デザイントークン

| 用途 | 名前 | 値 |
|---|---|---|
| ページ背景 | `color/bg/paper` | `#F7F2E9` |
| カード背景 | `color/bg/surface` | `#FFFDF8` |
| 本文 | `color/text/ink` | `#17243F` |
| 主色 | `color/action/indigo` | `#24365F` |
| CTA・注意 | `color/action/warm` | `#983F25` |
| 向く人背景 | `color/bg/mist-soft` | `#EEF3F2` |
| 向かない人背景 | `color/bg/warm-soft` | `#FFF8F3` |
| 差分セル | `color/bg/difference` | `#FFF4EC` |
| 補助色 | `color/text/muted` | `#4F5B57` |
| 罫線 | `color/border/default` | `#9BA9A5` |
| 弱い罫線 | `color/border/subtle` | `#D6DFDC` |

タイポグラフィ:

- 見出し: `ui-serif, Yu Mincho, Hiragino Mincho ProN, serif`、Weight 600
- 本文・UI: `ui-sans-serif, -apple-system, BlinkMacSystemFont, Hiragino Kaku Gothic ProN, Yu Gothic, sans-serif`
- 本文行間: 1.75〜1.85
- Desktop本文: 17px、Mobile本文: 15px

角丸は6〜8pxを基本とし、カードを丸めすぎない。影は商品カードだけに8%の薄い藍色で使用する。

## 4. セクション仕様

### Hero

- カテゴリ、H1、リード、執筆者、最終確認日、比較対象数、読み時間を表示。
- H1は結論を煽らず、比較の着眼点を示す。
- 更新日だけでなく「最終確認」と表記して、仕様確認時点であることを明確にする。

### Disclosure

- 記事冒頭、Hero直後に固定。
- アフィリエイトの存在と、掲載順・評価との切り分けを2文で説明。
- 削除不可の編集ブロックとして扱う。

### Decision summary

- 「総合1位」を使わず、「条件Aなら商品A」「条件Bなら商品B」を並列表示。
- 各カードは判断理由セクションへアンカーリンクする。

### 向く人・向かない人

- 記事全体の適用範囲を、比較表より前に示す。
- 「向かない人」を弱めず、同じ面積・同じ視認性で表示する。
- 商品カード内でも商品固有の向く人・向かない人を再掲する。

### 選定根拠 / Methodology

必須フィールド:

- 候補母集団
- 採用条件
- 除外条件
- 比較軸
- データ確認日
- 不明値の扱い

結論より前に基準を公開し、記事ごとの恣意的な採点を避ける。

### 比較表

- Desktopは行見出しを左、商品を列に置く。
- ヘッダーは濃藍、差のあるセルのみ淡い陶土色。
- 同じ値も省略しない。
- 出典種別と確認日を値の下に12pxで添える。
- 不明値は「未確認（一次情報なし）」と表示する。
- 表全体にcaptionを付け、`scope=row` / `scope=col` を実装する。

### Mobile comparison cards

- 横スクロール表ではなく、商品別カードへ変換する。
- すべてのカードで比較軸を同じ順序に保つ。
- 商品名と軸名を各カード内に保持し、表の関係性を失わない。

### 商品カード

構成順:

1. 商品画像（4:3）
2. 条件ラベル
3. 商品名
4. 1文評価
5. 確認済み要点
6. 向く人
7. 向かない人
8. 価格・在庫注意
9. 楽天CTA
10. アフィリエイト表記と最終確認日

CTA文言は `楽天市場で価格・在庫を見る` に統一する。「最安値」「今すぐ買う」「残りわずか」など、遷移先で確認できない誘導文は使わない。

### 出典

- 仕様はメーカー公式、価格・在庫は楽天市場と出典カテゴリを分ける。
- 出典ごとに確認対象、一次/二次情報、確認日を表示する。
- 記事末尾に更新履歴と編集方針へのリンクを置く。

## 5. レスポンシブ

| 項目 | Desktop | Mobile |
|---|---|---|
| 本文幅 | 1000px | 350px |
| 結論カード | 2列 | 1列 |
| 向く/向かない | 2列 | 1列 |
| 比較 | table | 商品別cards |
| 商品カード | 2列 | 1列 |
| 選定理由 | 4列 | 1列 |
| CTA | カード幅 | 全幅 |

推奨ブレークポイントは768px。比較表からカードへの切替はCSSだけでなく、同じデータモデルから別Rendererを出す。

## 6. アクセシビリティと信頼性

- 本文と背景のコントラストは4.5:1以上、CTA文字は3:1以上を維持する。
- CTAの最小高さは48px。Mobileは54px。
- キーボードフォーカスはWarm `#83361F` の3pxアウトラインを使用する。
- 商品画像には商品名と識別に必要な特徴を含むaltを付ける。装飾画像は空alt。
- CTAだけで商品を識別させず、商品名をボタンのアクセシブルネームへ含める。
- 出典リンクは「公式サイト」だけでなく、対象製品名と情報種別を含める。
- 価格・在庫は記事本文へ固定表示せず、必要な場合は取得時刻を併記する。

## 7. 既存RAOSブロックとの対応

| デザイン | 記事ブロック |
|---|---|
| Disclosure | `disclosure_slot` |
| Hero lead | `lead` |
| Decision summary | `decision_summary` |
| 向く人・向かない人 | `intended_reader` |
| Methodology | `methodology` |
| 比較前の差分要約 | `difference_matrix` |
| 比較表 / Mobile cards | `comparison_table` |
| 商品固有の利点・制約 | `tradeoff` |
| 条件別候補 | `recommendation_group` |
| 商品カード | `product_card` |
| 購入前注意 | `caution` |
| 出典 | `source_summary` |

この順序は既存の `product_comparison` テンプレート契約と整合する。
