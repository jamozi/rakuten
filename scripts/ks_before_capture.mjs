// Full-page screenshots of a running local WordPress at the given widths (Before evidence for
// scripts/ks_before_after.py --before-script). Same input JSON shape as preview-browser.mjs:
// { origin, widths, surfaces: [{ kind, path }], screenshots }
// Faster than preview-browser.mjs on a long-lived preview: waits for `load`, walks the page for
// lazy images, and never waits for network idle.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { refuseWhilePriceOverlayLive } from './raos_price_overlay_live_check.mjs';
const require = createRequire(import.meta.url);
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
// A local preview, or the public production origin when the published state is the Before.
if (!/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(input.origin) && input.origin !== 'https://kurashinoshirube.com') throw new Error('ORIGIN_NOT_ALLOWED');
// Contract §8: a capture while Rakuten price overlay values may be published stores the
// rendered prices and their hashes, wherever it writes them. The destination is no exemption
// any more (round 10): only the publisher's run-bound preview writes into the candidate
// directory the run itself deletes, so every other capture refuses while values are live.
await refuseWhilePriceOverlayLive();
const { chromium } = require('playwright');
fs.mkdirSync(input.screenshots, { recursive: true });
const browser = await chromium.launch({ headless: true });
const failures = [];
let count = 0;
try {
  for (const width of input.widths) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
    await context.route('**/*', (route) => {
      const url = new URL(route.request().url());
      return url.origin === input.origin || url.protocol === 'data:' ? route.continue() : route.abort();
    });
    for (const [index, surface] of input.surfaces.entries()) {
      const page = await context.newPage();
      const url = new URL(surface.path, input.origin).href;
      try {
        const response = await page.goto(url, { waitUntil: 'load', timeout: 60000 });
        if (!response || response.status() !== 200) failures.push(`${surface.path}:${width}:http`);
        await page.evaluate(async () => {
          for (const d of document.querySelectorAll('details')) d.open = true;
          const step = Math.max(600, innerHeight);
          for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
            scrollTo(0, y);
            await new Promise((r) => setTimeout(r, 120));
          }
          scrollTo(0, 0);
        });
        await page.waitForTimeout(800);
      } catch (error) {
        failures.push(`${surface.path}:${width}:${String(error.message).slice(0, 60)}`);
      }
      const destination = path.join(input.screenshots, `${index}-${surface.kind}-${width}.png`);
      await page.screenshot({ path: destination, fullPage: true }).catch(() => failures.push(`${surface.path}:${width}:screenshot`));
      count += 1;
      await page.close();
    }
    await context.close();
  }
} finally {
  await browser.close();
}
process.stdout.write(JSON.stringify({ status: failures.length ? 'WARN' : 'PASS', failures, screenshots: count }) + '\n');
