/** Two-width, same-origin smoke checks of a frozen local WordPress candidate. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { refuseWhilePriceOverlayLiveUnlessBoundCandidate } from '../../scripts/raos_price_overlay_live_check.mjs';

const require = createRequire(import.meta.url);
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
if (!/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(input.origin)) throw new Error('LOCAL_ORIGIN_REQUIRED');
// Contract §8: the loopback origin this script requires is the one the candidate preview docker
// serves the injected bodies on. This is the only capture left unrefused while values are
// published, and only into an owner-direct candidate directory whose own candidate.json carries
// a price-overlay binding - the directory the run deletes with itself. The verified path is what
// the screenshots are written to, so the destination that was proved is the one that is used.
const screenshotsDirectory = await refuseWhilePriceOverlayLiveUnlessBoundCandidate(input.screenshots);
const { chromium } = require('playwright');
const browser = await chromium.launch({ headless: true });
const failures = [];
const screenshots = [];
try {
  for (const width of input.widths) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
    await context.route('**/*', (route) => {
      const url = new URL(route.request().url());
      const mirrored = input.images?.[url.href];
      if (mirrored && route.request().resourceType() === 'image') {
        const body = fs.readFileSync(mirrored.path);
        if (crypto.createHash('sha256').update(body).digest('hex') !== mirrored.sha256) throw new Error('PINNED_IMAGE_CHANGED');
        return route.fulfill({ status: 200, contentType: mirrored.mime, body });
      }
      return url.origin === input.origin || url.protocol === 'data:' ? route.continue() : route.abort();
    });
    for (const [index, surface] of input.surfaces.entries()) {
      const url = new URL(surface.path, input.origin);
      if (url.origin !== input.origin) throw new Error('EXTERNAL_SURFACE_REFUSED');
      const page = await context.newPage();
      page.on('pageerror', () => failures.push(`${surface.path}:${width}:javascript`));
      const response = await page.goto(url.href, { waitUntil: 'networkidle', timeout: 45000 });
      for (const img of await page.locator('main img').all()) {
        await img.evaluate((e) => {
          for (let parent = e.parentElement; parent; parent = parent.parentElement) {
            if (parent instanceof HTMLDetailsElement) parent.open = true;
          }
        });
        if (await img.isVisible()) await img.scrollIntoViewIfNeeded();
        await page.waitForFunction((e) => e.complete && e.naturalWidth > 0,
          await img.elementHandle(), { timeout: 10000 }).catch(() => {});
      }
      await page.evaluate(() => scrollTo(0, 0));
      if (!response || response.status() !== 200) failures.push(`${surface.path}:${width}:http`);
      const result = await page.evaluate(({ kind, title }) => {
        const failures = [];
        const main = document.querySelector('main') || document.body;
        const text = main.innerText;
        if (text.trim().length < 10) failures.push('empty');
        if (title && !text.includes(title)) failures.push('title');
        if (document.documentElement.scrollWidth > innerWidth + 3) failures.push('horizontal-overflow');
        if (/Fatal error:|Uncaught Error:|Warning:.*on line \d/.test(text)) failures.push('php');
        if (kind === 'article') {
          const article = document.querySelector('.wp-block-post-content') || main;
          const links = [...article.querySelectorAll('a')];
          const affiliate = links.filter((a) => /^https:\/\/(?:hb\.afl\.rakuten\.co\.jp|a\.r10\.to|r10\.to)\//.test(a.href));
          if (affiliate.length && !/広告|PR|アフィリエイト/.test(text)) failures.push('disclosure');
          if (affiliate.some((a) => !/sponsored|nofollow/.test(a.rel))) failures.push('affiliate-rel');
          if (links.some((a) => /^javascript:/i.test(a.getAttribute('href') || ''))) failures.push('unsafe-link');
          if ([...article.querySelectorAll('img')].some((img) => !img.complete || img.naturalWidth === 0)) failures.push('broken-image');
        }
        return failures;
      }, surface);
      failures.push(...result.map((code) => `${surface.path}:${width}:${code}`));
      const destination = path.join(screenshotsDirectory, `${index}-${surface.kind}-${width}.png`);
      await page.screenshot({ path: destination, fullPage: true });
      screenshots.push({ path: destination, sha256: crypto.createHash('sha256').update(fs.readFileSync(destination)).digest('hex') });
      await page.close();
    }
    await context.close();
  }
} finally {
  await browser.close();
}
process.stdout.write(JSON.stringify({ status: failures.length ? 'FAIL' : 'PASS', failures, screenshots }) + '\n');
