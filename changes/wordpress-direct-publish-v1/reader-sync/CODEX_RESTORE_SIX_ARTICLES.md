# 暮らしのしるべ：検索・費用計算の復旧を最優先で実行

対象リポジトリ: jamozi/rakuten
所有者checkout: /home/minami/rakuten
本番: https://kurashinoshirube.com/

## 実行すること

AGENTS.mdとchanges/wordpress-direct-publish-v1/README.mdに従い、次の6記事について **現在の本文を維持した正規再公開と、公開側での動作確認** まで実施する。

- 86: solota-vs-rakua-mini-plus
- 262: dishwasher-installation-measurement
- 263: dishwasher-water-supply-methods
- 264: dishwasher-detergent-guide
- 265: dishwasher-cleaning-guide
- 266: dishwasher-running-cost

一般WordPress編集後、匿名公開でnoindex/nofollow・canonical欠落・サイトマップ除外が観測された。費用記事では計算用JSと入力欄も欠落。保存できたことだけで完了にしない。

## 順序

1. 無関係なdirtyファイルと現ブランチを保護。最新main/該当PRを確認し、既存owner-directのread-only statusで接続と対象権限を確認する。credentialは既存の保管先を使い、会話やログに出さない。
2. 現在の保存本文、post ID/slug/状態、承認snapshotとの一致項目を確認する。内部データは外部に出さず、不一致の項目名と判定だけ記録する。
3. `articles.v1.json`の上記6対象のpatch_sourceからprepareする。既存本文、画像、購入リンク、出典日付、商品構成を保持。商品ID・必須見出しが変わっていれば根拠を調べてレシピを修正し、古いfixtureで上書きしない。
4. 390px/1440pxの既存previewで確認し、対象6記事をowner-directで再公開する。公開機構の初回導入・権限拡張など別の承認が必要な操作は勝手に行わず、その箇所で具体的に報告する。テーマ不一致時は未検証のテーマを同梱しない。
5. 匿名公開URLを再取得してrobots、canonical、H1、サイトマップを確認。費用記事は実ブラウザでフォームの表示、空入力、既知値の単位換算、未確認費目がゼロにならないことを検査する。入力保存・外部送信を追加しない。
6. Gitへ対象差分とテストを同期する。変更範囲のCIを確認して、既存ルールの条件を満たせばマージする。

## 既存CLI

```sh
make wordpress-production-request ARGS='direct status'
make wordpress-production-request ARGS='direct prepare --articles solota-vs-rakua-mini-plus,dishwasher-installation-measurement,dishwasher-water-supply-methods,dishwasher-detergent-guide,dishwasher-cleaning-guide,dishwasher-running-cost'
make wordpress-production-request ARGS='direct preview --candidate <prepareで取得したcandidate-id>'
make wordpress-production-request ARGS='direct publish --candidate <同じcandidate-id>'
```

中断時は既存candidate/journalを読み、statusで照合して再開する。同じ内容を新candidateに作り直して多重公開しない。

## 合格条件

6URLが匿名200、意図したindex/followと自己参照canonical、ページlocとしてサイトマップ掲載。費用計算の既知入力例で期待した従量費を返し、不明費目・未入力をゼロにしない。既存の出典・対象商品・画像・CTAを維持する。検索エンジンへの実際の登録、購入成果、収益の増加は別に未確認として報告する。

## 禁止

robots強制解除、kill switch解除、権限の勝手な拡張、承認捏造、任意PHP/SQLでのCMS迂回、旧fixtureへの巻き戻し、credential表示、実在しない価格・レビュー・実機検証の追加。HTTP200やCI成功だけで「すべて完璧」と報告しない。
