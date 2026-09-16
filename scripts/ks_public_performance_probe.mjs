// KS-030: read-only lab performance and degraded-state readability probe for the public site.
//
// Usage: node scripts/ks_public_performance_probe.mjs [--out DIR] [--origin URL] [--runs N] [--only /path/]
// Output: DIR/performance-probe.json (+ first-viewport screenshots of run 1 under DIR/screens).
//
// Load count: 4 pages x 2 widths x 3 runs x 4 states = 96 page loads, run sequentially, a new
// browser context (empty cache, no cookies) for every load. GET only; consent is never granted and
// no link is clicked. Rakuten ad image hosts are aborted in EVERY state (owner decision 2026-09-15).
//
// States:
//   'normal'        ad image hosts aborted, everything else loads
//   'images-failed' every request of resource type image is aborted (any host)
//   'js-disabled'   javaScriptEnabled:false
//   'slow-network'  DevTools Network.emulateNetworkConditions with SLOW_NETWORK below (request-level
//                   emulation, not packet-level)
// Metrics: TTFB = navigation responseStart, FCP = paint entry, LCP = last largest-contentful-paint
// DevTools timeline event, CLS = largest session window (1 s gap / 5 s cap) of layout-shift timeline
// events without recent input. All are observed until load + OBSERVE_AFTER_LOAD_MS with no scrolling
// or input. INP needs interaction and is not measured. Values are single-environment lab observations
// and this script does not judge them against any threshold.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { refuseWhilePriceOverlayLiveUnlessPurged } from './raos_price_overlay_live_check.mjs';

const require = createRequire(import.meta.url);

const PAGES = ['/', '/standard-dishwasher-comparison/', '/dishwasher-installation-measurement/', '/dishwasher-running-cost/'];
const WIDTHS = [390, 1280];
const VIEWPORTS = { 390: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true }, 1280: { width: 1280, height: 900, deviceScaleFactor: 1, isMobile: false } };
const STATES = ['normal', 'images-failed', 'js-disabled', 'slow-network'];
const BLOCKED_AD_HOSTS = ['hbb.afl.rakuten.co.jp', 'hb.afl.rakuten.co.jp'];
const SLOW_NETWORK = { offline: false, latency: 150, downloadThroughput: Math.round((1600 * 1024) / 8), uploadThroughput: Math.round((750 * 1024) / 8) };
const OBSERVE_AFTER_LOAD_MS = 3000;

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
};
const ORIGIN = option('--origin', 'https://kurashinoshirube.com');
if (!/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(ORIGIN) && ORIGIN !== 'https://kurashinoshirube.com') throw new Error('ORIGIN_NOT_ALLOWED');
const OUT = option('--out', 'output/ks-20260915/w2-measure/ks-030');
// Contract §8: a capture while Rakuten price overlay values may be published stores the
// rendered prices and their hashes. The destination decides, not the origin: the candidate
// preview docker serves the injected bodies on 127.0.0.1 too, so a rendering may only be kept
// while values are live where the §5 purge sweep reaches it.
await refuseWhilePriceOverlayLiveUnlessPurged([path.resolve(OUT)]);
const { chromium } = require('playwright');
const RUNS = Number(option('--runs', '3'));
const ONLY = option('--only', '');
const pages = ONLY ? ONLY.split(',') : PAGES;
const SCREENS = path.join(OUT, 'screens');
fs.mkdirSync(SCREENS, { recursive: true });
const pageKey = (p) => (p === '/' ? 'home' : p.replace(/^\/|\/$/g, ''));

function clsFromShifts(shifts) {
  let best = 0;
  let current = 0;
  let first = null;
  let last = null;
  for (const shift of shifts.filter((item) => !item.hadRecentInput).sort((a, b) => a.time - b.time)) {
    if (first !== null && shift.time - last < 1000 && shift.time - first < 5000) {
      current += shift.value;
    } else {
      current = shift.value;
      first = shift.time;
    }
    last = shift.time;
    best = Math.max(best, current);
  }
  return Number(best.toFixed(4));
}

const median = (values) => {
  const list = values.filter((value) => typeof value === 'number').sort((a, b) => a - b);
  if (!list.length) return null;
  const mid = Math.floor(list.length / 2);
  return list.length % 2 ? list[mid] : (list[mid - 1] + list[mid]) / 2;
};

function readability() {
  const main = document.querySelector('main') || document.body;
  const text = main.innerText || '';
  const imgs = [...document.querySelectorAll('main img, article img, .entry-content img')];
  const shown = (el) => el && el.getClientRects().length > 0 && getComputedStyle(el).display !== 'none' && getComputedStyle(el).visibility !== 'hidden';
  const priceStates = {};
  for (const el of document.querySelectorAll('[data-ps-price-state]')) priceStates[el.getAttribute('data-ps-price-state')] = (priceStates[el.getAttribute('data-ps-price-state')] || 0) + 1;
  const external = [...document.querySelectorAll('main a[href^="http"], article a[href^="http"]')].filter((a) => new URL(a.href).origin !== location.origin);
  return {
    h1: (document.querySelector('h1')?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60),
    mainTextChars: text.length,
    tables: main.querySelectorAll('table').length,
    tableRows: main.querySelectorAll('tr').length,
    figcaptions: main.querySelectorAll('figcaption').length,
    images: imgs.length,
    imagesBroken: imgs.filter((img) => img.complete && img.naturalWidth === 0).length,
    externalLinks: external.length,
    adLabelMentions: (text.match(/広告/g) || []).length,
    priceStates,
    expiredPriceWording: (text.match(/確認期限切れ/g) || []).length,
    noScriptNoticeShown: shown(document.querySelector('.raos-cost-no-script')),
    budgetControlsShown: shown(document.querySelector('.ps-budget-controls')),
  };
}

async function loadOnce(browser, pagePath, width, state, run) {
  const viewport = VIEWPORTS[width];
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: viewport.deviceScaleFactor,
    isMobile: viewport.isMobile,
    hasTouch: viewport.isMobile,
    javaScriptEnabled: state !== 'js-disabled',
  });
  const aborted = { adHost: 0, image: 0 };
  const externalHosts = {};
  await context.route('**/*', (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (BLOCKED_AD_HOSTS.includes(url.hostname)) {
      aborted.adHost += 1;
      return route.abort();
    }
    if (state === 'images-failed' && request.resourceType() === 'image') {
      aborted.image += 1;
      return route.abort();
    }
    if (url.protocol.startsWith('http') && url.origin !== ORIGIN) externalHosts[url.hostname] = (externalHosts[url.hostname] || 0) + 1;
    return route.continue();
  });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  const events = [];
  cdp.on('PerformanceTimeline.timelineEventAdded', (event) => events.push(event.event));
  await cdp.send('PerformanceTimeline.enable', { eventTypes: ['largest-contentful-paint', 'layout-shift'] });
  if (state === 'slow-network') {
    await cdp.send('Network.enable');
    await cdp.send('Network.emulateNetworkConditions', SLOW_NETWORK);
  }
  const row = { page: pagePath, width, state, run, startedAt: new Date().toISOString(), aborted, externalHosts };
  try {
    const response = await page.goto(new URL(pagePath, ORIGIN).href, { waitUntil: 'load', timeout: 180000 });
    const headers = response ? response.headers() : {};
    row.status = response ? response.status() : null;
    row.headers = { 'content-encoding': headers['content-encoding'] || null, 'cache-control': headers['cache-control'] || null, 'content-type': headers['content-type'] || null };
    await page.waitForTimeout(OBSERVE_AFTER_LOAD_MS);
    const nav = await page.evaluate(() => {
      const entry = performance.getEntriesByType('navigation')[0];
      const fcp = performance.getEntriesByName('first-contentful-paint')[0];
      const resources = performance.getEntriesByType('resource');
      return {
        timeOrigin: performance.timeOrigin,
        ttfbMs: entry ? entry.responseStart : null,
        requestToResponseStartMs: entry ? entry.responseStart - entry.requestStart : null,
        domContentLoadedMs: entry ? entry.domContentLoadedEventEnd : null,
        loadMs: entry ? entry.loadEventEnd : null,
        fcpMs: fcp ? fcp.startTime : null,
        documentTransferBytes: entry ? entry.transferSize : null,
        documentEncodedBytes: entry ? entry.encodedBodySize : null,
        documentDecodedBytes: entry ? entry.decodedBodySize : null,
        resourceCount: resources.length,
        resourceTransferBytes: resources.reduce((sum, item) => sum + (item.transferSize || 0), 0),
      };
    });
    Object.assign(row, nav);
    const lcpEvents = events.filter((event) => event.type === 'largest-contentful-paint');
    const lastLcp = lcpEvents.at(-1);
    row.lcpMs = lastLcp ? Math.round(((lastLcp.lcpDetails.renderTime || lastLcp.lcpDetails.loadTime) * 1000 - nav.timeOrigin) * 10) / 10 : null;
    row.lcpSize = lastLcp ? lastLcp.lcpDetails.size : null;
    row.lcpUrl = lastLcp && lastLcp.lcpDetails.url ? String(lastLcp.lcpDetails.url).slice(0, 120) : null;
    const shifts = events.filter((event) => event.type === 'layout-shift').map((event) => ({ value: event.layoutShiftDetails.value, hadRecentInput: event.layoutShiftDetails.hadRecentInput, time: event.time * 1000 - nav.timeOrigin }));
    row.layoutShiftCount = shifts.length;
    row.cls = clsFromShifts(shifts);
    row.readability = await page.evaluate(readability);
    if (run === 1) {
      const file = path.join(SCREENS, `${pageKey(pagePath)}__${width}__${state}.jpg`);
      await page.screenshot({ path: file, type: 'jpeg', quality: 60 });
      row.shot = { file: path.relative(OUT, file), sha256: crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') };
    }
  } catch (error) {
    row.error = String(error.message).slice(0, 160);
  }
  await context.close();
  return row;
}

const browser = await chromium.launch({ headless: true, executablePath: process.env.KS_CHROME || '/opt/google/chrome/chrome' });
const startedAt = new Date().toISOString();
const results = [];
try {
  for (let run = 1; run <= RUNS; run += 1) {
    for (const width of WIDTHS) {
      for (const pagePath of pages) {
        for (const state of STATES) {
          const row = await loadOnce(browser, pagePath, width, state, run);
          results.push(row);
          process.stderr.write(`${results.length} run${run} ${width} ${state} ${pagePath} ttfb=${row.ttfbMs?.toFixed?.(0)} fcp=${row.fcpMs?.toFixed?.(0)} lcp=${row.lcpMs} cls=${row.cls} ${row.error || ''}\n`);
        }
      }
    }
  }
  const summary = [];
  for (const pagePath of pages) {
    for (const width of WIDTHS) {
      for (const state of STATES) {
        const rows = results.filter((row) => row.page === pagePath && row.width === width && row.state === state && !row.error);
        const stat = (key) => {
          const values = rows.map((row) => row[key]).filter((value) => typeof value === 'number');
          return values.length ? { median: median(values), min: Math.min(...values), max: Math.max(...values), n: values.length } : { median: null, n: 0 };
        };
        summary.push({ page: pagePath, width, state, runs: rows.length, ttfbMs: stat('ttfbMs'), fcpMs: stat('fcpMs'), lcpMs: stat('lcpMs'), cls: stat('cls'), documentTransferBytes: stat('documentTransferBytes'), readability: rows[0]?.readability || null, headers: rows[0]?.headers || null });
      }
    }
  }
  const output = {
    tool: 'scripts/ks_public_performance_probe.mjs',
    startedAt,
    finishedAt: new Date().toISOString(),
    origin: ORIGIN,
    browser: `chrome ${browser.version()}`,
    playwright: require('playwright/package.json').version,
    anonymous: true,
    consentGranted: false,
    cacheBetweenLoads: 'none (new context per load)',
    cpuThrottling: 'none',
    observeAfterLoadMs: OBSERVE_AFTER_LOAD_MS,
    blockedAdHostsEveryState: BLOCKED_AD_HOSTS,
    slowNetwork: SLOW_NETWORK,
    viewports: VIEWPORTS,
    states: STATES,
    pages,
    runs: RUNS,
    loads: results.length,
    errors: results.filter((row) => row.error).map((row) => `${row.page} ${row.width} ${row.state} run${row.run}: ${row.error}`),
    summary,
    results,
  };
  fs.writeFileSync(path.join(OUT, 'performance-probe.json'), JSON.stringify(output, null, 1));
  process.stdout.write(JSON.stringify({ out: path.join(OUT, 'performance-probe.json'), loads: results.length, errors: output.errors }, null, 1) + '\n');
} finally {
  await browser.close();
}
