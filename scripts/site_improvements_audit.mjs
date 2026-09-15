/** Read-only public/local audit. Never stores query values, cookie values, or request bodies. */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { chromium } from 'playwright';
const args = process.argv.slice(2);
const option = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const origin = new URL(option('--origin', 'https://kurashinoshirube.com')).origin;
const mode = option('--mode', 'public-baseline');
const output = option('--output', 'output/site-improvements-20260913/public-baseline.json');
const inventory = JSON.parse(
  readFileSync('changes/site-improvements-20260913/audit-inventory.json', 'utf8'),
);
const allWidths = args.includes('--all-widths');
const representatives = new Set([15, 130, 136, 41, 262, 266, 82, 120, 3]);
const widths = [320, 375, 390, 768, 1440];
const clean = (u) => {
  try {
    const x = new URL(u, origin);
    return x.origin + x.pathname;
  } catch {
    return 'INVALID';
  }
};
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  serviceWorkers: 'block',
});
const page = await ctx.newPage();
const rows = [];
try {
  for (const entry of inventory) {
    const row = { ...entry, failures: [], widths: [] };
    const target = origin + entry.path;
    try {
      const response = await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForTimeout(500);
      row.status = response?.status() ?? null;
      row.final_url = clean(page.url());
      row.x_robots_tag = response?.headers()['x-robots-tag'] || null;
      row.dom = await page.evaluate(() => {
        const url = (raw) => {
          try {
            const u = new URL(raw, location.href);
            return ['http:', 'https:'].includes(u.protocol)
              ? { origin: u.origin, path: u.pathname, hash: decodeURIComponent(u.hash.slice(1)) }
              : null;
          } catch {
            return null;
          }
        };
        const ids = [...document.querySelectorAll('[id]')].map((e) => e.id);
        const ld = [...document.querySelectorAll('script[type="application/ld+json"]')].map((e) => {
          try {
            const d = JSON.parse(e.textContent);
            return {
              valid: true,
              types: [...new Set(JSON.stringify(d).match(/"@type"\s*:\s*"([^"]+)"/g) || [])],
            };
          } catch {
            return { valid: false };
          }
        });
        return {
          title: document.title,
          h1: [...document.querySelectorAll('h1')].map((e) => e.textContent.trim()),
          canonical: url(document.querySelector('link[rel="canonical"]')?.href),
          robots: [...document.querySelectorAll('meta[name="robots"]')].map((e) => e.content),
          duplicate_ids: [...new Set(ids.filter((x, i) => ids.indexOf(x) !== i))],
          ids,
          json_ld: ld,
          links: [
            ...new Map(
              [...document.querySelectorAll('a[href]')]
                .map((e) => url(e.getAttribute('href')))
                .filter(Boolean)
                .filter((u) =>
                  ['kurashinoshirube.com', '127.0.0.1', 'localhost'].includes(
                    new URL(u.origin).hostname,
                  ),
                )
                .map((u) => [u.path + '#' + u.hash, u]),
            ).values(),
          ],
        };
      });
      if (row.status !== 200) row.failures.push('HTTP_NOT_200');
      if (!row.dom.title) row.failures.push('TITLE_EMPTY');
      if (row.dom.h1.length !== 1) row.failures.push('H1_COUNT_' + row.dom.h1.length);
      if (!row.dom.canonical || row.dom.canonical.path !== entry.path)
        row.failures.push('CANONICAL_PATH_MISMATCH');
      if (mode === 'public-baseline' && row.dom.canonical?.origin !== origin)
        row.failures.push('CANONICAL_ORIGIN_MISMATCH');
      if (mode === 'public-baseline' && row.dom.robots.some((x) => /noindex/i.test(x)))
        row.failures.push('PUBLIC_NOINDEX');
      if (row.dom.duplicate_ids.length) row.failures.push('DUPLICATE_IDS');
      if (row.dom.json_ld.some((x) => !x.valid)) row.failures.push('INVALID_JSON_LD');
      for (const width of allWidths || representatives.has(entry.post_id) ? widths : [1440]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate(async () => {
          for (let y = 0; y < document.body.scrollHeight; y += 850) {
            window.scrollTo(0, y);
            await new Promise((r) => setTimeout(r, 35));
          }
          await Promise.race([
            Promise.all([...document.images].map((i) => i.decode().catch(() => {}))),
            new Promise((r) => setTimeout(r, 2000)),
          ]);
          window.scrollTo(0, 0);
        });
        await page.waitForTimeout(150);
        row.widths.push(
          await page.evaluate(() => ({
            width: innerWidth,
            scroll_width: document.documentElement.scrollWidth,
            overflow: document.documentElement.scrollWidth > innerWidth + 1,
            overflow_elements: [...document.querySelectorAll('main *')]
              .filter((e) => {
                const b = e.getBoundingClientRect();
                return (
                  b.width > 0 &&
                  (b.right > innerWidth + 1 || b.left < -1) &&
                  !e.closest('.ps-table-scroll,.comparison-table-wrap,[role="region"]')
                );
              })
              .slice(0, 12)
              .map((e) => ({ tag: e.tagName, class: e.className })),
            images: [...document.querySelectorAll('main img,article img')].map((e) => ({
              alt: e.alt,
              host: (() => {
                try {
                  return new URL(e.currentSrc || e.src).hostname;
                } catch {
                  return 'INVALID';
                }
              })(),
              loaded: e.complete && e.naturalWidth > 0,
              natural_width: e.naturalWidth,
              display_width: Math.round(e.getBoundingClientRect().width),
              undersized:
                e.naturalWidth > 0 && e.naturalWidth < e.getBoundingClientRect().width * 0.9,
            })),
          })),
        );
      }
      if (row.widths.some((w) => w.overflow)) row.failures.push('HORIZONTAL_OVERFLOW');
      if (row.widths.some((w) => w.images.some((i) => !i.loaded)))
        row.failures.push('IMAGE_UNLOADED');
      if (row.widths.some((w) => w.images.some((i) => i.undersized)))
        row.failures.push('IMAGE_UPSCALED');
    } catch (e) {
      row.failures.push('NAVIGATION_OR_DOM_FAILURE');
      row.error_type = e.name;
    }
    rows.push(row);
    console.log(
      JSON.stringify({ post_id: entry.post_id, status: row.status, failures: row.failures }),
    );
  }
  // Resolve internal anchors against the entire requested inventory, including cross-page anchors.
  const byPath = new Map(rows.filter((r) => r.dom).map((r) => [r.path, r]));
  const uncheckedPaths = new Set();
  for (const row of rows.filter((r) => r.dom)) {
    row.broken_anchors = [];
    for (const link of row.dom.links) {
      const dest = byPath.get(link.path);
      if (!dest) {
        uncheckedPaths.add(link.path);
        continue;
      }
      if (link.hash && !dest.dom.ids.includes(link.hash))
        row.broken_anchors.push({ path: link.path, anchor: link.hash });
    }
    if (row.broken_anchors.length) row.failures.push('BROKEN_INTERNAL_ANCHORS');
  }
  for (const row of rows.filter((r) => r.dom)) {
    delete row.dom.ids;
    delete row.dom.links;
  }
  const infrastructure = [];
  for (const path of [
    '/robots.txt',
    '/sitemap_index.xml',
    '/wp-sitemap.xml',
    '/this-page-does-not-exist-raos-audit/',
  ]) {
    try {
      const r = await ctx.request.get(origin + path, { timeout: 30000 });
      const text = await r.text();
      infrastructure.push({
        path,
        status: r.status(),
        sitemap_references:
          path === '/robots.txt'
            ? (text.match(/^Sitemap:\s*(.+)$/gim) || []).map((x) =>
                clean(x.replace(/^Sitemap:\s*/i, '')),
              )
            : undefined,
        contains_xml_sitemap: /<(sitemapindex|urlset)\b/.test(text),
        robots_disallows_all:
          path === '/robots.txt' ? /^Disallow:\s*\/\s*$/m.test(text) : undefined,
      });
    } catch (e) {
      infrastructure.push({ path, status: null, error_type: e.name });
    }
  }
  const sitemapDocuments = [];
  const sitemapPaths = new Set();
  const sitemapQueue = ['/sitemap_index.xml', '/wp-sitemap.xml'];
  const sitemapSeen = new Set();
  while (sitemapQueue.length && sitemapSeen.size < 15) {
    const path = sitemapQueue.shift();
    if (sitemapSeen.has(path)) continue;
    sitemapSeen.add(path);
    try {
      const r = await ctx.request.get(origin + path, { timeout: 20000 });
      const body = await r.text();
      const locs = [...body.matchAll(/<loc>([^<]+)<\/loc>/g)]
        .map((m) => {
          try {
            return new URL(m[1].replaceAll('&amp;', '&'));
          } catch {
            return null;
          }
        })
        .filter(Boolean);
      sitemapDocuments.push({ path, status: r.status(), locations: locs.length });
      for (const u of locs) {
        if (/<sitemapindex[\s>]/.test(body)) {
          if (['kurashinoshirube.com', new URL(origin).hostname].includes(u.hostname))
            sitemapQueue.push(u.pathname);
        } else sitemapPaths.add(u.pathname);
      }
    } catch (e) {
      sitemapDocuments.push({ path, error_type: e.name });
    }
  }
  const sitemap = {
    documents: sitemapDocuments,
    listed_inventory: inventory.filter((r) => sitemapPaths.has(r.path)).map((r) => r.post_id),
    missing_inventory: inventory.filter((r) => !sitemapPaths.has(r.path)).map((r) => r.post_id),
  };
  const internal_path_status = [];
  for (const path of [...uncheckedPaths]
    .filter((p) => !p.startsWith('/wp-admin') && !p.startsWith('/wp-login') && !p.includes('/feed'))
    .slice(0, 80)) {
    try {
      const r = await ctx.request.get(origin + path, { timeout: 15000 });
      internal_path_status.push({ path, status: r.status() });
    } catch (e) {
      internal_path_status.push({ path, error_type: e.name });
    }
  }
  const titleGroups = new Map();
  for (const r of rows.filter((r) => r.dom)) {
    const ids = titleGroups.get(r.dom.title) || [];
    ids.push(r.post_id);
    titleGroups.set(r.dom.title, ids);
  }
  const duplicate_titles = [...titleGroups.values()].filter((ids) => ids.length > 1);
  const report = {
    schema: 'RAOSSiteImprovementsReadOnlyAuditV1',
    mode,
    origin,
    checked_at: new Date().toISOString(),
    not_candidate_verification: mode === 'public-baseline',
    viewport_scope: allWidths ? 'all34x5' : 'all34 desktop; nine representative templates x5',
    node: process.version,
    rows,
    infrastructure,
    duplicate_titles,
    sitemap,
    internal_path_status,
    unchecked_internal_paths: [...uncheckedPaths].sort(),
    summary: {
      pages: rows.length,
      pages_with_failures: rows.filter((r) => r.failures.length).length,
    },
    unavailable: {
      GSC: 'UNAVAILABLE',
      GA4_account: 'UNAVAILABLE',
      ASP_orders_and_earnings: 'UNAVAILABLE',
    },
    limitations: [
      'Browser rendered DOM and passive image requests only; no purchase-link activation or form submission.',
      'JSON-LD syntax/types checked; not a full Google eligibility test.',
      'Image loaded/size checks do not establish product identity or reuse rights.',
      'Public baseline is not evidence that local changes fixed production.',
    ],
  };
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
} finally {
  await browser.close();
}
