# 給水方法の記事を商品比較表へ変更

現在：39本文＋テーマを本番公開・本文照合済み。公開HTML検査は大容量記事のH1重複1件を残件として記録。[公開結果](publication-result.v1.json)。以下はローカル確認時の記録を含みます。

既存 `/dishwasher-water-supply-methods/`（ID263）の「型番別の条件」を商品比較表へ変更。冒頭の給水経路図・3方式の説明・既存31ID・既存リンク先は保持。

主表は SOLOTA NP-TMLK1-K、ラクアmini color TDWS25SBL/TDWS25SRD、シロカ SS-MA251、Panasonic NP-TSP1-W の4機種。SS-LH451は外部容器から給水する別の補足例として独立した表に表示。各行に確認済み写真・給排水の対応条件・確認日時付き本体参考価格・発行済み楽天購入リンクを配置した。

主4行の詳細手順と出典は共通カタログの water_supply / drainage から生成。ラクアmini colorの別売ポンプの停止動作と公式FAQを保持。SS-LH451の準備量10Lと使用水量9L/8.5Lは区別する。写真の元HTMLや購入先を創作・変更していない。

ガイドの既存写真上限4点へ例外的に上乗せするのではなく、公開runtimeに主対象と補足を区別した範囲を持たせた。PHPは主1〜4件・補足0〜1件、重複なし、登録範囲内の写真だけを認める。従来ガイドは従来上限のまま。snapshot・テーマhashの照合とdefault-offの動作を維持。

共有URL： http://127.0.0.1:41398/dishwasher-water-supply-methods/#guide-evidence

source `ac41ceed`。候補 `1e5335f747d6934d8eb894b83cd46c19f451817ff33bb9327d723c576e1466aa` は給水記事＋テーマのローカル追補。直前の39本文は候補8549ac2a、比較14記事の実表復元確認は80fd2d0eに対応する。本番未公開。

検証：owner-direct local preview PASS。5幅320/375/390/768/1440で実表3列・5写真・5購入リンク・横溢れなし。追加600pxを含む6幅で全CTA ID/商品ID/snapshot/発行URL・見出し中央・広告告知1回を照合。31旧ID/既存href/冒頭6区画の完全保持PASS。最小画像幅は320px時98.9px。価格期限直前・期限到達時・タブ復帰・2日経過相当・再読込・JavaScript無効時を確認し、期限後も購入リンクを保持。通常表示のJSエラーなし。

対象テスト22件PASS。画像範囲の欠損・重複・未登録商品の拒否、主/補足混同の拒否、カタログ手順変更の反映、別売ポンプ・旧アンカーの保持、全比較記事の写真projectionを含む。共通make fastは別途の記録を参照。

検証記録： `output/site-improvements-20260913/water-table-review/`、`output/site-improvements-20260913/common-layout-review/verification-dishwasher-water-supply-methods.json`。

変更後のユーザー最終了承は未取得。会話レビュー台帳では確認待ち。

共通条件が未確認へ戻った場合に、早見欄の古い値も撤回する対応をsource `d98087d2`へ追加。関連59件PASS、通常時の39本文の表示テキストはac41ceedと完全一致。最終統合候補 `ab3183434544c45cda7a761fdcc0e6bf16544481917743a57e0098e630e6ac0b` のlocal previewと5幅/価格表示チェックもPASS。共通検査の元実行・失敗修正・後続partitionの結果は table-update-progress/validation.json に区別して記録。

2026-09-13追記：39本文＋テーマを候補4d0a0dbc／83b8ea07で本番公開・本文照合済み。上記の「未公開」は当時のローカル検証記録。大容量H1重複1件を残件に追加し、会話レビュー・外部確認の未完了は保持。[公開結果](publication-result.v1.json)。
