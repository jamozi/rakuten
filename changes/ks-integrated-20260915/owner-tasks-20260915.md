# オーナー作業の手順書 (2026-09-15)

ログインが必要な画面の作業です。結果はこのファイルの「記入欄」に書くか、画面のスクリーンショット／CSV を `tmp/20260915/owner/` に置いてください。Claude が `evidence/KS-004.md` へ転記します。

## A. Search Console (KS-004 / KS-027) — 所要 10 分

1. https://search.google.com/search-console を開き、プロパティ `kurashinoshirube.com` (ドメイン or `https://kurashinoshirube.com/`) を選ぶ。
   - プロパティが無い場合: 「プロパティを追加」→ URL プレフィックス `https://kurashinoshirube.com/` → 所有権確認は「HTML タグ」を選び、表示された `content="…"` の値を控える (テーマの `googleverify` オプションに設定できます。値を教えてください)。
2. 左メニュー「サイトマップ」: `sitemap_index.xml` の行の **ステータス** (成功／取得できませんでした) と **検出された URL 数** を控える。未送信なら「新しいサイトマップの追加」に `sitemap_index.xml` と入力して送信。
3. 「ページ」(インデックス作成 → ページ): 「インデックスに登録済み」の件数と、「登録されていない理由」の上位 3 件と件数を控える。
4. 上部の検索窓 (URL 検査) で次の 5 件を順に検査し、「URL は Google に登録されています／いません」と「最終クロール日」を控える:
   - `https://kurashinoshirube.com/`
   - `https://kurashinoshirube.com/kitchen/`
   - `https://kurashinoshirube.com/compact-dishwasher-comparison/`
   - `https://kurashinoshirube.com/roomba-mini-vs-switchbot-k11-pro/`
   - `https://kurashinoshirube.com/portable-power-station-guide/`
5. 「検索パフォーマンス」: 期間を「過去 28 日間」にし、右上「エクスポート → CSV」で保存 (`tmp/20260915/owner/gsc-28d.zip`)。合計の **表示回数 / クリック数 / 平均 CTR / 平均掲載順位** も控える。

記入欄 (2026-09-15 14:30〜14:50 JST、Claude がログイン済みブラウザで取得):
```
サイトマップ status: 成功 (sitemap_index.xml 最終読込 2026/09/14)  検出 URL 数: 39 (wp-sitemap.xml も 39 で重複登録)
インデックス登録済み: 12 件 (レポート更新 2026/09/04) / 未登録 11: 404 ×4 (テーマ資産・WP コア・旧プレビュー URL), noindex ×3 (記事19 + 旧プレビュー 2), 403 ×2, リダイレクト ×1, 検出-未登録 ×1 (記事29)
URL 検査: / 登録済み ; /kitchen/ 登録済み ; /compact-dishwasher-comparison/ 登録済み ; /roomba-mini-vs-switchbot-k11-pro/ 登録済み ; /portable-power-station-guide/ 登録済み ; 新規 5 記事 (549〜553) 登録済み ; 記事19 未登録 (noindex の旧コピー) → 再クロール依頼済み ; 記事29 検出-未登録 → 再クロール依頼済み
28 日 (08/16〜09/12): 表示 241 / クリック 7 / CTR 2.9% / 順位 9.1。上位ページ: 記事85 (4 クリック/59 表示), 記事83 (2/60), 記事86 (1/42), ホーム (0/73)
```

## B. GA4 (KS-004) — 所要 5 分

1. https://analytics.google.com でプロパティ (測定 ID `G-7CV8F96487`) を開く。
2. 「レポート → リアルタイム」または「レポート → エンゲージメント → ページとスクリーン」で、過去 7 日の **表示回数** と **ユーザー数** を控える。2026-09-15 10:40 JST に `/roomba-mini-vs-switchbot-k11-pro/` へ同意付きで 1 回アクセスしています (検証ヒット)。
3. 「管理 → データストリーム → ウェブ → 拡張計測機能」: ON/OFF を控える (購入クリック計測を有効化する場合は OFF が前提)。
4. 決めること: 購入先クリック計測 `offer_click` を有効化するか。
   - 有効化する場合の作業は `changes/reader-purchase-support-v1/ga4-activation.md` の手順 (カスタムディメンション 7 件の登録 → 本番定数 `RAOS_PURCHASE_GA4_ENABLED` → DebugView 確認)。Claude 側の準備は完了しているので、指示があれば候補を作ります。
   - 有効化しない場合は、KS-005 の基準値は「ページビューのみ」で設計します。

記入欄 (2026-09-15 14:45〜14:55 JST、Claude が取得):
```
7 日: 表示回数 0 / ユーザー 0 (ホーム「受信したデータはまだありません」、ストリーム「過去 48 時間に受信したデータなし」)   拡張計測: OFF 相当 (測定中はページビュー数のみ)
データフィルタ: 「Internal Traffic」内部トラフィック・除外・有効 → 自宅回線 (Claude の検証も同じ回線) のヒットは除外される。送信自体は 204 で受理 (evidence/KS-004.md)
残り: スマホのモバイル回線で /kitchen/ を開いて同意 → リアルタイムに 1 ユーザーが出るか確認 (約 2 分)
offer_click を有効化: する / しない (理由: ______)  ← 未決定
```

## C. 楽天アフィリエイト管理画面 (KS-006 の項目 1・4) — 所要 5 分

公開規約の条文は Claude が取得済み (`evidence/KS-006.md`)。アカウント固有の 2 点だけ確認してください。

1. https://affiliate.rakuten.co.jp/ → 「サイト情報の登録・変更」: 登録済みサイト URL に `https://kurashinoshirube.com/` があるか、**審査状態** (承認済み／審査中) を控える。SNS を登録していれば併記。
2. 「レポート」: 直近 30 日の **クリック数 / 売上件数 / 確定報酬** を控える (KS-005 の基準値)。破棄 (自己購入等) があれば件数も。
3. 追加 ASP (Amazon アソシエイト、バリューコマース、もしも等) に**既に登録済み**のものがあれば名称と審査状態を控える。未登録なら「なし」。

記入欄 (2026-09-15 14:40 JST、Claude が取得):
```
楽天: 登録 URL https://kurashinoshirube.com/ (順位1位、ジャンル 住まい・インテリア・雑貨) / 登録済み (審査状態の表示なし = 利用可) / SNS なし / 計測ID 20 件設定済み
30 日: クリック 25 / 売上件数 0 / 確定報酬 0 円 / 破棄 表示なし (今月 9/1〜: クリック 12)
他 ASP: 画面では確認対象外 → 登録があれば名称を教えてください (なければ「なし」)
```

## D. 完了したもの (Claude が代行)

- KS-007: EcoFlow 公式ページ (https://jp.ecoflow.com/products/delta-3-classic) の仕様表で `サイズ（W×D×H） 20.0×39.8×28.3cm`、`重量 約12.1kg`、`容量 1024Wh`、`定格出力 1500W` を 2026-09-15 14:09 JST に実ブラウザで確認。記事 28 の修正値と一致 (証拠: `output/ks-20260915/ks-007-ecoflow-delta3-classic-spec-20260915.png`)。
- KS-006 の公開規約部分: 楽天アフィリエイトガイドライン (更新日 2025/6/26)、広告掲載基準、禁止事項 FAQ、楽天ウェブサービスのデータ更新頻度 FAQ を取得し `evidence/KS-006.md` に条文と URL を記録。
