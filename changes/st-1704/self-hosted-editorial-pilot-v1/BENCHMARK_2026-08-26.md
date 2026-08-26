# ST-1704 media benchmark — 2026-08-26

## Scope and method

This is an implementation benchmark, not a licence to reproduce a competitor's
copy, CSS, imagery, ranking, score, or information architecture. Observations were
made on 2026-08-26 (Asia/Tokyo) in a real Chromium browser at 1440 px desktop and
390 px mobile widths. The requested page and each site's home were checked. A score
is a qualitative 1–5 assessment of the visible surface only; `U` means that the
property could not be verified from the inspected surface. No competitor screenshot
is stored in the repository.

Performance is limited to perceived loading behaviour during the observation. It is
not Core Web Vitals, field data, or a lab benchmark. Accessibility scores are a
surface review and are not a conformance claim.

## Observation log

| Site | Home observation | Related/list/article observation | Viewports | Page types | Unknowns |
|---|---|---|---|---|---|
| SAKIDORI | <https://sakidori.co/> | <https://sakidori.co/article/20132> | 1440 / 390 | home / article | analytics, editorial conversion data |
| mybest | <https://my-best.com/> | <https://my-best.com/15> | 1440 / 390 | home / comparison article | ranking weights beyond visible explanation, analytics |
| 360LiFE | <https://360life.shinyusha.co.jp/> | <https://360life.shinyusha.co.jp/articles/-/344> | 1440 / 390 | home / tested article | internal test records, analytics |
| Picky's | <https://pickys-life.jp/> | <https://pickys-life.jp/carry-on-suitcase/> | 1440 / 390 | home / comparison article | analytics, field accessibility audit |
| HEIM | <https://heim.jp/> | <https://heim.jp/magazine/6130466> | 1440 / 390 | home / article | current maintenance state beyond visible date, analytics |
| Rentio PRESS | <https://www.rentio.jp/matome/> | <https://www.rentio.jp/matome/category/travel/suitcase/> | 1440 / 390 | home / category list | one canonical comparison article was not fixed for this review |
| ROOMIE | <https://www.roomie.jp/> | <https://www.roomie.jp/2023/09/1043121/> | 1440 / 390 | home / story-led article | comparison-table behaviour, analytics |
| 価格.com | <https://kakaku.com/> | <https://kakaku.com/ranking/houseware/0025_0005/0003/153650106/> | 1440 / 390 | home / ranking list | editorial story intent, analytics |
| Fav-Log | <https://nlab.itmedia.co.jp/fav/> | <https://nlab.itmedia.co.jp/fav/articles/3935874/> | 1440 / 390 | list home / article | product-test provenance beyond visible surface, analytics |
| GoodsPress | <https://www.goodspress.jp/> | <https://www.goodspress.jp/features/717874/> | 1440 / 390 | home / feature article | analytics, formal accessibility audit |

## Twelve-axis qualitative matrix

`1` is weak on the observed surface and `5` is a strong, repeatable pattern. The
scores are evidence pointers for design choices, not a market ranking.

| Site | Visual hierarchy | Navigation | Body typography | Article/card system | Comparison | Product + CTA | Author/source | Ad clarity | Mobile + a11y | Perceived speed | Japanese + story | Recommendation + trade-off |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SAKIDORI | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 3 | 4 | 3 | 4 | 3 |
| mybest | 4 | 5 | 4 | 5 | 5 | 5 | 4 | 4 | 4 | 3 | 4 | 5 |
| 360LiFE | 4 | 4 | 4 | 4 | 5 | 4 | 5 | 4 | 4 | 3 | 4 | 5 |
| Picky's | 4 | 4 | 4 | 4 | 4 | 5 | 4 | 4 | 4 | 3 | 5 | 4 |
| HEIM | 3 | 4 | 4 | 4 | 4 | 4 | 3 | 3 | 4 | 4 | 3 | 3 |
| Rentio PRESS | 4 | 5 | 4 | 4 | 3 | 5 | 4 | 4 | 4 | 4 | 4 | 4 |
| ROOMIE | 5 | 4 | 5 | 4 | 2 | 3 | 4 | 4 | 5 | 4 | 5 | 4 |
| 価格.com | 3 | 5 | 3 | 4 | 5 | 5 | 2 | 3 | 3 | 3 | 2 | 4 |
| Fav-Log | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 3 | 4 | 3 | 4 | 3 |
| GoodsPress | 5 | 4 | 5 | 4 | 2 | 3 | 4 | 4 | 4 | 3 | 5 | 3 |

## Evidence behind the useful patterns

- Visual: ROOMIE and GoodsPress use a strong editorial image and calm reading
  rhythm. RAOS adopts hierarchy and whitespace, not their assets or layout code.
- Recommendation: mybest and 360LiFE make the evaluation basis visible near the
  decision. RAOS answers with evidence-level labels and a three-model scope note.
- Japanese and story: Picky's and ROOMIE begin from a reader situation. RAOS gives
  each suitcase a different scene-led opening while keeping facts separate.
- CTA: Rentio and product-led publishers explain the action near the link. RAOS adds
  a short `cta_context`, while refusing urgency, lowest-price, and scarcity claims.
- Trust: tested-media surfaces make authorship or test basis conspicuous. RAOS shows
  author, fact checker, checked date, ad status, comparison scope, and “実機試験なし”
  before the decision summary.
- Mobile: the strongest surfaces collapse dense desktop structures into readable
  cards. RAOS retains a semantic desktop table and uses `article > dl` on mobile.
- Dense ranking pages help known-item scanning but are not the RAOS voice. RAOS keeps
  fewer options, explicit exclusions, and visible cautions.

## RAOS public baseline, kept separate from repository candidates

Observed on 2026-08-26 in the same browser:

| Public surface | Direct observation | Classification |
|---|---|---|
| <https://kurashinoshirube.com/> | The repository child-theme candidate could not be identified as active from the public surface. | production observation |
| home hero, 390 px | The visible hero occupied about 574 px before the following content, making the initial decision path feel oversized. | production observation |
| home trust bar, 390 px | Computed layout remained a three-column grid, producing three narrow columns. | production observation |
| <https://kurashinoshirube.com/carry-on-suitcase-comparison/> | Returned a public 404 during the observation. | production observation |

The local theme, preview fixture, generated draft HTML, and tests are repository
candidates only. They are never described as the production display.

## Gap statement used by the implementation

| Area | Baseline gap | Implemented principle |
|---|---|---|
| Look | oversized mobile hero; thin trust columns | bounded desktop hero, content-driven mobile hero, one-column trust bar |
| Product recommendation | decision rationale was not consistently surfaced | benefit, recommendation reason, fit, non-fit, caution, evidence label |
| Japanese | repeated spec-first prose | scene → fact → judgement → trade-off |
| Story | same rhythm across products | a distinct use situation for each model |
| CTA | action lacked a consistent verification reason | explain why to check, then exact inventory/price/colour CTA |
| Trust | source class and “not tested” were easy to miss | author/fact check/date/scope/ad/test status before the decision |
| Measurement | no accepted event design for the new surfaces | semantic attributes only; `analytics_transmission_added=false` |

## Post-deployment visual re-audit

The first implementation met the structural checklist but did not meet the visual
quality goal. A second browser review was therefore performed on 2026-08-27
(Asia/Tokyo) at 1440 × 900 and 390 × 844. Competitor captures remained in a
temporary directory outside the repository. This section supersedes the earlier
visual conclusion; it does not change the evidence or publication contracts.

### What the first benchmark missed

- It scored broad categories but did not record composition, crop choice, type
  scale, line breaks, information density, or the relationship between the hero
  image and the editorial promise.
- The implementation copied the idea of a large image-led hero without asking
  whether the image proved anything. The fabric photograph did not communicate
  product comparison, first-party evidence, or a reader situation.
- The desktop heading column was too narrow and split the Japanese compound
  `道具` across lines. The header wordmark and long policy navigation competed with
  the hero. The three trust statements read as a large bordered table.
- The public site had no eligible posts. Rendering latest, featured, and three
  category shelves as empty states produced a template-shaped page rather than an
  editorial front page.
- Accessibility checks found two skip links: the parent theme link and a child
  theme duplicate. Passing heading and overflow checks did not make the visual
  result acceptable.

### Current competitor patterns, abstracted rather than copied

| Surface | Observed visual strength | Reusable principle |
|---|---|---|
| [SAKIDORI](https://sakidori.co/) | compact grid, consistent image ratios, visible category labels, high article density | show what can be read immediately; let content imagery carry the page |
| [mybest](https://my-best.com/) | the hero shows a real test environment and leads directly to search and categories | use imagery as evidence, not decoration; expose the primary finding path in the first view |
| [360LiFE](https://360life.shinyusha.co.jp/) | unmistakable test-media identity, magazine brands, product collage, question-led search | make the editorial method a visual brand asset |
| [ROOMIE](https://www.roomie.jp/) | asymmetrical lead story, calm whitespace, varied image scale, restrained chrome | create rhythm with one lead and supporting stories instead of equal boxes |
| [Picky's](https://pickys-life.jp/) | category meaning is communicated by the hero collage before body copy | make the subject matter legible without asking the reader to decode abstract copy |

The competitors are not treated as universally attractive. SAKIDORI and Picky's
also show dated or busy patterns. Their advantage over the first RAOS result is
coherence: the logo, imagery, density, and finding path all describe the same kind
of product media.

### Design knowledge translated into constraints

- [Nielsen Norman Group's visual-design principles](https://www.nngroup.com/articles/principles-visual-design/)
  are applied through one dominant headline, one secondary proof panel, and no more
  than three major type scales in the first view. Scale, contrast, spacing, and
  grouping must all express the same hierarchy.
- [NN/g's signal-to-noise guidance](https://www.nngroup.com/articles/signal-noise-ratio/)
  rules out a large decorative photograph. A large element must communicate either
  an available guide, an actual comparison process, or the editorial standard.
- [Baymard's homepage research](https://baymard.com/homepage-and-category-usability/benchmark/page-types/homepage)
  treats the homepage as a navigational anchor. Category, search, and curated paths
  should be obvious, but unavailable paths must not be rendered as fake inventory.
- [W3C Japanese Layout Requirements](https://www.w3.org/TR/jlreq/)
  informs explicit phrase-boundary line control for the hero. A brand-critical
  compound must not be split merely to fill a fixed container.
- [Digital Agency spacing guidance](https://design.digital.go.jp/dads/foundations/spacing/)
  is applied as a small spacing scale that communicates grouping. Whitespace is not
  used to compensate for missing content.

### Revised home art direction

The repository candidate is now an editorial-utility front page:

1. Compact masthead with a theme-owned mark and reduced wordmark scale.
2. Light, text-led hero with fixed phrase-boundary headline wrapping.
3. Dark editorial-standard panel that visualises the three comparison rules; no
   stock hero image or invented product evidence.
4. Slim numbered trust strip instead of a shadowed three-column promise box.
5. Featured content is omitted when no eligible published guide exists. Category
   emptiness is stated once rather than repeated in three cards.
6. Real guide cards remain the visual centre once eligible public posts exist.

This direction keeps the palette, Mincho headings, fixed hero copy, disclosure,
and fail-closed publication behaviour. It deliberately does not claim that design
alone can equal a mature competitor while the public content inventory is empty.
