const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const css = fs.readFileSync(process.argv[3], 'utf8');
let clock = Date.parse('2026-09-10T06:00:00Z');
const context = { module: { exports: {} }, Date: class extends Date { static now() { return clock; } } };
vm.runInNewContext(source, context);
const { offerCost, budgetState, checkInstallation, parseMeasurement, assessInstallation, installationSummary, sameKnownValues, watchClock, numberInput } = context.module.exports;
const navigationSource = fs.readFileSync(require('node:path').join(require('node:path').dirname(process.argv[2]), 'editorial-navigation.js'), 'utf8');
const offer = { checked_at: '2026-09-10T05:00:00Z', valid_until: '2026-09-11T05:00:00Z',
  identity_verified: true, condition: 'new', state: 'AVAILABLE', total_scope_complete: true,
  price_yen: 30000, shipping_yen: 1000, required_items_yen: 500, points: 99999, conditional_coupon: 50000 };
assert.equal(offerCost(offer, clock).total, 31500);
assert.equal(budgetState([offer], 31500, clock), 'WITHIN_BUDGET');
assert.equal(budgetState([offer], 0, clock), 'OVER_BUDGET');
for (const delta of [{ shipping_yen: null }, { shipping_yen: false }, { total_scope_complete: false }, { identity_verified: false },
  { state: 'PREORDER' }, { state: 'UNKNOWN' }, { condition: 'used' }, { valid_until: '2026-09-10T06:00:00Z' },
  { checked_at: '2026-09-10T07:00:00Z' }, { checked_at: '2026-09-10T05:00:00' }, { price_yen: Infinity }]) {
  assert.equal(budgetState([{ ...offer, ...delta }], 999999, clock), 'UNKNOWN', JSON.stringify(delta));
}
assert.equal(budgetState([{ ...offer, shipping_yen: null }], 1, clock), 'UNKNOWN', 'lower bound over budget remains incomplete');
assert.equal(offerCost({ ...offer, valid_until: '2026-09-20T05:00:00Z' }, Date.parse('2026-09-11T05:00:00Z')).state, 'EXPIRED');
assert.equal(offerCost({ ...offer, valid_until: '2026-09-10T06:00:01Z' }, clock + 1000).state, 'EXPIRED');
assert.equal(budgetState([offer, { ...offer, shipping_yen: null }], 1, clock), 'UNKNOWN');
assert.equal(numberInput('').value, null);
assert.equal(numberInput('０').value, 0);
for (const v of ['-1', 'NaN', '0x20', 'Infinity', '1e9']) assert.equal(numberInput(v).invalid, true);
assert.equal(sameKnownValues(['3 L', '3 L']), true);
for (const v of ['未確認', 'UNKNOWN', '不明', '']) assert.equal(sameKnownValues([v, v]), false);
assert.equal(sameKnownValues(['3L', '4L']), false);
const dimensions = { width_mm: 310, depth_mm: 225, height_mm: 435, door_depth_mm: 485, door_height_mm: 435, above_mm: 100, left_mm: 0, right_mm: 0, rear_mm: 17 };
const measured = Object.fromEntries(Object.entries(dimensions).map(([k,v]) => [k, String(v)]));
assert.equal(checkInstallation(dimensions, measured).state, 'CONFIRMED');
assert.equal(checkInstallation({ ...dimensions, rear_mm: null }, measured).state, 'UNKNOWN');
assert.equal(checkInstallation(dimensions, { ...measured, width_mm: '' }).state, 'UNKNOWN');
assert.equal(checkInstallation(dimensions, { ...measured, width_mm: '309', depth_mm: '' }).state, 'MISMATCH');
assert.equal(checkInstallation(dimensions, { ...measured, width_mm: '-1' }).fields[0].invalid, true);
// Reference-aware matching: unknown keys on either side are configuration errors,
// missing site references are not the reader's missing input, and 0 is a valid reference.
assert.equal(assessInstallation(dimensions, measured).state, 'NUMERIC_MATCH');
assert.equal(JSON.stringify(assessInstallation(dimensions, measured).counts), JSON.stringify({ known: 9, matched: 9, mismatched: 0, missing: 0, invalid: 0, reference_unknown: 0, reference_invalid: 0 }));
assert.equal(assessInstallation({ ...dimensions, rear_mm: null }, measured).state, 'PARTIAL');
assert.equal(assessInstallation({ ...dimensions, rear_mm: null }, measured).fields[8].input_required, false);
assert.equal(assessInstallation(dimensions, { ...measured, width_mm: '' }).state, 'INPUT_MISSING');
const short = assessInstallation(dimensions, { ...measured, width_mm: '309' });
assert.equal(short.state, 'MISMATCH'); assert.equal(short.fields[0].shortfall_mm, 1);
assert.equal(assessInstallation(dimensions, { ...measured, width_mm: '５００' }).fields[0].match_state, 'MATCH');
for (const v of ['-1', 'Infinity', '0x20', 'NaN']) assert.equal(assessInstallation(dimensions, { ...measured, width_mm: v }).state, 'INPUT_INVALID', v);
assert.equal(assessInstallation({ ...dimensions, width_mm: -5 }, measured).state, 'REFERENCE_INVALID');
assert.equal(assessInstallation({ ...dimensions, left_mm: 0 }, { ...measured, left_mm: '0' }).fields[6].match_state, 'MATCH');
assert.throws(() => assessInstallation({ ...dimensions, with_mm: 1 }, measured), /UNKNOWN_REFERENCE_KEY/);
assert.throws(() => assessInstallation(dimensions, { ...measured, with_mm: '1' }), /UNKNOWN_MEASUREMENT_KEY/);
assert.throws(() => assessInstallation(null, measured), /REFERENCE_OBJECT_REQUIRED/);
assert.equal(parseMeasurement('').state, 'MISSING'); assert.equal(parseMeasurement('1e9').state, 'INVALID');
assert.match(installationSummary(short), /^数値一致 8項目／不足 1項目／未入力 0項目。/);
assert.match(installationSummary(assessInstallation({ ...dimensions, rear_mm: null }, { ...measured, width_mm: '' })), /未入力 1項目／サイト側の基準未確認 1項目/);
const handlers = {}, timers = new Map(); let count = 0, refreshes = 0;
const browser = { addEventListener: (name, callback) => { handlers[name] = callback; }, clearTimeout: id => timers.delete(id), setTimeout: (fn, ms) => { timers.set(++count, { fn, ms }); return count; } };
const pageEvents = { addEventListener: (name, callback) => { handlers[name] = callback; } };
watchClock(browser, pageEvents, () => { refreshes++; return [Date.parse('2026-09-10T06:00:01Z')]; });
assert.equal([...timers.values()][0].ms, 1000);
clock += 1000; [...timers.values()][0].fn();
assert.equal(refreshes, 2);
clock += 10 * 86400000; handlers.visibilitychange(); handlers.pageshow(); handlers.focus();
assert.equal(refreshes, 5); assert.equal(timers.size, 1);

(async () => {
  const engines = require('playwright');
  const engine = process.env.RAOS_PURCHASE_TEST_BROWSER || 'firefox';
  assert.ok(['firefox', 'chromium'].includes(engine));
  const browser = await engines[engine].launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    let requests = 0;
    page.on('request', () => requests++);
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    await page.clock.install({ time: new Date('2026-09-10T06:00:00Z') });
    const ids = ['a', 'b', 'c', 'd'];
    const prices = [30000, 60000, 90000, 10000];
    const offers = ids.map((id, i) => `<section class="ps-product-offers" data-ps-product="${id}"><div data-ps-offer="offer-${id}" data-ps-checked-at="2026-09-10T05:00:00Z" data-ps-valid-until="2026-09-10T06:00:01Z" data-ps-identity="true" data-ps-state="AVAILABLE" data-ps-condition="new" data-ps-complete="${id === 'c' ? 'false' : 'true'}" data-ps-price-yen="${prices[i]}" data-ps-shipping-yen="0" data-ps-required-items-yen="0"><p class="ps-price-status">確認時の条件</p></div></section>`).join('');
    const row = values => `<tr><th>項目</th>${ids.map((id,i) => `<td data-ps-product="${id}">${values[i]}</td>`).join('')}</tr>`;
    const html = `<div class="ps-article"><div class="ps-budget-controls" hidden data-ps-purpose-options='[{"id":"small","label":"少量"}]'></div><div class="ps-pair-controls" hidden data-ps-pair-options='${JSON.stringify(ids.map(id => ({ id, label: id })))}'></div><div class="ps-table-scroll" tabindex="0"><table class="ps-comparison"><thead><tr><th>項目</th>${ids.map(id => `<th data-ps-product="${id}">${id}</th>`).join('')}</tr></thead><tbody>${row(['同値','同値','別','別'])}${row(['未確認','未確認','未確認','未確認'])}</tbody></table></div><div class="ps-product-grid">${ids.map(id => `<article class="ps-product" data-ps-product="${id}" data-ps-use-cases="${id === 'd' ? 'large' : 'small'}"><h3>${id}</h3><p data-ps-product-budget role="status"></p></article>`).join('')}</div>${offers}<div class="ps-installation" data-ps-installation='${JSON.stringify(dimensions)}'><div class="ps-installation-controls" hidden></div><p>安全保証なし</p></div></div>`;
    await page.setContent(html);
    await page.addStyleTag({ content: css });
    assert.equal(await page.locator('.ps-product:visible').count(), 4, 'all products before JS');
    assert.equal(await page.locator('[data-ps-offer]:visible').count(), 4, 'all offers before JS');
    await page.addScriptTag({ content: source });
    assert.equal(await page.locator('.ps-budget-controls:visible').count(), 1);
    await page.locator('[data-ps-budget]').fill('50000');
    assert.deepEqual(await page.locator('.ps-product:visible').evaluateAll(nodes => nodes.map(n => n.dataset.psProduct)), ['a','b','c','d'], 'budget never hides a published candidate');
    assert.match(await page.locator('.ps-product[data-ps-product="c"]').textContent(), /予算未判定/);
    assert.match(await page.locator('.ps-product[data-ps-product="b"]').textContent(), /予算を超えています。候補は表示したままです/);
    await page.locator('[data-ps-purpose]').selectOption('small');
    assert.equal(await page.locator('.ps-product:visible').count(), 4, 'purpose only annotates cards');
    assert.deepEqual(await page.locator('.ps-product').evaluateAll(nodes => nodes.map(n => n.dataset.psPriorityMatch)), ['true','true','true','false']);
    assert.match(await page.locator('[data-ps-budget-result]').textContent(), /4候補を表示。優先する条件に合う候補は3件です。/);
    await page.locator('[data-ps-pair="a"]').selectOption('a');
    assert.equal(await page.locator('.ps-comparison thead [data-ps-product]:visible').count(), 2);
    await page.locator('[data-ps-differences]').check();
    assert.equal(await page.locator('.ps-comparison tbody tr:visible').count(), 1, 'unknown equal row kept');
    await page.locator('.ps-comparison tbody td').first().evaluate(n => { n.dataset.psFactState = 'UNKNOWN'; });
    await page.locator('[data-ps-differences]').dispatchEvent('change');
    assert.equal(await page.locator('.ps-comparison tbody tr:visible').count(), 2, 'structured UNKNOWN cannot be hidden despite matching text');
    await page.locator('[data-ps-pair="b"]').selectOption('a');
    assert.match(await page.locator('[data-ps-pair-result]').textContent(), /同じ商品/);
    assert.equal(await page.locator('.ps-comparison thead [data-ps-product]:visible').count(), 4);
    await page.locator('[data-ps-pair-reset]').click();
    assert.equal(await page.locator('.ps-comparison tbody tr:visible').count(), 2);
    await page.clock.runFor(1001);
    assert.match(await page.locator('.ps-price-status').first().textContent(), /期限切れ/);
    assert.equal(await page.locator('.ps-product:visible').count(), 4, 'expired candidates stay visible as UNKNOWN');
    assert.equal(await page.locator('.ps-installation-controls input:visible').count(), 9, 'every known reference gets one input');
    for (const [key, value] of Object.entries(dimensions)) await page.locator(`#ps-install-0-${key}`).fill(String(value));
    assert.match(await page.locator('.ps-installation-result').textContent(), /^数値一致 9項目／不足 0項目／未入力 0項目。/);
    await page.locator('#ps-install-0-width_mm').fill('1');
    assert.match(await page.locator('.ps-installation-result').textContent(), /^数値一致 8項目／不足 1項目／未入力 0項目。/);
    assert.match(await page.locator('#ps-install-0-width_mm-help').textContent(), /不足：309mm/);
    await page.locator('#ps-install-0-width_mm').fill('全角');
    assert.match(await page.locator('.ps-installation-result').textContent(), /入力形式の確認 1項目/);
    await page.getByText('測定値をクリア', { exact: true }).click();
    assert.match(await page.locator('.ps-installation-result').textContent(), /^数値一致 0項目／不足 0項目／未入力 9項目。/);
    // A missing pair part or a broken reference must not remove the static table or notes.
    const degraded = html.replace('data-ps-pair-options=', 'data-ps-pair-broken=').replace('"rear_mm":17', '"rear_mm":17,"with_mm":5');
    await page.setContent(degraded);
    await page.addScriptTag({ content: source });
    assert.equal(await page.locator('.ps-pair-controls:visible').count(), 0, 'pair controls stay hidden without valid options');
    assert.equal(await page.locator('.ps-comparison tbody tr:visible').count(), 2, 'static table remains');
    assert.equal(await page.locator('.ps-installation-controls:visible').count(), 0, 'unknown reference key disables matching');
    assert.equal(await page.getByText('安全保証なし').count(), 1, 'static installation note stays');
    assert.equal(await page.locator('.ps-budget-controls:visible').count(), 1, 'independent controls still mount');
    await page.setContent(html);
    await page.addStyleTag({ content: css });
    await page.addScriptTag({ content: source });
    await page.locator('[data-ps-budget]').fill('50000');
    await page.locator('.ps-article').evaluate(n => { n.style.fontSize = '32px'; });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, '200% mobile text does not overflow body');
    await page.locator('[data-ps-budget]').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('[data-ps-pair="a"]').evaluate(n => n === document.activeElement), true);
    await page.setViewportSize({ width: 1280, height: 900 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'desktop 200% text remains contained');
    assert.equal(requests, 0);
    assert.deepEqual(errors, []);
    // Exercise the current generated renderer output, not just the isolated fixture.
    const catalog = JSON.parse(fs.readFileSync('changes/reader-purchase-support-v1/purchase-support.v1.json', 'utf8'));
    const noScript = await browser.newPage({ javaScriptEnabled: false });
    for (const article of catalog.articles) {
      const body = fs.readFileSync(`changes/wordpress-direct-publish-v1/articles/${article.slug}.html`, 'utf8');
      await noScript.setContent(body);
      assert.equal(await noScript.locator('input, select, button, noscript').count(), 0, `${article.slug}: inert published content`);
      if (article.kind === 'comparison') {
        assert.equal(await noScript.locator('.ps-product:visible').count(), 4);
        assert.equal(await noScript.locator('.ps-product-offers:visible').count(), 4);
        await page.setContent(body);
        await page.addScriptTag({ content: source });
        if (article.slug === 'countertop-dishwasher-for-small-households') {
          // Links-only comparison: no purpose/budget inputs, four condition links, pair still works.
          assert.equal(await page.locator('[data-ps-purpose], [data-ps-budget]').count(), 0, 'no purpose/budget inputs on the main comparison');
          assert.equal(await page.locator('#ps-choose a[href^="#product-"]').count(), 4);
          assert.equal(await page.locator('.ps-product:visible').count(), 4);
          await page.locator('[data-ps-pair="a"]').selectOption(article.product_ids[0]);
          assert.equal(await page.locator('.ps-comparison thead [data-ps-product]:visible').count(), 2);
          assert.equal(await page.locator('.ps-installation-details thead [data-ps-product]:visible').count(), 4, 'detail table keeps all candidates');
          assert.equal(await page.locator('.ps-product-caution:visible').count(), 8, 'cautions stay visible for every candidate');
          await page.locator('[data-ps-pair-reset]').click();
          assert.equal(await page.locator('.ps-comparison thead [data-ps-product]:visible').count(), 4);
          // Same-document hash: product anchors are revealed and focused on hashchange, back/forward and same-hash clicks.
          await page.addScriptTag({ content: navigationSource });
          const anchor = 'product-dish-ss-ma251';
          await page.evaluate(id => { location.hash = '#' + id; }, anchor);
          await page.waitForFunction(id => document.activeElement && document.activeElement.id === id, anchor);
          await page.evaluate(() => history.back());
          await page.waitForFunction(() => location.hash === '');
          await page.evaluate(() => history.forward());
          await page.waitForFunction(id => location.hash === '#' + id && document.activeElement && document.activeElement.id === id, anchor);
          await page.locator('h1, .ps-lead').first().focus();
          await page.locator(`#ps-choose a[href="#${anchor}"]`).click();
          await page.waitForFunction(id => document.activeElement && document.activeElement.id === id, anchor);
          assert.equal(await page.locator('.ps-product:visible').count(), 4, 'hash navigation does not hide candidates');
        } else {
          assert.equal(await page.locator('[data-ps-purpose]:visible').count(), 1);
          await page.locator('[data-ps-budget]').fill('1');
          assert.equal(await page.locator('.ps-product:visible').count(), 4, 'budget never hides published candidates');
          const firstCase = article.conditions[0].id;
          await page.locator('[data-ps-purpose]').selectOption(firstCase);
          assert.match(await page.locator('[data-ps-budget-result]').textContent(), /候補を表示/);
        }
      }
      if (article.slug === 'dishwasher-installation-measurement') {
        await page.setContent(body);
        await page.addScriptTag({ content: source });
        const known = catalog.products.filter(p => article.product_ids.includes(p.product_id) || true).filter(p => catalog.articles.find(a => a.slug === 'countertop-dishwasher-for-small-households').product_ids.includes(p.product_id))
          .reduce((n, p) => n + Object.values(p.installation).filter(v => typeof v === 'number').length, 0);
        assert.equal(await page.locator('.ps-installation-controls input:visible').count(), known, 'one input per known reference only');
        assert.ok(await page.locator('.ps-installation-field').count() > known, 'unknown references are listed as site-side gaps');
        await page.locator('#ps-install-0-width_mm').fill('1');
        assert.match(await page.locator('.ps-installation-result').first().textContent(), /不足 1項目/);
        assert.match(await page.locator('.ps-installation-result').first().textContent(), /サイト側の基準未確認 4項目/);
      }
    }
    await noScript.close();
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
  console.log('Purchase UI pure logic, timer/resume, inert renderer DOM, mobile and keyboard checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
