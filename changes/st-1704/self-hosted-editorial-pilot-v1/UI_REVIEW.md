# ST-1704 six-pillar UI review

Status: `PASS_LOCAL_STATIC_BROWSER_REVIEW`; `HUMAN_REVIEW_PENDING`.

This review uses the repository candidate and local static fixture only. It is not a
production, staging, release, or WordPress-activation claim.

| Pillar | Current assessment | Evidence / remaining gate |
|---|---|---|
| Hierarchy | PASS in source | fixed hero copy, five-section home order, decision summary before detail |
| Content quality | PASS in contract | three-model scope, scene-led cards, fit/non-fit/caution, no overall winner |
| Responsive layout | PASS | 360/390/768/1440 and 200% text zoom had no page overflow; long-name, no-image, no-stock, unknown, no-CTA, no-related states rendered |
| Accessibility | PASS in local fixture | one H1, no heading jumps, landmarks, skip link, keyboard focus, visible outline, desktop table/mobile dl, labelled placeholder, forced colors, reduced motion |
| Trust and conversion | PASS in source | ad/test/scope/source/date visible; CTA context; finance-independent order |
| Resilience and performance | PASS for local contract | no-JS content, no page overflow, neutral placeholder, no false measured-CWV claim |

The requested GSD UI-review workflow references were not present in this workspace,
so this equivalent six-pillar artifact is maintained inside the ST-1704 slice.

Chromium matrix: Google Chrome 151.0.7922.174 driven through Playwright. At 360 and
390 px the desktop table was hidden and the `article > dl` cards were visible; at
768 and 1440 px the table was visible and mobile cards hidden. The first Tab focused
the skip link with a solid outline. Forced-colors and reduced-motion media queries
both matched, and computed root scroll behaviour became `auto`.

This is not a full assistive-technology audit or a production-performance result.
