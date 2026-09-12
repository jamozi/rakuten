# Guide and policy changes — 2026-09-13

以下は作業中の確認履歴を含みます。現在の候補・統合後の検証結果・残件は [最終検証](verification.md) と [136項目の進捗](progress-evidence.v1.json) を参照してください。過去の候補の中断・未統合記述を現在の状態として使用しません。

Scope: PG262–266, PG010, PG120, PG003 text; G08/G09/G15. Local source work only; no publication, external writes, mail tests, or commits.

## Rendering and source ownership

`render_guide` builds the five current guides from catalog facts and summaries; most content in the legacy five HTML templates is not emitted. New reader content therefore lives in `python/raos/application/editorial/site_guide_improvements.py`, integrated by the root agent using `render_guide_intro(stage, products)` after the model index and `render_model_handout(stage, product)` inside each model section. Existing model anchors and legacy evidence locators remain. The legacy templates were deliberately not replaced with another copy of generated prose. Policy pages use their existing HTML templates directly.

Catalog changes are in `guide-catalog-updates.json`: merge product fields by product_id, preserving all other catalog data. The catalog worker owns the merge. No main catalog/registry/theme changes were made by this worker.

## Addressed

- PG262-01: live official NP-TSP1 manual P9901-17D10, printed p.15, separately states combustible clearance 11.5cm and installation total height72cm. 120mm is 720−600, a derived input condition, not manufacturer wording or rounded manufacturer clearance. PG262-02: three-direction original explanatory HTML diagrams with numbered measurements, scale disclaimer, notes for opening envelope and hose route, paper measurement memo. PG262-03 runtime boundary/units remains root verification.
- PG263-01: each current model has an ordered water-source → fill-stop signal → drain route diagram sourced to its own facts. No unknown dimensions filled. PG263-02: added NP-TSP1 faucet-specific branch requirements from printed pp.15,18–22, separate from tank operation. Existing SS-MA251 branch requirements retained. PG263-03: normal fill prohibition separated from tank-cleaning exceptions, with cross-links.
- PG264-01: immediate four-column ordinary detergent answer. PG264-02: live mini color manual p.14 confirms powder/liquid/gel/tablet; former type UNKNOWN resolved. Individual tablet count/size remains UNKNOWN because p.14 does not specify it. PG264-03: model-specific insertion locations, official figure locators, clear prohibition of hand-washing detergent. Existing model-specific prohibited-material details retained. A newly invented product exterior photo was not used.
- PG265-02: mini color printed pp.20–22 visually confirmed and concrete filter/tray and nozzle removal/wash/refit steps added. PG265-03: per-model printable □ checklists in keyboard-operable details, printable after opening the native details section; no measured duration claims. PG265-01 title/frequency layout integration is owned by root/catalog worker.
- PG266-01: prominent explicitly fictional arithmetic example230Wh2.5L30yen/kWh300yen/m³5yen/detergent30cycles=12.65yen/cycle379.5yen/month; no input required. PG266-02 unknown energy cannot become zero or a total. PG266-03 current/retained grouping and calculator tests are root integration.
- PG010-01: distinguish advertising purchase/image links from ordinary manufacturer references; no hard-coded ad article count. PG010-02: no new personal/team/qualification claims. PG010-03: correction request fields provided; no deadline or verified delivery claim added.
- PG120-02/03: short three-point overview and evidence use table, clarifying traceable third-party measurements vs impressions/candidate discovery. PG120-01 mechanical identity/price expiration enforcement remains root work.
- PG003-02/03: standard cookie expiry no longer implies verified site configuration; unknown server/log/contact retention explicitly not guessed; image fetch is not proof of conversion measurement. PG003-01 consent/withdrawal statements require root network/runtime validation.

## Fresh official evidence

Read-only retrieved 2026-09-13. Temporary local copies and screenshots are under `/tmp/raos-guides-0913/`, not publication artifacts.

- https://www.data.thanko.jp/download/manual/tdws25s_man_web_01.pdf — 32 pages; visual p.14 detergent type/3–5g/door insertion illustration, pp.20–21 filter and mesh tray, p.22 upper/lower nozzle. mini Plus instructions were not substituted.
- https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/000/370/092/000000000370092/np-tsp1.pdf — current PDF12 spreads, version P9901-17D10; printed p.15 and pp.18–19 read as text. 115mm and720mm both present. Web open failed safe-open; direct read-only official HTTPS download succeeded, PDF parsed locally.
- https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/000/379/872/000000000379872/np-tml1.pdf — P9901-20V10, printed p.6 visual/text checked, explicitly covers NP-TML1 and NP-TMLK1. Detergent falls into tub from basket front; normal2g and3cm limit retained.
- https://www.siroca.co.jp/im/ss-ma251.pdf — printed p.14 text and screenshot checked: powder/liquid4g; tablet1 on mesh tray; high-temperature rinse requires no detergent.

## Validation / remaining checks

`uv run ruff format` and `uv run ruff check` helper passed. `uv run pytest tests/purchase_support/test_site_guide_improvements.py -q`: 4 passed. These verify no-input arithmetic, unknown conditions not guessed, escaping/model amount not inferred, and inert publishable handout markup (no input/form). Integration, representative mobile/desktop display, print layout, keyboard controls, source anchors and root-selected regressions remain the parent task's checks.

External pending: email actual receipt/reply/authentication (no sends authorized); GA4 runtime consent/network and real server retention settings; production readback/publication only after user approval. Missing mini color tablet count/size and unpublished operator staffing/history were not invented. The follow-up below completes the material/reason tables and the remaining three current-model cleaning procedures.

## Remaining D implementation completed (same local task)

PG264-03 now has inert, per-exact-model material / prohibition-reason / exception tables in `render_model_handout('detergent', product)`. Seven material groups retain distinct80℃/75℃/65℃soft/60℃low-soft boundaries. Where the Siroca/THANKO manuals list a material without an individual reason, the table says the reason is unprinted instead of borrowing Panasonic wording. mini Plus does not receive mini color's table.

PG265-02: fetched and read all remaining current-model instructions. NP-TML1/NP-TMLK1 activity guide printedpp16–18: basket grooves faceback, filterright/no-gap, nozzle pullstraightup/refitclick/free-turn, tank/filter and lattice/drain/heater-area cleaning. SS-MA251 pp17–20: basket hook removal, counterclockwise filter/tray removal, separate upperfilter/two tabs, reassembleclockwise to mark; nozzle two tabs; ソフト+おいそぎ3seconds for tubcycle, dedicated4g. NP-TSP1 activity guide printedpp22–25 (tank-fill section): filterA/B sequence/clickrefit, residuals afteroperation require A that time; weekly assumes2uses/day. Draincover monthly with neutral detergent rinsed off; tub2–3times/month with doubleordinarydetergent; tankcleaning60g39℃max,60min soak, お手入れ5sec + 一時停止/スタート, repeatwater-rinse. Relevant button names were visually checked in PDF figures. No tankcleaning operation is generalized to ordinary fill.

Fresh evidence files use the official URLs already above plus `https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/003/059/015/000000003059015/np-tsp1_guide.pdf`. Three guide PDFs were downloaded2026-09-13; printed page numbers (not PDFspread indexes) are stored in locators. Material sources: NP-TMLK1 guidep7, NP-TSP1 guidep9, SS-MA251p8, mini colorp13; mini colorp18–19 visually rechecked.

A prior mini color claim prohibiting dry-only for75℃+ plastic was not supported by p13/18/19; removed in completion delta. p13 says75℃+usable; table still requires the dishmaker's labeling. Prior blanket noeverytimeNP-TSP1 maintenance wording was narrowed using guidep23 residual exception.

`guide-catalog-completion-updates.json` contains the four-product guide-only completion merge for root; it replaces old maintenance blocks to avoid conflicting frequency prose. Main catalog not edited by this worker. Scoped tests now8passed (guide5 + progress3); Ruff passes. Integration/localdisplay/publication remain separate.

Progress semantic correction: Q16 is safe publication/restoration, not contact-mail testing; all136titles matched against original audit. G18 now correctly records existing-page priority/new-articleconditions rather than inventing GSC as its prerequisite. Contact draft remains PG010-03 only. Updated progress XLSX was regenerated without changing the original workbook.

## Integrated candidate evidence and subsequent shared-theme correction

The D completion merge is now in the generated candidate `23e2e8ab7b99746405c1cb7447bcd0ba2156f88f8db92a808a988cd621634d60`. Preview at `http://127.0.0.1:41398` passed for34 pages. `output/site-improvements-20260913/local-final-audit.json` records all34×5 normal viewports=170 checks with no failures, duplicate IDs/titles or broken anchors. The material tables and all four maintenance procedures are integrated; earlier wording that a parent merge was pending is historical and superseded by this evidence.

A later text-only200% check found the shared footer email overflowing on all15 articles (document475px). The entry-page worker is correcting the shared theme. The normal-width report remains valid for23e2; it is not a200% pass or proof of the next candidate. Final make fast was interrupted for this correction and is not PASS. Q12/G12/G13 remain correction/recheck pending. Root will generate a new candidate and append final verification. This worker did not regenerate the progress workbook while results are changing.

External link checks now exist in `technical-public-verification.json`, `technical-official-destinations.json` and `technical-ad-destinations.json`: official31 have29 reachable and406/SSL unavailable; adoptedruntime26 URLs have16 affiliate destinations all200 and ordinary9 reachable/1Samsonite406. Exact selected variant/color/stock and confirmed affiliate earnings remain unverified. Contact drafts are unsent; GSC/GA4-account/ASP data are UNAVAILABLE. No new production publication or live readback is claimed.
