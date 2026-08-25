# Revenue experiment runbook for the five-article pilot

This runbook begins only after a human publication action has produced one exact,
indexable final URL and the article's public verification has passed. It creates no
tracking, publication, content, recommendation, provider, or finance authority.
Incremental external spend is fixed to zero.

## Measurement clock and evidence

- The article's successful final public action is `T0`. Record the exact 14-day
  period beginning at `T0`; collect delayed Search Console data for that same period
  after the provider has made it available.
- Store observations only through the owner-private V2 interface documented at
  `../affiliate-learning-v2/README.md`. Never write observations into the tracked
  V1 compatibility template.
- Accept article views or outbound affiliate clicks only when the existing Site Kit
  consent/configuration and the metric provenance are verified. Otherwise record
  `UNAVAILABLE`, not zero, and do not add a new tracking sender for this pilot.
- Before article-level revenue is used, compare one minimal sanitized Rakuten export
  with its source hash, period, currency, row count, outcome totals, and provider
  total. Direct article attribution requires a provider-supplied verifiable key.
  Without it, preserve the reward only as an unattributed program total.
- Pending or immature outcomes remain nonfinal. Confirmed reward metrics remain
  `UNAVAILABLE` until the cohort and provider confirmation period are mature.
  The normal operating expectation is to wait through the end of the following
  month before treating an outcome as mature; the provider report remains the
  authority if its confirmation timing differs.
- Operational metrics are direct confirmed reward per content hour and confirmed
  reward minus incremental external cost. Formal labor-inclusive profit remains
  unavailable until the human reviewer and hourly-cost decision is recorded.

## One-variable decision order

Only the first applicable row is eligible for a proposal. Every change remains a
new human-reviewed successor snapshot; this runbook never edits a live article.

| Observed bottleneck | Next proposal | Minimum evidence | Keep rule | Stop or extend rule |
| --- | --- | --- | --- | --- |
| Low search visibility | Change either title or meta description to the observed search intent | 28 days and 200 impressions per compared variant | organic clicks or CTR improves at least 20%, and average position worsens by no more than 2 | any index/canonical defect rolls back; insufficient sample extends unchanged for 30 days |
| Article views but few affiliate clicks | Change one CTA label or one allowed placement | verified click measurement, 500 impressions, and 20 clicks for the evaluated variant | retain only after the predeclared affiliate-click metric improves with no disclosure, destination, or link-health defect; this runbook imposes no unapproved percentage threshold | unavailable measurement blocks the experiment |
| Affiliate clicks but no confirmed outcome | Recheck audience condition and product fit after maturity | verified clicks and a mature provider confirmation period | proceed only when the reviewed condition/product proposal has primary evidence | do not reorder products by commission, EPC, RPM, revenue, or profit |
| Confirmed reward exists | Add at most two query-led comparison/difference/model articles | verified Search Console demand, a mature confirmed outcome, and complete attribution classification | the two successor proposals pass the normal primary-source, link, image, snapshot, and human publication gates | do not infer article-level reward from an unattributed program total; further expansion remains blocked |

Sticky CTAs, popups, click requirements, affiliate redirects, and automatic live
changes are forbidden. Finance may decide whether to continue producing a topic; it
never changes the recommendation order inside an article.

## Expansion boundary

Do not begin the 30–45 article portfolio, YouTube, ROOM, SNS, a new paid provider, or
a new plugin until all five final URLs are indexable, critical defects and broken
affiliate links are zero, and Rakuten confirmed outcomes have been reconciled at
least twice. Missing data is a reason to extend the observation period, not evidence
of zero demand or zero reward. The at-most-two successor articles in the table are
the only pre-portfolio exception and still require an observed confirmed outcome and
verified Search Console demand.
