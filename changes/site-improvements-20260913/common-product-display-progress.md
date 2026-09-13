# 子商品ページの共通購入情報：進捗

確認：2026-09-13T03:15:05.916474+00:00。ホーム・カテゴリ等の誘導ページを除く20本文。見た目の了承と、今回追加のブランド／実物写真／楽天価格／広告リンクの充足を別管理する。

共有プレビューは初稿候補 `8b3416d…`。共通カタログの名称修正は次の共有候補で反映予定。外部素材不足を完了扱いしない。

| 対象 | 公開ID | 共通情報の担当・状態 |
| --- | --- | --- |
| without-installation | 144 | 専任作業中／01a0987b-b01a-70e3-8353-541edddbff88 |
| carry-on-suitcase-comparison | 19 | 専任作業中／01a098c1-8a77-7550-ba35-7aa7883acf9b |
| carry-on-suitcase-under-100-seats | 82 | 専任作業中／01a098c1-9120-7361-bf09-1674bde6c692 |
| lightweight-carry-on-suitcase-under-3kg | 83 | 専任作業中／01a098c1-97e7-7d60-bb84-ff4a60c5d413 |
| front-open-carry-on-suitcase-with-stopper | 84 | 専任作業中／01a098c1-9f67-7d51-b78f-9ab404bf95d6 |
| countertop-dishwasher-for-small-households | 41 | 専任作業中／01a098c1-da26-7933-832b-d986f44fd858 |
| solota-vs-rakua-mini-plus | 86 | 専任作業中／01a098c1-df93-7df3-bdf8-e0f374cdf7ea |
| dishwasher-installation-measurement | 262 | 専任作業中／01a098c2-2b84-7203-854b-ded5dceadd32 |
| dishwasher-water-supply-methods | 263 | 専任作業中／01a0987c-3d94-7ec2-9bcc-c447e2ce4154 |
| dishwasher-detergent-guide | 264 | 専任作業中／01a098c2-31ef-7053-bb53-0de9507b6d41 |
| dishwasher-cleaning-guide | 265 | 専任作業中／01a098c2-396d-7592-919b-160f04c1f0ca |
| dishwasher-running-cost | 266 | 専任作業中／01a098c2-40cf-70c1-91fb-52124933a225 |
| compact-robot-vacuum-shortlist | 30 | 専任作業中／01a098c1-e5eb-7a22-959d-e7ef541ee59a |
| roomba-mini-vs-switchbot-k11-pro | 85 | 専任作業中／01a098c1-ed2e-78c3-9e19-1d12ac1c79a5 |
| portable-power-station-guide | 28 | 専任作業中／01a098c1-f344-7012-bfb7-a6ad5dd1a3e4 |
| anker-solix-c300-c800-c1000-differences | 29 | 専任作業中／01a098c2-24e9-7693-b030-b6a97bf3eab0 |
| compact-dishwasher-comparison | 未取得 | 専任作業中／01a09879-c31a-71a0-bc4a-8e25573f797b |
| standard-dishwasher-comparison | 未取得 | 専任作業中／01a0987c-8828-7a51-9473-762925e96608 |
| large-dishwasher-comparison | 未取得 | 専任作業中／01a0987c-d1ab-7923-b9eb-610731e0e655 |
| dishwasher-branch-faucet-guide | 未取得 | 専任作業中／01a0987b-fb6f-7901-af4f-d4f7101b8d92 |

詳細は [商品別の確認状態](common-product-display-progress.v1.json)。新規候補の商品同一性と購入条件は各担当の構造化資料を順次統合する。

- 既存カタログ31商品：登録媒体確認済み15、画像未確認16。広告画像原文の利用先を無制限には広げない。
- 既存限定captureの対象外と、正規画面で新規取得できない状態は区別する。単発APIのinstalled doctorはNOT_READYで、原因の細目は未取得。
- ValueCommerce／LinkShareの設定診断はREADY。楽天市場の商品広告が取得できたことを示すものではない。
- Windowsの認証済み画面を操作するnode_repl/browser toolがこのタスクでは使えず、ログイン状態は未検証。認証情報の入力・閲覧は行っていない。
- 楽天の商品別の発行済みリンク／画像HTMLが取得不能な機種は、担当の不足一覧で最小入力を整理する。
- 価格はJSの期限内表示のみ。送料・必要品・新品/中古・色やセットが不明なら総額または購入可能な価格を確定しない。

2026-09-13 訂正：SOLOTA・SS-MA251・NP-TSP1 の3売り場は新品明示を確認できず、旧NEW候補を撤回。共通の[確認済み観測台帳](purchase-observations.v1.json)にUNKNOWNと根拠不足を固定した。型番・色・税込価格の観測と、価格を表示するための条件を分離する。旧候補は共有catalog/WordPressへ取り込んでいない。
