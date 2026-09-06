# Anker Solix 4モデルの寿命表記・限定編集レビュー

2026-09-06に、既存記事の寿命条件を追記し、サイクル数だけを根拠にした推薦・除外条件を修正した。対象は既存のC300、C800 Plus、C1000、C1000 Gen 2。実機の耐久性や使用年数を検証した結果ではない。

| 変更ファイル | 変更内容 |
| --- | --- |
| [articles.v1.json](../st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json) | Anker記事のみ。主要仕様表の後に条件表を追加。推薦等の14文字列を限定修正し、比較方法に年数換算・寿命順位付けをしない説明を追加 |
| [source-registry.v1.json](../st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json) | 変更前に親へ通知。Anker packetに単独公式出典へ結ぶ寿命条件claimを4件追加。既存の条件別推薦claimの1文を修正。関連する4出典と1 packetの構造化JSON hash、coverageを整合 |
| [test_anker_lifecycle_conditions.py](../../tests/st1704/test_anker_lifecycle_conditions.py) | 型番ごとの単独出典、条件のUNKNOWN、確認日の整合、補助表の4製品構成、推薦からサイクル数を除く境界を検査 |
| 本書 | 根拠、差分、検査、残るUNKNOWNを記録 |

4製品の名前・代表型番・掲載順、slug、canonical URL、既存source refs、基本仕様・寸法、CTA、既存の取得日・記事確認日・カード確認日・販売状態の日時を維持した。他記事と他article source packetの内容は変更していない。

| Finding | 修正と残る条件 |
| --- | --- |
| P1：Gen 2の4,000回以上を、残存容量・試験条件なしで推薦やC1000の除外理由に使用 | 冒頭の選び方、選定軸、tradeoff、推薦データ、商品カードの該当文だけを、軽さ・USB-C 3口・拡張性による既存判断へ修正。公表回数は条件表に残した |
| P2：サイクル回数と製品保証の意味を読み分ける表がない | 5軸×4モデルの補助表を追加。残存容量と試験条件の欠損はUNKNOWNとして表示 |
| P2：汎用claimの個別観測日時を保持する構造化フィールドがない | 下記の日付制約を明示。既存共通日付は変更せず、補助表のchecked_atと各専用claim本文に今回の限定確認日を記録 |

公式一次情報の読み取りだけを行い、各製品ページの本文・比較表・保証欄を確認した。レビュー本文、他モデルの保証、共通ナビゲーションの会員特典を根拠に転用していない。「未確認」は今回確認した範囲で未確認という意味であり、公式情報に存在しないという断定ではない。

| モデル・既存代表型番 | 電池の公表サイクル数 | 対応する残存容量基準 | サイクル試験条件 | その型番の製品ページで確認した保証案内 | 個別の公式出典・locator |
| --- | --- | --- | --- | --- | --- |
| C300 / A17225Z1 | 3,000回 | 未確認 | 温度・充放電レート・放電深度は未確認 | 通常18か月。Anker Japan公式オンラインストア会員は5年へ延長。購入先ごとの適用可否・除外条件は未確認 | [C300公式製品ページ](https://www.ankerjapan.com/products/a1722)：「類似商品と比較する」のC300列・寿命行、製品固有の保証欄。SRC-ANKER-SOLIX-C300 |
| C800 Plus / A1754 | 3,000回 | 未確認 | 温度・充放電レート・放電深度は未確認 | 通常18か月。Anker Japan公式オンラインストア会員は5年へ延長。購入先ごとの適用可否・除外条件は未確認 | [C800 Plus公式製品ページ](https://www.ankerjapan.com/products/a1754)：「類似商品と比較する」のC800 Plus列・寿命行、製品固有の保証欄。SRC-ANKER-SOLIX-C800-PLUS |
| C1000 / A17615Z1 | 3,000回以上 | 初期容量の80%まで低下するまでの回数 | 温度・充放電レート・放電深度は未確認 | 通常18か月。Anker Japan公式オンラインストア会員は5年へ延長。購入先ごとの適用可否・除外条件は未確認 | [C1000公式製品ページ](https://www.ankerjapan.com/products/a1761)：本機の特徴欄のサイクル数注記、比較表のC1000列・寿命行、製品固有の保証欄。SRC-ANKER-SOLIX-C1000 |
| C1000 Gen 2 / A17635Z1 | 4,000回以上 | 初期容量の80%まで低下するまでの回数 | 温度・充放電レート・放電深度は未確認 | 通常18か月。Anker Japan公式オンラインストア会員は5年へ延長。購入先ごとの適用可否・除外条件は未確認 | [C1000 Gen 2公式製品ページ](https://www.ankerjapan.com/products/a1763)：サイクル数を説明する特徴欄の注記、比較表のGen 2列・寿命行、製品固有の保証欄。SRC-ANKER-SOLIX-C1000-GEN2 |

4ページの寿命条件を今回実際に確認した日は2026-09-06。C1000とGen 2の80%基準はそれぞれ自身の注記で確認した。C300・C800 Plusには流用していない。急速充電時間についての20°Cという条件、動作・保管温度、一般的な使用環境の説明はサイクル試験条件へ転用していない。保証欄の記載が4モデルで同じであることは各出典で個別に確認した。全販売店・全購入者への5年保証、容量低下への保証適用は主張していない。

日付の保持範囲は次のとおり。

| 項目 | 日付・状態 |
| --- | --- |
| 既存4公式sourceのretrieved_on | 2026-08-31を維持 |
| 記事freshness、既存商品カード、methodology、source_summary | 既存の2026-09-01を維持 |
| 既存manufacturer_sales_state.checked_at | 2026-08-31T14:19:31Zを維持。今回の寿命確認で販売状態は再確認・更新していない |
| 補助表presentation.checked_at | 2026-09-06。寿命・保証条件の限定確認 |
| 4件の寿命条件claimと各出典セル | 2026-09-06を明記 |
| claim単位の構造化observed_at / checked_at | 現行スキーマ未対応 |

python/raos/application/editorial/self_hosted_editorial_pilot.py のsource読込はexact_keysで、日付はretrieved_onのみを許容する。_CLAIM_BASE_KEYS / _CLAIM_OPTIONAL_KEYSには汎用のobserved_at / checked_atがない。既存のmanufacturer_sales_state.checked_atは販売状態専用で、evaluated_atは市場候補用の必須フィールド群に属するため、寿命条件の観測日時には流用しなかった。

したがって、旧sourceのretrieved_onを今回の4件の新規観測日時と解釈してはいけない。今回の確認日は補助表の構造化checked_atと専用claim本文に分けたが、個別claimの日付をruntimeが独立して検証する仕組みは未対応である。更新したhashは既存関数が算出する構造化fact JSONの整合値であり、今回取得したwebレスポンスそのものの固定記録ではない。この制約は親へ通知済み。

ASTでは既存のcomparison_table型を再利用した。

- block：BLK-ANKER-LIFECYCLE-001
- table：TABLE-ANKER-LIFECYCLE-V1
- 追加軸：AXIS-ANKER-LIFECYCLE-CYCLES / CAPACITY / TEST / WARRANTY / SOURCE
- 各行：CLM-ST1704-ANKER-{C300,C800-PLUS,C1000,C1000-GEN2}-LIFECYCLE-CONDITIONSの1件だけを参照し、各claimのevidence_refsは対応する公式製品ページ1件
- 任意表示メタデータ：{"role":"supporting_evidence","checked_at":"2026-09-06","source_axis_ref":"AXIS-ANKER-LIFECYCLE-SOURCE"}

元のtableの4keyを維持したうえでpresentationを追加した。source_axis_refが実在するaxis_refsと一致することも検査した。親担当が汎用の補助表レンダリング、表固有の見出し・日付・出典リンク、画像の重複抑制を実装する。この担当ではrendererを変更していない。

差分の中心は、既存の主要仕様表からGen 2の無条件な電池回数表示を取り除いて条件表へ集約したことと、次の推薦文の変更である。

| 箇所 | 変更前の要点 | 変更後の要点 |
| --- | --- | --- |
| Gen 2の選択条件 | 軽さ・4,000回以上・USB-C 3口 | 軽さ・USB-C 3口 |
| C1000を選ばない条件 | 4,000回以上やUSB-C 3口を優先 | USB-C 3口が必要 |
| Gen 2の向く人 | 頻繁に使用するため公表回数を重視 | 拡張不要で持ち運ぶ重さを抑えたい |
| 既存CONDITIONAL-CHOICES claim | 公表サイクル数を条件にGen 2を推薦 | 条件が揃わないため寿命の優劣・推薦条件に使わない |

実行した検査（いずれもWSL Ubuntu-22.04、実repo内）：

~~~sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider \
  tests/st1704/test_anker_lifecycle_conditions.py \
  tests/st1704/test_self_hosted_editorial_content.py -q
# 24 passed in 0.38s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m ruff check --no-cache \
  tests/st1704/test_anker_lifecycle_conditions.py
# All checks passed!

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m ruff format --check --no-cache \
  tests/st1704/test_anker_lifecycle_conditions.py
# 1 file already formatted

git diff --check
# exit 0
~~~

既存contentの18検査と追加6検査で、凍結ASTスキーマ、claim coverage、全sourceの構造化hash、既存製品・出典境界を確認した。別途、読み取り専用のHEAD比較をPythonのassertで実行し、非Anker記事・他packetが不変、既存sourceの変更は4件のhashのみ、既存claimの変更はCONDITIONAL-CHOICESの1件のみ、型番・source refs・既存日時が不変であることを確認した。formatterの初回指摘は追加テストファイルだけ整形して解消した。

この担当では共通generate、生成済みHTML、reader-experience.v1.json、local-reader-guides.v1.json、料金フォーム、renderer、branch操作、commit、サブエージェント起動を行っていない。provider request、login、規約同意、CMS送付、本番・公開更新も行っていない。新しい補助表のHTML表示と統合検査は、親のレンダラー実装・共通generate後に確認するため、この報告の24件の合格には含めない。

残るUNKNOWNは、C300・C800 Plusの残存容量基準、全4モデルの詳細なサイクル試験条件、購入先ごとの保証適用・購入証明や登録の手続き・容量低下の扱いを含む除外条件、実機の経年劣化・使用年数、claim単位の独立した観測日時の機械検証である。既存のリコール・修理等の未完了条件や公開ゲートを、この寿命表の追加で解消した扱いにはしていない。

統合中の再確認で、C1000自身の特徴欄の注記に「80%まで」「3,000回以上」を確認し、当初のUNKNOWNを訂正した。年数の宣伝表記は記事へ採用せず、詳細試験条件UNKNOWNと順位付け禁止は維持した。上記24件は訂正前の担当内検査であり、最終結果は統合実装報告を参照する。
