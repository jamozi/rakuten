# Current State and Research

## 1. Scope, authority and method

- **Packet assembled:** `2026-08-27T13:47:34Z`
- **Packet authority:** `UNAPPROVED_DESIGN_INPUT_ONLY`
- **Repository snapshot:** branch `codex/st1704-publish-five-articles`, HEAD `83cfa17f91dddbee2bcd4e781545fd2bb4a5bcc4`
- **Canonical mutated:** `false`
- **Credentials used / external writes:** `false / false`
- **Archive integrity:** `MANIFEST.sha256`の対象561件を再計算し全件一致。archive総memberは562。
- **Current-fact rule:** packetは2026-08-27のtime-bounded snapshotである。repository・provider・public siteの変更可能な事実は実装/P3前に再確認する。
- **Prohibited inputs:** secret、credential値、個人/production data、raw prompt、private provider data、競合review本文を読み込まない。

Evidence vocabulary:

- **FACT:** packet/公式sourceが直接示す。
- **OBSERVATION:** capture/screenshotの可視面から記録。測定・conformance claimではない。
- **INFERENCE:** 複数factから導く設計判断。sourceからの直接記述ではない。
- **HYPOTHESIS:** baseline不足のため検証が必要。safe default付き。
- **RECOMMENDATION:** V2で採用した規範。
- **UNKNOWN:** sourceが支えない。0や「問題なし」に変換しない。

## 2. Repository audit

### 2.1 Snapshot state

| Field | Observed |
| --- | --- |
| repository root | /home/minami/rakuten |
| branch | codex/st1704-publish-five-articles |
| HEAD | 83cfa17f91dddbee2bcd4e781545fd2bb4a5bcc4 |
| observed_at | 2026-08-27T13:47:34Z |
| worktree diffstat | changes/build/manifest.v2.json \| 117 ++++++++++++++++++++++++++++++++++++++++-<br> 1 file changed, 116 insertions(+), 1 deletion(-) |
| evidence boundary | {"production_readiness": "NOT_CLAIMED", "public_site": "SEPARATE_PUBLIC_READ_ONLY_CAPTURE", "repository": "LIVE_WORKTREE_OBSERVATION_NOT_FORMAL_CI", "staging": "NOT_CLAIMED"} |

Dirty stateは完成済みとも削除対象とも扱わない。特に`changes/build/manifest.v2.json`の変更、`.playwright-cli/**`、full redesign inputs、reliability product selectionのuntracked code/fixturesが存在した。Codexはcurrent live stateを再確認し、監査時のdirty一覧を現在値として使わない。

### 2.2 Repository strengths to retain

- root `AGENTS.md`がdirty protection、immutable path、secret禁止、external action boundary、local evidence namingを明示している。
- `make setup/generate/check/fast/final`が標準workflowとして統合され、generator owner graphを`changes/build/manifest.v2.json`で管理する。
- publication operator、owner-private affiliate learning、claim/evidence、security、rollbackに広いcode/contract/test資産がある。
- WordPress公開面とローカルcandidate/formal CI/staging/Productionを区別する規律がある。
- ST-1704にはbrand voice、design system、5 article packet、source/media registry、publication blocker、measurement ledgerがある。

### 2.3 Repository liabilities and simplification target

- v1 canonical/status/open decisionとactive v2 implementationが併存し、recorded fixture・disabled adapter・local candidate・formal/live evidenceの状態誤読リスクが高い。
- public reader valueが1記事、measurementが全NOT_RECORDEDである一方、内部platform surfaceは広い。市場学習前の過剰設計が疑われる。
- Next.js/public app、general persistence、custom admin、advanced attribution等を初期V2に同時維持すると1人運営のTCOが増える。
- 複数categoryのeditorial pilotは比較可能だが、wedge/authorityを分散し、実機なしでは中核価値が不足するarticleも含む。
- 生成物ownershipは守る必要があるため、手編集でmanifest/generated fileを直す実装は禁止。

### 2.4 Source-of-truth map observed

| Surface | Observed role | V2 disposition |
| --- | --- | --- |
| `docs/canonical/**` | checksum-protected v1 product baseline | KEEP immutable; read-only reference |
| `changes/build/manifest.v2.json` | active generator ownership inventory | KEEP; V2 ownerをgeneratorから追加 |
| `changes/st-1704/**` | active/archived editorial, publication, revenue candidates | REWORK/MIGRATE as evidence, not V2 SoT |
| `python/raos/**` | domain/application/ports/adapters | REWORK narrow V2 modules; do not preserve by volume |
| `apps/web` / packages | local/public candidate rendering | DEFER public Next; reuse preview components when fit |
| WordPress production | current public delivery | MIGRATE route-by-route; not editorial SoT |

## 3. Public site audit

### 3.1 URL and indexable inventory

| URL | Observed state | Canonical | Sitemap | Design implication |
| --- | --- | --- | --- | --- |
| https://kurashinoshirube.com/ | 200 capture/live search | canonical self | Yoast page sitemap | home; one guide; brand/policy links |
| https://kurashinoshirube.com/carry-on-suitcase-comparison/ | 200 capture/live search | canonical self | post sitemap | only published article in packet sitemap |
| https://kurashinoshirube.com/about-ad-policy/ | 200 capture/live search | canonical self | page sitemap | operator/affiliate/editorial policy |
| https://kurashinoshirube.com/privacy-policy/ | 200 capture/live search | canonical self | page sitemap | privacy and external transmission disclosure |
| other four pilot slugs | not in packet post sitemap | unknown | not listed | do not treat draft as public |

The live/public recheck on 2026-08-28 found the same home and carry-on article surfaces in search. This is not a Search Console index-status claim; only the public response/capture and sitemap listing are known.

### 3.2 Information architecture and trust

**Strengths**

- Brand, privacy, operator/advertising policy and affiliate independence are publicly visible.
- The article discloses affiliate compensation, AI assistance, exact three-model scope, no hands-on test, official sources and checked dates.
- Recommendation copy is condition-led rather than a universal winner.
- Yoast-generated canonical and sitemap exist in the capture.

**Gaps**

- Home promises movement/housework/preparedness but has only one indexed guide; empty categories imply breadth not yet delivered.
- The first view explains editorial philosophy before giving a concrete decision tool or a useful query path.
- Cookie/privacy banner dominates mobile and desktop content; action hierarchy is stronger than the editorial CTA.
- Home desktop wastes most width around a single card; article desktop text and tables are visually undersized.
- Article mobile is readable only with high scanning effort; dense cards and small type weaken conversion and comprehension.
- No public condition checker, airline rule hub, product identity explanation or visible freshness queue exists.
- Measurement values are not recorded, so popularity, high-performing content, EPC or profit must not be inferred.

### 3.3 Screenshot findings

| Viewport | Observed | Severity | V2 correction |
| --- | --- | --- | --- |
| Home 1440 | Large hero/proof area, one small guide card, long empty sections; coherent palette but inventory-density mismatch. | MAJOR | Lead with checker/hub, remove empty categories, use 1120px content grid and real asset states. |
| Home 390 | Privacy banner fills much of first screen; evidence/proof order is interrupted; small copy. | CRITICAL UX | Compact consent surface, never obscure primary content/focus; 16px body/44px targets. |
| Article 1440 | Reading column appears very narrow and small; tables/cards do not use desktop space efficiently. | MAJOR | 720px reading, 1120px comparison surface, sticky first column only within labelled region. |
| Article 390 | Long dense sequence, small text, stacked comparison and CTAs require effort. | MAJOR | Summary first, disclosure compact, dl comparison cards, progressive detail, persistent context not sticky sales CTA. |

## 4. Five-article pilot reconciliation

| Article ID | Slug | Title | Publication plan | Public observation |
| --- | --- | --- | --- | --- |
| st1703-first-suitcase-comparison | carry-on-suitcase-comparison | エースの機内持ち込みスーツケース3モデル比較｜軽さ・容量・開き方で選ぶ | BLOCKED_PENDING_EXACT_SNAPSHOT_HUMAN_CONFIRMATION | PUBLISHED_PUBLIC_CAPTURE |
| st1704-portable-power-station-guide | portable-power-station-guide | 停電対策用ポータブル電源の選び方｜容量・定格出力・持ち運びで決める | BLOCKED_PENDING_EXACT_SNAPSHOT_HUMAN_CONFIRMATION | NOT_FOUND_IN_PUBLIC_SITEMAP |
| st1704-anker-solix-c300-c800-c1000-differences | anker-solix-c300-c800-c1000-differences | Anker Solix C300・C800 Plus・C1000・C1000 Gen 2の違い | BLOCKED_PENDING_EXACT_SNAPSHOT_HUMAN_CONFIRMATION | NOT_FOUND_IN_PUBLIC_SITEMAP |
| st1704-countertop-dishwasher-for-small-households | countertop-dishwasher-for-small-households | 工事不要の食洗機を1〜2人暮らし向けに比較 | BLOCKED_PENDING_EXACT_SNAPSHOT_HUMAN_CONFIRMATION | NOT_FOUND_IN_PUBLIC_SITEMAP |
| st1704-compact-robot-vacuum-shortlist | compact-robot-vacuum-shortlist | 省スペースのロボット掃除機を条件で絞る | BLOCKED_PENDING_EXACT_SNAPSHOT_HUMAN_CONFIRMATION | NOT_FOUND_IN_PUBLIC_SITEMAP |

- Publication plan: 5/5 are `BLOCKED_PENDING_EXACT_SNAPSHOT_HUMAN_CONFIRMATION`.
- Measurement: 5/5 are `NOT_RECORDED`; `analytics_transmission_added=false`.
- Official source registry: 19 records.
- Product media registry: 18 assets; 18 await owner-local exact Rakuten evidence; missing media blocks publication under the current policy.
- **V2 action:** migrate only the published carry-on article. Preserve but defer portable power station, Anker differences, dishwasher and robot vacuum. Do not count a draft, fixture or local package as public.

## 5. External official research

| ID | Publisher | Source | Checked | Design consequence |
| --- | --- | --- | --- | --- |
| WEB-001 | 楽天グループ | 楽天アフィリエイトガイドライン — https://affiliate.rakuten.co.jp/guideline/rule/ | 2026-08-28 | 広告表示、掲載禁止面、リンク・画像の取扱いをpublication前に再確認する。ページ上の更新表示は2025-06-26。 |
| WEB-002 | 楽天グループ | 楽天アフィリエイト パートナー規約 — https://affiliate.rakuten.co.jp/guideline/terms/ | 2026-08-28 | 成果・禁止行為・変更可能性はprovider authority。設計は規約を複製せずrelease gateで再確認する。 |
| WEB-003 | 楽天グループ | 楽天アフィリエイト広告掲載基準 — https://affiliate.rakuten.co.jp/guideline/adrule/ | 2026-08-28 | 誤認を招く表示、クリック誘導の過剰化、許容されない改変を禁止する。 |
| WEB-004 | 楽天グループ | ステルスマーケティング規制の対応について — https://affiliate.rakuten.co.jp/guideline/stealth_marketing_regulation/ | 2026-08-28 | 楽天アフィリエイト投稿では広告であることが分かりやすい表示を行う。 |
| WEB-005 | 楽天Web Service | Rakuten Ichiba Item Search API version 2026-07-01 — https://webservice.rakuten.co.jp/documentation/ichiba-item-search | 2026-08-28 | 2026-07-01版をversion pin。applicationIdとaccessKeyを要求し、live requestは別承認。商品identityはitemCode等を保存する。 |
| WEB-006 | Google Search Central | Creating helpful, reliable, people-first content — https://developers.google.com/search/docs/fundamentals/creating-helpful-content | 2026-08-28 | 検索順位目的ではなく、対象読者が判断を完了できる固有価値をquality gateとする。 |
| WEB-007 | Google Search Central | Spam policies for Google Web Search — https://developers.google.com/search/docs/essentials/spam-policies | 2026-08-28 | 大量の低独自性ページを検索操作目的で生成するscaled content abuseを禁止する。 |
| WEB-008 | Google Search Central | Guidance on generative AI content — https://developers.google.com/search/docs/fundamentals/using-gen-ai-content | 2026-08-28 | AIは効率化に使えるが、正確性・品質・独自価値・人間責任を代替しない。 |
| WEB-009 | Google Search Central | Google Search Essentials — https://developers.google.com/search/docs/essentials | 2026-08-28 | crawlable links、検索語を反映したtitle/H1、technical eligibilityを守る。 |
| WEB-010 | Google Search Central | Introduction to structured data — https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data | 2026-08-28 | 可視内容と一致し、page contextに適合するmarkupだけを出力する。 |
| WEB-011 | Google Search Central | Article structured data — https://developers.google.com/search/docs/appearance/structured-data/article | 2026-08-28 | Article metadataを記事可視情報と一致させる。 |
| WEB-012 | Google Search Central | Core Web Vitals — https://developers.google.com/search/docs/appearance/core-web-vitals | 2026-08-28 | p75目標をLCP 2.5秒以内、INP 200ms以内、CLS 0.1以下とする。 |
| WEB-013 | 消費者庁 | ステルスマーケティングに関するQ&A — https://www.caa.go.jp/policies/policy/representation/fair_labeling/faq/stealth_marketing/ | 2026-08-28 | アフィリエイト表示はページ全体・位置・文字サイズ・色等から明瞭である必要がある。冒頭文言だけで常に足りるとは扱わない。 |
| WEB-014 | 個人情報保護委員会 | 個人情報保護法ガイドライン（通則編） — https://www.ppc.go.jp/personalinfo/legal/guidelines_tsusoku/ | 2026-08-28 | eventは利用目的・最小化・保管・安全管理をprivacy reviewへ接続する。 |
| WEB-015 | W3C | Web Content Accessibility Guidelines 2.2 — https://www.w3.org/TR/WCAG22/ | 2026-08-28 | WCAG 2.2 AAを目標。keyboard、focus visibility/not obscured、contrast、reflow、target size等を検証する。 |
| WEB-016 | ANA | 機内に持ち込める手荷物のサイズとルール（日本国内線） — https://www.ana.co.jp/ja/jp/guide/boarding-procedures/baggage/domestic/carry-rule/ | 2026-08-28 | 座席数別の各辺・3辺合計、身の回り品、総重量、付属品をdecision ruleにする。2026年変更を含むためeffective date必須。 |
| WEB-017 | JAL | 機内持ち込みお手荷物 — https://www.jal.co.jp/jp/ja/dom/baggage/inflight/ | 2026-08-28 | 座席数別の寸法・総重量・付属品を記録し、乗継は最も厳しい区間を採用する。 |
| WEB-018 | Peach Aviation | 機内持ち込み手荷物について — https://www.flypeach.com/lm/ai/airports/baggage/carry_on_bag | 2026-08-28 | 身の回り品込み2個、合計7kg、3辺合計115cm等をairline-specific ruleとして扱う。 |
| WEB-019 | Jetstar | 機内持込手荷物 — https://www.jetstar.com/jp/ja/help/articles/carry-on-baggage | 2026-08-28 | 運賃/option別の重量条件をvariant化し、常にstandard 7kgと断定しない。 |

### 5.1 Research conclusions

- **Rakuten:** links/images/advertising display are provider-governed and changeable. V2 stores provenance and version, prohibits arbitrary image modification, and rechecks current rules before public activation. Live API is separate from recorded-contract implementation.
- **Google Search:** people-first value, clear site focus, crawlable structure, accurate metadata and unique decision support are adopted. Scaled article generation, scraped summaries and thin affiliate pages are rejected.
- **Japanese advertising/privacy:** affiliate relationship must be clear from the whole visible context. Analytics is minimized and disabled until policy/consent review; this design is not legal advice.
- **Accessibility/performance:** WCAG 2.2 AA is a target, not a pre-implementation conformance claim. Field CWV only exists after public traffic; local budgets are supporting controls.
- **Airline rules:** carrier/effective-date/aircraft/fare/route variants matter. A single universal “機内持ち込みサイズ” value is not a safe data model.

## 6. Competitor benchmark

Competitor surfaces are used only to study market structure and UX. Their copy, code, image, score, ranking, review or product claim is not an evidence source.

| Site | Public strength | Gap/boundary for RAOS |
| --- | --- | --- |
| SAKIDORI | 広い商品カテゴリ、視覚的商品探索、短い推薦導線 | 独自実測の境界や型番同一性・更新根拠を公開面で一貫表示する余地 |
| mybest | 多数商品の比較検証、評価軸、表・ランキング | 実機試験規模では競わず、航空ルール×公式仕様の条件判定で差別化 |
| 360LiFE | 検証ラボ・雑誌編集・明確なランキング | 実機検証をしないRAOSが同じ訴求を模倣するのは禁止 |
| Picky's | カテゴリ専門性、見つけやすい比較構造 | 広告密度・長文化を避け、条件入力から短く決める |
| HEIM | 広いロングテール、商品分類、更新運用 | 量ではなくsource freshnessと差分可視化で勝つ |
| Rentio PRESS | 生活条件起点、レンタル知見、カテゴリ導線 | レンタル/実機体験を使わず、公式条件の適合判定へ限定 |
| ROOMIE | 生活場面から始まる物語、落ち着いた編集体験 | 一人称実体験は使わず、困る場面→仕様→意味の順序だけ採用 |
| 価格.com | 価格・在庫・商品網・比較機能 | 価格網羅性で競わず、楽天内のexact identityと意思決定説明へ限定 |
| Fav-Log | ニュース性・更新頻度・商品紹介 | 速報量ではなく確認日・変更履歴・向かない条件を強化 |
| GoodsPress | プロダクトニュースと雑誌的編集 | 新製品ニュースはwedge外。購入条件解決へ集中 |
| Wirecutter | 透明な推薦方針、用途別pick、affiliate independence | testなしで同等を名乗らず、推薦と事業スコア分離だけ採用 |

### 6.1 Competitive conclusion

RAOS cannot credibly beat mature competitors on hands-on test scale, product count, price coverage, editorial staffing or review volume. It can win a narrower job by combining: (1) current airline rules, (2) exact manufacturer models and variant states, (3) deterministic eligibility, (4) visible unknowns, (5) official-source freshness and (6) non-financial conditional recommendations. The product is a **decision system with articles**, not an article factory.

## 7. Evidence classification register

| Class | Statement | Evidence | Confidence |
| --- | --- | --- | --- |
| FACT | Packet authority is UNAPPROVED_DESIGN_INPUT_ONLY; no credential/external write/canonical mutation was performed. | AUD-001 | HIGH |
| FACT | Snapshot branch `codex/st1704-publish-five-articles`, HEAD `83cfa17f91dddbee2bcd4e781545fd2bb4a5bcc4`; worktree was dirty with 129 porcelain entries. | AUD-002 | HIGH |
| FACT | Root rules prohibit editing immutable baselines and require preserving unrelated dirty changes. | AUD-003 | HIGH |
| FACT | Public sitemap captured one post and three pages: home, policy, privacy. | AUD-010 | HIGH |
| FACT | Five pilot articles exist; all publication-plan states are BLOCKED_PENDING_EXACT_SNAPSHOT_HUMAN_CONFIRMATION. | AUD-015/AUD-016 | HIGH |
| FACT | All five measurement rows are NOT_RECORDED; analytics_transmission_added=false. | AUD-017 | HIGH |
| FACT | 19 official source records and 18 media asset records exist; 18 media assets await owner-local Rakuten evidence. | AUD-018/AUD-019 | HIGH |
| OBSERVATION | Desktop home has a coherent editorial palette but excessive empty horizontal/vertical space relative to one available guide. | AUD-011 | MEDIUM_HIGH |
| OBSERVATION | At 390px the privacy banner occupies a large share of the first view and separates hero promise from proof. | AUD-012 | MEDIUM_HIGH |
| OBSERVATION | Article desktop uses a narrow column and small text; mobile comparison/product content is dense and scanning cost is high. | AUD-013/AUD-014 | MEDIUM_HIGH |
| INFERENCE | Repository governance, publication, evidence and test infrastructure is more mature than public reader-value/measurement learning. | AUD-003/AUD-005/AUD-017/AUD-026 | MEDIUM_HIGH |
| HYPOTHESIS | Official-rule × product-spec decision tooling can create a stronger moat than another untested ranking article. | AUD-023/AUD-024/WEB-016..019 | MEDIUM |

## 8. Known gaps and safe defaults

| ID | Unknown | Owner / due gate | Safe default |
| --- | --- | --- | --- |
| ASM-001 | 検索需要と楽天内商品/ショップ厚みの定量値 | OWNER / P0 + Day 90 | 25本を一括作らずWave 1の6 assetsだけで検証 |
| ASM-002 | 現行GA4/Site Kit/CMP構成と有用な履歴 | OWNER / P0/P3 | 変更しない。新規third-party senderも追加しない |
| ASM-003 | Rakuten成果reportの直接article key可否 | OWNER / P5 | UNATTRIBUTED_PROGRAMとして保持しarticle confirmed rewardを作らない |
| ASM-004 | live WordPress host/version/theme/plugin/REST capability | CODEX_READ_ONLY_THEN_OWNER / P0/P3 | productionを変更せずlocal contractのみ |
| ASM-005 | first-party eventの法的適用とpolicy文言 | OWNER_OR_COUNSEL / before P3 activation | event transmission OFF、metric UNAVAILABLE |
| ASM-006 | internal labor rate | OWNER / P5 | internal planning rate ¥3,000/h、cash版を併記 |

These are evidence gaps, not implementation choices. The safe default is binding until the named evidence is obtained and recorded; Codex must not substitute a plausible value.
