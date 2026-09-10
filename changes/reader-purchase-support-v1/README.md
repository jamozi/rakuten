# 読者の購入判断をつなぐ後継契約

2026-09-10採用。対象は比較41・83・30・28、食洗機ガイド262〜266、食洗機カテゴリ136、方針10・120・3の13既存URL。広告報酬・契約・広告リンク有無による評価と推薦を禁止し、購入総額・維持費・納期・保証を用途と予算への適合判断に使う。値下げは性能評価へ加点しない。旧Editorial V3の性能ゼロ加点、旧CTA/provider slot、不変baselineを保持する。全面的なナビゲーション変更、実読者募集、6社専用APIは対象外。

## 編集元と公開側

- `purchase-support.v1.json`: 16商品枠の仕様、型番・構成、出典・確認日、販売先、期限、調査課題、20本の商品別guide route。
- `articles/`: 最新公開本文を取り込んだ通常の編集元。方針本文と保持する詳細・出典を編集する。比較表・カード・guideの共通項目はカタログを編集する。
- 既存`local-reader-guides.v1.json`: 型番・コース・単位・出典に紐づく費用profile。既存6件を保持しmini colorとNP-TSP1を加えた8件。共通rendererを再利用し、他型番・別コースの値を拒否する。
- `scripts/build_reader_purchase_support_v1.py`: 13本文を`changes/wordpress-direct-publish-v1/articles/`へ、CTAの表示用allowlistだけをtheme `assets/purchase-support.v1.json`へ生成する。本文台帳は既存IDを保持する。
- PHPは適用済みowner-direct public snapshotと生本文、slug、投稿種別、タイトル・抜粋、runtime本文hashを照合する。runtime metadataもtheme integrity hashで検証する。public側は編集元・内部Evidence・Finance・ASP rawへ接続しない。

```sh
.venv/bin/python scripts/build_reader_purchase_support_v1.py
.venv/bin/python scripts/build_editorial_portfolio_v3.py
.venv/bin/python scripts/build_st1704_self_hosted_theme.py --generate
```

本文編集日は仕様確認日・販売条件確認日時とは別。今回の価格確認は2026-09-10の公開販売ページ照合完了時刻を記録した。古い仕様を再調査済みの現在日付へ一括変更しない。価格を更新するときは対象offerの出典、税込・構成、送料、必須品、確認時刻と期限を一緒に更新する。

## 予算・購入導線

購入総額は税込本体・送料・必須品がすべて確認済みで、対象構成・新品・注文可能・総額の適用範囲が一致し、確認後24時間以内かつ提供元の期限内の場合だけ判定する。送料・必要品が欠ける、予約、期限切れ、売り切れ、型番未照合は予算未判定。既知の費目は小計で表示する。0円は確認した0円だけに使う。ポイント・条件付きクーポンは控除しない。通常使用と別の構成（車載・太陽光充電、分岐水栓など）は別途確認が必要。

用途の絞り込みは性能・機能等の理由による既存順を保持する。予算不足が判定できる候補を絞り、未判定は理由付きで残す。入力は保存・送信しない。JSなしでも仕様・条件・出典・購入先を読める。2商品比較では未知の値が一致して見えても行を隠さない。測定欄は9項目の数値照合であり、安全な設置の保証ではない。

6件の通常の公式販売ページを案内し、残る10枠も具体的な調査理由・確認先・次回日を持つ。これは16商品の保証・安全・費用調査が全面完了したという意味ではない。予約品は予約と表示する。NP-TSP1は停止中の旧リンクを購入可能と案内しない。旧公開本文の写真7枚は、今回の候補で再利用できる許諾・利用条件・鮮度の根拠まで追えなかったため表示しない。出典URLと再確認理由・次回確認日を共通データの image_review に残す。全16枠を同じ見出し・条件説明・販売条件の構造にそろえ、素材の許諾が確認できた時だけ追加する。

## ASP取り込みとの接続

既存`tools.affiliate_ingestion.normalize.normalize_record`のproduct出力に、対象記録のfingerprintと完全一致する編集確認票`RAOS_PURCHASE_ASP_REVIEW_V1`を添える。確認票にはpublic offer項目と、広告主提携・当該サイトのリンク利用・素材保存の権限確認が必要。provider statusや商品名だけでは購入先へ昇格しない。private ID、commission、rawは表示用データへ渡さない。6社の接続状態は[既存準備文書](../../docs/affiliate-network-ingestion.md)のまま。

```sh
.venv/bin/python scripts/raos_purchase_support.py import-offer \
  --normalized <許諾済みの1商品レコード.json> --review <編集確認票.json> \
  --output <所有者専用領域の候補カタログ.json>
```

既存カタログは自動変更せず、別候補へ出力する。確認票の`offer`はカタログと同じpublic項目に限り、`affiliate`・`advertiser_authorized`・`link_usage_authorized`がtrue、`site_origin`が当該サイト、`url`が正規化記録の発行URLと完全一致する必要がある。確認票の`source_fingerprint_sha256`で取り込み記録を限定し、`material_storage_authorized=true`を別に確認する。今回、新たなASP素材・提携権限を確認したとは扱わない。

## 検証と公開

`tests/purchase_support/`、既存費用計算、Google取り込み、Editorial V3、owner-direct境界を検証し、`make fast`で関連生成・回帰を実行する。[GA4有効化手順](ga4-activation.md)の本番状態はOFF。所有者・テスト除外、Basic Consent、7識別子、クリックと閲覧分母の分離を維持する。GA4プロパティ設定・実DebugView照合は未実施。

[owner-direct-v1](../wordpress-direct-publish-v1/README.md)で固定候補とlocal previewを作る。未委任の4固定ページは`owner-delegation-additions.v1.json`の追加分だけを提示する。prepareは未委任対象をREADYにせず、後続の委任済み対象の照合は続ける。未委任ページの権限追加後は新しい候補を固定し直す。記事・テーマ公開、GA4設定・本番計測開始は、その具体的対象への所有者の指示後に行う。

[所有者確認・改善観察の記録](evaluation.v1.json)は、3課題の操作確認を実読者調査と呼ばない。計測欠損を0とせず、帰属できない確定報酬は未帰属のまま。分子・分母の対象範囲がそろう場合だけ確定報酬／1,000セッションを算出し、前後差を因果効果と断定しない。
