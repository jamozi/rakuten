# Product, Brand and Category Strategy

## 1. Product thesis

暮らしのしるべは、商品を大量に並べる比較メディアではなく、**公開ルールと製品仕様を条件式へ変換し、読者の候補を安全に減らすdecision-support product**とする。記事は検索入口と説明面、toolは条件判定、source registryは根拠、Rakuten linkは候補の価格・在庫・色を外部で再確認する出口である。

### Product promise

> 公式ルールと製品仕様を照合し、あなたの条件で買える候補だけを残す。

### Product boundaries

- 価格・在庫・point・shop状態は観測時点のoffer情報であり、恒久商品事実にしない。
- 実機試験がないため、耐久性、走行性、静音性、操作性、収納のしやすさを経験したように評価しない。
- 「おすすめ」は全員向け総合winnerではなく、入力条件と一次情報に対する編集判断である。
- 条件適合は搭乗保証ではない。最終判断主体、便、機材、運賃、空港運用の確認linkを必ず示す。
- 競合はmarket/UX研究だけ。商品claim、文章、画像、score、reviewは取り込まない。

## 2. Audience and JTBD

### Primary audience

日本で飛行機を使う1〜4泊の旅行者・出張者のうち、次のいずれかを抱える購入検討者。

- 航空会社、LCC、座席数、運賃で規定が変わり「機内持ち込み対応」の表示を信用しきれない。
- スーツケースの外寸、キャスター込み、拡張時寸法、重量、身の回り品を同時に確認したい。
- 買い直しを避けたいが、review volumeや人気順だけでは決められない。
- 実店舗で試さず、公式情報と楽天で購入候補を絞りたい。

### Secondary audience

- 既に持っているバッグが便の条件に合うか確認したい人。
- 7kg制限で「買う」以外に荷物を減らす方法を探す人。
- 家族/同行者/乗継で最も厳しい条件を把握したい人。

### Jobs to be Done

| JTBD | Trigger | Desired progress | Failure to avoid | Product response |
| --- | --- | --- | --- | --- |
| JTBD-01 適合確認 | 予約した航空会社・便・運賃が決まった | 今のバッグ/候補が各辺・合計・重量・個数に合うか分かる | 一般的115cmだけを信じて当日超過 | checker + exact official rule + UNKNOWN handling |
| JTBD-02 候補削減 | 機内持込用のバッグ/スーツケースを買う | 自分の制約に適合する数個へ絞る | 人気/報酬/広告で不要な候補を買う | hard eligibility + conditional fit |
| JTBD-03 trade-off理解 | 軽さ/容量/開き方/PC収納で迷う | 得るものと失うものを理解する | 仕様を便益として過大解釈 | official fact → editorial meaning → non-fit |
| JTBD-04 代替案 | 重量/寸法を満たせない | 買い替え、荷物削減、預け入れ等を比較 | 無理に商品購入へ誘導 | buy-nothing path and official check |
| JTBD-05 最終確認 | 楽天で候補を見つけた | 型番・variant・現在の価格/在庫/色を確認する | アクセサリ/旧型/別容量を誤購入 | exact identity CTA and verification checklist |

## 3. Category selection model

### Weighted criteria

| Criterion | Weight | Meaning |
| --- | --- | --- |
| decision_difficulty | 12 | 読者が複数条件を統合しないと誤る度合い。 |
| primary_source_value | 14 | 一次情報の正規化だけで独自価値を作れるか。 |
| no_hands_on_viability | 14 | 実機試験なしで誠実な推薦が成立するか。 |
| rakuten_depth | 10 | 楽天内の商品/ショップ出口の厚み。数値は今後確認。 |
| long_tail_breadth | 10 | rule/task/difference/compatibility queryの広さ。 |
| differentiation_room | 10 | 大手のtest/volume以外の勝ち筋。 |
| identity_manageability | 7 | 型番・variant・セット同定の扱いやすさ。 |
| freshness_manageability | 7 | 1人で変更監視可能か。 |
| low_safety_misrepresentation_risk | 7 | 安全/法令/期待誤認riskが低いか。 |
| production_cost_manageability | 5 | 一次情報の取得・更新時間。 |
| topical_authority_potential | 4 | 内部linkで明瞭なtopic graphを作れるか。 |

Scoring is 1–5 internal judgement. Weighted score is not market fact and will be recalibrated after Phase 0 demand/Rakuten evidence.

| ID | Category | Weighted /100 | Primary source | No hands-on | Rakuten depth | Long-tail | Differentiation | Low-risk | Decision | Principal risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAT-01 | 機内持ち込み条件と短期旅行荷物 | 90.8 | 5 | 5 | 4 | 5 | 4 | 4 | SELECT_INITIAL_WEDGE | 航空会社ルール変更、路線・運賃差、拡張時寸法、商品世代差。 |
| CAT-02 | 収納寸法・設置制約で選ぶ小型家具/収納 | 80.2 | 4 | 4 | 5 | 5 | 4 | 4 | EXPANSION_CANDIDATE_AFTER_GATE | サイズvariant、組立、耐荷重の表記差。 |
| CAT-03 | 工事不要・設置条件で選ぶ小型家電 | 74.0 | 4 | 3 | 4 | 5 | 4 | 2 | DEFER | 電気/水/熱/安全、設置可否、実使用品質を公式仕様だけで断定できない。 |
| CAT-06 | 期限・行政条件で選ぶ備え用品 | 72.8 | 5 | 4 | 3 | 4 | 4 | 2 | INFORMATIONAL_ONLY_LATER | 行政情報の地域差・期限管理・安全表示。商品推薦より情報提供が主。 |
| CAT-04 | 防災電源・ポータブル電源 | 64.4 | 4 | 2 | 4 | 4 | 3 | 1 | DEFER_SAFETY_HIGH | 安全・電池・出力互換・法令・災害時期待。誤認コストが高い。 |
| CAT-05 | ロボット掃除機・食洗機等の使用品質比較 | 60.6 | 3 | 1 | 4 | 5 | 2 | 3 | REJECT_INITIAL | 清掃力・静音・使い勝手・耐久など実機なしでは中核価値が不足。 |

### Selected wedge

**旅の機内持ち込み条件と荷物選び**を選ぶ。スーツケースだけをtaxonomyにするのではなく、航空ルール、手荷物/身の回り品、重量、寸法、荷造り、バッグ/スーツケースの選択を1つのdecision graphにする。

**Why it wins**

1. 一般的な「115cm以内」では足りず、carrier、座席数、運賃、便、乗継、個数、重量、身の回り品、拡張時という条件統合が必要。
2. 航空会社とメーカーの一次情報があり、実機を使わずにcompatibilityという価値を作れる。
3. 商品を買わない解決も含められ、thin affiliate化を避けられる。
4. 既存の公開記事とACE 3モデルsourceをmigration seedにできる。
5. rule/tool/guide/comparison/difference/policyの内部linkが自然で、25 assets以内に明確なauthority graphを作れる。

**Why not the alternatives**

- ポータブル電源は安全、出力互換、電池、災害時期待を扱い、実機なしの誤認costが高い。
- 食洗機/robot vacuumは使用品質が中心で、公式仕様だけでは独自推薦の中核が弱い。
- 収納/小型家具は有望だが、初期wedgeの学習を分散するためPhase 6候補。
- 備え用品は行政情報価値があるが、product commerceよりpublic information運用が重い。

## 4. Search-intent clusters

| Cluster | Primary question | Page types | Representative assets | Internal conversion |
| --- | --- | --- | --- | --- |
| C1 Rule compatibility | この便/航空会社に持ち込めるか | HUB / GUIDE / TOOL | A01,A02,A03,A07–A13,A23,A24 | tool result → official rule → suitable product comparison |
| C2 Packing and task constraint | 7kg/1〜2泊/PC込みでどう収めるか | GUIDE / TOOL | A04,A06,A14,A20–A22 | task guide → weight/tool → bag/product condition |
| C3 Product shortlist | 条件に合う候補はどれか | COMPARISON | A05,A15–A17 | eligibility → fit/non-fit → exact Rakuten CTA |
| C4 Difference decision | 方式/モデルの違いでどちらを選ぶか | DIFFERENCE | A18,A19 | difference branch → comparison/product card |
| C5 Trust and method | 何を根拠に、実機なしでどう比較するか | POLICY | A25 | method/evidence → return to decision surface |

### Cannibalization rules

- 1 query familyにprimary ownerは1 URL。secondary pageはdifferent jobを明示する。
- Carrier pageはcarrier-specific rule、general guideはruleの読み方、toolは個別入力結果を担う。
- Comparisonは複数modelの条件選択、differenceは固定model/方式間の差分だけを担う。
- Search Console query overlapが28日間で高く、どちらも固有QDSを作れない場合は統合を優先。
- color/size/brand query variantを自動で別page化しない。

## 5. Brand strategy

### Name

**暮らしのしるべを維持。** 公開面ではRAOSを出さない。RAOS V2はrepository/architecture/operations名。

### One-sentence positioning

> 公式ルールと製品仕様を照合し、あなたの条件で買える候補だけを残す購買支援メディア。

### Voice

- Calm: 急がせない、煽らない、在庫scarcityを使わない。
- Specific: model number、条件、確認日、source、unknownを具体化。
- Reader-led: 商品起点でなく困る場面と条件から始める。
- Bounded: exact scopeを言い、market-wide winnerを装わない。
- Honest: 実機なし、未確認、変わり得る情報、affiliate relationshipを見える場所に置く。

### Reusable copy logic

- Story: `困る場面 → 条件 → 公式事実 → 生活上の意味 → 選択肢`。
- Recommendation: `この条件なら候補 → official facts → D編集判断 → 向かない条件`。
- Trade-off: `得る便益 → 失うもの/不確実性 → 代替案`。
- CTA: `外部で再確認する項目 → 中立的な行動文`。

### Trust basis

1. source classと確認日。
2. fact/judgement/unknownの分離。
3. recommendation/business scoreの非干渉。
4. exact model identity。
5. update historyとcorrection path。
6. operator/advertising/privacy/editorial policy。
7. no-hands-on disclosure。

### Operator presentation

- 公開名は「暮らしのしるべ編集者」。保有していない資格・実験設備・専門家監修を示唆しない。
- About pageは運営目的、編集責任、AI利用、source policy、収益関係、訂正窓口、更新方針を示す。
- 記事ごとにreviewed by、last checked、change logを表示。個人情報を不必要に公開しない。

## 6. First 25-asset portfolio

| ID | Route | Working title | Template | Intent | Wave | Role |
| --- | --- | --- | --- | --- | --- | --- |
| A01 | /carry-on/ | 機内持ち込み荷物の条件から選ぶ | HUB | RULE/NAV | Wave 1 | wedgeの全導線と航空会社別更新を束ねる。 |
| A02 | /tools/carry-on-size-checker/ | 機内持ち込みサイズ・重量チェッカー | TOOL | DECISION | Wave 1 | 入力した航空会社/便条件/寸法/重量から適合・未確定・不可を返す。 |
| A03 | /guides/carry-on-baggage-rules/ | 機内持ち込み手荷物の基本ルール | GUIDE | RULE | Wave 1 | 個数・身の回り品・各辺・合計・重量の読み方。 |
| A04 | /guides/low-cost-carrier-7kg-packing/ | LCC 7kg以内に収める考え方 | GUIDE | TASK | Wave 1 | 商品を買う前に荷物重量を減らす代替案を示す。 |
| A05 | /carry-on-suitcase-comparison/ | 機内持ち込みスーツケース3モデル条件別比較 | COMPARISON | PRODUCT | Wave 1 | 既存URLを維持しV2へ移行。 |
| A06 | /guides/carry-on-bag-measurement/ | キャスター・持ち手込みで測る方法 | GUIDE | HOW_TO | Wave 1 | 自己計測と公式仕様の差を扱う。 |
| A07 | /guides/domestic-airline-carry-on-size/ | 国内線100席以上・未満のサイズ差 | GUIDE | RULE | Wave 2 | 座席数別の条件と確認導線。 |
| A08 | /guides/ana-carry-on-baggage/ | ANAの機内持ち込み条件 | GUIDE | RULE | Wave 2 | effective date付き公式ルール要約。 |
| A09 | /guides/jal-carry-on-baggage/ | JALの機内持ち込み条件 | GUIDE | RULE | Wave 2 | 乗継時の厳しい区間を含む。 |
| A10 | /guides/peach-carry-on-baggage/ | Peachの機内持ち込み条件 | GUIDE | RULE | Wave 2 | 個数・7kg・寸法。 |
| A11 | /guides/jetstar-carry-on-baggage/ | Jetstarの機内持ち込み条件 | GUIDE | RULE | Wave 2 | 運賃/option差をvariant化。 |
| A12 | /guides/carry-on-expanded-suitcase/ | 拡張機能を使うと持ち込めない場合 | GUIDE | RISK | Wave 2 | 通常時/拡張時寸法を分離。 |
| A13 | /guides/carry-on-personal-item/ | 身の回り品と手荷物の違い | GUIDE | RULE | Wave 2 | バッグ2個の誤解を解消。 |
| A14 | /guides/carry-on-weight-calculator/ | 荷物の合計重量を見積もる方法 | TOOL | DECISION | Wave 2 | 個人データを送信せずlocal calculation。 |
| A15 | /comparisons/lightweight-carry-on-suitcases/ | 公称重量で比べる軽量機内持ち込み候補 | COMPARISON | PRODUCT | Wave 3 | 軽さ以外のtrade-offを明示。 |
| A16 | /comparisons/front-open-carry-on-suitcases/ | フロントオープン候補の条件比較 | COMPARISON | PRODUCT | Wave 3 | 開口方式・寸法・容量・拡張を比較。 |
| A17 | /comparisons/carry-on-suitcases-with-stopper/ | ストッパー付き候補の条件比較 | COMPARISON | PRODUCT | Wave 3 | 搭載有無は公式仕様のみ。 |
| A18 | /comparisons/soft-vs-hard-carry-on/ | ソフトとハードの仕様差から選ぶ | DIFFERENCE | DECISION | Wave 3 | 耐久性を経験したかのように断定しない。 |
| A19 | /differences/ace-cresta-vs-difference-vs-maxpass4/ | ACE 3モデルの違い | DIFFERENCE | PRODUCT | Wave 3 | 既存記事と重複しないquery roleで設計。 |
| A20 | /guides/business-trip-carry-on/ | 1〜2泊出張で先に決める条件 | GUIDE | TASK | Wave 3 | PC・書類・移動条件の質問表。 |
| A21 | /guides/weekend-trip-carry-on/ | 週末旅行の荷物から容量を決める | GUIDE | TASK | Wave 3 | 日数×容量の断定ではなく荷物listで判断。 |
| A22 | /guides/carry-on-laptop-size/ | PC収納と外寸を同時に確認する | GUIDE | TASK | Wave 4 | 内寸UNKNOWNを許容し公式情報へ誘導。 |
| A23 | /guides/carry-on-liquid-rules/ | 液体物ルールの公式確認手順 | GUIDE | RULE | Wave 4 | 国内/国際差と保安情報の更新負荷を管理。 |
| A24 | /guides/carry-on-battery-rules/ | モバイルバッテリー持ち込み確認手順 | GUIDE | SAFETY | Wave 4 | 航空会社・容量・端子保護等はofficial-only。 |
| A25 | /policy/how-we-compare-carry-on-products/ | 機内持ち込み用品の比較方法 | POLICY | TRUST | Wave 1 | 実機なし・source tier・推薦/事業分離を公開。 |

### Wave gates

- **Wave 1 (6 assets):** A01–A06 plus A25 method within the six-deliverable implementation grouping; A25 can ship as policy block/page without a seventh product article. Public action is Phase 3 human-gated.
- **Wave 2:** Day 30でcritical defect 0、source SLA 100%、index/canonical issue 0、QDS measurementがAVAILABLEまたはowner-approved unavailable explanation、少なくとも2つのnon-brand query familyが観測された場合。
- **Wave 3:** Day 90でwedge decisionがCONTINUE/REPAIR、eligible article sessions 500以上または期間延長決定、AOC 3%以上を初期signalとして確認、broken affiliate links 0。3%はplanning thresholdで市場benchmarkではない。
- **Wave 4:** High-risk liquid/battery contentはsource owner・30日SLA・human safety reviewを確保してから。商品CTAを必須にしない。

## 7. Growth and retreat gates

### 30-day gate

| Decision | Condition | Action |
| --- | --- | --- |
| CONTINUE | technical/public critical 0、source freshness 100%、GSC query/impressionが取得可能、QDS instrumentation verified | Wave 2を最大4 assets許可。 |
| REPAIR | index/canonical/UX/measurement defectがあるがwedge intent signalあり | 新規記事停止。既存page/measurementだけ修正。 |
| EXTEND | sample insufficient、provider delay、measurement unavailable but no critical defect | 変更せず30日延長。zero需要とみなさない。 |
| RETREAT | 重大事実欠陥が反復、source更新不能、reader harm complaint、production cost ceiling超過 | CTA/expansion停止、public correction、撤退案をownerへ。 |

### 90-day gate

- **Continue:** 3以上のquery family、月500以上non-brand organic sessionsまたは前月比改善を伴う有効sample、QDS率20%以上、AOC 3%以上、重大欠陥0、更新工数がSLA内。
- **Repair:** impressionはあるがQDS/AOCが低い。title/meta、summary、tool entry、CTA contextの1変数だけを改善。
- **Consolidate:** 2 URLが同じintent/queryを奪い、片方の固有decision valueが弱い。
- **Retreat:** source freshnessを1人で維持できない、critical defectが2回以上、90日でintent signalが極小かつ改善仮説がない。public useful guideは維持し、affiliate expansionを停止。

### 12-month gate

- 24〜25 assetsを目標とするが、gate未通過なら少数で止める。
- 12-month KPI tableのquality guardrailを全て満たし、成熟したeconomic contribution profitが3か月連続positiveであればadjacent category scoringへ。
- 月次cash profitがpositiveでもeconomic profit negative、またはupdate labor ceiling超過なら新規article停止・既存改善/統合。
- Confirmed rewardがUNATTRIBUTED_PROGRAMだけならarticle/category expansionの確信度を下げ、直接因果を主張しない。

## 8. Twelve-month revenue hypothesis

外部の市場規模・検索volume・conversion benchmarkを取得していないため、次は**scenario planning**でありforecastではない。

| Scenario | Mature monthly eligible sessions | AOC | Confirmed EPC | Confirmed reward | Variable cost | Human hours × ¥3,000 | Economic contribution | Interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Downside | 2,000 | 3% | ¥20 | ¥1,200 | ¥0〜2,000 | 30h=¥90,000 | negative | wedge commerceを縮小し、public utility/SEO assetとして最小維持。 |
| Base gate | 5,000 | 6% | ¥30 | ¥9,000 | ¥0〜3,000 | 16h=¥48,000 | negative | 12か月目の目標利益¥60kにはtraffic/EPC/efficiencyの追加改善が必要。 |
| Target viability | 20,000 | 7% | ¥45 | ¥63,000 | ¥3,000 | 12h=¥36,000 | ¥24,000 | cash positiveだがtarget経済利益には未達。 |
| Target 12m planning | 30,000 | 8% | ¥50 | ¥120,000 | ¥5,000 | 18h=¥54,000 | ¥61,000 | 品質guardrailと成熟成果を伴えば継続gate。 |

The calculation makes the constraint explicit: a low-traffic affiliate site cannot reach target economics merely by publishing 25 articles. The design therefore prioritizes decision completion, outbound quality, attribution integrity and low update cost. The target scenario must be replaced with real cohort data at P5.

## 9. Expansion candidates

1. **収納寸法・設置制約で選ぶ小型収納/家具** — exact dimensions and room constraints; only after P5.
2. **旅行用電源/adapterの持込規則** — informational safety cluster, not product ranking, after stronger review capacity.
3. **預け入れ荷物/長期旅行** — same travel authority, but requires airline fee/route freshness model.

Only one may enter P6. The initial wedge remains the default if no candidate clearly exceeds it on decision value per update hour.

## 10. Anti-goals

- 「おすすめ100選」や色・容量ごとのprogrammatic pageを量産しない。
- 料率アップ、価格、在庫、ranking badgeをeditorial orderへ使わない。
- 使用者reviewを収集・要約して実体験を代替しない。
- 空カテゴリ、根拠のない人気、閲覧数ranking、No.1 copyを表示しない。
- SNS/YouTube/ROOMをmeasurement-ready public coreより先に拡張しない。
- 新paid tool、outsource、商品購入、rental、equipmentをdefault planに入れない。
