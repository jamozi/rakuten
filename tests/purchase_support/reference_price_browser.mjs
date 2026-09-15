import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';

const source = fs.readFileSync(process.argv[2], 'utf8');
const ref = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const start = Date.parse(ref.checked_at);
const escapeAttribute = value => value.replaceAll('&', '&amp;').replaceAll('"', '&quot;');
const html = '<div class="ps-article">' + Array.from({length:4}, (_, i) =>
  `<section><p class="ps-reference-price" data-ps-reference-price="${escapeAttribute(JSON.stringify({...ref, valid_until:new Date(start + 1000).toISOString()}))}">価格は販売先で確認</p><a href="#product-${i}">楽天で見る</a></section>`).join('') + '</div>';
const browser = await chromium.launch();
try {
  const nojs = await browser.newContext({javaScriptEnabled:false});
  const staticPage = await nojs.newPage();
  await staticPage.setContent(html + '<script>' + source + '</script>');
  assert.doesNotMatch(await staticPage.locator('body').innerText(), /29,800|29800/);
  assert.equal(await staticPage.getByRole('link').count(), 4);
  await nojs.close();

  const page = await browser.newPage();
  const errors = [], requests = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('request', r => requests.push(r.url()));
  await page.clock.install({time:new Date(start - 10000)});
  await page.clock.pauseAt(new Date(start));
  await page.setContent(html);
  await page.addScriptTag({content:source});
  assert.equal(await page.getByText(/参考価格 29,800円/).count(), 4);
  await page.clock.runFor(999);
  assert.equal(await page.getByText(/参考価格 29,800円/).count(), 4);
  await page.clock.runFor(1);
  assert.equal(await page.getByText(/参考価格 29,800円/).count(), 0);
  assert.equal(await page.getByRole('link').count(), 4);
  await page.clock.setSystemTime(new Date(start + 86400000 * 2));
  for (const event of ['pageshow', 'focus']) await page.evaluate(event => window.dispatchEvent(new Event(event)), event);
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  assert.equal(await page.getByText(/参考価格 29,800円/).count(), 0);
  // A stale cached page loaded afresh must also have no visible price.
  await page.setContent(html);
  await page.addScriptTag({content:source});
  assert.equal(await page.getByText(/参考価格 29,800円/).count(), 0);
  assert.equal(await page.getByRole('link').count(), 4);
  assert.deepEqual(errors, []);
  assert.deepEqual(requests, []);
} finally {
  await browser.close();
}
