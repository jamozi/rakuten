/** Local form audit; no script injection, publication, provider calls or human-test claims.
 * Usage: node changes/wordpress-local-preview-v1/browser/local_running_cost_audit.mjs ORIGIN OUTPUT
 * Layout enlargement follows reader_experience_audit: 200% computed text sizes, not browser zoom. */
import { chromium } from 'playwright';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import path from 'node:path';

const [origin, output] = process.argv.slice(2), target = new URL(origin);
if (!['127.0.0.1', 'localhost'].includes(target.hostname) || target.protocol !== 'http:' || target.username || target.password || target.pathname !== '/' || target.search || target.hash || !output) throw Error('LOCAL_ORIGIN_AND_OUTPUT_REQUIRED');
const widths = [360, 390, 768, 1024, 1440], keys = ['electricity', 'water', 'detergent', 'runs'];
const mount = '[data-raos-cost-calculator="v1"]', form = mount + ' .raos-cost-form', normal = ['30.7', '262', '2.1', '30'];
const invalid = [['negative', 'electricity', '-1'], ['nonfinite', 'water', 'Infinity'], ['nan', 'electricity', 'NaN'], ['nonnumeric', 'detergent', 'abc'], ['fraction-runs', 'runs', '2.5'], ['rounded-fraction-runs', 'runs', '1.0000000000000001']];
const names = ['load', 'initial', 'profiles', 'blank', 'zero', 'normal', 'unknown', ...invalid.map(x => x[0]), 'keyboard', 'reset', 'privacy', 'reload', 'no-js', ...widths.flatMap(w => [1, 2].map(s => 'layout-' + w + '-' + s))];
const report = { schema: 'LOCAL_RUNNING_COST_AUDIT_V1', status: 'NOT_RUN', origin: target.origin, started_at: new Date().toISOString(), human_tests: 'NOT_PERFORMED', checks: Object.fromEntries(names.map(n => [n, { status: 'NOT_RUN' }])), requests: [], storageEvents: [], runtimeAssets: [], errors: [], artifacts: [] };
const save = () => writeFile(path.join(output, 'manifest.json'), JSON.stringify(report, null, 2) + '\n');
await mkdir(output, { recursive: true }); await save();
let browser, page, phase = 'setup', observing = false;
const check = async (name, run) => {
  phase = name; const row = report.checks[name]; row.status = 'RUNNING'; await save();
  try { await run(row); row.status = 'PASS'; } catch (e) { row.status = 'FAIL'; row.error = String(e.stack || e); }
  await save(); return row.status === 'PASS';
};
const snapshot = async (p, name, locator) => {
  const file = path.resolve(output, name + '.png');
  await (locator || p).screenshot({ path: file, ...(locator ? {} : { fullPage: true }) }); report.artifacts.push(file);
};
const context = async (javaScriptEnabled = true) => {
  const ctx = await browser.newContext({ javaScriptEnabled, serviceWorkers: 'block', viewport: { width: 1440, height: 900 } });
  ctx.on('request', r => { if (observing) report.requests.push({ phase, method: r.method(), url: r.url(), type: r.resourceType() }); });
  ctx.on('page', p => p.on('pageerror', e => report.errors.push({ phase, error: e.message })));
  await ctx.route('**/*', async route => {
    const r = route.request(), allowed = new URL(r.url()).origin === target.origin && ['GET', 'HEAD'].includes(r.method());
    if (!allowed) { report.errors.push({ phase, error: 'NONLOCAL_OR_MUTATING_REQUEST', method: r.method(), url: r.url() }); return route.abort(); }
    // Do not let an automatic redirect escape the local GET/HEAD boundary.
    try {
      const response = await route.fetch({ maxRedirects: 0 });
      if (r.method() === 'GET' && new URL(r.url()).pathname.endsWith('/assets/local-running-cost.js')) { const bytes = await response.body(); report.runtimeAssets.push({ phase, url: r.url(), status: response.status(), sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length, captured_at: new Date().toISOString() }); }
      if (response.status() >= 300 && response.status() < 400) { report.errors.push({ phase, error: 'REDIRECT_BLOCKED', url: r.url() }); await response.dispose(); return route.abort(); }
      await route.fulfill({ response }); await response.dispose();
    } catch (e) { report.errors.push({ phase, error: String(e), url: r.url() }); await route.abort(); }
  });
  await ctx.routeWebSocket('**/*', ws => { report.errors.push({ phase, error: 'WEBSOCKET_BLOCKED', url: ws.url() }); return ws.close(); });
  return ctx;
};
try {
  const bytes = await readFile('changes/editorial-portfolio-v3/local-reader-guides.v1.json', 'utf8'), registry = JSON.parse(bytes);
  assert.equal(registry.publication_authority, false);
  const guide = registry.articles.find(a => a.article_id === 'dishwasher-running-cost'), config = guide.cost_calculator;
  assert.match(guide.local_slug, /^local-preview-[a-z0-9-]+$/); report.url = new URL('/' + guide.local_slug + '/', target).href;
  report.registry_sha256 = createHash('sha256').update(bytes).digest('hex');
  report.audit_sha256 = createHash('sha256').update(await readFile(new URL(import.meta.url))).digest('hex');
  report.owner_asset_sha256 = createHash('sha256').update(await readFile('changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/local-running-cost.js')).digest('hex');
  const expected = config.profiles.map(p => {
    const q = (ref, kind) => ref === null ? null : registry.facts.find(f => f.evidence_ref === ref && f.exact_model === p.exact_model).quantities.find(v => v.kind === kind && v.course === p.course);
    const e = q(p.energy_ref, 'energy_per_cycle'), w = q(p.water_ref, 'water_per_cycle');
    assert.notEqual(e, undefined); assert.notEqual(w, undefined); if (e && w) assert.equal(e.course_label, w.course_label);
    return { id: p.profile_id, model: p.exact_model, course: e?.course_label ?? w?.course_label ?? 'コース別の消費量は未確認', energy: e ? String(e.value) : null, water: w ? String(w.value) : null };
  });
  assert.equal(expected.length, 6); report.expectedProfiles = expected;
  browser = await chromium.launch({ channel: 'chrome', headless: true }); report.browser = browser.version();
  const ctx = await context(); page = await ctx.newPage(); page.setDefaultTimeout(12000);
  const field = k => page.locator('#raos-cost-' + k), result = page.locator(form + ' .raos-cost-result');
  const fill = async values => { for (let i = 0; i < keys.length; i++) await field(keys[i]).fill(values[i]); };
  const submit = async row => { await page.locator(form + ' button[type="submit"]').click(); row.text = await result.innerText(); };
  const values = () => Promise.all(keys.map(k => field(k).inputValue()));
  const storage = async () => ({ state: await ctx.storageState({ indexedDB: true }), session: await page.evaluate(() => Object.entries(sessionStorage).sort()), caches: await page.evaluate(async () => Promise.all((await caches.keys()).sort().map(async n => [n, (await (await caches.open(n)).keys()).map(r => r.url).sort()]))) });
  const cdp = await ctx.newCDPSession(page); await cdp.send('DOMStorage.enable');
  for (const event of ['domStorageItemAdded', 'domStorageItemUpdated', 'domStorageItemRemoved', 'domStorageItemsCleared']) cdp.on('DOMStorage.' + event, data => { if (observing) report.storageEvents.push({ phase, event, data }); });
  report.status = 'RUNNING';
  const loaded = await check('load', async row => {
    const response = await page.goto(report.url, { waitUntil: 'networkidle' }); assert.equal(response.status(), 200);
    const html = await response.text(); await writeFile(path.join(output, 'response.html'), html); report.artifacts.push(path.resolve(output, 'response.html'));
    row.response_sha256 = createHash('sha256').update(html).digest('hex');
    assert.ok(html.includes('data-raos-cost-calculator="v1"') && !html.includes('class="raos-cost-form"'));
    row.scripts = await page.locator('script[src]').evaluateAll(nodes => nodes.map(n => n.src));
    row.theme_revisions = [...new Set(row.scripts.filter(s => s.includes('/themes/kurashinoshirube-child/')).map(s => new URL(s).searchParams.get('ver')))];
    assert.ok(row.scripts.some(s => new URL(s).pathname.endsWith('/assets/local-running-cost.js')), 'LOCAL_COST_SCRIPT_NOT_ENQUEUED');
    await page.locator(form).waitFor({ state: 'visible' }); await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator(form).count(), 1);
  });
  if (loaded) {
    const before = await storage(); observing = true; report.observation = { started_at: new Date().toISOString(), quietWindowMs: 1000, scope: 'post-load form actions; DOMStorage events plus cookies/localStorage/IndexedDB/sessionStorage/CacheStorage-key snapshots; deliberate reload excluded' };
    await check('initial', async row => { row.values = await values(); assert.deepEqual(row.values, ['', '', '', '']); assert.equal(await field('profile').inputValue(), config.default_profile); assert.match(await result.innerText(), /未入力/); });
    await check('profiles', async row => {
      row.data = await page.locator(mount + ' [data-raos-cost-profile]').evaluateAll(rs => rs.map(r => ({ id: r.dataset.raosCostProfile, model: r.dataset.raosCostModel, course: r.dataset.raosCostCourse, energy: r.getAttribute('data-raos-energy-wh'), water: r.getAttribute('data-raos-water-litres') })));
      assert.deepEqual(row.data, expected);
      row.tableText = await page.locator(mount + ' [data-raos-cost-profile]').evaluateAll(rs => rs.map(r => [...r.cells].map(c => c.textContent.trim())));
      for (let i = 0; i < expected.length; i++) { const p = expected[i], cells = row.tableText[i]; assert.equal(cells[0], p.model); assert.equal(cells[1], p.course); assert.ok(cells[2].includes(p.energy === null ? '未確認' : p.energy + 'Wh')); assert.ok(cells[3].includes(p.water === null ? '未確認' : p.water + 'L')); }
      row.options = await field('profile').locator('option').evaluateAll(os => os.map(o => ({ value: o.value, text: o.textContent })));
      assert.deepEqual(row.options, expected.map(p => ({ value: p.id, text: p.model + ' — ' + p.course }))); row.conditions = [];
      for (const p of expected) { await field('profile').selectOption(p.id); const text = await page.locator('#raos-cost-selected-condition').innerText(); row.conditions.push(text); for (const part of [p.model, p.course, p.energy === null ? '消費電力量：未確認' : p.energy + 'Wh/回', p.water === null ? '使用水量：未確認' : p.water + 'L/回']) assert.ok(text.includes(part)); }
      await field('profile').selectOption(config.default_profile);
    });
    await check('blank', async row => { await field('profile').selectOption(config.default_profile); await fill(['', '', '', '']); await submit(row); assert.match(row.text, /計算できる費目がありません/); assert.match(row.text, /月の概算：未計算/); assert.doesNotMatch(row.text, /0円/); });
    await check('zero', async row => { await field('profile').selectOption(config.default_profile); await fill(['0', '0', '0', '0']); await submit(row); for (const text of ['一回分：0円', '0回分：0円/月']) assert.ok(row.text.includes(text)); assert.doesNotMatch(row.text, /小計|未計算/); });
    await check('normal', async row => {
      await field('profile').selectOption('np-tmlk1-standard'); await fill(normal); await submit(row);
      for (const text of ['電気代：7.06円/回', '上下水道代：0.66円/回', '洗剤代：2.1円/回', '一回分：9.82円', '30回分：294.48円/月']) assert.ok(row.text.includes(text), text);
      await snapshot(page, 'normal-result', page.locator(form));
      await writeFile(path.join(output, 'rendered.html'), await page.content()); report.artifacts.push(path.resolve(output, 'rendered.html'));
    });
    await check('unknown', async row => {
      await field('profile').selectOption('dws-33b-unknown'); await fill(normal); await submit(row);
      for (const text of ['小計', '電気代：未計算', '上下水道代：未計算', '一回分の小計：2.1円', '30回分の小計：63円/月']) assert.ok(row.text.includes(text), text);
      assert.doesNotMatch(row.text, /(?:電気代|上下水道代)：0円/); await snapshot(page, 'unknown-result', page.locator(form));
      row.waterOnly = {}; await field('profile').selectOption('tk-mdw22b-spec'); await submit(row.waterOnly);
      for (const text of ['電気代：未計算', '上下水道代：0.84円/回', '一回分の小計：2.94円', '30回分の小計：88.15円/月']) assert.ok(row.waterOnly.text.includes(text), text);
      await snapshot(page, 'water-only-result', page.locator(form));
    });
    for (const [name, key, bad] of invalid) await check(name, async row => {
      await field('profile').selectOption(config.default_profile); await fill(normal); await field(key).fill(bad); await submit(row);
      row.focus = await page.evaluate(() => document.activeElement.id); row.ariaInvalid = await field(key).getAttribute('aria-invalid'); row.validationMessage = await page.locator('#raos-cost-' + key + '-error').innerText();
      assert.equal(row.focus, 'raos-cost-' + key); assert.equal(row.ariaInvalid, 'true'); assert.ok(row.validationMessage.trim()); assert.ok(await page.locator('#raos-cost-' + key + '-error').isVisible());
      assert.ok((await field(key).getAttribute('aria-describedby')).split(' ').includes('raos-cost-' + key + '-error')); assert.match(row.text, key === 'runs' ? /月の概算：未計算/ : /小計/);
      await field(key).fill('0'); assert.equal(await field(key).getAttribute('aria-invalid'), null); assert.ok(await page.locator('#raos-cost-' + key + '-error').isHidden()); assert.match(await result.innerText(), /入力を変更/);
    });
    await check('keyboard', async row => {
      row.fields = await page.locator(form + ' input').evaluateAll(es => es.map(e => ({ id: e.id, name: [...e.labels].map(l => l.textContent).join(' '), mode: e.inputMode, autocomplete: e.autocomplete, described: (e.getAttribute('aria-describedby') || '').split(' ').every(id => !!document.getElementById(id)) })));
      assert.equal(row.fields.length, 4); assert.ok(row.fields.every(f => f.name.trim() && f.described && f.autocomplete === 'off')); assert.deepEqual(row.fields.map(f => f.mode), ['decimal', 'decimal', 'decimal', 'numeric']);
      await field('profile').selectOption(config.default_profile); await fill(normal); await field('profile').focus(); row.tabOrder = [];
      for (const selector of [...keys.map(k => '#raos-cost-' + k), form + ' button[type="submit"]', form + ' button[type="reset"]']) {
        await page.keyboard.press('Tab'); const focused = await page.locator(selector).evaluate(e => ({ focused: e === document.activeElement, outline: getComputedStyle(e).outlineStyle, width: parseFloat(getComputedStyle(e).outlineWidth) }));
        row.tabOrder.push({ selector, ...focused }); assert.ok(focused.focused && focused.outline !== 'none' && focused.width > 0);
      }
      await page.keyboard.press('Shift+Tab'); assert.ok(await page.locator(form + ' button[type="submit"]').evaluate(e => e === document.activeElement));
      await page.keyboard.press('Enter'); row.submittedText = await result.innerText(); assert.ok(row.submittedText.includes('30回分：294.48円/月'));
      await page.keyboard.press('Tab'); await page.keyboard.press('Space'); assert.deepEqual(await values(), ['', '', '', '']);
    });
    await check('reset', async row => {
      await fill(normal); await field('profile').selectOption('dws-33b-unknown'); await field('runs').fill('2.5'); await submit(row); await page.locator(form + ' button[type="reset"]').click();
      row.values = await values(); assert.deepEqual(row.values, ['', '', '', '']); assert.equal(await field('profile').inputValue(), config.default_profile);
      assert.equal(await page.locator(form + ' [aria-invalid="true"]').count(), 0); assert.equal(await page.locator(form + ' .raos-cost-error:visible').count(), 0); assert.match(await result.innerText(), /未入力/);
    });
    await check('privacy', async row => {
      await fill(normal); await page.waitForTimeout(1000); row.before = before; row.after = await storage();
      row.requestCount = report.requests.length; row.storageEventCount = report.storageEvents.length; row.storageChanged = JSON.stringify(row.before) !== JSON.stringify(row.after);
      assert.equal(row.requestCount, 0); assert.equal(row.storageEventCount, 0); assert.equal(row.storageChanged, false);
    });
    observing = false; report.observation.finished_at = new Date().toISOString();
    await check('reload', async row => {
      row.dirtyBefore = await values(); assert.deepEqual(row.dirtyBefore, normal);
      const response = await page.reload({ waitUntil: 'networkidle' }); assert.equal(response.status(), 200); await page.locator(form).waitFor({ state: 'visible' });
      row.values = await values(); assert.deepEqual(row.values, ['', '', '', '']); assert.equal(await field('profile').inputValue(), config.default_profile); assert.match(await result.innerText(), /未入力/); assert.deepEqual(await storage(), before);
    });
  }
  if (!loaded) await snapshot(page, 'form-unavailable');
  if (loaded) for (const width of widths) for (const scale of [1, 2]) await check('layout-' + width + '-' + scale, async row => {
    await page.setViewportSize({ width, height: 900 }); const response = await page.goto(report.url, { waitUntil: 'networkidle' }); assert.equal(response.status(), 200);
    await page.locator(form).waitFor({ state: 'visible' }); await page.evaluate(() => document.fonts.ready); await fill(normal); await submit(row);
    if (scale === 2) await page.evaluate(() => { const sizes = [...document.querySelectorAll('body *')].map(e => [e, parseFloat(getComputedStyle(e).fontSize)]); for (const [e, size] of sizes) if (e instanceof HTMLElement) e.style.fontSize = size * 2 + 'px'; });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    row.width = width; row.textScale = scale; row.geometry = await page.locator(form).evaluate(e => ({ documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, formOverflow: e.scrollWidth - e.clientWidth }));
    const table = page.locator(mount + ' .comparison-table-wrap');
    row.table = await table.evaluate(e => ({ scrollWidth: e.scrollWidth, clientWidth: e.clientWidth, tabindex: e.getAttribute('tabindex'), name: document.getElementById(e.getAttribute('aria-labelledby'))?.textContent }));
    await snapshot(page, 'calculator-' + width + '-text-' + scale * 100); await snapshot(page, 'table-' + width + '-text-' + scale * 100, table);
    assert.ok(row.geometry.documentOverflow <= 1 && row.geometry.formOverflow <= 1); assert.ok(row.table.name); if (row.table.scrollWidth > row.table.clientWidth + 1) assert.equal(row.table.tabindex, '0');
  });
  await check('no-js', async row => {
    const nojs = await context(false), p = await nojs.newPage(); p.setDefaultTimeout(12000);
    try {
      const response = await p.goto(report.url, { waitUntil: 'networkidle' }); assert.equal(response.status(), 200); assert.equal(await p.locator(form).count(), 0); assert.ok(await p.locator(mount + ' .raos-cost-no-script').isVisible());
      row.text = await p.locator('main').innerText(); for (const pattern of [/Wh/, /1,?000/, /kWh/, /m[3³]/, /洗剤/]) assert.match(row.text, pattern);
      assert.equal(await p.locator(mount + ' [data-raos-cost-profile]').count(), 6); row.sources = await p.locator('#guide-evidence a[href^="https://"]').evaluateAll(es => es.map(e => e.href)); assert.ok(row.sources.length > 0);
      row.brokenEvidence = await p.locator(mount + ' a[href^="#guide-evidence-"]').evaluateAll(es => es.filter(e => !document.getElementById(e.hash.slice(1))).map(e => e.hash)); assert.deepEqual(row.brokenEvidence, []);
      await writeFile(path.join(output, 'no-js.html'), await p.content()); report.artifacts.push(path.resolve(output, 'no-js.html')); await snapshot(p, 'no-js');
    } finally { await nojs.close(); }
  });
} catch (e) { report.errors.push({ phase, error: String(e.stack || e) }); }
finally {
  observing = false; try { await browser?.close(); } catch (e) { report.errors.push({ error: String(e) }); }
  report.runtime_asset_sha256 = [...new Set(report.runtimeAssets.filter(a => a.status === 200).map(a => a.sha256))];
  report.runtime_asset_status = report.runtime_asset_sha256.length === 1 ? 'OBSERVED' : report.runtime_asset_sha256.length ? 'CHANGED_DURING_AUDIT' : 'NOT_LOADED';
  report.owner_asset_matches_runtime = report.runtime_asset_sha256.length === 1 && report.runtime_asset_sha256[0] === report.owner_asset_sha256;
  if (report.runtime_asset_sha256.length === 1 && !report.owner_asset_matches_runtime) report.errors.push({ error: 'OWNER_RUNTIME_ASSET_SHA256_MISMATCH', owner_sha256: report.owner_asset_sha256, runtime_sha256: report.runtime_asset_sha256[0] });
  if (report.checks.load.status === 'PASS' && report.runtime_asset_sha256.length !== 1) report.errors.push({ error: 'RUNTIME_ASSET_VERSION_MISSING_OR_CHANGED_DURING_AUDIT' });
  const states = Object.values(report.checks).map(c => c.status);
  report.status = report.errors.length || states.includes('FAIL') ? 'FAIL' : states.every(s => s === 'PASS') ? 'PASS' : 'INCOMPLETE';
  report.finished_at = new Date().toISOString(); await save();
  console.log(JSON.stringify({ status: report.status, manifest: path.resolve(output, 'manifest.json'), checks: Object.fromEntries(Object.entries(report.checks).map(([k, v]) => [k, v.status])) }));
  process.exitCode = report.status === 'PASS' ? 0 : 1;
}
