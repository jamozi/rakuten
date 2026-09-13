# 子商品ページの共通購入情報：進捗

確認 2026-09-13T06:57:15.879754+00:00。対象21本文のうち、商品比較14記事の共通行を共有ローカルへ反映・検証済み。残る7手順・給水記事の購入情報追加は別の未完了範囲。会話上の了承と本番公開は別管理。

[14記事の実装・検証結果](comparison-row-progress.md)／[商品別台帳](common-product-display-progress.v1.json)。

54商品中50商品の写真を表示でき、71商品行に66写真・67発行購入リンクを結合。画像未確認は60524、INV50、82353704、STTDWADWの4機種。全商品に確認済みの購入先または公式リンクを保持。

認証済み楽天画面から発行原文を取得・同一商品と実画像を照合。限定API doctorはローカル修復後READYだが、APIのlive取得や自動価格収集は追加していない。

価格は期限付き本体参考価格。新品明示・送料・必要品が未確認なら総額を確定しない。期限切れ・再訪・タブ復帰で数値を消す共通JSを使用。JavaScript無効では価格数値を出さない。

未完了の手順・給水記事：without-installation、dishwasher-installation-measurement、dishwasher-water-supply-methods、dishwasher-detergent-guide、dishwasher-cleaning-guide、dishwasher-running-cost、dishwasher-branch-faucet-guide。現行本文の共有反映を、購入情報追加や元136監査の全項目完了とは扱わない。

共有候補 `498e64af203150fd2de62ab22ea36505aa25c8f49ce40d86cb21a308640c90e3`。本番未公開。
