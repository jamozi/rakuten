# ST-1003 V2 — recorded comparison and product components

## Local result

V2 adds real server-renderable React components for `UI-C032` ProductCard,
`UI-C033` ComparisonTable, and `UI-C036` UnknownValue, plus an explicit
Trade-off section. The components use native headings, table caption,
column/row `scope`, definition lists, a keyboard-focusable horizontal-scroll
region, and responsive product cards.

The only renderable values are a fixed, visibly labelled recorded-synthetic
fixture. It contains no real product, recommendation, identity, price, stock,
image, link, CTA, provider, measurement, or finance data. Unknown remains
visible as `不明（一次情報未確認）`; it is never converted to zero, an empty
string, or an inferred value. The fixture is not mounted on the recorded public
article because ST-0904 supplies no comparison rows or product cards.

## Dependency and authority boundary

ST-0803 remains the validator for future value-bearing comparison input. This
Story does not invent an ST-0803-to-public mapping or promote its synthetic
receipt to publication evidence. A future owner-approved public projection can
replace the fixture through a new version without weakening this component
semantics.

No route, client component, click handler, raw HTML, network, database,
analytics, publication, staging, release, or Production action is added. Local
TypeScript, Next build, static semantic checks, and ST-0803 regression are not
formal TST-022 or manual TST-024 evidence.
