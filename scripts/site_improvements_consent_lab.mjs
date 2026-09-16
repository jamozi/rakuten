/** Ephemeral consent checks, with passive requests only and aggregate host/category output. */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { refuseWhilePriceOverlayLiveUnlessPurged } from './raos_price_overlay_live_check.mjs';
const args = process.argv.slice(2),
  opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const origin = new URL(opt('--origin', 'https://kurashinoshirube.com')).origin;
const output = opt('--output', 'output/site-improvements-20260913/consent-lab-baseline.json');
// Contract §8: a capture while Rakuten price overlay values may be published stores the
// rendered prices and their hashes. The destination decides, not the origin: the candidate
// preview docker serves the injected bodies on 127.0.0.1 too, so a rendering may only be kept
// while values are live where the §5 purge sweep reaches it.
await refuseWhilePriceOverlayLiveUnlessPurged([resolve(output)]);
const { chromium } = await import('playwright');
const browser = await chromium.launch({ headless: true });
const flows = [];
const category = (u) =>
  /google-analytics\.com|googletagmanager\.com|analytics\.google\.com/.test(u.hostname)
    ? u.pathname.includes('collect')
      ? 'google_measurement'
      : 'google_tag'
    : /cookieyes/.test(u.hostname)
      ? 'consent_management'
      : /rakuten/.test(u.hostname)
        ? u.hostname.startsWith('hbb.')
          ? 'affiliate_image_endpoint'
          : 'product_image_host'
        : u.origin === origin
          ? 'first_party'
          : 'other_external';
async function consentFlow(choice) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  let phase = 'initial';
  const requests = [];
  page.on('request', (r) => {
    const u = new URL(r.url());
    if (['http:', 'https:'].includes(u.protocol))
      requests.push({ phase, host: u.hostname, category: category(u), method: r.method() });
  });
  const snapshots = [];
  const snapshot = async (label) => {
    await page.waitForTimeout(2500);
    const cookies = await context.cookies();
    snapshots.push({
      phase: label,
      requests: [
        ...new Map(
          requests
            .filter((r) => r.phase === label)
            .map((r) => [r.host + '|' + r.category + '|' + r.method, r]),
        ).values(),
      ],
      cookie_names: [...new Set(cookies.map((c) => c.name.replace(/^_ga_.+$/, '_ga_*')))].sort(),
      ga_cookie_present: cookies.some((c) => c.name.startsWith('_ga')),
      google_tag_element_present: await page.locator('script[src*="googletagmanager.com"]').count(),
      input_values_used: false,
    });
  };
  try {
    await page.goto(origin + '/privacy-policy/', { waitUntil: 'domcontentloaded', timeout: 45000 });
    await snapshot('initial');
    phase = choice;
    const selector =
      choice === 'reject'
        ? '.cky-consent-container .cky-btn-reject'
        : '.cky-consent-container .cky-btn-accept';
    const button = page.locator(selector).first();
    if (await button.isVisible()) {
      await button.click();
      await snapshot(phase);
    } else {
      snapshots.push({ phase, status: 'CONTROL_NOT_VISIBLE' });
    }
    if (choice === 'grant') {
      phase = 'withdraw';
      const revisit = page.locator('.cky-btn-revisit');
      await revisit.waitFor({ state: 'visible', timeout: 5000 });
      await revisit.click();
      await page
        .locator('.cky-btn-reject:visible')
        .last()
        .waitFor({ state: 'visible', timeout: 5000 });
      snapshots.push({
        phase: 'withdraw_control',
        method: 'CookieYes floating revisit button',
      });
      const reject = page.locator('.cky-btn-reject:visible').last();
      if (await reject.isVisible()) {
        await reject.click();
        await snapshot('withdraw');
      } else snapshots.push({ phase, status: 'WITHDRAW_CONTROL_NOT_VISIBLE' });
    }
    phase = 'revisit';
    await page.reload({ waitUntil: 'domcontentloaded' });
    await snapshot('revisit');
    flows.push({ choice, snapshots });
  } catch (e) {
    flows.push({ choice, snapshots, error_type: e.name });
  } finally {
    await context.close();
  }
}
const lab = [];
try {
  await consentFlow('reject');
  await consentFlow('grant');
  for (const path of [
    '/',
    '/countertop-dishwasher-for-small-households/',
    '/dishwasher-installation-measurement/',
  ]) {
    const c = await browser.newContext({
      viewport: { width: 390, height: 844 },
      serviceWorkers: 'block',
    });
    const p = await c.newPage();
    await p.addInitScript(() => {
      window.__raosLab = { lcp_ms: null, cls: 0 };
      try {
        new PerformanceObserver((l) => {
          for (const e of l.getEntries()) window.__raosLab.lcp_ms = e.startTime;
        }).observe({ type: 'largest-contentful-paint', buffered: true });
        new PerformanceObserver((l) => {
          for (const e of l.getEntries()) if (!e.hadRecentInput) window.__raosLab.cls += e.value;
        }).observe({ type: 'layout-shift', buffered: true });
      } catch {}
    });
    try {
      await p.goto(origin + path, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await p.waitForTimeout(5000);
      lab.push({ path, ...(await p.evaluate(() => window.__raosLab)) });
    } catch (e) {
      lab.push({ path, error_type: e.name });
    } finally {
      await c.close();
    }
  }
  const report = {
    schema: 'RAOSPassiveConsentLabV1',
    origin,
    checked_at: new Date().toISOString(),
    node: process.version,
    flows,
    lab,
    limitations: [
      'Ephemeral browser state only; consent choices are local visitor interactions. No administrative/provider settings changed.',
      'Only aggregate host/category/method and cookie names saved; no cookie values, query values, event payloads, or user/account identifiers.',
      'No affiliate clicks, purchase events, remote form submissions, or invented analytics properties.',
      'LCP/CLS are a single unthrottled headless Chromium lab observation at390px, not field Core Web Vitals or a Lighthouse score.',
      'An absence of observed requests during the bounded window is not proof of all future behavior.',
      'Cookie presence/absence and network sending are reported separately.',
    ],
    GSC: 'UNAVAILABLE',
    GA4_account_settings: 'UNAVAILABLE',
    ASP_earnings: 'UNAVAILABLE',
  };
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
} finally {
  await browser.close();
}
