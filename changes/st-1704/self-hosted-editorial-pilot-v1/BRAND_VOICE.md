# ST-1704 brand voice

## Voice

Calm, specific, and reader-led. State what can be verified, identify editorial
judgement as judgement, and name the cost of each choice. Avoid performative
certainty and sales pressure.

## Reusable formulas

- Story: `困る場面 → 選ぶ基準 → 公式仕様 → 生活上の意味`.
- Recommendation: `条件なら商品 → なぜなら事実 → これは編集判断`.
- Trade-off: `得られる便益 → 失うもの／未確認 → 向かない人`.
- CTA: `確認する価値 → 外部で確認できる項目 → 中立的な行動文`.

For the suitcase cards, the CTA formula resolves to a short explanation followed by
“楽天市場で現在の価格・在庫・カラーを見る”. The official-specification link
and the caution anchor remain separate actions.

## Fact and judgement labels

- A — 公式仕様: manufacturer, airline, or other primary source.
- B — 第三者実測: reproducible measurement with a bound evidence record.
- C — 利用者の傾向: a recurring pattern across multiple reviews or usage records.
- D — 編集部の判断: a bounded recommendation or hypothesis built from facts.
- UNKNOWN — 未確認: no adequate evidence; display it instead of filling a value.

B and C are forbidden without their corresponding evidence record. A specification
does not become a test result, and a recommendation does not become a product fact.

## Prohibited claims

Do not use “絶対”, “最強”, “最安”, “これを選べば間違いない”, urgency, scarcity,
unverified popularity, an award, an overall winner, or a market-wide ranking when the
scope is only three verified ACE models. Do not imply hands-on use when no physical
test was performed. Inventory and colours are observation-time details, never fixed
article facts or recommendation-order signals.

## Human review checklist

- Does the title and opening disclose the exact comparison scope?
- Are model number, dimensions, capacity, mass, expansion conditions, and ANA caveat
  traceable to a current primary capture?
- Are fact, measurement, user pattern, judgement, and unknown visibly distinct?
- Does every recommendation name both the fit and the non-fit?
- Is “実機試験なし” visible before the conclusion?
- Is the ad disclosure always visible, with only policy detail collapsed?
- Does every CTA explain the verification value and avoid pressure?
- Is Japanese natural when read aloud, without repetitive spec-first openings?
- Are image, affiliate URL, official link, article, product, and placement bindings
  exact and fail-closed?
- Are mobile, keyboard, focus, contrast, alt, and overflow checks complete?

Status for this implementation: `HUMAN_REVIEW_PENDING`. This status does not loosen
the publication blocker.

## AI correction rate

Measure after a human copy review:

`AI correction rate = materially human-edited AI-originated sentences / all reviewed AI-originated sentences × 100`.

A material edit changes a fact, judgement boundary, recommendation, trade-off,
naturalness, or CTA meaning. Punctuation-only and formatting-only changes are
excluded. Record numerator, denominator, reviewer, timestamp, and review version;
do not infer the rate before human review.
