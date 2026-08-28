# UX and Design System

## 1. Experience objective

The interface should help a mobile reader answer three questions in order:

1. **私の条件は何か。**
2. **その条件に何が適合し、何が不明か。**
3. **次にどこで何を確認するか。**

Visual beauty is judged by hierarchy, clarity, consistency, restraint and trust—not by decorative density. A large block must carry decision value, proof or navigation. Empty inventory is omitted rather than styled.

## 2. Page architecture

| Page | Primary job | Primary CTA | Secondary CTA | Must not contain |
| --- | --- | --- | --- | --- |
| Home `/` | site promise and first decision path | 機内持ち込み条件を確認する | 機内持ち込みガイドを見る | empty category cards, fake popular ranking |
| Wedge hub `/carry-on/` | navigate rule/task/product jobs | checkerを使う | airline rule or comparison | generic mixed lifestyle feed |
| Guide | understand rule/task and exceptions | official ruleを確認 | tool/comparison when relevant | product grid before answer |
| Comparison | reduce exact eligible models | 楽天で型番・現在情報を確認 | official source / checker | universal winner, finance order |
| Difference | choose between defined options | 該当条件の候補を確認 | full comparison | duplicate full ranking |
| Tool | return PASS/FAIL/UNKNOWN with evidence | official sourceで最終確認 | eligible next guide/comparison | preselected carrier, hidden data send |
| Policy | explain trust and accountability | 訂正/問い合わせ | related policy | marketing superlatives |

## 3. Global navigation

### Desktop

- Left: compact wordmark “暮らしのしるべ”.
- Primary nav: `機内持ち込み` / `条件チェッカー` / `比較ガイド` / `比較方法`.
- Utility: `運営・広告` / `プライバシー`.
- No search field until at least 20 public assets and query logs show need; then add simple internal search with noindex results.
- No “家事”“備え” until validated published inventory exists.

### Mobile

- Header height 56px, wordmark and one menu button.
- Menu opens as native dialog/drawer with focus trap, escape, labelled close; content remains accessible without motion.
- Primary “条件チェッカー” appears first; policy links last.
- Cookie/consent UI may not cover the header, first form control, current focus or >35% of 390×844 viewport. Prefer a compact bottom sheet with short purpose and `設定`/`必要のみ`/`同意` equal-weight actions. This is design guidance; actual policy requires owner/legal approval.

## 4. Wireframes

### 4.1 Home — 390px

```text
┌──────────────────────────────────────┐
│ [skip]                               │
│ 暮らしのしるべ                 [☰]   │ 56
├──────────────────────────────────────┤
│ 広告を利用しています  [方針]         │ compact, always visible
├──────────────────────────────────────┤
│ OFFICIAL RULE × PRODUCT SPEC         │
│ この荷物、                            │
│ 機内に持ち込める？                    │ H1 32–36
│ 航空会社と外寸・重量を照合します。    │
│ [条件を確認する]                      │ primary 44+
│ [機内持ち込みガイド]                  │ text link
├──────────────────────────────────────┤
│ 3分で確認                             │
│ 航空会社 [選択してください ▼]         │ no default
│ 便/機材 [わからない]                  │
│ 外寸  高さ[ ] 幅[ ] 奥行[ ] cm        │
│ 合計重量 [ ] kg                       │
│ [結果を見る]                          │
│ 入力は送信・保存しません              │
├──────────────────────────────────────┤
│ まず読む                              │
│ [基本ルール] [7kg] [測り方]           │ horizontal? no; stacked cards
├──────────────────────────────────────┤
│ 条件別比較                            │
│ [3モデル比較 card]                    │ only published
├──────────────────────────────────────┤
│ 根拠が見える                          │
│ 公式情報 / 編集判断 / 確認日          │
│ [比較方法] [訂正を知らせる]           │
├──────────────────────────────────────┤
│ footer policies                       │
└──────────────────────────────────────┘
```

### 4.2 Home — 1440px

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ wordmark     機内持ち込み  条件チェッカー  比較ガイド          policy links │
├──────────────────────────────────────────────────────────────────────────────┤
│ disclosure strip                                                              │
├────────────────────────────── 1120 content grid ──────────────────────────────┤
│ ┌─────────────────────────── 7 cols ┐ ┌────────────── 5 cols ──────────────┐ │
│ │ H1 + proposition + CTA             │ │ compact checker / 3 rule inputs     │ │
│ │ no decorative stock photo          │ │ result preview / privacy note       │ │
│ └─────────────────────────────────────┘ └────────────────────────────────────┘ │
│ Three decision paths: Rule / Pack / Compare                                   │
│ Latest verified guides: one lead + up to two supporting, no empty slots       │
│ Trust method + change log                                                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Guide

```text
breadcrumb
visible disclosure
H1 + exact scope + checked date
summary box: answer / exception / official final check
problem and inputs to collect
rule sections with source chips
worked example (hypothetical label)
UNKNOWN / edge cases
buy-nothing or alternate route
next decision links
sources + change log + correction
```

### 4.4 Comparison — desktop

```text
720px intro: disclosure / H1 / exact models / no-hands-on
1120px decision summary: 3 conditional conclusions
1120px semantic table in labelled scroll region
1120px product grid: 3 cards aligned by content slots
720px detailed trade-offs / none-fit / sources / related
```

### 4.5 Comparison — mobile

```text
H1 / scope / disclosure
[条件A → model] [条件B → model] [条件C → model]
method accordion (native details; essential summary outside)
for each criterion:
  <article><h3>criterion</h3><dl>model/value/evidence...</dl></article>
for each product:
  condition → model → judgement → facts → fit → non-fit → unknown
  official source → CTA context → affiliate CTA
none-of-these block
sources/change log
```

Desktop table and mobile cards are generated from one normalized comparison matrix. They must have semantic parity; no important cell may disappear on mobile.

### 4.6 Tool result states

```text
PASS     green icon + “入力した条件では規定内” + condition list + official final check
FAIL     red icon + each failed edge/weight/count + alternatives; no celebratory CTA
UNKNOWN  amber icon + missing/ambiguous input + how to find it + no definitive claim
ERROR    neutral/red technical message + reset; never reuse stale prior result
STALE    warning that official source review is due; definitive result disabled
```

## 5. Design tokens

### 5.1 Color

| Token | Value | Use | Constraint |
| --- | --- | --- | --- |
| --color-ink | #17213A | body/headings on light | primary text |
| --color-paper | #FBF8F1 | site background | not pure white glare |
| --color-surface | #FFFFFF | cards/forms | border required when grouping ambiguous |
| --color-muted | #F1F5F4 | summary/source surfaces | not for low-contrast text |
| --color-indigo | #243B6B | primary action/brand panel | white text; verify contrast |
| --color-indigo-dark | #172A52 | hover/active/footer | white text |
| --color-accent | #A4492C | small editorial accent/warning emphasis | not sole state cue |
| --color-success | #216E5A | PASS/state | icon + text label |
| --color-warning | #8A5A00 | UNKNOWN/due | icon + text label |
| --color-danger | #A23434 | FAIL/error | icon + text label |
| --color-focus | #005FCC | 3px focus ring | offset and not obscured |
| --color-border | #D9D5CB | dividers/input/card borders | minimum visible against surfaces |

Do not introduce more semantic colors without token review. Affiliate CTA uses the same primary action color as other outbound verification; it does not receive urgency red/orange.

### 5.2 Typography

Use platform/system Japanese fonts to remove external font dependency:

```css
--font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Kaku Gothic ProN", "Yu Gothic", Meiryo, sans-serif;
--font-serif: "Hiragino Mincho ProN", "Yu Mincho", "YuMincho", serif;
```

- Body: 16px minimum, `line-height: 1.8`, letter-spacing normal.
- Small/meta: 14px minimum, `line-height: 1.6`; never use 10–12px for substantive content.
- H1: `clamp(2rem, 5vw, 3.5rem)`, line-height 1.25; Japanese phrase boundaries controlled with `<span>` only for meaningful chunks.
- H2: `clamp(1.5rem, 3vw, 2.25rem)`, 1.35.
- H3: `1.25rem`, 1.5.
- Body serif is not default. Serif is reserved for brand display headings; long comparison/body text is sans for clarity.
- No more than three major type scales in the first view.

### 5.3 Layout

- Reading width: `45rem` (720px).
- Wide comparison/tool surface: `70rem` (1120px).
- Max shell: `80rem` (1280px) including gutters.
- Mobile gutter: 16px; ≥768: 24px; ≥1280: 32px.
- Grid: 12 columns desktop, 8 tablet, 4 mobile; content order independent of visual columns.
- Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64, 96px.
- Radius: 6, 12, 20px. Shadows minimal; borders/spacing define grouping.
- Breakpoints: 480, 768, 1024, 1280px. Components respond to container where practical.
- Touch target design target: at least 44×44px. WCAG exceptions do not justify smaller primary controls.

## 6. Component hierarchy and contracts

| Component | Required content/order | States | Failure behavior |
| --- | --- | --- | --- |
| DisclosureBar | affiliate relationship + finance independence + policy link | default/PR relationship variant | always visible; never collapse essential message |
| DecisionHero | eyebrow, H1, one-sentence promise, primary/secondary CTA | tool available/unavailable | unavailable CTA links to guide, not dead control |
| ConditionForm | labels, unit, help, validation, submit, privacy note | empty/valid/invalid/submitting/result | no carrier default; error bound to field and summary |
| ResultPanel | PASS/FAIL/UNKNOWN, reasons, source/effective/checked, next step | pass/fail/unknown/stale/error | stale disables definitive result |
| GuideCard | type, title, decision value, checked/updated date | published only | omit, no placeholder for unpublished article |
| TrustStrip | official facts/editorial judgement/checked dates | normal | not statistics or fake counts |
| SourceChip | source class, publisher, checked date, external label | fresh/due/stale | stale warning, link retained if valid |
| ComparisonMatrix | caption, row/column headers, values, evidence/unknown | desktop table/mobile dl | single normalized data source |
| ProductCard | fixed order specified in editorial system | exact/no image/no offer/unknown/stale | identity unresolved blocks CTA; no invented image |
| AffiliateCTA | context sentence + exact outbound link + external indication | enabled/disabled/unavailable | no destination fallback or generic search unless explicitly designed |
| ChangeLog | material date/change/source impact | 0/n entries | display at least checked date if no change entries |
| CorrectionLink | issue/report path | available | cannot be hidden behind login |
| ConsentSurface | short purpose/actions/settings link | unconfigured/required/accepted/rejected | must not obscure focus/content; no dark pattern |

## 7. CTA and advertising design

### Placement rules

- Primary affiliate CTA appears only inside an exact product card after fit/non-fit/caution and near the closing conditional summary.
- Maximum two affiliate placements per product per article unless UAT and one-variable experiment approves another placement.
- No sticky affiliate CTA, interstitial, popup, countdown, animated urgency, forced click or disabled-content gate.
- “楽天市場で現在の価格・在庫・カラーを確認する” is the default action label where those items are genuinely checked at destination.
- Official source is a separate link, visually distinct but not de-emphasized below readability.
- On FAIL/UNKNOWN tool state, do not show “buy now”. Offer a rule/measurement/alternative path.

### Disclosure copy contract

Compact default:

> このページには広告リンクがあります。報酬は商品の選定・掲載順に影響しません。実機試験を行っていない比較では、公式情報と編集判断を分けて表示します。

The exact public wording requires owner/legal/provider review before P3. The design mandates prominence and content, not a legal conclusion.

## 8. Responsive rules

- 320px is not a primary design viewport but content must reflow without horizontal page scroll at 320 CSS px / 400% equivalent where applicable.
- Required test viewports: 390×844, 768×1024, 1440×900. Add 360px regression for existing contract continuity.
- Desktop-only table is permitted only when mobile `dl` has exact semantic parity and one source matrix generates both.
- Card grids: 1 column <768, 2 at 768–1023 if content slots align, 3 at ≥1024 for exactly three models.
- Never place model facts in tooltip/hover only.
- Long Japanese model names wrap; IDs/model numbers use `overflow-wrap:anywhere` only where needed, not letter-by-letter Japanese breakup.
- Images use `object-fit: contain`, intrinsic width/height/aspect ratio and no crop/upscale. Layout space is reserved to prevent CLS.
- Navigation and consent surfaces are keyboard operable and do not obscure focus.

## 9. Accessibility acceptance

WCAG 2.2 AA is the target. Passing automated tests is not a conformance claim.

| Area | Acceptance |
| --- | --- |
| Structure | one H1, ordered headings, header/nav/main/footer, skip link, article/section labels where meaningful |
| Keyboard | all actions reachable in logical order; no trap except valid modal with escape/return focus; first focus visible |
| Focus | 3px focus-visible ring, ≥2px offset where possible; not hidden by sticky header/consent surface |
| Contrast | normal text ≥4.5:1, large ≥3:1, UI/focus/non-text ≥3:1; state not color-only |
| Reflow/zoom | 200% text and 400%/320px equivalent without loss; local labelled table scroll allowed, page scroll not |
| Forms | persistent labels, units, instructions before input, field error + summary, programmatic associations |
| Tables | caption, scope/headers, row labels; mobile semantic equivalent; no layout table |
| Images | empty alt for decorative; verified concise Japanese alt for informative; product name alone if image adds no more |
| Motion | no content reveal dependency; reduced-motion disables smooth/animated changes; result announced politely |
| Screen reader | tool status via `aria-live=polite`; errors not repeatedly announced; outbound link purpose clear |
| Target size | 44px design target; spacing prevents adjacent accidental activation |
| Language | `lang=ja`, abbreviations explained, model names preserved, natural Japanese punctuation/line breaking |

Required tools/evidence: axe or equivalent automation, keyboard recording, browser accessibility tree/screen reader smoke, contrast calculation, visual screenshots. Human review remains required.

## 10. Performance and resilience budgets

### Budgets

| Budget | Target | Failure response |
| --- | --- | --- |
| Field CWV p75 | LCP ≤2.5s, INP ≤200ms, CLS ≤0.1 on mobile and desktop when enough data | P4 repair; no claim before field data |
| Article JS | ≤60KB gzip first-party; core article content works without JS | block package if exceeded without approved exception |
| CSS | ≤40KB gzip critical/editorial bundle | remove unused/global styles |
| Page transfer | article ≤1.2MB; home/tool initial ≤800KB | image/font/script reduction |
| Fonts | no external font request | use system stack |
| Images | responsive size, WebP/AVIF where provider/license allows, intrinsic dimensions | omit/placeholder if compliant asset unavailable |
| Third party | none before consent/approval; affiliate link navigation is user action | block unapproved sender |
| No-JS | article, source, comparison and basic tool fallback remain understandable | block critical content dependency |

### Resilience states

- Source unavailable: show last verified checked date only if within SLA; otherwise UNKNOWN/HARD_STALE.
- Rakuten unavailable: article remains useful; CTA state “現在の販売情報を確認できません”. Do not redirect to generic unbound search.
- Product image unavailable: neutral product-name/shape-independent placeholder, not a generated likeness.
- Analytics unavailable: content operates normally, metrics UNAVAILABLE.
- Consent rejected: no nonessential event; affiliate outbound link remains ordinary link where policy permits, with no hidden tracking enrichment.
- CSS/JS failure: semantic content order remains usable.

## 11. Visual QA matrix

| Page/state | 390 | 768 | 1440 | Special |
| --- | --- | --- | --- | --- |
| Home with 1 published guide | required | required | required | consent accepted/rejected/unconfigured |
| Home with 0/3 guides | required | spot | required | no empty fake cards |
| Tool empty/PASS/FAIL/UNKNOWN/STALE/ERROR | all states | PASS/UNKNOWN | PASS/FAIL | keyboard + live region + no network |
| Guide long source titles | required | spot | required | 200% zoom |
| Comparison 3 models | required mobile dl | table/dl breakpoint | semantic table | long model, unknown, no image, no CTA |
| Policy | required | spot | required | link focus/heading order |
| Forced colors | tool + comparison | — | — | state remains distinguishable |
| Reduced motion | home/tool | — | — | no smooth/reveal dependency |

Visual review severity:

- **Critical:** misleading result/CTA, hidden disclosure, inaccessible primary task, content/focus obscured, data parity loss.
- **Major:** hierarchy, readability, overflow, touch target, inconsistent state that materially increases decision effort.
- **Minor:** polish not affecting understanding/action.

P2 exit requires critical 0 and major 0 in representative matrix. Minor issues may be documented only when not violating token/component contract.

## 12. Design decision acceptance

- Home’s first substantive interaction is the checker or rule path, not an abstract editorial manifesto.
- No empty “家事”“備え” category card or unpublished placeholder.
- At 390px, primary message and CTA are visible without a consent surface blocking them.
- Comparison value and evidence are equivalent across desktop/mobile.
- Every product card shows fit, non-fit, caution/unknown and checked date before affiliate CTA.
- Reader can complete rule checking and article reading with JS and analytics disabled.
- Components are distinct enough for implementation without choosing a new style variant.
