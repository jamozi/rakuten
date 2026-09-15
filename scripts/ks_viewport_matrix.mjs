// KS-017: read-only viewport / text-enlargement / keyboard-focus matrix for the public site.
//
// Usage: node scripts/ks_viewport_matrix.mjs [--out DIR] [--origin URL] [--concurrency N]
//        [--only /path/,/path2/] [--no-keyboard] [--no-screens]
// Output: DIR/viewport-matrix.json (+ screenshots under DIR/screens, sha256 in the JSON manifest).
// GET only. Never grants cookie consent and never clicks links. Rakuten ad image hosts are
// aborted in every run (owner decision 2026-09-15, Q22) and the abort counts are recorded.
//
// Modes:
//   w<width>      desktop emulation, viewport <width> x 900, deviceScaleFactor 1
//   zoom200-640   640 x 450 CSS px, deviceScaleFactor 2 = a 1280 x 900 window at 200% browser zoom
//   tsa200-<w>    mobile emulation (isMobile, hasTouch, DSF 2) with html{text-size-adjust:200%}.
//                 Root font-size is NOT used: the theme sets many sizes in px, which root font-size
//                 does not scale. The script records the measured px of a body paragraph and a table
//                 cell before/after so the enlargement actually applied is visible in the output.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const WIDTHS = [320, 375, 390, 640, 768, 1280, 1440];
const BLOCKED_AD_HOSTS = ['hbb.afl.rakuten.co.jp', 'hb.afl.rakuten.co.jp'];
const SCROLL_INSTRUCTION = 'スクロール|左右に動かせ|横に動かせ|スワイプ';
// Representative sample for the keyboard walk and the full-page screenshots.
const KEYBOARD_PAGES = ['/', '/kitchen/', '/large-dishwasher-comparison/', '/small-carry-on-suitcase-comparison/', '/dishwasher-running-cost/', '/privacy-policy/'];
const KEYBOARD_WIDTHS = [390, 1280];
const KEYBOARD_STOPS = 5;
// Anonymous visitors get the consent banner first; also record the first stops outside it (consent is never granted).
const CONSENT_BANNER = '.cky-consent-container';
const MAX_TAB_PRESSES = 40;
// The 39 production pages (20 posts + 19 pages) as of 2026-09-15.
const PAGES = ['/', '/travel/', '/kitchen/', '/cleaning/', '/preparedness/', '/categories/', '/small-space/', '/save-housework/', '/without-installation/', '/easy-maintenance/', '/comfortable-travel/', '/prepare-outage/', '/purposes/', '/guides/', '/comparisons/', '/updates/', '/carry-on-suitcase-comparison/', '/carry-on-suitcase-under-100-seats/', '/lightweight-carry-on-suitcase-under-3kg/', '/front-open-carry-on-suitcase-with-stopper/', '/countertop-dishwasher-for-small-households/', '/solota-vs-rakua-mini-plus/', '/dishwasher-installation-measurement/', '/dishwasher-water-supply-methods/', '/dishwasher-detergent-guide/', '/dishwasher-cleaning-guide/', '/dishwasher-running-cost/', '/compact-robot-vacuum-shortlist/', '/roomba-mini-vs-switchbot-k11-pro/', '/portable-power-station-guide/', '/anker-solix-c300-c800-c1000-differences/', '/about-ad-policy/', '/comparison-policy/', '/privacy-policy/', '/compact-dishwasher-comparison/', '/standard-dishwasher-comparison/', '/large-dishwasher-comparison/', '/dishwasher-branch-faucet-guide/', '/small-carry-on-suitcase-comparison/'];

const MODES = [
  ...WIDTHS.map((width) => ({ id: `w${width}`, width, height: 900, deviceScaleFactor: 1, isMobile: false })),
  { id: 'zoom200-640', width: 640, height: 450, deviceScaleFactor: 2, isMobile: false },
  { id: 'tsa200-320', width: 320, height: 640, deviceScaleFactor: 2, isMobile: true, textSizeAdjust: 200 },
  { id: 'tsa200-390', width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, textSizeAdjust: 200 },
];

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
};
const ORIGIN = option('--origin', 'https://kurashinoshirube.com');
if (!/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(ORIGIN) && ORIGIN !== 'https://kurashinoshirube.com') throw new Error('ORIGIN_NOT_ALLOWED');
const OUT = option('--out', 'output/ks-20260915/w2-measure/ks-017');
const CONCURRENCY = Number(option('--concurrency', '3'));
const ONLY = option('--only', '');
const pages = ONLY ? ONLY.split(',') : PAGES;
const withKeyboard = !args.includes('--no-keyboard');
const withScreens = !args.includes('--no-screens');
const SCREENS = path.join(OUT, 'screens');
fs.mkdirSync(SCREENS, { recursive: true });

const pageKey = (p) => (p === '/' ? 'home' : p.replace(/^\/|\/$/g, '').replace(/\//g, '_'));
const blocked = Object.fromEntries(BLOCKED_AD_HOSTS.map((host) => [host, 0]));
const externalHosts = {};
const manifest = [];

async function saveShot(page, name, options) {
  if (!withScreens) return null;
  const file = path.join(SCREENS, name);
  try {
    await page.screenshot({ path: file, ...options });
    const sha256 = crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
    manifest.push({ file: path.relative(OUT, file), sha256, bytes: fs.statSync(file).size });
    return path.relative(OUT, file);
  } catch (error) {
    return `SCREENSHOT_FAILED: ${String(error.message).slice(0, 80)}`;
  }
}

async function newContext(browser, mode) {
  const context = await browser.newContext({
    viewport: { width: mode.width, height: mode.height },
    deviceScaleFactor: mode.deviceScaleFactor,
    isMobile: mode.isMobile,
    hasTouch: mode.isMobile,
    reducedMotion: 'reduce',
  });
  await context.route('**/*', (route) => {
    const url = new URL(route.request().url());
    if (BLOCKED_AD_HOSTS.includes(url.hostname)) {
      blocked[url.hostname] += 1;
      return route.abort();
    }
    if (url.protocol.startsWith('http') && url.origin !== ORIGIN) externalHosts[url.hostname] = (externalHosts[url.hostname] || 0) + 1;
    return route.continue();
  });
  return context;
}

// Runs inside the page. Everything here is read-only except `details.open` in the second phase.
function analyse(pattern) {
  const re = new RegExp(pattern);
  const root = document.documentElement;
  const vw = root.clientWidth;
  const describe = (el) => {
    if (!el || !el.tagName) return String(el);
    const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    return `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${cls ? '.' + cls : ''}`;
  };
  const snippet = (el) => (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40);
  const visible = (el) => {
    if (!el.getClientRects().length) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && Number(cs.opacity) !== 0;
  };
  const visuallyHidden = (el, rect) => {
    const cs = getComputedStyle(el);
    return (rect.width <= 1 && rect.height <= 1) || /inset\(50%\)/.test(cs.clipPath) || cs.clip === 'rect(0px, 0px, 0px, 0px)';
  };
  const scrollables = (el) => [el, ...el.querySelectorAll('*')].filter((node) => node.scrollWidth - node.clientWidth > 1 && /(auto|scroll)/.test(getComputedStyle(node).overflowX));

  // 1. Page-level horizontal overflow outside tables and outside scroll/clip containers.
  const offenders = [];
  const counts = { inTable: 0, inScrollContainer: 0, clipped: 0, fixed: 0, visuallyHidden: 0 };
  for (const el of document.body.querySelectorAll('*')) {
    if (/^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|BR)$/.test(el.tagName)) continue;
    const rect = el.getBoundingClientRect();
    if (!rect.width && !rect.height) continue;
    if (!(rect.right > vw + 1 || rect.left < -1)) continue;
    if (!visible(el)) continue;
    if (visuallyHidden(el, rect)) { counts.visuallyHidden += 1; continue; }
    if (el.closest('table')) { counts.inTable += 1; continue; }
    let container = null;
    let fixed = getComputedStyle(el).position === 'fixed';
    for (let node = el.parentElement; node && node !== document.body && node !== root; node = node.parentElement) {
      const cs = getComputedStyle(node);
      if (cs.position === 'fixed') fixed = true;
      if (!container && cs.overflowX !== 'visible') container = { node, overflowX: cs.overflowX };
    }
    if (fixed) { counts.fixed += 1; continue; }
    if (container && /(auto|scroll)/.test(container.overflowX)) { counts.inScrollContainer += 1; continue; }
    if (container) { counts.clipped += 1; continue; }
    const parent = el.parentElement;
    const parentRect = parent && parent !== document.body ? parent.getBoundingClientRect() : null;
    if (parentRect && (parentRect.right > vw + 1 || parentRect.left < -1)) continue; // keep outermost offender only
    offenders.push({ el: describe(el), text: snippet(el), left: Math.round(rect.left), right: Math.round(rect.right), width: Math.round(rect.width) });
  }

  // 2. Scroll instructions: DOM text, aria-label/title, ::before/::after content, and stylesheet rules.
  const instructions = [];
  const addInstruction = (source, el, text, shown) => {
    let regions = scrollables(el);
    if (!regions.length) {
      let sibling = el.nextElementSibling;
      for (let i = 0; i < 3 && sibling && !regions.length; i += 1, sibling = sibling.nextElementSibling) regions = scrollables(sibling);
    }
    if (!regions.length && el.parentElement) regions = scrollables(el.parentElement);
    const inTableOnly = regions.length > 0 && regions.every((node) => node.querySelector('table') || node.closest('table'));
    instructions.push({ source, el: describe(el), text: text.slice(0, 60), shown, regionScrolls: regions.length > 0, scrollingRegionHasTable: inTableOnly });
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const parent = node.parentElement;
    if (!parent || seen.has(parent) || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(parent.tagName)) continue;
    if (!re.test(node.nodeValue)) continue;
    seen.add(parent);
    addInstruction('dom-text', parent, node.nodeValue.replace(/\s+/g, ' ').trim(), visible(parent));
  }
  for (const el of document.body.querySelectorAll('[aria-label],[title]')) {
    for (const attr of ['aria-label', 'title']) {
      const value = el.getAttribute(attr);
      if (value && re.test(value)) addInstruction(attr, el, value, visible(el));
    }
  }
  for (const el of document.body.querySelectorAll('*')) {
    for (const pseudo of ['::before', '::after']) {
      const cs = getComputedStyle(el, pseudo);
      if (!cs.content || cs.content === 'none' || cs.content === 'normal') continue;
      if (!re.test(cs.content)) continue;
      addInstruction(`css${pseudo}`, el, cs.content, visible(el) && cs.display !== 'none' && cs.visibility !== 'hidden');
    }
  }
  const cssRules = [];
  const walkRules = (rules, media, href) => {
    for (const rule of rules) {
      if (rule.cssRules && !rule.selectorText) walkRules(rule.cssRules, rule.conditionText || rule.media?.mediaText || media, href);
      else if (rule.style && re.test(rule.style.getPropertyValue('content') || '')) cssRules.push({ selector: rule.selectorText, media: media || '', content: rule.style.getPropertyValue('content'), sheet: href });
    }
  };
  for (const sheet of document.styleSheets) {
    try { walkRules(sheet.cssRules, '', sheet.href ? new URL(sheet.href).pathname : `inline:${describe(sheet.ownerNode)}`); } catch { cssRules.push({ sheet: sheet.href, error: 'CSSOM_NOT_READABLE' }); }
  }

  // 3. Actual horizontal scroll regions, for context.
  const regions = [...document.body.querySelectorAll('*')].filter((node) => node.scrollWidth - node.clientWidth > 1 && /(auto|scroll)/.test(getComputedStyle(node).overflowX) && visible(node));
  return {
    viewportCssWidth: vw,
    docOverflow: root.scrollWidth - vw,
    rootOverflowX: `${getComputedStyle(root).overflowX}/${getComputedStyle(document.body).overflowX}`,
    offenders: offenders.slice(0, 12),
    offenderCount: offenders.length,
    excluded: counts,
    instructions,
    cssRules,
    scrollRegions: regions.map((node) => ({ el: describe(node), overflowPx: node.scrollWidth - node.clientWidth, hasTable: Boolean(node.querySelector('table')) })).slice(0, 20),
    scrollRegionCount: regions.length,
  };
}

function sampleFontSizes() {
  const pick = (selector) => [...document.querySelectorAll(selector)].find((el) => el.getClientRects().length && (el.textContent || '').trim().length > 10);
  const para = pick('main p, .entry-content p, article p');
  const cell = pick('main td, .entry-content td, article td');
  return { paragraphPx: para ? parseFloat(getComputedStyle(para).fontSize) : null, tableCellPx: cell ? parseFloat(getComputedStyle(cell).fontSize) : null };
}

async function measure(context, mode, pagePath) {
  const page = await context.newPage();
  const row = { page: pagePath, mode: mode.id, width: mode.width, deviceScaleFactor: mode.deviceScaleFactor, isMobile: mode.isMobile };
  try {
    const response = await page.goto(new URL(pagePath, ORIGIN).href, { waitUntil: 'load', timeout: 90000 });
    row.status = response ? response.status() : null;
    if (mode.textSizeAdjust) {
      row.fontBefore = await page.evaluate(sampleFontSizes);
      await page.addStyleTag({ content: `html{-webkit-text-size-adjust:${mode.textSizeAdjust}% !important;text-size-adjust:${mode.textSizeAdjust}% !important}` });
      await page.waitForTimeout(300);
      row.fontAfter = await page.evaluate(sampleFontSizes);
    } else {
      row.fontAfter = await page.evaluate(sampleFontSizes);
    }
    await page.evaluate(async () => {
      const step = Math.max(500, innerHeight);
      for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
        scrollTo(0, y);
        await new Promise((resolve) => setTimeout(resolve, 60));
      }
      scrollTo(0, 0);
    });
    await page.waitForTimeout(400);
    row.asLoaded = await page.evaluate(analyse, SCROLL_INSTRUCTION);
    const shouldShoot = row.asLoaded.docOverflow > 0 || row.asLoaded.offenderCount > 0 || row.asLoaded.instructions.some((item) => item.shown && !item.regionScrolls);
    if (KEYBOARD_PAGES.includes(pagePath)) row.fullPage = await saveShot(page, `${pageKey(pagePath)}__${mode.id}.jpg`, { fullPage: true, type: 'jpeg', quality: 60 });
    if (shouldShoot) {
      const target = row.asLoaded.instructions.find((item) => item.shown && !item.regionScrolls);
      if (target) {
        await page.evaluate(({ text, selector }) => {
          let el = text ? [...document.querySelectorAll('body *')].find((node) => (node.textContent || '').includes(text) && node.children.length === 0) : null;
          try { el = el || document.querySelector(selector); } catch { /* description is not a valid selector */ }
          if (el) el.scrollIntoView({ block: 'center' });
        }, { text: target.source === 'dom-text' ? target.text.slice(0, 12) : '', selector: target.el });
      }
      row.defectShot = await saveShot(page, `${pageKey(pagePath)}__${mode.id}__defect.png`, { fullPage: false });
    }
    await page.evaluate(() => { for (const details of document.querySelectorAll('details')) details.open = true; });
    await page.waitForTimeout(300);
    const opened = await page.evaluate(analyse, SCROLL_INSTRUCTION);
    row.detailsOpen = { docOverflow: opened.docOverflow, offenderCount: opened.offenderCount, offenders: opened.offenders, shownInstructionsWithoutScroll: opened.instructions.filter((item) => item.shown && !item.regionScrolls).length };
  } catch (error) {
    row.error = String(error.message).slice(0, 160);
  }
  await page.close();
  return row;
}

function keyboardProbe(bannerSelector) {
  const selector = 'a[href],button,input:not([type=hidden]),select,textarea,summary,iframe,[tabindex]:not([tabindex="-1"])';
  const props = ['outlineStyle', 'outlineWidth', 'outlineColor', 'outlineOffset', 'boxShadow', 'backgroundColor', 'color', 'borderTopColor', 'borderBottomColor', 'textDecorationLine'];
  const read = (el) => Object.fromEntries(props.map((prop) => [prop, getComputedStyle(el)[prop]]));
  if (!window.__ksBaseline) {
    window.__ksBaseline = new Map();
    for (const el of document.querySelectorAll(selector)) window.__ksBaseline.set(el, read(el));
    return null;
  }
  const el = document.activeElement;
  if (!el || el === document.body) return { el: 'body', inConsentBanner: false };
  const now = read(el);
  const base = window.__ksBaseline.get(el) || {};
  const changed = props.filter((prop) => base[prop] !== undefined && base[prop] !== now[prop]);
  const transparent = /rgba\([^)]*,\s*0\)|transparent/.test(now.outlineColor);
  const outlineVisible = now.outlineStyle !== 'none' && parseFloat(now.outlineWidth) > 0 && !transparent;
  const rect = el.getBoundingClientRect();
  const inViewport = rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < document.documentElement.clientWidth;
  const cx = Math.min(Math.max(rect.left + rect.width / 2, 0), document.documentElement.clientWidth - 1);
  const cy = Math.min(Math.max(rect.top + rect.height / 2, 0), innerHeight - 1);
  const hit = document.elementFromPoint(cx, cy);
  const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
  return {
    el: `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''}`,
    inConsentBanner: Boolean(el.closest(bannerSelector)),
    text: (el.getAttribute('aria-label') || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40),
    href: el.getAttribute('href'),
    focusVisible: el.matches(':focus-visible'),
    outline: `${now.outlineStyle} ${now.outlineWidth} ${now.outlineColor}`,
    boxShadow: now.boxShadow,
    outlineVisible,
    changedFromUnfocused: changed,
    indicator: outlineVisible || changed.length > 0,
    inViewport,
    obscuredBy: hit && (hit === el || el.contains(hit)) ? null : hit ? `${hit.tagName.toLowerCase()}.${String(hit.className).slice(0, 30)}` : 'none',
    rect: { top: Math.round(rect.top), left: Math.round(rect.left), width: Math.round(rect.width), height: Math.round(rect.height) },
  };
}

async function keyboardWalk(browser, pagePath, width) {
  const mode = { id: `kb${width}`, width, height: width < 700 ? 844 : 900, deviceScaleFactor: 1, isMobile: false };
  const context = await newContext(browser, mode);
  const page = await context.newPage();
  // stops: the first KEYBOARD_STOPS Tab stops as they come. pageStops: the first KEYBOARD_STOPS stops
  // outside the consent banner, reached by continuing to press Tab (at most MAX_TAB_PRESSES in total).
  const result = { page: pagePath, width, stops: [], pageStops: [], tabPresses: 0 };
  try {
    await page.goto(new URL(pagePath, ORIGIN).href, { waitUntil: 'load', timeout: 90000 });
    await page.waitForTimeout(800);
    await page.evaluate(keyboardProbe, CONSENT_BANNER);
    while (result.tabPresses < MAX_TAB_PRESSES && (result.stops.length < KEYBOARD_STOPS || result.pageStops.length < KEYBOARD_STOPS)) {
      await page.keyboard.press('Tab');
      result.tabPresses += 1;
      await page.waitForTimeout(200);
      const info = await page.evaluate(keyboardProbe, CONSENT_BANNER);
      info.press = result.tabPresses;
      const first = result.stops.length < KEYBOARD_STOPS;
      const outside = !info.inConsentBanner && info.el !== 'body' && result.pageStops.length < KEYBOARD_STOPS;
      if (first || outside) info.shot = await saveShot(page, `${pageKey(pagePath)}__kb${width}__tab${result.tabPresses}.png`, { fullPage: false });
      if (first) result.stops.push({ ...info, stop: result.stops.length + 1 });
      if (outside) result.pageStops.push({ ...info, stop: result.pageStops.length + 1 });
    }
  } catch (error) {
    result.error = String(error.message).slice(0, 160);
  }
  await context.close();
  return result;
}

const browser = await chromium.launch({ headless: true, executablePath: process.env.KS_CHROME || '/opt/google/chrome/chrome' });
const startedAt = new Date().toISOString();
const results = [];
const tasks = MODES.flatMap((mode) => pages.map((pagePath) => ({ mode, pagePath })));
let cursor = 0;
async function worker() {
  let context = null;
  let contextMode = null;
  while (cursor < tasks.length) {
    const { mode, pagePath } = tasks[cursor];
    cursor += 1;
    if (contextMode !== mode.id) {
      if (context) await context.close();
      context = await newContext(browser, mode);
      contextMode = mode.id;
    }
    const row = await measure(context, mode, pagePath);
    results.push(row);
    process.stderr.write(`${results.length}/${tasks.length} ${mode.id} ${pagePath} overflow=${row.asLoaded?.docOverflow} offenders=${row.asLoaded?.offenderCount} ${row.error || ''}\n`);
  }
  if (context) await context.close();
}
try {
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  const keyboard = [];
  if (withKeyboard) {
    for (const pagePath of KEYBOARD_PAGES.filter((p) => pages.includes(p))) {
      for (const width of KEYBOARD_WIDTHS) keyboard.push(await keyboardWalk(browser, pagePath, width));
    }
  }
  results.sort((a, b) => pages.indexOf(a.page) - pages.indexOf(b.page) || MODES.findIndex((m) => m.id === a.mode) - MODES.findIndex((m) => m.id === b.mode));
  const shown = (row) => (row.asLoaded?.instructions || []).filter((item) => item.shown);
  const summary = {
    loads: results.length,
    errors: results.filter((row) => row.error).map((row) => `${row.page} ${row.mode}: ${row.error}`),
    non200: results.filter((row) => row.status !== 200).map((row) => `${row.page} ${row.mode}: ${row.status}`),
    docOverflowRows: results.filter((row) => row.asLoaded?.docOverflow > 0).map((row) => `${row.page} ${row.mode}: ${row.asLoaded.docOverflow}px`),
    offenderRows: results.filter((row) => row.asLoaded?.offenderCount > 0).map((row) => `${row.page} ${row.mode}: ${row.asLoaded.offenderCount}`),
    detailsOpenOverflowRows: results.filter((row) => row.detailsOpen?.docOverflow > 0 || row.detailsOpen?.offenderCount > 0).map((row) => `${row.page} ${row.mode}: doc=${row.detailsOpen.docOverflow} offenders=${row.detailsOpen.offenderCount}`),
    shownInstructionsWithoutScroll: results.flatMap((row) => shown(row).filter((item) => !item.regionScrolls).map((item) => `${row.page} ${row.mode} ${item.source} ${item.el} "${item.text}"`)),
    shownInstructionsWithScroll: results.flatMap((row) => shown(row).filter((item) => item.regionScrolls).map((item) => `${row.page} ${row.mode} ${item.source} ${item.el} "${item.text}"`)),
    cssContentRules: [...new Set(results.flatMap((row) => (row.asLoaded?.cssRules || []).map((rule) => JSON.stringify(rule))))].map((value) => JSON.parse(value)),
    keyboardStopsWithoutIndicator: keyboard.flatMap((walk) => [...walk.stops, ...walk.pageStops.filter((stop) => !walk.stops.some((first) => first.press === stop.press))].filter((stop) => stop.el !== 'body' && !stop.indicator).map((stop) => `${walk.page} ${walk.width} tab${stop.press} ${stop.el}`)),
    keyboardStopsOutOfViewportOrObscured: keyboard.flatMap((walk) => [...walk.stops, ...walk.pageStops.filter((stop) => !walk.stops.some((first) => first.press === stop.press))].filter((stop) => stop.el !== 'body' && (!stop.inViewport || stop.obscuredBy)).map((stop) => `${walk.page} ${walk.width} tab${stop.press} ${stop.el} inViewport=${stop.inViewport} obscuredBy=${stop.obscuredBy}`)),
    keyboardWalksWithFewerPageStops: keyboard.filter((walk) => walk.error || walk.pageStops.length < KEYBOARD_STOPS).map((walk) => `${walk.page} ${walk.width} pageStops=${walk.pageStops.length} ${walk.error || ''}`),
  };
  const output = {
    tool: 'scripts/ks_viewport_matrix.mjs',
    startedAt,
    finishedAt: new Date().toISOString(),
    origin: ORIGIN,
    browser: `chrome ${browser.version()}`,
    playwright: require('playwright/package.json').version,
    anonymous: true,
    consentGranted: false,
    blockedAdHosts: BLOCKED_AD_HOSTS,
    blockedRequestCounts: blocked,
    otherExternalHostsRequested: externalHosts,
    widths: WIDTHS,
    modes: MODES,
    pages,
    keyboardPages: KEYBOARD_PAGES,
    keyboardWidths: KEYBOARD_WIDTHS,
    summary,
    results,
    keyboard,
    screenshots: manifest,
  };
  fs.writeFileSync(path.join(OUT, 'viewport-matrix.json'), JSON.stringify(output, null, 1));
  process.stdout.write(JSON.stringify({ out: path.join(OUT, 'viewport-matrix.json'), ...summary, cssContentRules: summary.cssContentRules.length }, null, 1) + '\n');
} finally {
  await browser.close();
}
