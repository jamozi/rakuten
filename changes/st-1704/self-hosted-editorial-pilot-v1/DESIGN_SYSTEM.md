# ST-1704 editorial design system

## Intent

Preserve the existing indigo, warm clay, paper palette and Mincho display voice,
while making comparison decisions calm, explicit, and usable without JavaScript.
The source of truth for values is `assets/theme.css`; the theme contract records the
public interface.

## Tokens and layout

- Reading width: `45rem`; wide surface: `76rem`.
- Space: `0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4rem`.
- Radius: `0.35, 0.75, 1.25rem`.
- Shadows: a low-contrast card shadow and a larger floating-surface shadow.
- Article imagery: 4:3 framing. Product imagery: square box, `contain`, never crop
  or upscale.
- Desktop hero: `clamp(32rem, 56svh, 42rem)`. Mobile hero: content height with
  copy and CTA in normal flow.
- Motion: no content reveal dependency; reduced-motion disables smooth scrolling.

## Component rules

- Home order is fixed: 最新のガイド → 注目ガイド → 条件から選ぶ →
  カテゴリから選ぶ → 編集部の比較方針.
- Only published posts with an exact valid bound snapshot can appear. A neutral
  theme-owned fallback is allowed; a product or manufacturer image is not invented.
- Cards show category, title, one-sentence conclusion, updated date, and article
  type. “よく読まれている” is prohibited without real ranking data.
- The trust bar is three equal desktop cells and an explicit one-column 390 px
  layout using a selector strong enough to override WordPress block styles.
- Comparison is one semantic table on desktop and `article > dl` cards at 640 px and
  below. The first column is sticky; different cells have both a data marker and a
  visible value/evidence label.
- Product-card order is image → condition → name → benefit → recommendation reason
  → three facts → fits → non-fits → caution → checked date → official link →
  caution anchor → CTA context → affiliate CTA.

## Accessibility contract

- One H1, ordered headings, header/main/footer landmarks, and a skip link.
- Native links and details; no scripted interaction is required.
- `:focus-visible` has a 3 px visible outline. Forced-colors and reduced-motion
  modes are defined.
- Decorative images use empty alt; informative images require verified Japanese
  alt. Tables use caption, column headers, and row headers.
- No horizontal page overflow at 360, 390, 768, or 1440 px. The table's labelled
  region may scroll locally on desktop-sized table content.
- Text/background pairs and focus indicators target WCAG AA contrast.

## Content states

Long product names wrap; missing images use a neutral fixture only; missing or
unverified affiliate evidence fails public rendering; unknown facts display
`未確認`; empty related links and unpublished cards do not create fake popularity or
publication history.
