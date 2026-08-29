# 暮らしのしるべ 比較記事 — Editorial V2

## 変更した考え方

初案の「要件ごとにカードへ分解する」考え方を廃止し、一つの特集記事として読ませる誌面に変更した。

- 角丸カード、ドロップシャドウ、バッジ、背景色付きボックスの反復を削除
- 写真、明朝見出し、広い余白、細い罫線、脚注を主役に変更
- 各セクションを同じパターンにせず、左右分割、番号付きリスト、表、商品評、編集後記でリズムを変化
- 「総合1位」ではなく、条件ごとの短い結論を提示
- 商品カードはタイルではなく、写真と文章を組み合わせた `Product Portrait` として設計
- 楽天CTAは塗りつぶしの広告ボタンから、陶土色のアウトライン導線へ変更
- 出典はカードではなく、記事末尾の脚注として表示

## アートディレクション

- 基準: 日本の生活文化誌、フィールドガイド、長文編集記事
- 印象: 静か、温かい、観察的、誠実
- 背景: Paper `#F7F2E9`
- 本文: Ink `#17243F`
- 判断・注意: Clay `#8A3924`
- 補助: Muted `#59635F`
- 見出し: `Yu Mincho / Hiragino Mincho ProN`
- 本文・UI: `Hiragino Kaku Gothic ProN / Yu Gothic`

## 写真

`kurashinoshirube-editorial-hero-v2.png` はレイアウト検討用の生成写真。公開時は比較対象を識別でき、権利と出典を確認した実商品画像へ差し替える。

生成仕様:

- Built-in image generation
- Use case: `photorealistic-natural`
- 静かな日本の住空間、朝の自然光、ロゴのない大小2台のポータブル電源
- 左側に余白、右側に商品を非対称配置
- ロゴ、文字、人物、過剰な小物、CG的な光沢、広告的な発光を禁止

## Figma取り込み

1. Desktop / Mobile SVGと写真PNGを同じFigmaページへドラッグする。
2. SVG内の相対画像参照が復元されない場合、`HeroImage` と `ProductProfile` の画像領域へPNGを再配置する。
3. SVGの主要グループ名をFigma Frame名として維持する。
4. `Hero`, `Lead`, `DecisionSummary`, `IntendedReader`, `Methodology`, `ComparisonTable` / `ComparisonCards`, `ProductProfiles`, `SelectionRationale`, `Sources` の順に縦Auto Layoutへ変換する。
5. Desktopは1200pxグリッド、Mobileは350px本文幅を維持する。

## 実装上の必須事項

- Desktopの比較は表、Mobileは商品別の定義リストとして同じデータから描画する。
- 不明値は `未確認` として表示し、空欄・ゼロ・推測値へ置き換えない。
- CTA直前に価格・在庫の注意とアフィリエイト表記を置く。
- CTAのアクセシブルネームへ商品名を含める。
- 写真キャプションへ出典と確認情報を表示する。
- 選定根拠に候補条件、除外条件、比較日、不明値の扱いを含める。
