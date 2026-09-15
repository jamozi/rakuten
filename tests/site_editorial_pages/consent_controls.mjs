import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';
const root = new URL('../../', import.meta.url);
const asset = 'changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/';
const script = readFileSync(new URL(asset + 'consent-controls.js', root), 'utf8');
const css = readFileSync(new URL(asset + 'theme.css', root), 'utf8');
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.setContent(`<a href="/privacy-policy/" class="cky-banner-element">Cookie設定を変更</a><button class="cky-btn-revisit">設定を再表示</button>
  <div class="cky-modal" style="position:fixed;left:50%;top:257px;width:368px"><div class="cky-preference-center" style="background:white;display:none"><header class="cky-preference-header">設定</header><div class="cky-preference-body-wrapper"><div style="height:950px">任意カテゴリはオフのまま</div></div><footer class="cky-footer-wrapper"><div class="cky-prefrence-btn-wrapper"><button class="cky-btn cky-btn-reject">すべて拒否</button></div></footer></div></div>`);
  await page.addStyleTag({ content: css });
  await page.evaluate(() => {
    document.querySelector('.cky-btn-revisit').addEventListener('click', () => {
      document.querySelector('.cky-preference-center').style.display = 'flex';
      document.body.dataset.opened = 'true';
    });
  });
  await page.addScriptTag({ content: script });
  await page.locator('a.cky-banner-element').click();
  assert.equal(await page.getAttribute('body', 'data-opened'), 'true');
  assert.equal(page.url(), 'about:blank');
  const box = await page.locator('.cky-btn-reject').boundingBox();
  assert.ok(box && box.y >= 0 && box.y + box.height <= 844, JSON.stringify(box));
  assert.deepEqual(await page.context().cookies(), []);
  const fallback = await page.evaluate(() => {
    document.querySelector('.cky-btn-revisit').remove();
    const event = new MouseEvent('click', { bubbles: true, cancelable: true });
    document.querySelector('.cky-banner-element').dispatchEvent(event);
    return !event.defaultPrevented;
  });
  assert.equal(fallback, true);
  console.log('Consent controls PASS: opens provider UI; no navigation, cookie change, or clipped reject; fallback retained.');
} finally { await browser.close(); }
