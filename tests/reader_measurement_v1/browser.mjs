/**
 * Explicit bounded browser simulation. ALL network requests are fulfilled or
 * aborted locally before goto; a closed loopback proxy + blocked service workers prevent
 * any production/provider request. PHP fixture uses only in-memory fake WP.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { firefox } from 'playwright';

const root = new URL('../../', import.meta.url).pathname;
const plugin = root + 'changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement/';
const script = readFileSync(plugin + 'assets/reader-measurement.js', 'utf8');
const css = readFileSync(plugin + 'assets/reader-measurement.css', 'utf8');
const aid = 'st1703-first-suitcase-comparison';
const policy = JSON.parse(readFileSync(plugin + 'config/reader-runtime.v1.json', 'utf8')).policy_sha256;
const origin = 'https://kurashinoshirube.com';
const pageURL = origin + '/carry-on-suitcase-comparison/';
const article = `<main class="raos-editorial-v2"><span class="raos-reader-view" data-raos-article-id="${aid}" hidden></span>
<p class="raos-contextual-related" data-journey-stage="compare"><a id="guide" href="/lightweight-carry-on-suitcase-under-3kg/" target="_blank">別の記事</a></p>
<details id="reader-evidence"><summary>確認する</summary><p>内容</p></details>
<a id="axes" href="#reader-axes">判断条件へ</a><section id="reader-axes">判断条件</section>
<a id="reference" href="https://store.ace.jp/shop/g/g01541-10/" target="_blank">公式出典</a>
<a id="unknown" href="https://unknown.invalid/private" target="_blank">対象外</a>
<input id="generic" aria-label="一般の入力"></main>`;
const footer = off => execFileSync(process.env.RAOS_READER_TEST_PHP || 'php',
  [root + 'tests/reader_measurement_v1/runtime.php', '--footer', ...(off ? ['--off'] : [])],
  { encoding: 'utf8', maxBuffer: 1024 * 1024 });
const html = off => '<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>Offline reader fixture</title>'
  + '<link rel="stylesheet" href="/reader-simulation.css"></head><body>' + article + footer(off)
  + '<script src="/reader-simulation.js"></script></body></html>';

const browser = await firefox.launch({
  headless: true,
  ...(process.env.RAOS_READER_FIREFOX ? { executablePath: process.env.RAOS_READER_FIREFOX } : {}),
});
try {
  const create = async off => {
    const context = await browser.newContext({ proxy: { server: 'http://127.0.0.1:9' }, serviceWorkers: 'block', viewport: { width: 1000, height: 900 } });
    await context.addCookies([{ name: 'simulation_cookie', value: 'must-not-send', domain: 'kurashinoshirube.com', path: '/' }]);
    const received = [];
    let status = 202;
    const document = html(off);
    await context.route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin === origin && url.pathname === '/wp-json/raos-reader/v1/events') {
        received.push({ body: JSON.parse(request.postData()), headers: await request.allHeaders(), method: request.method() });
        await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ accepted: status === 202 }) });
      } else if (url.origin === origin && url.pathname === '/reader-simulation.js') {
        await route.fulfill({ status: 200, contentType: 'text/javascript', body: script });
      } else if (url.origin === origin && url.pathname === '/reader-simulation.css') {
        await route.fulfill({ status: 200, contentType: 'text/css', body: css });
      } else if (request.isNavigationRequest()) {
        await route.fulfill({ status: 200, contentType: 'text/html', body: url.href === pageURL ? document : '<!doctype html><title>Offline target</title>' });
      } else await route.abort('blockedbyclient');
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pageURL);
    await page.waitForFunction(() => document.getElementById('raos-reader-consent-settings').dataset.readerConsentBound === 'true');
    return { context, page, received, errors, fail() { status = 503; } };
  };
  const settle = async page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const choose = async (page, value) => {
    await page.locator('#raos-reader-consent-reopen').click();
    await page.locator('#raos-reader-consent-' + value).click();
  };

  const off = await create(true);
  assert.deepEqual(await off.page.evaluate(() => Object.keys(localStorage)), []);
  assert.match(await off.page.locator('#raos-reader-site-status').textContent(), /停止中/);
  await off.page.locator('#generic').fill('private input never measured');
  await off.page.locator('#reader-evidence summary').click();
  await choose(off.page, 'allow');
  await off.page.locator('#reference').click();
  await settle(off.page);
  assert.equal(off.received.length, 0, 'OFF cannot collect even after browser allows');
  assert.deepEqual(await off.page.evaluate(() => JSON.parse(localStorage.getItem('raos_reader_consent_v1'))), { choice: 'granted', policy_version: policy });
  await off.page.locator('#raos-reader-consent-revoke').click();
  assert.equal(await off.page.evaluate(() => JSON.parse(localStorage.getItem('raos_reader_consent_v1')).choice), 'denied');
  assert.deepEqual(off.errors, []);
  await off.context.close();

  const on = await create(false);
  await on.page.locator('#reader-evidence summary').click();
  await on.page.locator('#generic').fill('not telemetry');
  assert.equal(on.received.length, 0, 'unselected cannot send');
  assert.deepEqual(await on.page.evaluate(() => Object.keys(localStorage)), []);
  await choose(on.page, 'deny');
  await on.page.locator('#reference').click();
  await settle(on.page);
  assert.equal(on.received.length, 0, 'denied cannot send');
  await choose(on.page, 'allow');
  // Duplicate bundle execution cannot attach duplicate listeners.
  await on.page.addScriptTag({ content: script });
  await on.page.locator('#reader-evidence summary').click(); // close
  await on.page.locator('#reader-evidence summary').click(); // genuinely open
  await on.page.waitForFunction(() => document.querySelector('#reader-evidence').open);
  await settle(on.page);
  await on.page.locator('#reference').click();
  await on.page.locator('#guide').click();
  await settle(on.page);
  assert.equal(on.received.length, 3, 'three genuine supported operations only, duplicate listener suppressed');
  assert.deepEqual(on.received.map(r => r.body), [
    { event_name: 'decision_check_open', article_id: aid, panel_id: 'reader-evidence' },
    { event_name: 'official_reference_open', article_id: aid, source_ref: 'SRC-PROTECA-TRI-AIR-01541' },
    { event_name: 'guide_navigation', article_id: aid, target_article_id: 'lightweight-carry-on-suitcase-under-3kg', journey_stage: 'compare' }
  ]);
  for (const row of on.received) {
    assert.equal(row.method, 'POST');
    assert.equal(row.headers.cookie, undefined, 'credentials omitted');
    assert.equal(row.headers.referer, undefined, 'referrer omitted');
    assert.equal(row.headers['x-raos-reader-consent'], 'granted');
    assert.equal(row.headers['x-raos-reader-policy'], policy);
    assert.equal(row.headers.origin, origin);
    assert.equal(row.headers['sec-fetch-site'], 'same-origin');
    assert.ok(Buffer.byteLength(JSON.stringify(row.body)) < 1024);
  }
  await on.page.locator('#unknown').click();
  await on.page.evaluate(() => {
    document.querySelector('#reference').click();
    document.querySelector('#reader-evidence').open = false;
    document.querySelector('#reader-evidence').open = true;
    document.querySelector('#generic').dispatchEvent(new Event('input', { bubbles: true }));
  });
  await settle(on.page);
  assert.equal(on.received.length, 3, 'scripted clicks/toggles, generic inputs and unknown references ignored');
  await on.page.locator('#raos-reader-consent-revoke').click();
  await on.page.locator('#reference').click();
  await settle(on.page);
  assert.equal(on.received.length, 3, 'revocation immediate with no backend UI request');
  assert.deepEqual(await on.page.evaluate(() => Object.keys(localStorage)), ['raos_reader_consent_v1']);
  assert.equal(await on.page.evaluate(() => sessionStorage.length), 0);
  await choose(on.page, 'allow');
  on.fail();
  await on.page.locator('#reference').click();
  await on.page.waitForFunction(() => document.getElementById('raos-reader-site-status').textContent.includes('受付を確認できない'));
  await on.page.locator('#reference').click();
  await settle(on.page);
  assert.equal(on.received.length, 4, 'no retries/queue after failure');
  assert.ok(on.context.pages().length > 1, 'native target navigation remains available');
  assert.deepEqual(on.errors, []);
  await on.context.close();

  const stale = await create(false);
  await stale.page.evaluate(() => localStorage.setItem('raos_reader_consent_v1', JSON.stringify({ choice: 'granted', policy_version: 'previous-policy' })));
  await stale.page.reload();
  await stale.page.locator('#reference').click();
  await settle(stale.page);
  assert.equal(stale.received.length, 0, 'stale policy cannot authorize');
  assert.match(await stale.page.locator('#raos-reader-user-status').textContent(), /未選択/);
  await stale.context.close();
  console.log('browser behavior OK (isolated browser; no production/provider requests)');
} finally { await browser.close(); }
