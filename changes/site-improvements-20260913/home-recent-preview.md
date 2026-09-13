# 新着4記事の画像差し替え

ユーザーの指示に従い、新着4カードに異なる写真風の編集画像を生成して割り当てた。費用は電卓と家計ノート、お手入れはフィルター・布・ブラシ、洗剤は匿名の容器と空の計量スプーン、給排水は容器と未接続のホース。構図と主役が異なる4枚で、自然光・生成り・木・淡い緑の色調を統一した。画像へ見出しやロゴを追加せず、実機の型番や手順・用量の証明に使わない。

元PNGを保存し、owner generatorから900×600pxのWebPへ変換。4枚合計204,650bytes。組み込みimage_genを使用し、特定のモデル名はツールから取得できないため断定しない。生成元・保存先・alt・ハッシュは [home-recent-images.v1.json](home-recent-images.v1.json) に記録した。

- 候補: `e5bf33d2441ca8cb0813feb1f86c8c780dc56537cb321bffe2938252a5f14742`（source commit `4209f93d`）、本番未公開。
- プレビュー: http://127.0.0.1:41398/#km-updates-title
- Source: `aef0482cd9c4b14d769dde1e80a7eafcaab037ffb02fa44a9e4e5dd7ae163548`
- Runtime: `e7b808b7bb0eb974e48598464775c42fe17a80c8a373a4f1d88959d788ecbe8a`
- ホーム本文は新着4枚のimgタグ以外同一。ヒーロー、カテゴリー、方針、レイアウトCSS、記事の選出と順番266・265・264・263、全リンクを保持。他33本文も同一。
- PC1440px・スマートフォン390pxで4枚の読み込みと見た目を確認。配信画像のバイトハッシュが4枚とも記録と一致。画像リンク4つからキーボードで元の記事へ実遷移しHTTP200。可視注記を復活させていない。
- 関連25テスト＋16subtests通過。テーマsource・画像生成物・計測bindingの整合性を確認。owner-direct preview既定処理もPASS。無関係な全件テストや新しい全サイト監査は行っていない。

確認画像: `output/site-improvements-20260913/home-recent-1440.png`、`home-recent-390.png`。実画面記録は `home-recent-verification.json`、変更限定の照合は `home-recent-delta.json`。以前の全34ページ検証と外部確認待ちを保持する。
