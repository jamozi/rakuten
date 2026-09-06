/**
 * Isolated reader-measurement view checks. Every browser request is routed
 * before navigation; no route continues or fetches from the shaped production
 * origin. PHP uses only the repository's in-memory WordPress doubles.
 */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync } from 'node:fs';
import { firefox } from 'playwright';

const root = new URL('../../', import.meta.url).pathname;
const plugin = root + 'changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement/';
const php = process.env.RAOS_READER_TEST_PHP || 'php';
const origin = 'https://kurashinoshirube.com';
const pageURL = origin + '/carry-on-suitcase-comparison/';
const articleID = 'st1703-first-suitcase-comparison';
const viewports = [360, 390, 768, 1024, 1440];
const artifactRelative = 'output/playwright/reader-measurement-v1/browser-views';
const artifactDirectory = root + artifactRelative;
mkdirSync(artifactDirectory, { recursive: true });

const runtime = JSON.parse(readFileSync(plugin + 'config/reader-runtime.v1.json', 'utf8'));
const jsBytes = readFileSync(plugin + 'assets/reader-measurement.js');
const cssBytes = readFileSync(plugin + 'assets/reader-measurement.css');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const integrity = bytes => 'sha256-' + createHash('sha256').update(bytes).digest('base64');
assert.equal(digest(jsBytes), runtime.files['assets/reader-measurement.js']);
assert.equal(digest(cssBytes), runtime.files['assets/reader-measurement.css']);

const phpQuote = value => "'" + value.replaceAll('\\', '\\\\').replaceAll("'", "\\'") + "'";
const assetProgram = [
  'require ' + phpQuote(root + 'tests/reader_measurement_v1/wp.php') + ';',
  'require ' + phpQuote(root + 'tests/reader_measurement_v1/store-double.php') + ';',
  'require ' + phpQuote(plugin + 'raos-reader-measurement.php') + ';',
  '$runtime=RAOS_Reader_Measurement::instance();',
  'echo $runtime->asset_tag("", "raos-reader-measurement-style");',
  'echo $runtime->asset_tag("", "raos-reader-measurement");',
].join(' ');
const assetTags = execFileSync(php, ['-r', assetProgram], {
  cwd: root,
  encoding: 'utf8',
  maxBuffer: 1024 * 1024,
});
const cssTag = assetTags.match(/<link[^>]+>/)?.[0];
const jsTag = assetTags.match(/<script[^>]+><\/script>/)?.[0];
assert.ok(cssTag, 'real PHP asset_tag() must emit the stylesheet tag');
assert.ok(jsTag, 'real PHP asset_tag() must emit the script tag');

const expectedAssets = {
  css: {
    url: origin + '/wp-content/plugins/raos-reader-measurement/assets/reader-measurement.css?ver=' + digest(cssBytes),
    integrity: integrity(cssBytes),
  },
  js: {
    url: origin + '/wp-content/plugins/raos-reader-measurement/assets/reader-measurement.js?ver=' + digest(jsBytes),
    integrity: integrity(jsBytes),
  },
};
assert.ok(cssTag.includes('href="' + expectedAssets.css.url + '"'));
assert.ok(cssTag.includes('integrity="' + expectedAssets.css.integrity + '"'));
assert.ok(cssTag.includes('crossorigin="anonymous"'));
assert.ok(jsTag.includes('src="' + expectedAssets.js.url + '"'));
assert.ok(jsTag.includes('integrity="' + expectedAssets.js.integrity + '"'));
assert.ok(jsTag.includes('crossorigin="anonymous"'));

const footer = off => execFileSync(
  php,
  [root + 'tests/reader_measurement_v1/runtime.php', '--footer', ...(off ? ['--off'] : [])],
  { cwd: root, encoding: 'utf8', maxBuffer: 1024 * 1024 },
);
const article = `<main class="raos-editorial-v2">
<span class="raos-reader-view" data-raos-article-id="${articleID}" hidden></span>
<h1>機内持ち込みスーツケース比較</h1>
<p>自分の条件を確認して候補を選ぶための、通信しない表示検査です。</p>
<p class="raos-contextual-related" data-journey-stage="compare"><a id="guide" href="/lightweight-carry-on-suitcase-under-3kg/" target="_blank">次の比較ガイドを見る</a></p>
<details id="reader-evidence"><summary>判断の根拠を確認する</summary><p>確認済みの根拠です。</p></details>
<details id="unknown-panel"><summary>未登録パネル</summary><p>計測対象ではありません。</p></details>
<a id="reference" href="https://store.ace.jp/shop/g/g01541-10/" target="_blank">公式出典を確認する</a>
<a id="unknown" href="https://unknown.invalid/private" target="_blank">未登録の参照先</a>
</main>`;
const baseStyle = '<style>html{overflow-wrap:anywhere}body{margin:0;padding:16px;font-family:system-ui,sans-serif}.raos-editorial-v2{max-width:800px;margin:auto}a{display:inline-block;margin:.35rem 0}</style>';
const documentFor = off => '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
  + '<title>Reader measurement isolated view</title>' + baseStyle + cssTag + '</head><body>'
  + article + footer(off) + jsTag + '</body></html>';

const browser = await firefox.launch({
  headless: true,
  ...(process.env.RAOS_READER_FIREFOX ? { executablePath: process.env.RAOS_READER_FIREFOX } : {}),
});
const screenshots = [];
const unexpectedRequests = [];
let networkPassthroughs = 0;

const settle = async page => page.evaluate(() => new Promise(resolve => {
  requestAnimationFrame(() => requestAnimationFrame(resolve));
}));

const createScenario = async ({ width = 390, off = false } = {}) => {
  const context = await browser.newContext({
    proxy: { server: 'http://127.0.0.1:9' },
    serviceWorkers: 'block',
    viewport: { width, height: 900 },
  });
  const received = [];
  const loadedAssets = new Set();
  const pageErrors = [];
  const consoleErrors = [];
  const requestFailures = [];
  const html = documentFor(off);

  // This handler is installed before newPage()/goto(). Every request is either
  // fulfilled from owned bytes or aborted; route.continue/fetch are forbidden.
  await context.route('**/*', async route => {
    const request = route.request();
    const requestURL = request.url();
    const url = new URL(requestURL);
    if (requestURL === expectedAssets.js.url) {
      loadedAssets.add('js');
      await route.fulfill({ status: 200, contentType: 'text/javascript', body: jsBytes });
    } else if (requestURL === expectedAssets.css.url) {
      loadedAssets.add('css');
      await route.fulfill({ status: 200, contentType: 'text/css', body: cssBytes });
    } else if (url.origin === origin && url.pathname === '/wp-json/raos-reader/v1/events') {
      let body = null;
      try { body = JSON.parse(request.postData() || 'null'); } catch { /* recorded as unknown below */ }
      const allowed = [
        ['decision_check_open', 'article_id,event_name,panel_id'],
        ['official_reference_open', 'article_id,event_name,source_ref'],
        ['guide_navigation', 'article_id,event_name,journey_stage,target_article_id'],
      ].some(([eventName, keys]) => body?.event_name === eventName
        && Object.keys(body).sort().join(',') === keys);
      received.push({ body, allowed, method: request.method() });
      await route.fulfill({
        status: allowed ? 202 : 400,
        contentType: 'application/json',
        body: JSON.stringify({ accepted: allowed }),
      });
    } else if (request.isNavigationRequest()) {
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: requestURL === pageURL ? html : '<!doctype html><html lang="ja"><title>Locally fulfilled target</title></html>',
      });
    } else {
      unexpectedRequests.push(requestURL);
      await route.abort('blockedbyclient');
    }
  });

  const page = await context.newPage();
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('requestfailed', request => requestFailures.push(request.url()));
  await page.goto(pageURL, { waitUntil: 'load' });
  await page.waitForFunction(() => document.getElementById('raos-reader-consent-settings')?.dataset.readerConsentBound === 'true');
  await settle(page);
  assert.deepEqual([...loadedAssets].sort(), ['css', 'js'], 'exact PHP asset tags must load both owned assets');
  assert.deepEqual(pageErrors, []);
  assert.deepEqual(consoleErrors, []);
  assert.deepEqual(requestFailures, []);
  return { context, page, received };
};

const assertAssetDOM = async page => {
  const actual = await page.evaluate(() => ({
    css: {
      url: document.getElementById('raos-reader-measurement-style-css')?.href,
      integrity: document.getElementById('raos-reader-measurement-style-css')?.integrity,
      crossorigin: document.getElementById('raos-reader-measurement-style-css')?.crossOrigin,
    },
    js: {
      url: document.getElementById('raos-reader-measurement-js')?.src,
      integrity: document.getElementById('raos-reader-measurement-js')?.integrity,
      crossorigin: document.getElementById('raos-reader-measurement-js')?.crossOrigin,
    },
  }));
  assert.deepEqual(actual, {
    css: { ...expectedAssets.css, crossorigin: 'anonymous' },
    js: { ...expectedAssets.js, crossorigin: 'anonymous' },
  });
  const style = await page.locator('#raos-reader-consent-settings').evaluate(element => {
    const computed = getComputedStyle(element);
    return { border: computed.borderTopStyle, background: computed.backgroundColor };
  });
  assert.deepEqual(style, { border: 'solid', background: 'rgb(255, 255, 255)' });
};

const assertNoHorizontalOverflow = async page => {
  const overflow = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
    offenders: [...document.querySelectorAll('body *')]
      .filter(element => element.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
      .map(element => element.id || element.tagName),
  }));
  assert.ok(overflow.scroll <= overflow.client + 1, JSON.stringify(overflow));
  assert.deepEqual(overflow.offenders, []);
};

const assertEqualChoicesAndKeyboard = async page => {
  const allow = page.locator('#raos-reader-consent-allow');
  const deny = page.locator('#raos-reader-consent-deny');
  const [allowBox, denyBox] = await Promise.all([allow.boundingBox(), deny.boundingBox()]);
  assert.ok(allowBox && denyBox);
  assert.ok(Math.abs(allowBox.width - denyBox.width) <= 1, 'allow and deny must have equal visual weight');
  assert.ok(Math.abs(allowBox.height - denyBox.height) <= 1, 'allow and deny must have equal visual weight');
  const visual = locator => locator.evaluate(element => {
    const style = getComputedStyle(element);
    return [style.backgroundColor, style.color, style.borderTopWidth, style.borderTopColor, style.fontSize, style.fontWeight];
  });
  assert.deepEqual(await visual(allow), await visual(deny));
  assert.ok(allowBox.height >= 44 && denyBox.height >= 44);

  await deny.focus();
  const outline = await deny.evaluate(element => getComputedStyle(element).outlineStyle);
  assert.notEqual(outline, 'none', 'keyboard focus must remain visible');
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'raos-reader-consent-reopen');
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(() => document.activeElement?.id), 'raos-reader-consent-allow');
};

const choose = async (page, value) => {
  const choicesHidden = await page.locator('#raos-reader-consent-choices').getAttribute('hidden');
  if (choicesHidden !== null) await page.locator('#raos-reader-consent-reopen').click();
  await page.locator('#raos-reader-consent-' + value).click();
};

const operate = async page => {
  await page.locator('#reader-evidence summary').click();
  await page.locator('#reference').click();
  await page.locator('#guide').click();
  await settle(page);
};

try {
  for (const width of viewports) {
    const scenario = await createScenario({ width });
    await assertAssetDOM(scenario.page);
    await assertEqualChoicesAndKeyboard(scenario.page);
    await assertNoHorizontalOverflow(scenario.page);
    const normal = `${artifactRelative}/consent-${width}px-100pct.png`;
    await scenario.page.screenshot({ path: root + normal, fullPage: true });
    screenshots.push(normal);

    await scenario.page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
    await settle(scenario.page);
    await assertNoHorizontalOverflow(scenario.page);
    const enlarged = `${artifactRelative}/consent-${width}px-200pct.png`;
    await scenario.page.screenshot({ path: root + enlarged, fullPage: true });
    screenshots.push(enlarged);
    await scenario.context.close();
  }

  const off = await createScenario({ off: true });
  await choose(off.page, 'allow');
  await operate(off.page);
  assert.equal(off.received.length, 0, 'the OFF profile must never POST');
  await off.context.close();

  const unselected = await createScenario();
  await operate(unselected.page);
  assert.equal(unselected.received.length, 0, 'unselected must never POST');
  await unselected.context.close();

  const denied = await createScenario();
  await choose(denied.page, 'deny');
  await operate(denied.page);
  assert.equal(denied.received.length, 0, 'denied must never POST');
  await denied.context.close();

  const revoked = await createScenario();
  await choose(revoked.page, 'allow');
  await revoked.page.locator('#raos-reader-consent-revoke').click();
  await operate(revoked.page);
  assert.equal(revoked.received.length, 0, 'revoked must never POST');
  await revoked.context.close();

  const allowed = await createScenario();
  await choose(allowed.page, 'allow');
  await operate(allowed.page);
  await allowed.page.waitForFunction(() => document.getElementById('raos-reader-user-status')?.textContent.includes('許可'));
  assert.equal(allowed.received.length, 3, 'allowed sends only the three registered operations');
  assert.ok(allowed.received.every(row => row.allowed && row.method === 'POST'));
  assert.deepEqual(allowed.received.map(row => row.body), [
    { event_name: 'decision_check_open', article_id: articleID, panel_id: 'reader-evidence' },
    { event_name: 'official_reference_open', article_id: articleID, source_ref: 'SRC-PROTECA-TRI-AIR-01541' },
    { event_name: 'guide_navigation', article_id: articleID, target_article_id: 'lightweight-carry-on-suitcase-under-3kg', journey_stage: 'compare' },
  ]);
  await allowed.page.locator('#unknown-panel summary').click();
  await allowed.page.locator('#unknown').click();
  await settle(allowed.page);
  assert.equal(allowed.received.length, 3, 'unknown panel and reference are rejected before POST');
  await allowed.context.close();

  assert.deepEqual(unexpectedRequests, []);
  const summary = {
    viewports,
    zoom_percent: 200,
    production_requests: networkPassthroughs,
    unexpected_requests: unexpectedRequests,
    screenshots,
  };
  console.log('BROWSER_VIEWS_JSON=' + JSON.stringify(summary));
  console.log('browser views OK (offline Firefox; fake owner consent only; no production/provider requests)');
} finally {
  await browser.close();
}
