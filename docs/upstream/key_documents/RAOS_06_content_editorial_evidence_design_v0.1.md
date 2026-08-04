# RAOS-CONTENT-001: 記事タイプ・編集・根拠仕様

- 文書版: `0.1`
- 基準日: `2026-07-30`
- 状態: `APPROVED_FOR_IMPLEMENTATION_CONTRACT`
- 対象市場・言語: `日本 / ja-JP`
- 上位文書: `RAOS-REQ-001`, `RAOS-ARCH-001`, `RAOS-DATA-001`, `RAOS-API-001`, `RAOS-AI-001`
- 次工程: `RAOS-UI-001`

> 本書は、記事を「文章ファイル」ではなく、意思決定、商品同定、根拠、推薦方法、広告表示、Metadata、承認を結び付けたVersioned Productとして定義する。実装者は、本文生成の便利さを理由に、本書の根拠境界、Renderer所有領域、人間承認、推薦の独立性を緩和してはならない。

---

# 0. 文書の目的と正本順位

## 0.1 目的

本書はRAOSのMVPで公開する30～45記事について、次を実装可能な契約へ落とす。

1. 5つの記事タイプと、それぞれが支援する購買意思決定
2. Content AST、Block、Rich Textの許可範囲
3. Claim分類とEvidence要件
4. Product、Variant、Offerを取り違えない比較方法
5. 料率・報酬と分離した推薦Methodology
6. 広告表示、楽天Link、画像、Review情報の扱い
7. SEO Metadata、Canonical、Index、Structured Data
8. 鮮度、Safe Degradation、更新・統合・撤退
9. 品質Score、Zero-tolerance Blocker、人間Review
10. Publication Snapshotへ固定するVersionとHash
11. Data/API/AI上位契約との整合提案
12. CodexがPR単位で実装する順序とTest

## 0.2 正本順位

矛盾時の優先順位は次のとおりとする。

```text
法令・行政上の要求
  > 楽天の規約・ガイドライン・公式API条件
  > RAOS-REQ-001のHard Constraintと成功Gate
  > RAOS-ARCH-001のTrust BoundaryとADR
  > RAOS-DATA/API/AIの既存契約
  > 本書のContent契約
  > 実装都合、SEO仮説、生成速度、記事数
```

本書が上位物理契約へ追加変更を必要とする箇所は、`PROPOSAL_ONLY`のPatchとして分離した。Codexは提案SQLやYAMLを本番へ直接適用してはならない。

## 0.3 非目標

本工程では次を実装・解放しない。

- 自動公開
- 商品ごとの自動詳細ページ量産
- Tagや条件パラメータの組合せページ量産
- 楽天レビュー本文の取得・要約
- 検索結果ページの直接スクレイピング
- AIが自由にHTML、Affiliate URL、JSON-LDを生成する機能
- 料率やEPCによるおすすめ順位変更
- 高リスクな医療、法務、金融、安全助言
- 実体験記録のない「使ってみた」記事
- Rich Result獲得を事業成功条件にすること

---

# 1. エグゼクティブサマリー

RAOSの記事は、検索Keywordを満たすための文章ではない。読者が特定の購入判断を行うために、候補、比較軸、根拠、条件、トレードオフを明確にする**購買意思決定Artifact**である。

MVPでは、選び方ガイド、用途別おすすめ、少数商品比較、型番・世代・容量差分、条件別絞り込みの5型だけを公開対象にする。各記事は一つのPrimary Intent Clusterと一つのPrimary Decisionを持つ。同じ意思決定を検索語だけ変えて別ページにしない。

本文はVersioned Content ASTで保存する。EditorとAIが編集できるのは許可済みBlockとRich Textだけである。価格、在庫、商品カード、比較表、広告表示、Affiliate CTA、API Credit、JSON-LDは、承認済みResourceから決定的にRendererが生成する。任意HTML、Script、手入力Affiliate URLは存在しない。

記事中の検証可能な記述はClaimへ分解し、FactとSource原本へ逆引きできなければならない。主要Claimは100%、全検証可能Claimは95%以上のEvidence Coverageを要求する。AI出力、競合記事、検索Snippet、楽天レビュー本文はEvidenceにならない。

推薦はArticle固有の読者条件に対するEditorial Suitabilityで計算する。Hard Constraintを先に適用し、Fact Coverage、不確実性、競合、鮮度を反映する。料率、EPC、RPM、報酬、利益、スポンサー便益は入力Schemaと管理画面から排除する。Score差が2点以内なら無理に勝者を作らない。

公開には100点中85点以上、各評価軸のFloor、Zero-tolerance違反0、Blocking Finding 0、人間の明示承認を要求する。価格・在庫・Linkが失効した場合は、該当FieldまたはCTAを非表示にして記事本体を残す。ただし推薦根拠そのものが失効した場合は記事をPauseする。失効を理由に推薦順位を自動変更してはならない。

---

# 2. 外部条件スナップショット（2026-07-30確認）

本節は実装時点の外部条件を固定するためのスナップショットであり、将来変更され得る。Policy Update Workflowは公式文書を定期確認し、変更時に影響記事を再評価する。

## 2.1 Google Search

GoogleのPeople-first guidanceは、独自情報、十分な説明、明確なSource、実体験・専門性、他サイトの要約だけでない追加価値を重視している。逆に、検索流入を主目的として多数のTopicを自動生成し、既存情報を付加価値なく要約することは警告対象である。RAOSは記事数を成功指標の下位に置き、Article Typeごとの意思決定価値とEvidence Gateを先に置く。

生成AIの利用自体を禁止するのではなく、正確性、品質、関連性、Metadataを含む公開物の責任をサイト側が負う。したがって、RAOSはAI出力をSourceとせず、Structured Output、Claim照合、Policy Check、人間Reviewを分離する。

Affiliate等の有償関係Linkには`rel="sponsored"`を使い、ページ本文は独自価値を持たせる。検索機能に特別なAI用MarkupやKeyword Variantページは必要としない。

Product Rich Resultの現行Guideは、単一商品または同一商品のVariantに焦点を当てたページを対象としており、商品一覧・Category型ページへProduct Markupを勧めていない。RAOSのMVP記事は複数商品比較が中心であるため、Product/Offer Markupは出さない。

FAQ Rich Resultの文書は2026年5月以降に削除され、2026年6月のDocumentation Updateで廃止が明示された。可視のFAQは読者価値として残せるが、RAOSはFAQPage JSON-LDを生成しない。

参照:

- https://developers.google.com/search/docs/fundamentals/creating-helpful-content
- https://developers.google.com/search/docs/essentials/spam-policies
- https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links
- https://developers.google.com/search/docs/fundamentals/using-gen-ai-content
- https://developers.google.com/search/docs/fundamentals/ai-optimization-guide
- https://developers.google.com/search/docs/specialty/ecommerce/write-high-quality-reviews
- https://developers.google.com/search/docs/appearance/structured-data/product-snippet
- https://developers.google.com/search/updates#removing-faq-rich-result

## 2.2 楽天・広告表示

RAOSは楽天アフィリエイトガイドライン、媒体登録、HTTPS、リンク・画像・API Credit等の条件を守る。楽天レビュー本文を取得、転載、編集、要約、変形しない。レビュー件数と平均評価は許可された集計Factとしてのみ扱い、それだけから利用者の代表意見や商品の品質を推定しない。

RAOSでは、法的な最低限のケース分けだけに依存せず、すべてのAffiliate記事上部に広告関係を表示する。商品提供、イベント招待、無償Coupon、金品その他の便益がある場合は、一般Affiliate表示とは別に具体的関係を追加表示する。CTAは楽天市場へ遷移することを明示し、正規URLへ直接遷移する。

参照:

- https://affiliate.rakuten.co.jp/guideline/rule/
- https://affiliate.rakuten.co.jp/guideline/stealth_marketing_regulation/
- https://webservice.rakuten.co.jp/guide/credit
- https://www.caa.go.jp/policies/policy/representation/fair_labeling/stealth_marketing

## 2.3 Accessibilityと画像

情報を含む非Text Contentには同等目的の代替Textを用意する。複雑な比較図・Chartは短いaltだけで済ませず、同等のData Tableまたは詳細説明を持つ。装飾画像は空altとする。楽天提供画像は利用条件に従い、文字重畳、切抜き、縦横比破壊を行わない。

参照:

- https://developers.google.com/search/docs/appearance/google-images
- https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html
- https://www.w3.org/WAI/tutorials/images/decision-tree/

---

# 3. Content Productの定義

## 3.1 Article Aggregate

論理ArticleはURLや本文そのものではない。次を結ぶAggregateである。

```text
Article Plan
  + Primary Intent Cluster
  + Primary Decision
  + Article Type Version
  + Candidate Universe
  + Source Packet Version
  + Methodology Version
  + Content AST Version
  + Claim / Evidence Links
  + SEO Metadata Version
  + Policy Bundle Version
  + Quality Result
  + Human Approval
  + Publication Snapshot
```

いずれかのVersionを欠いた公開は認めない。

## 3.2 Stable ID

次にStable IDを持たせる。

- Article Plan
- Article
- Article Version
- Article Type Version
- Article Template Version
- Content Schema Version
- Block
- Product Selection
- Comparison Axis
- Recommendation Set / Recommendation
- Claim
- Fact / Source / Raw Artifact
- Methodology Version
- SEO Metadata Version
- Policy Bundle Version
- Quality Result
- Review Decision / Approval
- Publication Snapshot

画面TextやSlugをIdentityに使わない。Slug変更、Title変更、商品名変更があっても、監査と帰属が切れないようにする。

## 3.3 One Decision per Article

一つの記事は、読者が一つの主要判断を行えることを目標とする。例えば「猫のいる家庭向け掃除機を選ぶ」と「一人暮らし向け空気清浄機を選ぶ」を一記事に混在させない。

Primary Decisionが異なる場合は別Article候補になり得る。一方、同じDecisionを「おすすめ」「比較」「ランキング」「人気」等のKeyword Variationだけで分けてはならない。違いが記事型やCandidate Universeを変えるほど実質的か、人間が判定する。

## 3.4 Unique Decision Value

公開候補は、少なくとも次のいずれかを追加しなければならない。

- Category固有の判断軸とトレードオフ
- 用途・制約ごとに異なる適合関係
- 型番・Variantの正確な差分
- 同じ軸・同じ時点での比較
- 明示的な除外条件と不足Dataの扱い
- RAOS独自の許諾済み計測・体験
- 一次Sourceを結合して得た説明可能なDerived Fact

API値の並び替え、商品名の置換、説明文の言い換え、価格だけの一覧はUnique Valueとして数えない。

---

# 4. 記事タイプ

| ID | 記事型 | 主要判断 | 推奨商品数 | 最小軸数 | 順位方針 |
| --- | --- | --- | --- | --- | --- |
| AT-001 | 選び方ガイド | カテゴリ内で自分に合う商品を選ぶための評価軸と判断手順を理解する | 5-12 | 4 | contextual_only |
| AT-002 | 用途別おすすめ | 明確な利用状況・制約に対して、候補ごとの適合理由と妥協点を比較する | 3-8 | 3 | use_case_specific |
| AT-003 | 商品比較（A対B等） | 少数候補の差異を同じ評価軸・同じ時点で比較し、自分の優先条件に合う方を選ぶ | 2-4 | 4 | conditional_winner_only |
| AT-004 | 型番・世代・容量差分 | 同一系列の型番・世代・容量・セット差を正しく同定し、追加費用に見合う差を判断する | 2-6 | 3 | upgrade_value_by_condition |
| AT-005 | 条件別絞り込み | 複数の明示条件を満たす候補だけを絞り、除外理由と残った候補の差を理解する | 3-15 | 3 | eligible_set_then_contextual_order |

## 4.1 AT-001 選び方ガイド

### 目的

Categoryの判断基準そのものを理解させる。商品一覧を先に置くのではなく、読者条件、評価軸、Tradeoff、避ける条件を先に構造化する。

### 必須内容

- 対象読者と対象外
- Candidate Universeの範囲
- 4軸以上のCategory固有Criteria
- 軸間のTradeoff
- 条件別Recommendation Group
- 候補が合わない条件
- Data確認時点

### 不合格例

- 「人気順」だけで商品を並べる
- メーカー説明を短く言い換える
- すべての読者へ同じ1位を示す
- 検索語ごとにほぼ同じガイドを量産する

## 4.2 AT-002 用途別おすすめ

Use Case、環境、予算、サイズ等のHard Constraintを定義し、その条件で候補がなぜ適合するかを説明する。推薦は対象条件外へ一般化しない。

### 必須内容

- Use Caseと前提
- Hard ConstraintとSoft Preference
- 適合候補、代替候補、不向き候補
- 候補ごとのFit / Non-fit / Tradeoff
- Scoreまたは順序を使う場合のMethodology

## 4.3 AT-003 商品比較

2～4候補を中心に、同じ比較軸・同じ単位・可能な限り近い取得時点で比較する。「A対B」の答えは一つではなく、条件別の結論として示す。

### 必須内容

- 比較対象の正確なProduct/Variant
- 共通点、差分、不明点
- 決定要因
- 条件別勝者または同等
- 時点差・Source差の注記

## 4.4 AT-004 型番・世代・容量差分

同じ系列に見える候補を誤統合しないことが最優先である。発売年が新しいというだけで新型を推奨しない。追加費用に対応する差、旧型で十分な条件、互換性・付属品差を示す。

## 4.5 AT-005 条件別絞り込み

Parameter Combinationを自動IndexするFaceted Pageではない。Hard Constraint、除外理由、不明値、条件を緩める影響を説明するEditorial Pageである。

### Indexable条件

- 検索語だけでなく明確な意思決定価値がある
- 条件の定義と除外Logicを説明する
- 残った候補間の比較を持つ
- Candidate UniverseとData時点を示す
- 他の条件ページと重複しない

---

# 5. Content AST

## 5.1 基本原則

Content ASTは`schemas/content-ast.schema.json`を正本とする。Schema Versionを認識できないRendererは推測して描画せず、直前正常Snapshotまたは安全なErrorへFail Closedする。

Editor/AIが保存できるのは許可されたBlockとRich Text Nodeだけである。Raw HTML、Script、iframe、Style、Event Handler、data URI、外部画像URL、手入力Affiliate URL、Finance指標はSchemaで拒否する。

## 5.2 Block一覧

| ID | code | 名称 | 所有 | Claim可 | 記事内範囲 |
| --- | --- | --- | --- | --- | --- |
| BLK-001 | lead | 導入 | editorial | true | 0..1 |
| BLK-002 | decision_summary | 結論要約 | editorial | true | 0..1 |
| BLK-003 | intended_reader | 対象読者・対象外 | editorial | true | 0..1 |
| BLK-004 | methodology | 選定・比較方法 | editorial | true | 0..1 |
| BLK-005 | selection_criteria | 選び方・評価軸 | editorial | true | 1..12 |
| BLK-006 | heading | 見出し | editorial | false | 0..40 |
| BLK-007 | paragraph | 本文段落 | editorial | true | 0..120 |
| BLK-008 | bullet_list | 箇条書き | editorial | true | 0..30 |
| BLK-009 | numbered_list | 番号付き手順 | editorial | true | 0..20 |
| BLK-010 | comparison_table | 比較表 | renderer | true | 0..8 |
| BLK-011 | product_card | 商品カード | renderer | true | 0..20 |
| BLK-012 | recommendation_group | 条件別推奨 | editorial | true | 1..12 |
| BLK-013 | difference_matrix | 差分マトリクス | renderer | true | 0..4 |
| BLK-014 | pros_cons | 長所・短所 | editorial | true | 0..20 |
| BLK-015 | tradeoff | トレードオフ | editorial | true | 1..20 |
| BLK-016 | caution | 注意事項 | editorial | true | 1..12 |
| BLK-017 | evidence_note | 根拠注記 | renderer | false | 0..20 |
| BLK-018 | source_summary | 情報源・更新情報 | renderer | false | 1..1 |
| BLK-019 | faq | よくある質問 | editorial | true | 0..12 |
| BLK-020 | media | 画像・図表 | renderer | true | 0..20 |
| BLK-021 | internal_links | 関連記事 | renderer | false | 0..3 |
| BLK-022 | update_notice | 更新注記 | renderer | false | 0..2 |
| BLK-023 | callout | 補足コールアウト | editorial | true | 0..12 |
| BLK-024 | disclosure_slot | 広告・提携表示枠 | renderer | false | 1..1 |

## 5.3 Rich Text

許可Nodeは次だけである。

```text
text
strong
emphasis
inline_code
internal_link(route_ref)
approved_external_citation(source_ref)
line_break
```

`internal_link`はRoute ID、`approved_external_citation`はSource IDを保持する。URL文字列を本文へ直接持たせない。Rendererが現在の安全なURLへ解決し、Escaping、CSP、rel属性を適用する。

## 5.4 Renderer所有Block

次は人間やAIが表示値を自由入力するBlockではない。

- `product_card`
- `comparison_table`
- `difference_matrix`
- `evidence_note`
- `source_summary`
- `internal_links`のURL解決
- `update_notice`の時刻
- `disclosure_slot`

Editorは参照ID、表示方針、説明文の一部を選べるが、価格、在庫、Affiliate URL、Disclosure、API Credit、JSON-LDを直接書けない。

## 5.5 Disclosure Slot

`disclosure_slot`はSchema上のBlockとして追跡するが、Rendererが記事先頭へ必ず挿入する。Editorは削除、移動、非表示にできない。実装はContent配列の存在だけを信用せず、RendererでPolicy Bundleから再挿入・検証する。

## 5.6 Block順序

Article TemplateがRequired Sequenceを持つ。順序は完全固定Layoutではなく、意思決定の理解に必要なAnchorを保証するための契約である。

```text
Disclosure
→ Lead
→ Decision Summary
→ Intended Reader
→ Methodology / Criteria
→ Comparison / Difference / Recommendation
→ Tradeoff / Caution
→ Source Summary
```

Heading、Paragraph、Media、FAQ、Internal Linksは意味のある位置へ追加できる。

---

# 6. Article PlanとCandidate Universe

## 6.1 Article Plan Freeze

AI Draftの前に、Article PlanをFreezeする。最低限、次を持つ。

- Article Type Version
- Primary Intent Cluster
- Primary Decision
- Target Reader
- Included/Excluded Use Cases
- Candidate Universe Definition
- Candidate Inclusion/Exclusion Rules
- Minimum Decision Axes
- Risk Classification
- Required Source Types
- Publication GoalとMeasurement Plan

PlanがFreezeされない状態でSource PacketやDraftを作らない。

## 6.2 Candidate Universe

「比較対象」は商品名のListだけではない。

```text
universe_definition
inclusion_rules
exclusion_rules
search_and_fetch_boundary
canonical_product_ids
variant_identity
shop_offer_scope
unresolved_candidates
excluded_candidates_with_reason
frozen_at
artifact_sha256
```

最上級や「3商品中最も軽い」のようなClaimは、このUniverseに対してのみ成立する。市場全体へ一般化しない。

## 6.3 Product / Variant / Offer

- Product: 商品として共通する同一性
- Variant: 容量、色、世代、型番、Bundle等の違い
- Offer: 特定ショップが特定条件で販売する状態

価格、在庫、送料、Point、Affiliate URLはOfferのFactである。Product一般の性能・仕様と混ぜない。異なるVariantの重量と価格を組み合わせた架空候補を作らない。

---

# 7. Source Packet

## 7.1 承認前提

AI Writer、Comparison Architect、Recommendation Rationaleは、承認済みSource Packet Versionだけを入力にする。Packetが次のいずれかならJobを発行しない。

- `DRAFT`
- Hash不一致
- Critical Source欠損
- Product Identity未解決
- Policy違反Sourceを含む
- Critical Fact期限切れ
- Source Conflict未解決

## 7.2 内容

Source Packetには次を含む。

- Article PlanとCandidate Universe
- Canonical Product / Variant / Offer参照
- Source SnapshotとRaw Artifact Hash
- FactとDerived Fact
- Comparison Axis
- Freshness State
- Missing Evidence
- Conflict
- Prohibited Sourceの除外記録
- Packet Schema VersionとHash
- Reviewer、時刻、承認Note

## 7.3 Source Tier

| Tier | 名称 | 主な用途 | 制限 |
| --- | --- | --- | --- |
| SRC-TIER-A | 一次・権威ソース | official_spec<br>legal_policy<br>standard<br>manufacturer_status<br>official_api_fact | 取得時点と対象Variantを必須化 |
| SRC-TIER-B | 販売・Offerソース | price<br>availability<br>shipping<br>shop_specific_bundle<br>seller_status | 商品一般仕様や性能優位の根拠には単独利用しない |
| SRC-TIER-C | 許諾済み独立評価 | independent_measurement<br>comparative_observation<br>market_context | 転載条件・方法・サンプル・日付を記録 |
| SRC-TIER-D | RAOS独自一次体験 | first_hand_experience<br>measurement<br>photo_evidence<br>usage_observation | 担当者、手順、試料、環境、原本Assetを記録 |
| SRC-DISCOVERY | 発見専用 | topic_discovery<br>question_discovery<br>comparison_axis_candidate | 記事Claimの根拠として引用・要約・言い換え利用しない |
| SRC-EXCLUDED | 利用禁止 |  | Source Packetへの採用禁止 |

Discovery Sourceは質問や比較軸の候補発見に使えるが、記事Claimの根拠には使えない。競合記事を入力して近似言い換えを生成するWorkflowは設けない。

---

# 8. Claim–Evidence

## 8.1 Claim分類

| ID | 名称 | code | 推奨Source | 最低Evidence | Block条件 |
| --- | --- | --- | --- | --- | --- |
| CLM-TYPE-001 | 直接事実 | direct_fact | SRC-TIER-A / SRC-TIER-B | 同一Product/Variantを示す有効Fact 1件 | 対象Variant不明<br>単位不明<br>Source期限切れ |
| CLM-TYPE-002 | 派生事実 | derived_fact | SRC-TIER-A / SRC-TIER-B | 全入力Fact<br>式ID<br>丸め規則<br>計算時点 | 入力欠損<br>式未登録<br>異通貨・異単位の無変換比較 |
| CLM-TYPE-003 | 比較主張 | comparative | SRC-TIER-A / SRC-TIER-C / SRC-TIER-D | 比較対象全件の同一軸Fact<br>同等な取得時点または差の注記<br>比較母集団 | 母集団不明<br>比較時点の非対称<br>不明値を劣位扱い |
| CLM-TYPE-004 | 推薦判断 | recommendation | SRC-TIER-A / SRC-TIER-C / SRC-TIER-D | Methodology Version<br>対象条件<br>適合Fact<br>不向き条件<br>代替候補または代替なし理由 | 料率・EPC・利益の混入<br>万能推奨<br>根拠なし順位 |
| CLM-TYPE-005 | 使用・検証体験 | experience | SRC-TIER-D | First-hand Experience Record<br>手順<br>日時<br>担当者<br>原本Asset | 実施記録なし<br>他者体験の自称<br>AIによる体験生成 |
| CLM-TYPE-006 | 価格・在庫・販売状態 | price_availability | SRC-TIER-B | Offer Fact<br>取得日時<br>ショップ・商品コード<br>鮮度判定 | 鮮度期限超過<br>税込・送料条件不明<br>別Offer混同 |
| CLM-TYPE-007 | 最上級・唯一性 | superlative | SRC-TIER-A / SRC-TIER-B / SRC-TIER-C / SRC-TIER-D | 対象母集団の完全定義<br>全候補の同一軸Fact<br>時点・範囲・除外条件 | 市場全体を暗示する狭い比較<br>母集団欠損<br>時点なし |
| CLM-TYPE-008 | 安全・法令・規制 | safety_legal_regulatory | SRC-TIER-A | 官公庁・法令・規格等の一次ソース<br>Compliance Review | MVP低リスク範囲外<br>医療・法務・金融助言<br>非公式ソースのみ |
| CLM-TYPE-009 | 予測・将来主張 | predictive | SRC-TIER-A / SRC-TIER-C | 承認済み予測Methodology<br>不確実性と期間 | MVPでは既定禁止<br>断定表現<br>根拠なし将来予測 |

## 8.2 Claim抽出

Claim Auditorは、Article ASTのTextから検証可能なClaim候補を抽出し、次を返す。

```text
claim_id
claim_type
criticality
claim_text
subject_refs
block_id
required_fact_types
temporal_scope
support_status
```

AIが「これは一般論だからEvidence不要」と独断しない。Style、意見、明示的な編集判断以外の検証可能記述はClaimとして扱う。

## 8.3 Coverage

```text
Major Claim Coverage = supported major claims / all major claims = 100%
All Verifiable Claim Coverage >= 95%
```

残り5%はEvidenceなしを許す意味ではない。検証可能性判定、重複、削除予定等のReview上の誤差Budgetである。公開時にUnsupported状態の主要Claimは0件でなければならない。

## 8.4 Temporal Claim

価格、在庫、送料、Rank、販売状態、最上級等には`as_of`を持たせる。Source取得時刻と表示確認時刻を区別する。公開文では「記事更新時点」「2026年7月30日確認」等、読者に理解可能な形で示す。

## 8.5 Derived Fact

計算可能な比較はLLMに暗算させず、決定論的Functionで作る。

例:

```text
price_per_unit = tax_included_price / normalized_capacity
weight_difference = product_a_weight - product_b_weight
relative_price_difference = (a - b) / b
```

式ID、Input Fact ID、単位変換、丸め、計算Versionを保存する。

## 8.6 Conflict

Sourceが競合した場合、権威性だけで自動的に値を上書きしない。対象Variant、地域、版、取得時点、定義の違いを調べる。解消できない場合は「不明」「Source間で差がある」とし、Recommendation Criticalなら順位対象から外す。

---

# 9. 実体験・Review・社会的証明

## 9.1 実体験

`First-hand Experience Record`がない限り、次のような表現を公開してはならない。

- 使ってみた
- 試した
- 愛用している
- 実感した
- 検証した
- 編集部が使用した

Recordには、Tester、対象Variant、手順Version、環境、日時、原本写真・Log・Measurement、限界、Reviewを持たせる。画像だけ、購入履歴だけ、AI生成文だけでは体験Evidenceにならない。

## 9.2 楽天レビュー

楽天レビュー本文は取得、保存、転載、編集、要約、Embedding、感情分析、Prompt投入を禁止する。Review CountとAverage Ratingが公式API等で利用可能な場合も、次を推定しない。

- 多くの人が使いやすいと感じている
- 耐久性が高いという声が多い
- 悪い口コミは少ない
- 利用者の共通意見

集計値を表示する場合は、取得時点と「楽天上の集計値」であることを示し、RAOSの評価やRecommendationとは分離する。

## 9.3 Popularity

RankingやReview Countは「品質」ではない。公式Ranking Factを使う場合も、Provider、Category、期間、順位、取得時点を限定する。「人気」「売れている」を恒久的な性質として書かない。

---

# 10. Comparison Axis

## 10.1 型付き値

Comparison Axisは次をVersion管理する。

```text
axis_id
label
data_type
unit
normalization_rule
better_direction or no universal direction
criticality
allowed_source_types
freshness_class
unknown_value_policy
display_format
```

## 10.2 同じ軸・同じ定義

「重量」を比較する場合、本体のみ、付属品込み、梱包重量を混ぜない。「価格」は税込、送料、Coupon、Pointを別Fieldとして扱う。値の定義が違う場合は比較不能として表示する。

## 10.3 Unknown

Unknownを0、平均、最良、最悪へ自動変換しない。TableはUnknownを明示し、Decision Criticalな軸ならCandidateをUnrankedにする。

## 10.4 表示

Desktop TableとMobile Cardsは同じComparison Value Projectionから描画する。順序、Value、Unit、FootnoteがViewportで変わらないようContract Testを置く。

---

# 11. Recommendation Methodology

## 11.1 原則

Recommendationは記事固有のUse Caseへの適合度である。商品そのものの絶対的品質Scoreではなく、他の記事へ流用しない。

## 11.2 Pipeline

```text
Decision Context
→ Candidate Universe Freeze
→ Identity / Evidence Check
→ Hard Constraints
→ Dimension Normalization
→ Weighted Evidence Coverage
→ Base Suitability
→ Uncertainty Penalty
→ Tie Rule / Labels
→ Human Review
```

## 11.3 Formula

```text
coverage = Σ(weight of valid current dimensions) / Σ(all required weights)
base = 100 * Σ(weight × normalized score) / Σ(scored weights)
penalty = min(20, 20×(1-coverage) + conflict_penalty + staleness_penalty)
editorial_suitability = clamp(base - penalty, 0, 100)
```

内部計算は4桁保持し、公開する場合は整数へ丸める。ただしScore自体を権威化せず、読者には主要理由とTradeoffを優先して示す。

## 11.4 Coverage Threshold

- Rank可能: 0.80以上
- Primary Recommendation可能: 0.90以上
- Critical Dimension欠損: IneligibleまたはUnranked
- Product Identity Conflict: Ineligible
- Critical Fact Stale: RefreshまでIneligible

## 11.5 Tie

Score差が2.0以下なら、共同推奨または明示的な非Score条件で順序を決める。見栄えやAffiliate収益のために勝者を作らない。

## 11.6 Human Override

人間Overrideは許可するが、Before/After順位、Reason Code、自由記述、Evidence、Review Decisionを保存する。Finance理由は禁止する。Primary Recommendation変更、Hard Constraint例外、10点超の逆転はSecondary Review対象とする。

## 11.7 Finance分離

次のFieldはRecommendation Engine、Editorial API、Prompt、Review画面へ渡さない。

```text
affiliate_rate
commission
epc
rpm
revenue
confirmed_commission
contribution_profit
sponsor_benefit
```

Business Analyticsは公開後のPortfolio判断に使えるが、公開記事のRecommendation順位へ自動Feedbackしない。

---

# 12. Editorial Policy

| ID | Severity | Stage | Code | Rule | Enforcement |
| --- | --- | --- | --- | --- | --- |
| POL-CONT-001 | BLOCKER | all | approved_source_packet_required | 承認済みSource Packetがない記事生成・公開を禁止する | deterministic |
| POL-CONT-002 | BLOCKER | draft | major_claim_evidence | 主要ClaimのEvidence Coverageは100% | deterministic |
| POL-CONT-003 | BLOCKER | draft | fabricated_experience | 実施記録のない使用・検証・愛用表現を禁止する | hybrid |
| POL-CONT-004 | BLOCKER | ingest | rakuten_review_body | 楽天レビュー本文の取得・保存・要約・変形・依拠を禁止する | deterministic |
| POL-CONT-005 | BLOCKER | recommendation | affiliate_bias | 料率・EPC・RPM・報酬・利益を推薦入力へ含めない | deterministic |
| POL-CONT-006 | BLOCKER | content_ast | raw_html | 任意HTML、Script、iframe、Style、Event Handlerを禁止する | schema |
| POL-CONT-007 | BLOCKER | content_ast | manual_affiliate_url | Affiliate URLの手入力を禁止し、Offer/Link Resourceから解決する | schema |
| POL-CONT-008 | BLOCKER | render | disclosure_top | 広告・アフィリエイト関係を記事上部の初回表示範囲で明示する | deterministic |
| POL-CONT-009 | BLOCKER | render | cta_destination | CTAは楽天市場への遷移であることを明示する | deterministic |
| POL-CONT-010 | BLOCKER | render | paid_link_rel | Affiliate Linkへrel=sponsoredを付与する | deterministic |
| POL-CONT-011 | BLOCKER | render | direct_affiliate_link | 自社RedirectでAffiliate URLを中継・改変しない | deterministic |
| POL-CONT-012 | BLOCKER | render | rakuten_api_credit | 楽天API利用時の指定クレジットを共通Rendererへ表示する | deterministic |
| POL-CONT-013 | BLOCKER | media | rakuten_image_integrity | 楽天提供画像の改変、文字重畳、切り抜き、縦横比破壊を禁止する | hybrid |
| POL-CONT-014 | BLOCKER | draft | unsupported_superlative | 母集団・範囲・時点がない最上級・唯一性を禁止する | hybrid |
| POL-CONT-015 | BLOCKER | publication | stale_critical_fact | 鮮度期限を超えた価格・在庫・リンク・主要仕様を最新として表示しない | deterministic |
| POL-CONT-016 | BLOCKER | draft | product_identity | 商品、型番、容量、色、セット、ショップOfferの同定不一致を禁止する | deterministic |
| POL-CONT-017 | BLOCKER | scope | high_risk_claim | MVPで医療・法務・金融・安全性の高リスク助言を扱わない | hybrid |
| POL-CONT-018 | BLOCKER | publication | human_approval | 人間の明示承認なしに公開しない | deterministic |
| POL-CONT-019 | MAJOR | plan | one_primary_intent | 一記事一主要意思決定・一主要Intent Clusterを維持する | human |
| POL-CONT-020 | MAJOR | plan | scaled_thin_pages | 検索語、Tag、条件の組合せだけで低価値ページを量産しない | hybrid |
| POL-CONT-021 | MAJOR | draft | competitor_copy | 競合記事は発見専用とし、根拠・転載・近似言い換えに使用しない | hybrid |
| POL-CONT-022 | MAJOR | draft | balanced_tradeoffs | 推薦候補の不向き条件・制約・トレードオフを隠さない | human |
| POL-CONT-023 | MAJOR | draft | uncertainty_disclosure | 不明・競合・欠損を推測で埋めず、表示またはClaim除外する | hybrid |
| POL-CONT-024 | MAJOR | seo | unique_metadata | Title、H1、Meta Descriptionをページ固有かつ内容一致にする | deterministic |
| POL-CONT-025 | BLOCKER | seo | index_state | Draft/Preview/noindexページをSitemapへ含めず、公開CanonicalのみIndexableにする | deterministic |
| POL-CONT-026 | BLOCKER | structured_data | visible_match | JSON-LDと可視本文の不一致、存在しないRating/Review/Offer補完を禁止する | deterministic |
| POL-CONT-027 | MAJOR | structured_data | multi_product_product_markup | 複数商品記事にProduct Product Snippet用Markupを出さない | deterministic |
| POL-CONT-028 | MAJOR | structured_data | faqpage_disabled | 可視FAQは許可するがFAQPage JSON-LDを生成しない | deterministic |
| POL-CONT-029 | MAJOR | structured_data | rakuten_rating_markup | 楽天の平均評価・件数からReview/AggregateRating JSON-LDを生成しない | deterministic |
| POL-CONT-030 | MAJOR | seo | query_variant_consolidation | 意味が同じ検索語Variantは単一Canonical記事へ統合する | human |
| POL-CONT-031 | MAJOR | links | internal_link_quality | 公開済み関連Routeだけへ説明的AnchorでLinkし、過剰Exact Matchを避ける | deterministic |
| POL-CONT-032 | BLOCKER | accessibility | non_text_alternative | 情報画像・図表に同等目的の代替テキストまたは詳細説明を付与する | hybrid |
| POL-CONT-033 | MAJOR | accessibility | semantic_structure | 見出し階層、表見出し、Keyboard操作、色以外の区別を維持する | hybrid |
| POL-CONT-034 | MAJOR | metadata | substantive_lastmod | lastmod/Updated Atは実質的変更時のみ更新する | deterministic |
| POL-CONT-035 | BLOCKER | publication | kill_switch | Publication/Affiliate Link Kill Switchが有効な場合は該当出力をFail Closedする | deterministic |
| POL-CONT-036 | BLOCKER | publication | snapshot_integrity | 承認Version・Methodology・Policy・Evidence・SEO・Schema HashをPublication Snapshotへ固定する | deterministic |
| POL-CONT-037 | MAJOR | draft | review_aggregate_inference | レビュー平均・件数だけから品質・満足・長所短所・代表意見を推定しない | hybrid |
| POL-CONT-038 | MAJOR | draft | price_language | 価格は取得時点の事実として書き、常時価格・最安保証を暗示しない | hybrid |
| POL-CONT-039 | BLOCKER | media | ai_product_depiction | 実在商品の外観・仕様をAI生成画像で代替しない | hybrid |
| POL-CONT-040 | MAJOR | publication | safe_degradation | 変動Factが失効した場合は該当Field/CTAを縮退し、推薦順位を自動変更しない | deterministic |

## 12.1 Blocker

BlockerはWaiver不可である。Scoreが100でも公開できない。法令・楽天規約・Source Integrity・商品同定・広告表示・Kill Switch・Secretに関する違反はBlockerとする。

## 12.2 Major

Majorは通常、解消してから公開する。例外的にWaiverする場合は範囲、理由、Evidence、Expiry、Approver、Auditを要求する。期限切れWaiverはFail Closedする。

## 12.3 Policy as Code

全PolicyはIDとVersionを持ち、Findingに次を記録する。

```text
policy_id
policy_version
severity
article_version_id
block_id / claim_id / recommendation_id / asset_id
evidence
rule_result
detected_by
created_at
resolution
```

Policy Sourceが変更された場合、影響するPublication Snapshotを逆引きし、CTA停止、記事Pause、Re-reviewのいずれかへ移す。

---

# 13. DisclosureとAffiliate CTA

## 13.1 標準表示

全Affiliate記事上部に、少なくとも次の意味を持つ表示をRendererから出す。

> 本記事には広告・アフィリエイトリンクが含まれます。掲載情報は記事更新時点のものです。価格・在庫・条件は楽天市場の販売ページでご確認ください。

文言はPolicy BundleでVersion管理する。Editor本文へCopy&Pasteせず、必須領域から削除できない。

## 13.2 Material Benefit

商品提供、招待、Coupon、金品その他の便益がある場合、`article_disclosure_context`に種類と追加文を持ち、標準表示とは別に具体的に表示する。関係を「PR」だけで曖昧にせず、読者が理解できる位置と表現をCompliance Reviewする。

## 13.3 CTA

標準Label例:

- 楽天市場で価格・在庫を確認
- 楽天市場の商品ページを見る

禁止例:

- 詳細はこちら
- 最安で買う
- 今すぐ確実に購入
- 公式サイト（実際は楽天Shop）

CTAはOffer/Link Resourceから正規Affiliate URLを受け取り、直接遷移する。計測Beacon失敗で遷移を止めない。

## 13.4 Link State

```text
VERIFIED → CTA表示
NEAR_EXPIRY → 表示 + Queue
UNVERIFIED / FAILED → CTA非表示
GLOBAL_LINKS_OFF → 全CTA非表示
ARTICLE/CATEGORY_PAUSED → Scopeに応じ非表示
```

Rendererは`rel="sponsored"`を付与する。管理画面のPreviewではCTAを無効化する。

---

# 14. Media・Accessibility

## 14.1 Asset Provenance

MediaはURLではなくAsset IDを参照する。Asset ManifestにSource、Raw Artifact、Hash、License、Modification Policy、Alt、Dimensions、時刻、Approvalを保存する。

## 14.2 楽天画像

- Providerが許可した画像のみ
- 画像自体へのText/Badge重畳禁止
- Crop禁止
- 縦横比維持
- `object-fit: contain`
- 商品識別とSourceを維持
- Cache/Proxy等はProvider条件とAPI Guidelineを確認

UI上の周辺Labelは画像外のHTMLとして表示する。

## 14.3 独自Chart

Chartは決定論的にFactから生成し、次を持つ。

- Input Fact IDs
- Formula / Chart Generator Version
- Data checked at
- Accessible Data TableまたはLong Description
- 色以外のLegend/Pattern/Label
- Image Hash

## 14.4 AI画像

実在商品の外観や性能を示すAI生成画像は禁止する。装飾的Concept Imageも、商品や実測と誤認される可能性がある場合は使用しない。

## 14.5 Alt Decision

- Informative: 画像が伝える情報と目的
- Functional/Linked: Linkや操作の目的
- Complex: 簡潔alt + 詳細説明/Data Table
- Decorative: 空alt
- Text in image: 原則避け、必要なら同等Textを提供

Keywordを詰め込まない。

---

# 15. SEO Metadata

## 15.1 Title/H1/Meta Description

固定文字数をHard Gateにしない。日本語で自然に、主題と対象条件を説明し、重複とKeyword羅列を避ける。UIは長さをWarningとして表示できるが、検索表示幅を保証する数値として扱わない。

Meta Descriptionは記事固有のDecision Valueを要約する。Programmaticに生成してもよいが、Templateの同一文や商品名Listだけにならないよう重複・可読性検査を行う。

## 15.2 Canonical

公開Indexable記事はSelf Canonicalを基本とする。Merge時は正本へ301し、Canonical、Internal Link、Sitemapを揃える。Canonical Cycle、Redirect Chain、noindexとの矛盾をBlockingにする。

## 15.3 Preview

- OIDC認証
- `noindex,nofollow`
- Public CDN Cache禁止
- Draft Watermark
- Affiliate CTA無効
- Source/Claim Overlay
- Screenshot共有注意

## 15.4 Sitemap

次を満たすRouteだけを含める。

```text
published
HTTP 200
index_state = index
canonical self
not paused
not redirect source
current publication snapshot
```

`lastmod`は本文、Recommendation、Methodology、主要Fact等の実質的変更時だけ更新する。Dynamic Price Projectionだけの変化では更新しない。

---

# 16. Structured Data

## 16.1 決定的生成

LLMへJSON-LDを自由生成させない。Publication SnapshotとSite ConfigからRendererが生成し、Visible Content HashとJSON-LD HashをManifestに保存する。

## 16.2 MVPで許可

- ArticleまたはBlogPosting
- BreadcrumbList
- Site ConfigからOrganization / WebSite

## 16.3 MVPで禁止

- 複数商品記事のProduct / Offer
- FAQPage
- 楽天平均評価・件数からのReview / AggregateRating
- 可視本文にないPrice、Availability、Rating、Author、Review
- AI検索向けと称する独自Schema

## 16.4 検証

- JSON parse / Schema validation
- 可視Title、Author、Date、Breadcrumbとの一致
- Canonical URL一致
- Image Assetの公開可否
- 禁止Typeなし
- Snapshot HashとManifest一致
- Template Release後のStage/Production検査

Rich Resultの表示はGoogle側の判断であり、RAOSの受入条件や収益予測に含めない。

---

# 17. Internal Link

Internal Linkは「SEO Link数」を増やすためではなく、読者のDecision Journeyを接続する。

```text
選び方 → 条件別候補 → 少数比較 → 型番差 → 楽天確認
```

AIは候補を提案できるが、入力はPublished Route Projectionだけとする。Raw URL、未公開、Paused、noindex、Affiliate URLを返してはならない。Route ResolverがCurrent URLへ変換する。

Orphan判定は、Category Hubまたは他のIndexable Articleから到達経路があるかで行う。Link quotaのために無関係な記事を繋がない。

---

# 18. FreshnessとSafe Degradation

| ID | Fact class | Warning(h) | Block(h) | Degradation | Editorial impact |
| --- | --- | --- | --- | --- | --- |
| FRESH-001 | offer_price | 24 | 72 | hide_value_and_show_provider_check_label | if recommendation depends on price tier, create blocking review candidate |
| FRESH-002 | availability | 12 | 48 | hide_availability_assertion | if all primary offers unavailable, pause CTA and create review candidate |
| FRESH-003 | affiliate_link_health | 24 | 72 | hide_cta | article body remains unless product identity or policy also fails |
| FRESH-004 | shipping_condition | 24 | 72 | hide_shipping_assertion | do not infer free shipping |
| FRESH-005 | points_coupon_campaign | 6 | 12 | hide_entire_field | MVP default is not to editorially rely on promotions |
| FRESH-006 | official_ranking | 24 | 72 | remove_rank_claim | never convert provider rank into enduring popularity claim |
| FRESH-007 | product_specification | 720 | 2160 | mark_for_review_or_hide_affected_field | pause article if recommendation-critical specification is stale/conflicted |
| FRESH-008 | manufacturer_lifecycle_status | 168 | 720 | show_last_checked_and_review | pause CTA for discontinued/recall/safety concern as policy determines |
| FRESH-009 | editorial_methodology | 720 | 2160 | revalidate_methodology | new version requires impact analysis |
| FRESH-010 | policy_disclosure | 0 | 0 | immediate_renderer_update | blocking policy change overrides prior approval |
| FRESH-011 | first_hand_experience | 4320 | 8760 | show_test_date_and_limitations | do not imply current product revision without identity recheck |
| FRESH-012 | internal_link_target | 168 | 720 | remove_or_replace_broken_link | must not create redirect chain or orphan |

数値はMVPの暫定値であり、Category、Provider、Fact Typeの実測に基づきVersioned Configで変更する。Codeへ散在させない。

## 18.1 状態

```text
FRESH
NEAR_EXPIRY
STALE
CONFLICTED
UNAVAILABLE
UNVERIFIED
```

## 18.2 原則

- 古い価格を最新として見せない
- 在庫を推測しない
- Link未検証時はCTAを出さない
- Article本文を残せる場合は該当Fieldだけ縮退する
- Recommendationの決定根拠が失効した場合はArticleをPauseする
- Safe Degradationを理由に推薦順位を自動変更しない
- 再取得後もValidationと影響判定を通してから復元する

## 18.3 Dynamic ProjectionとArticle Version

Price、Availability、Link Stateのような変動Factは、Publication Snapshot本文と分離したPublic Projectionから描画できる。これらの更新だけでArticle Versionやlastmodを変更しない。

本文、Recommendation、Comparison Axis、Methodology、商品集合、主要Specが変わる場合は、新Article Version、人間Review、新Snapshotが必要である。

---

# 19. 更新・統合・撤退

## 19.1 Update

Primary DecisionとIntentが同じで、Source、商品集合、Fact、Methodologyを更新すれば価値を回復できる場合はUpdateする。

## 19.2 Merge

次を満たす場合、Merge Candidateを作る。

- 同じPrimary Intent
- 同じPrimary Decision
- Candidate Universeが大きく重なる
- Unique Value差が基準未満
- Search/行動DataからCannibalizationの可能性

自動Mergeしない。人間が正本、移行Content、301、Internal Link、Sitemap、Analytics継続を承認する。

## 19.3 Retire

- 等価な後継がある: 301
- 一時的Evidence不足: Paused/noindex hold
- 代替なく意思決定価値が消滅: 410候補
- 法令/規約/重大誤り: 即時PauseまたはLinks Off

DBのArticle、Approval、Snapshot、Auditは削除しない。Public Routeだけを状態遷移させる。

---

# 20. 品質ScoreとGate

## 20.1 Score

| ID | 評価軸 | 配点 | 軸Floor |
| --- | --- | --- | --- |
| QAX-001 | 検索意図への適合 | 15 | 10 |
| QAX-002 | 購買意思決定価値 | 20 | 14 |
| QAX-003 | 独自価値 | 15 | 9 |
| QAX-004 | 事実正確性・根拠 | 20 | 16 |
| QAX-005 | 公平性・説明可能性 | 10 | 7 |
| QAX-006 | 鮮度 | 10 | 7 |
| QAX-007 | 読みやすさ・UX | 5 | 3 |
| QAX-008 | 広告・規約表示 | 5 | 5 |

公開条件:

```text
Total Score >= 85
AND every axis >= floor
AND zero-tolerance blockers = 0
AND unresolved blocking findings = 0
AND human approval exists
```

## 20.2 Gate

| ID | Stage | 名称 | 合格条件 | 失敗処理 |
| --- | --- | --- | --- | --- |
| QG-CONT-001 | article_plan | Article Plan Freeze | Primary Intent、Decision、Article Type、Candidate Universe、対象外が明確 | BLOCK |
| QG-CONT-002 | source_packet | Evidence Readiness | 承認済みSource Packet、商品同定、主要Fact、鮮度、欠損が条件を満たす | BLOCK |
| QG-CONT-003 | content_schema | Content AST Contract | Schema、Block順序、許可Node、未知Field、URL禁止が合格 | BLOCK |
| QG-CONT-004 | claim_evidence | Claim–Evidence | 主要Claim 100%、全検証可能Claim 95%以上、競合・期限切れなし | BLOCK |
| QG-CONT-005 | recommendation | Recommendation Integrity | Methodology、Hard Constraint、Coverage、Bias、Tradeoff、Overrideを検査 | BLOCK |
| QG-CONT-006 | editorial_quality | Editorial Quality | 100点中85点以上かつ各軸Floor以上 | BLOCK |
| QG-CONT-007 | compliance | Compliance | 広告表示、楽天規約、体験、レビュー、画像、CTA、Policy Findingを検査 | BLOCK |
| QG-CONT-008 | seo_accessibility | SEO & Accessibility | Metadata、Canonical、Structured Data、Link、Heading、Alt、表を検査 | BLOCK |
| QG-CONT-009 | freshness_link | Freshness & Link | Critical Fact、Offer、Affiliate Link、確認時刻、Safe Degradationを検査 | BLOCK |
| QG-CONT-010 | human_review | Human Approval | ReviewerがEvidenceへアクセスし、Finding解消と明示承認を実施 | BLOCK |
| QG-CONT-011 | publication_snapshot | Publication Snapshot | Version、Hash、Policy、Methodology、SEO、Disclosure、Kill Switchを再確認 | BLOCK |
| QG-CONT-012 | post_publication | Post-publication Verification | 公開HTML、CTA、JSON-LD、Canonical、robots、RUM、Cacheを実URLで検査 | ROLLBACK_OR_PAUSE |

## 20.3 Zero-tolerance

Score平均で相殺できない。

- 架空体験
- 主要Claim根拠欠落
- 楽天Review本文
- 料率/利益によるRecommendation
- Product/Variant/Offer同定ミス
- 広告表示欠落
- 不正Link
- 期限切れ価格の断定
- Prompt Injection追随
- Structured Dataの重大な虚偽
- Kill Switch無視
- Secret/Restricted Data公開

---

# 21. Human Review

## 21.1 Reviewerが見るもの

- Rendered Preview
- Content AST
- Before/After Diff
- Claim Drawer
- FactとSource原本
- Product/Variant/Offer Identity
- Recommendation MethodologyとScore内訳
- Missing/Conflicted/Stale Evidence
- Policy Finding
- AI Job、Prompt、Model、Cost
- SEO/Structured Data Preview
- Media License/Alt
- Publication Snapshot Manifest候補

## 21.2 Team Mode

AuthorとFinal Approverを別Actorにする。Critical/Compliance FindingはCompliance Approverを要求する。

## 21.3 Solo MVP Exception

上位Architectureが一人運用を許容しているため、同一自然人がRoleを兼務できる。ただし次を必須にする。

- Generation/EditとApprovalを別Command・別Audit Eventにする
- Approval時に再認証
- 全Checklistを明示入力
- Blocking Finding 0
- 理由を入力
- 自動承認禁止
- AI JobからApproval APIを呼べない
- 将来複数人になったらTeam Modeへ移行可能

一人運用を理由にEvidence、Compliance、Review手順を省略しない。

## 21.4 Review Checklist

`RAOS_06_review_checklist_v0.1.yaml`に75項目を定義した。`NOT_APPLICABLE`には理由が必要で、BlockerをN/Aにはできない。

---

# 22. AIとの境界

## 22.1 AIに許可

- Intent分類候補
- Comparison Axis候補
- Outline/Block候補
- Approved Evidence内のDraft
- Claim抽出
- Missing Evidence候補
- Finding修正案
- Internal Link候補
- 更新影響の説明

## 22.2 AIに禁止

- Raw HTML
- Affiliate URL
- Disclosure文の削除・上書き
- Product Cardの価格・在庫を自由生成
- JSON-LD
- Recommendationの最終確定
- Finance入力による順位変更
- Source外のFact補完
- 実体験の創作
- Approval/Publish/Kill Switch操作

## 22.3 Content Input Contract

AI Taskには次を追加する。

```text
article_type_version
article_template_version
content_schema_version
methodology_version
candidate_universe_manifest
claim_evidence_policy_version
editorial_policy_bundle_version
seo_policy_version
renderer_owned_fields
```

## 22.4 評価追加

- AST Schema Adherence
- Required Block Coverage
- Product Identity
- Claim Evidence Coverage
- Temporal Accuracy
- Recommendation Bias
- Tradeoff Completeness
- Renderer Ownership
- Forbidden Review Body
- Experience Record Enforcement
- No Structured Data/URL Generation

既存RAOS-AI-001を黙って書き換えず、`RAOS_06_003_ai_alignment_patch_v0.1.yaml`をVersioned Revision入力にする。

---

# 23. Publication Snapshot

公開候補は次をHashで固定する。

```text
article_version_id
content_schema_version
article_type_version
article_template_version
content_ast_sha256
source_packet_version + sha256
candidate_universe_sha256
methodology_version + sha256
policy_bundle_version
seo_metadata_version + sha256
structured_data_manifest + sha256
disclosure_policy_version
quality_result_id
review_decision / approval ids
renderer_version
media_asset ids + hashes
safe offer projection version
```

SnapshotにFinance、Secret、内部Source URI、Raw Prompt、未公開Evidenceを含めない。

## 23.1 Public Rendering

1. Snapshot Schema Validation
2. Kill Switch評価
3. Current Safe Product Projection結合
4. Disclosure/API Credit挿入
5. Safe HTML Render
6. Metadata/Canonical/Robots
7. Deterministic JSON-LD
8. Accessibility属性
9. Cache KeyへPublication Version/Kill Switch Generation
10. Click Beacon属性
11. Error Boundary

未知SchemaやHash不一致では、直前正常版へFallbackするか安全なErrorを表示する。

## 23.2 Rollback

Content誤りはPublication Rollback、Code障害はDeployment Rollback、DB変更はMigration Rollbackとして分ける。旧Snapshotを再公開する場合も、現在のPolicy Bundleで再評価し、現在非準拠ならRollbackを拒否する。

---

# 24. Data/API/AI整合

## 24.1 DATA

RAOS-DATA-001はArticle Version、Block、Comparison、Recommendation、Claim、Snapshotを既に持つ。本工程で不足するVersioned Contract、Methodology、SEO、Structured Data、Media、First-hand Experience、Disclosure Contextは、Proposal SQLへ分離した。

提案は追加型であり、既存Tableを破壊しない。Codexは実DBのColumn、Constraint、Roleを確認し、不要な重複Tableを作らず、正式Migrationへ変換する。

## 24.2 API

Content Schema/Template/Methodology/SEO/Media/Review/ManifestのResourceとCommand追加が必要である。Public APIはRead Model以外を返さず、Evidence原本、AI内部、Financeを漏らさない。

## 24.3 AI

既存AIT-002/003/004/005/006/008/009/010へContent Version、Renderer所有Field、禁止Output、評価を追加する。既存契約互換性とPrompt Hashを維持し、新VersionとしてReleaseする。

---

# 25. 実装スライス

| Slice | 名称 | 依存 | 目的 |
| --- | --- | --- | --- |
| CONT-SLICE-001 | Content contract repository bootstrap |  | 契約、Schema、Template、Fixtureを配置し、Lint/Hash/Drift CIを構築する |
| CONT-SLICE-002 | Content AST domain types and loader | CONT-SLICE-001 | Content AST v1をPython/PydanticとTypeScript型へ生成し、安全なLoaderを実装する |
| CONT-SLICE-003 | Article type and template validator | CONT-SLICE-002 | 5記事型のRequired Block、順序、商品数、Unique Value Gateを検証する |
| CONT-SLICE-004 | Claim–Evidence validator | CONT-SLICE-002 | Claim分類、Coverage、Source Tier、Conflict、Temporal Scopeを検査する |
| CONT-SLICE-005 | Product identity and comparison validator | CONT-SLICE-004 | Product/Variant/Offer同定と同一軸比較を検証する |
| CONT-SLICE-006 | Recommendation methodology engine | CONT-SLICE-004<br>CONT-SLICE-005 | Hard Constraint、正規化、Coverage、Penalty、Tie、Overrideを決定論的に計算する |
| CONT-SLICE-007 | Disclosure and affiliate CTA renderer | CONT-SLICE-002 | Disclosure、楽天遷移ラベル、rel=sponsored、直接Link、API CreditをRendererで強制する |
| CONT-SLICE-008 | SEO metadata and route policy | CONT-SLICE-002 | Title/H1/Meta/Canonical/Index/Sitemap/RedirectをVersion管理し検証する |
| CONT-SLICE-009 | Deterministic structured data renderer | CONT-SLICE-008 | Article/BlogPosting、Breadcrumb等を可視Snapshotから決定的に生成する |
| CONT-SLICE-010 | Media asset and accessibility pipeline | CONT-SLICE-002 | Asset Provenance、利用条件、alt、図表説明、画像変形禁止を検査する |
| CONT-SLICE-011 | Freshness and safe degradation | CONT-SLICE-004<br>CONT-SLICE-007 | Fact/Offer/Linkの鮮度状態とField/CTA/Article縮退を実装する |
| CONT-SLICE-012 | Internal link and content lifecycle | CONT-SLICE-008 | Internal Link Journey、Orphan、Merge/301/410/noindex候補を管理する |
| CONT-SLICE-013 | Editorial review and quality gates | CONT-SLICE-003<br>CONT-SLICE-004<br>CONT-SLICE-006<br>CONT-SLICE-010<br>CONT-SLICE-011 | Checklist、Score、Finding、Solo Exception、Final Approval Gateを実装する |
| CONT-SLICE-014 | Publication content manifest and renderer | CONT-SLICE-007<br>CONT-SLICE-008<br>CONT-SLICE-009<br>CONT-SLICE-013 | 承認済みVersionからSnapshot Manifestを作り、Public Read Modelへ投影する |
| CONT-SLICE-015 | Upstream data/API/AI alignment | CONT-SLICE-001 | 提案Patchを正式Migration/OpenAPI/AI Contractへ移植し、互換性Testを行う |
| CONT-SLICE-016 | End-to-end editorial pilot | CONT-SLICE-014<br>CONT-SLICE-015 | 5記事型の合成・Recorded Fixtureで企画から公開後検査まで通す |

## 25.1 最初のPR

最初は`CONT-SLICE-001`だけを実装する。

- 契約Filesを配置
- JSON Schema Draft 2020-12 Validation
- YAML/JSON/CSV Lint
- `$id`、Hash、Cross-reference検査
- Valid/Invalid Fixture
- Python/TypeScript型生成の検証
- Generated Drift Check
- Secret/Review-body/Finance-field Scan
- CODEOWNERS/PR Template

Business Logic、DB Migration、OpenAPI変更、OpenAI Call、Public Rendererは最初のPRで実装しない。

---

# 26. 受入条件

本工程のArtifactは次を満たす。

- 5記事型がVersioned Catalogにある
- 24 BlockとRich Text許可範囲がSchema化されている
- 任意HTML、手入力Affiliate URL、Finance FieldがSchemaから除外されている
- 9 Claim TypeとSource Tierが定義されている
- RecommendationのHard Constraint、Coverage、Penalty、Tie、Overrideが定義されている
- 40 Editorial PolicyがID付きで存在する
- 12 Freshness ClassとSafe Degradationがある
- SEO、Canonical、Sitemap、Structured Data、FAQ、Product Markup方針がある
- Media ProvenanceとAccessibilityがある
- 100点Score、85点閾値、Axis Floor、Zero-toleranceがある
- Human ReviewとSolo Exceptionが定義されている
- Publication SnapshotへVersion/Hashを固定する
- Data/API/AI Proposalが本番変更と分離されている
- 全Catalog、Schema、Fixture、CSVが機械検証できる
- Codex実装順序がPR単位に分解されている

---

# 27. 未決事項・Production前確認

次は本書で無理に確定せず、実装・Category選定・法務確認で決める。

1. MVPの具体CategoryとCategory固有Freshness SLA
2. Manufacturer SourceのFetch/引用条件
3. 楽天画像のCache/Proxy/Resize実装の最終利用条件
4. Standard Disclosure文の法務最終確認
5. Material Benefitの具体的表示Template
6. Solo Reviewへ追加する外部監査頻度
7. Score WeightとEvidence CoverageのPilot Calibration
8. Price Tier変化等のReview Trigger閾値
9. 将来の単一商品Review型とProduct Markup解放条件
10. 独自実機Testの手順、設備、責任境界
11. 生成AI装飾画像を完全禁止にするかのBrand Policy
12. 301/410/holdのAnalytics評価期間

これらを理由に、Blockerを緩めて実装を進めてはならない。未決値はVersioned ConfigとFeature Flagで閉じる。

---

# 28. 公式参照資料

## Google Search Central

- https://developers.google.com/search/docs/fundamentals/creating-helpful-content
- https://developers.google.com/search/docs/essentials/spam-policies
- https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links
- https://developers.google.com/search/docs/fundamentals/using-gen-ai-content
- https://developers.google.com/search/docs/fundamentals/ai-optimization-guide
- https://developers.google.com/search/docs/specialty/ecommerce/write-high-quality-reviews
- https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data
- https://developers.google.com/search/docs/appearance/structured-data/article
- https://developers.google.com/search/docs/appearance/structured-data/product-snippet
- https://developers.google.com/search/docs/appearance/structured-data/breadcrumb
- https://developers.google.com/search/docs/appearance/snippet
- https://developers.google.com/search/docs/appearance/google-images
- https://developers.google.com/search/updates#removing-faq-rich-result

## 楽天・消費者庁

- https://affiliate.rakuten.co.jp/guideline/rule/
- https://affiliate.rakuten.co.jp/guideline/stealth_marketing_regulation/
- https://webservice.rakuten.co.jp/guide/credit
- https://www.caa.go.jp/policies/policy/representation/fair_labeling/stealth_marketing

## Accessibility

- https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html
- https://www.w3.org/WAI/tutorials/images/decision-tree/

---

# 付録A. ファイル正本

| 領域 | 正本 |
|---|---|
| 記事型 | `RAOS_06_article_type_catalog_v0.1.yaml` |
| Block | `RAOS_06_content_block_catalog_v0.1.yaml` |
| AST/Schema | `RAOS_06_schema_registry_v0.1.yaml`, `schemas/**` |
| Claim/Evidence | `RAOS_06_claim_evidence_policy_v0.1.yaml` |
| Recommendation | `RAOS_06_recommendation_methodology_v0.1.yaml` |
| Policy | `RAOS_06_editorial_policy_catalog_v0.1.yaml` |
| SEO/Structured Data | `RAOS_06_seo_metadata_structured_data_policy_v0.1.yaml` |
| Freshness/Lifecycle | `RAOS_06_freshness_update_policy_v0.1.yaml` |
| Internal Link | `RAOS_06_internal_link_policy_v0.1.yaml` |
| Media/Accessibility | `RAOS_06_media_asset_policy_v0.1.yaml` |
| Quality Gate | `RAOS_06_quality_gate_catalog_v0.1.yaml` |
| Human Review | `RAOS_06_review_checklist_v0.1.yaml` |
| Implementation | `RAOS_06_implementation_slices_v0.1.yaml` |
| Test | `RAOS_06_content_test_matrix_v0.1.csv` |
| Traceability | `RAOS_06_traceability_matrix_v0.1.csv` |

# 付録B. Codex不変条件

1. 記事をMarkdown/HTMLだけの正本へ簡略化しない。
2. Content ASTにRaw HTML escape hatchを追加しない。
3. Affiliate URLをText/Promptへ入れない。
4. DisclosureをEditor任意Blockにしない。
5. Product Card/Comparison Table/JSON-LDをLLM自由生成にしない。
6. RecommendationへFinance指標を入れない。
7. Unsupported Claimを「自然な文章」にして隠さない。
8. Unknown/Stale Factを推測値で埋めない。
9. 楽天レビュー本文の収集Fieldを作らない。
10. Human ApprovalをCI/Testの都合で迂回しない。
11. 提案SQLを本番へ直接適用しない。
12. 外部仕様の変更を検知したらDecision Record候補を出す。


---

# 付録C. 記事タイプ詳細

## AT-001 選び方ガイド

- Code: `selection_guide`
- Primary Decision: カテゴリ内で自分に合う商品を選ぶための評価軸と判断手順を理解する
- Allowed Intent: how_to_choose, buying_guide, criteria_explanation
- Product Count: minimum 3, recommended 5-12, maximum 15
- Minimum Decision Axes: 4
- Ranking Policy: `contextual_only`
- Required Blocks: lead, decision_summary, intended_reader, methodology, selection_criteria, comparison_table, recommendation_group, caution, source_summary
- Required Unique Value: カテゴリ固有の判断軸 / 軸ごとのトレードオフ / 条件別に異なる結論 / 対象外条件または避けるべき選択
- Disallowed: API項目の羅列 / 商品名だけを差し替えた量産 / 全員向けの単一総合1位 / 検索語の言い換えだけの別ページ
- Template: `templates/selection_guide.template.yaml`

## AT-002 用途別おすすめ

- Code: `use_case_recommendation`
- Primary Decision: 明確な利用状況・制約に対して、候補ごとの適合理由と妥協点を比較する
- Allowed Intent: best_for_use_case, constraint_based_recommendation, persona_fit
- Product Count: minimum 2, recommended 3-8, maximum 12
- Minimum Decision Axes: 3
- Ranking Policy: `use_case_specific`
- Required Blocks: lead, decision_summary, intended_reader, methodology, selection_criteria, recommendation_group, product_card, tradeoff, caution, source_summary
- Required Unique Value: 利用状況の明示 / ハード制約 / 適合理由 / 向かない条件 / 代替候補
- Disallowed: 根拠のないおすすめ順 / 誰にでも最適という表現 / 料率を反映した順位 / 利用場面の抽象化不足
- Template: `templates/use_case_recommendation.template.yaml`

## AT-003 商品比較（A対B等）

- Code: `product_comparison`
- Primary Decision: 少数候補の差異を同じ評価軸・同じ時点で比較し、自分の優先条件に合う方を選ぶ
- Allowed Intent: a_vs_b, product_comparison, which_is_better_for
- Product Count: minimum 2, recommended 2-4, maximum 6
- Minimum Decision Axes: 4
- Ranking Policy: `conditional_winner_only`
- Required Blocks: lead, decision_summary, intended_reader, methodology, difference_matrix, comparison_table, tradeoff, recommendation_group, caution, source_summary
- Required Unique Value: 同一軸での比較 / 差がない項目の明示 / 条件別勝者 / 決定要因 / 比較不能項目の明示
- Disallowed: 全条件を無視した総合勝者 / 取得時点が異なる値の無注記比較 / Variantの取り違え / 比較母集団の不明確化
- Template: `templates/product_comparison.template.yaml`

## AT-004 型番・世代・容量差分

- Code: `model_generation_capacity_difference`
- Primary Decision: 同一系列の型番・世代・容量・セット差を正しく同定し、追加費用に見合う差を判断する
- Allowed Intent: model_difference, generation_difference, capacity_difference, variant_difference
- Product Count: minimum 2, recommended 2-6, maximum 8
- Minimum Decision Axes: 3
- Ranking Policy: `upgrade_value_by_condition`
- Required Blocks: lead, decision_summary, intended_reader, methodology, difference_matrix, selection_criteria, tradeoff, recommendation_group, caution, source_summary
- Required Unique Value: 型番・Variant同定 / 変わった点・変わらない点 / 差額判断 / 旧型を選べる条件 / 互換性または付属品差
- Disallowed: 別商品系列の混入 / 仕様差の推測 / 発売年だけによる新型推奨 / 価格差の鮮度無視
- Template: `templates/model_generation_capacity_difference.template.yaml`

## AT-005 条件別絞り込み

- Code: `condition_filtering`
- Primary Decision: 複数の明示条件を満たす候補だけを絞り、除外理由と残った候補の差を理解する
- Allowed Intent: filter_by_condition, products_under_constraints, shortlist
- Product Count: minimum 3, recommended 3-15, maximum 20
- Minimum Decision Axes: 3
- Ranking Policy: `eligible_set_then_contextual_order`
- Required Blocks: lead, decision_summary, intended_reader, methodology, selection_criteria, comparison_table, recommendation_group, caution, source_summary
- Required Unique Value: 条件の定義 / 除外ロジック / 不足データの扱い / 残存候補の比較 / 条件を緩める場合の影響
- Disallowed: URLパラメータごとの自動量産 / 条件一致だけで本文価値がないページ / 不明値を条件合格扱い / 在庫だけの一覧
- Template: `templates/condition_filtering.template.yaml`


---

# 付録D. Claim Type詳細

## CLM-TYPE-001 直接事実

- Code: `direct_fact`
- Examples: 重量は1.2kg / 容量は500mL
- Minimum Evidence: 同一Product/Variantを示す有効Fact 1件
- Preferred Source Tiers: SRC-TIER-A, SRC-TIER-B
- Blocking Conditions: 対象Variant不明 / 単位不明 / Source期限切れ

## CLM-TYPE-002 派生事実

- Code: `derived_fact`
- Examples: 1g当たり価格 / 差額率
- Minimum Evidence: 全入力Fact / 式ID / 丸め規則 / 計算時点
- Preferred Source Tiers: SRC-TIER-A, SRC-TIER-B
- Blocking Conditions: 入力欠損 / 式未登録 / 異通貨・異単位の無変換比較

## CLM-TYPE-003 比較主張

- Code: `comparative`
- Examples: AはBより軽い / 3候補中最小
- Minimum Evidence: 比較対象全件の同一軸Fact / 同等な取得時点または差の注記 / 比較母集団
- Preferred Source Tiers: SRC-TIER-A, SRC-TIER-C, SRC-TIER-D
- Blocking Conditions: 母集団不明 / 比較時点の非対称 / 不明値を劣位扱い

## CLM-TYPE-004 推薦判断

- Code: `recommendation`
- Examples: 狭い部屋向け / 予算優先ならA
- Minimum Evidence: Methodology Version / 対象条件 / 適合Fact / 不向き条件 / 代替候補または代替なし理由
- Preferred Source Tiers: SRC-TIER-A, SRC-TIER-C, SRC-TIER-D
- Blocking Conditions: 料率・EPC・利益の混入 / 万能推奨 / 根拠なし順位

## CLM-TYPE-005 使用・検証体験

- Code: `experience`
- Examples: 実際に測定した / 使用時に確認した
- Minimum Evidence: First-hand Experience Record / 手順 / 日時 / 担当者 / 原本Asset
- Preferred Source Tiers: SRC-TIER-D
- Blocking Conditions: 実施記録なし / 他者体験の自称 / AIによる体験生成

## CLM-TYPE-006 価格・在庫・販売状態

- Code: `price_availability`
- Examples: 12,800円 / 在庫あり
- Minimum Evidence: Offer Fact / 取得日時 / ショップ・商品コード / 鮮度判定
- Preferred Source Tiers: SRC-TIER-B
- Blocking Conditions: 鮮度期限超過 / 税込・送料条件不明 / 別Offer混同

## CLM-TYPE-007 最上級・唯一性

- Code: `superlative`
- Examples: 最軽量 / 最安 / 唯一
- Minimum Evidence: 対象母集団の完全定義 / 全候補の同一軸Fact / 時点・範囲・除外条件
- Preferred Source Tiers: SRC-TIER-A, SRC-TIER-B, SRC-TIER-C, SRC-TIER-D
- Blocking Conditions: 市場全体を暗示する狭い比較 / 母集団欠損 / 時点なし

## CLM-TYPE-008 安全・法令・規制

- Code: `safety_legal_regulatory`
- Examples: 法令上必要 / 安全性が高い
- Minimum Evidence: 官公庁・法令・規格等の一次ソース / Compliance Review
- Preferred Source Tiers: SRC-TIER-A
- Blocking Conditions: MVP低リスク範囲外 / 医療・法務・金融助言 / 非公式ソースのみ

## CLM-TYPE-009 予測・将来主張

- Code: `predictive`
- Examples: 値上がりする / 長く売れ続ける
- Minimum Evidence: 承認済み予測Methodology / 不確実性と期間
- Preferred Source Tiers: SRC-TIER-A, SRC-TIER-C
- Blocking Conditions: MVPでは既定禁止 / 断定表現 / 根拠なし将来予測


---

# 付録E. Editorial Policy詳細

## POL-CONT-001 `approved_source_packet_required`

- Severity: `BLOCKER`
- Stage: `all`
- Enforcement: `deterministic`
- Rule: 承認済みSource Packetがない記事生成・公開を禁止する

## POL-CONT-002 `major_claim_evidence`

- Severity: `BLOCKER`
- Stage: `draft`
- Enforcement: `deterministic`
- Rule: 主要ClaimのEvidence Coverageは100%

## POL-CONT-003 `fabricated_experience`

- Severity: `BLOCKER`
- Stage: `draft`
- Enforcement: `hybrid`
- Rule: 実施記録のない使用・検証・愛用表現を禁止する

## POL-CONT-004 `rakuten_review_body`

- Severity: `BLOCKER`
- Stage: `ingest`
- Enforcement: `deterministic`
- Rule: 楽天レビュー本文の取得・保存・要約・変形・依拠を禁止する

## POL-CONT-005 `affiliate_bias`

- Severity: `BLOCKER`
- Stage: `recommendation`
- Enforcement: `deterministic`
- Rule: 料率・EPC・RPM・報酬・利益を推薦入力へ含めない

## POL-CONT-006 `raw_html`

- Severity: `BLOCKER`
- Stage: `content_ast`
- Enforcement: `schema`
- Rule: 任意HTML、Script、iframe、Style、Event Handlerを禁止する

## POL-CONT-007 `manual_affiliate_url`

- Severity: `BLOCKER`
- Stage: `content_ast`
- Enforcement: `schema`
- Rule: Affiliate URLの手入力を禁止し、Offer/Link Resourceから解決する

## POL-CONT-008 `disclosure_top`

- Severity: `BLOCKER`
- Stage: `render`
- Enforcement: `deterministic`
- Rule: 広告・アフィリエイト関係を記事上部の初回表示範囲で明示する

## POL-CONT-009 `cta_destination`

- Severity: `BLOCKER`
- Stage: `render`
- Enforcement: `deterministic`
- Rule: CTAは楽天市場への遷移であることを明示する

## POL-CONT-010 `paid_link_rel`

- Severity: `BLOCKER`
- Stage: `render`
- Enforcement: `deterministic`
- Rule: Affiliate Linkへrel=sponsoredを付与する

## POL-CONT-011 `direct_affiliate_link`

- Severity: `BLOCKER`
- Stage: `render`
- Enforcement: `deterministic`
- Rule: 自社RedirectでAffiliate URLを中継・改変しない

## POL-CONT-012 `rakuten_api_credit`

- Severity: `BLOCKER`
- Stage: `render`
- Enforcement: `deterministic`
- Rule: 楽天API利用時の指定クレジットを共通Rendererへ表示する

## POL-CONT-013 `rakuten_image_integrity`

- Severity: `BLOCKER`
- Stage: `media`
- Enforcement: `hybrid`
- Rule: 楽天提供画像の改変、文字重畳、切り抜き、縦横比破壊を禁止する

## POL-CONT-014 `unsupported_superlative`

- Severity: `BLOCKER`
- Stage: `draft`
- Enforcement: `hybrid`
- Rule: 母集団・範囲・時点がない最上級・唯一性を禁止する

## POL-CONT-015 `stale_critical_fact`

- Severity: `BLOCKER`
- Stage: `publication`
- Enforcement: `deterministic`
- Rule: 鮮度期限を超えた価格・在庫・リンク・主要仕様を最新として表示しない

## POL-CONT-016 `product_identity`

- Severity: `BLOCKER`
- Stage: `draft`
- Enforcement: `deterministic`
- Rule: 商品、型番、容量、色、セット、ショップOfferの同定不一致を禁止する

## POL-CONT-017 `high_risk_claim`

- Severity: `BLOCKER`
- Stage: `scope`
- Enforcement: `hybrid`
- Rule: MVPで医療・法務・金融・安全性の高リスク助言を扱わない

## POL-CONT-018 `human_approval`

- Severity: `BLOCKER`
- Stage: `publication`
- Enforcement: `deterministic`
- Rule: 人間の明示承認なしに公開しない

## POL-CONT-019 `one_primary_intent`

- Severity: `MAJOR`
- Stage: `plan`
- Enforcement: `human`
- Rule: 一記事一主要意思決定・一主要Intent Clusterを維持する

## POL-CONT-020 `scaled_thin_pages`

- Severity: `MAJOR`
- Stage: `plan`
- Enforcement: `hybrid`
- Rule: 検索語、Tag、条件の組合せだけで低価値ページを量産しない

## POL-CONT-021 `competitor_copy`

- Severity: `MAJOR`
- Stage: `draft`
- Enforcement: `hybrid`
- Rule: 競合記事は発見専用とし、根拠・転載・近似言い換えに使用しない

## POL-CONT-022 `balanced_tradeoffs`

- Severity: `MAJOR`
- Stage: `draft`
- Enforcement: `human`
- Rule: 推薦候補の不向き条件・制約・トレードオフを隠さない

## POL-CONT-023 `uncertainty_disclosure`

- Severity: `MAJOR`
- Stage: `draft`
- Enforcement: `hybrid`
- Rule: 不明・競合・欠損を推測で埋めず、表示またはClaim除外する

## POL-CONT-024 `unique_metadata`

- Severity: `MAJOR`
- Stage: `seo`
- Enforcement: `deterministic`
- Rule: Title、H1、Meta Descriptionをページ固有かつ内容一致にする

## POL-CONT-025 `index_state`

- Severity: `BLOCKER`
- Stage: `seo`
- Enforcement: `deterministic`
- Rule: Draft/Preview/noindexページをSitemapへ含めず、公開CanonicalのみIndexableにする

## POL-CONT-026 `visible_match`

- Severity: `BLOCKER`
- Stage: `structured_data`
- Enforcement: `deterministic`
- Rule: JSON-LDと可視本文の不一致、存在しないRating/Review/Offer補完を禁止する

## POL-CONT-027 `multi_product_product_markup`

- Severity: `MAJOR`
- Stage: `structured_data`
- Enforcement: `deterministic`
- Rule: 複数商品記事にProduct Product Snippet用Markupを出さない

## POL-CONT-028 `faqpage_disabled`

- Severity: `MAJOR`
- Stage: `structured_data`
- Enforcement: `deterministic`
- Rule: 可視FAQは許可するがFAQPage JSON-LDを生成しない

## POL-CONT-029 `rakuten_rating_markup`

- Severity: `MAJOR`
- Stage: `structured_data`
- Enforcement: `deterministic`
- Rule: 楽天の平均評価・件数からReview/AggregateRating JSON-LDを生成しない

## POL-CONT-030 `query_variant_consolidation`

- Severity: `MAJOR`
- Stage: `seo`
- Enforcement: `human`
- Rule: 意味が同じ検索語Variantは単一Canonical記事へ統合する

## POL-CONT-031 `internal_link_quality`

- Severity: `MAJOR`
- Stage: `links`
- Enforcement: `deterministic`
- Rule: 公開済み関連Routeだけへ説明的AnchorでLinkし、過剰Exact Matchを避ける

## POL-CONT-032 `non_text_alternative`

- Severity: `BLOCKER`
- Stage: `accessibility`
- Enforcement: `hybrid`
- Rule: 情報画像・図表に同等目的の代替テキストまたは詳細説明を付与する

## POL-CONT-033 `semantic_structure`

- Severity: `MAJOR`
- Stage: `accessibility`
- Enforcement: `hybrid`
- Rule: 見出し階層、表見出し、Keyboard操作、色以外の区別を維持する

## POL-CONT-034 `substantive_lastmod`

- Severity: `MAJOR`
- Stage: `metadata`
- Enforcement: `deterministic`
- Rule: lastmod/Updated Atは実質的変更時のみ更新する

## POL-CONT-035 `kill_switch`

- Severity: `BLOCKER`
- Stage: `publication`
- Enforcement: `deterministic`
- Rule: Publication/Affiliate Link Kill Switchが有効な場合は該当出力をFail Closedする

## POL-CONT-036 `snapshot_integrity`

- Severity: `BLOCKER`
- Stage: `publication`
- Enforcement: `deterministic`
- Rule: 承認Version・Methodology・Policy・Evidence・SEO・Schema HashをPublication Snapshotへ固定する

## POL-CONT-037 `review_aggregate_inference`

- Severity: `MAJOR`
- Stage: `draft`
- Enforcement: `hybrid`
- Rule: レビュー平均・件数だけから品質・満足・長所短所・代表意見を推定しない

## POL-CONT-038 `price_language`

- Severity: `MAJOR`
- Stage: `draft`
- Enforcement: `hybrid`
- Rule: 価格は取得時点の事実として書き、常時価格・最安保証を暗示しない

## POL-CONT-039 `ai_product_depiction`

- Severity: `BLOCKER`
- Stage: `media`
- Enforcement: `hybrid`
- Rule: 実在商品の外観・仕様をAI生成画像で代替しない

## POL-CONT-040 `safe_degradation`

- Severity: `MAJOR`
- Stage: `publication`
- Enforcement: `deterministic`
- Rule: 変動Factが失効した場合は該当Field/CTAを縮退し、推薦順位を自動変更しない
