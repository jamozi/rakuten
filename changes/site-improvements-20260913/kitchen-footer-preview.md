# 食洗機カテゴリ末尾の3リンク削除

> 追加指示の反映：現在の候補は `ae4dff663a809c8648aa46f874fba610c4a091242b60b4609d6fe3360622c7de`（source `70a173b9`）、本番未公開。「使っている方へ」2画像案内と冒頭の同セクションへのリンクも除去。洗剤・お手入れの記事とデータ、容量・給水・「ほかの条件」は保持。PC1440/390px、残った内部リンク・アンカー、5画像、案内を除去した2記事の存続を確認。関連2テストとlocal preview PASS。現在の結果は `output/site-improvements-20260913/kitchen-care-removal-integration.v1.json`。以下は前回の3リンク削除の記録。

ユーザーの明示指示に従い、本文末尾の「スーツケース」「ロボット掃除機」「ポータブル電源」の列だけを削除した。比較・編集方針、運営・広告方針、画像7枚、食洗機の導線、共通ヘッダー・フッターを保持。削除したnav以外の本文バイトと他33本文が同一であることを照合した。既存のhub validatorから当該navの必須条件だけを除外した。

候補 `84512fa944fcd18eae70b9f13313cd9f19688150a95fd72f89e4b6496d0044f3`（source commit `2f4a51ec`）。プレビュー: http://127.0.0.1:41398/kitchen/ 。本番未公開。

- Source: `d7306d163d059990ae6c5f89f8b49c804e99e5d863713e2212979847de694d69`
- Runtime: `7dfee79eea22aacf272d05673e1a457ce578f19230ca763d2b63148892fd37e6`

関連2テスト、本文・テーマ・計測bindingのgenerator照合、owner-direct preview既定処理PASS。PC1440px・スマートフォン390pxで3リンクの不在、方針リンク2件・画像7枚・共通フッターの保持と周辺表示を確認。無関係な全件検査や再設計は行っていない。

確認画像: `output/site-improvements-20260913/kitchen-footer-1440.png`、`kitchen-footer-390.png`。記録: `kitchen-footer-verification.json`、`kitchen-footer-delta.json`。容量・給水構成の前回確認は [kitchen-preview.md](kitchen-preview.md) の候補別記録を保持。
