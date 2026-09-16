// Measure the real horizontal scroll frame and column widths of the tables in a
// published body, so the numbers in phone_table_frames.py are measured rather
// than derived. Read-only: no network, no production request.
//
//   node tests/purchase_support/phone_table_frames.mjs <slug>[,<slug>...] [widths]
//   node tests/purchase_support/phone_table_frames.mjs small-carry-on-suitcase-comparison 320,360,375,390
//
// The page is assembled the way the running site assembles it:
//   * body{margin:0} -- WordPress global styles for a block theme. The same
//     reset is used by tests/st1704/test_header_text_resize.py. Without it the
//     user-agent's 8px body margin shrinks every frame by 16px.
//   * theme.css + editorial-v2.css + purchase-support.css, and editorial-v2.css
//     only for comparison / guide / curated_comparison bodies, exactly as
//     inc/purchase-support.php enqueues them (the kind is read from the same
//     assets/purchase-support.v1.json the theme reads).
//   * main.raos-article-shell > article.raos-article > .wp-block-post-content,
//     the structure of templates/single.html.
// For each table it reports the nearest ancestor that scrolls sideways, that
// container's clientWidth (the frame), and the rendered width of every column.
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { refuseWhilePriceOverlayLive } from '../../scripts/raos_price_overlay_live_check.mjs';

// Contract §8: this reads only tracked bodies and opens no network, but it does drive a
// browser over a published body, so it refuses to run while a price-overlay run is live
// rather than leaving the one browser in this directory unguarded.
await refuseWhilePriceOverlayLive();

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const root = new URL('../../', import.meta.url).pathname;
const dir = root + 'changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/';
const sheet = (name) => readFileSync(dir + name, 'utf8');
const ARTICLE_KINDS = new Set(['comparison', 'guide', 'curated_comparison']);
const kinds = Object.fromEntries(
  JSON.parse(readFileSync(dir + 'purchase-support.v1.json', 'utf8')).articles.map((a) => [a.slug, a.kind]),
);

const document_for = (slug) => {
  const editorialV2 = ARTICLE_KINDS.has(kinds[slug] ?? null);
  const css = [sheet('theme.css'), ...(editorialV2 ? [sheet('editorial-v2.css')] : []), sheet('purchase-support.css')].join('\n');
  const body = readFileSync(root + 'changes/wordpress-direct-publish-v1/articles/' + slug + '.html', 'utf8')
    .replace(/<!--\s*\/?wp:[^>]*?-->/g, '');
  return [editorialV2, `<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>frame</title>
<style>body{margin:0}*{box-sizing:border-box}</style><style>${css}</style></head>
<body class="wp-singular${editorialV2 ? ' raos-editorial-v2-page' : ''}">
<div class="wp-site-blocks"><main id="main-content" class="wp-block-group raos-article-shell">
<article class="wp-block-group raos-article"><div class="entry-content wp-block-post-content">${body}</div>
</article></main></div></body></html>`];
};

const slugs = (process.argv[2] ?? '').split(',').filter(Boolean);
if (slugs.length === 0) throw new Error('USAGE: phone_table_frames.mjs <slug>[,<slug>...] [widths]');
const widths = (process.argv[3] ?? '320,360,375,390').split(',').map(Number);

const browser = await chromium.launch({ headless: true });
const report = {};
try {
  for (const slug of slugs) {
    const [editorialV2, html] = document_for(slug);
    report[slug] = { kind: kinds[slug] ?? null, editorial_v2: editorialV2, widths: {} };
    for (const width of widths) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      const page = await context.newPage();
      await page.route('**/*', (route) => (route.request().isNavigationRequest()
        ? route.fulfill({ status: 200, contentType: 'text/html', body: html })
        : route.abort('blockedbyclient')));
      await page.goto('https://kurashinoshirube.com/measure/', { waitUntil: 'load' });
      report[slug].widths[width] = await page.evaluate(() => {
        const shell = document.querySelector('.raos-article-shell');
        const tables = [];
        for (const table of document.querySelectorAll('table')) {
          let node = table.parentElement;
          let frame = null;
          while (node && node !== document.body) {
            if (/auto|scroll/.test(getComputedStyle(node).overflowX)) { frame = node; break; }
            node = node.parentElement;
          }
          const header = table.querySelector('thead tr') ?? table.querySelector('tr');
          const cells = header ? [...header.children] : [];
          tables.push({
            id: table.id || null,
            class: (table.className || '').trim() || null,
            container: frame ? frame.className : null,
            frame_outer: frame ? Number(frame.getBoundingClientRect().width.toFixed(2)) : null,
            frame_inner: frame ? frame.clientWidth : null,
            scrolls: frame ? frame.scrollWidth > frame.clientWidth + 0.5 : false,
            sticky_first_column: cells[0] ? getComputedStyle(cells[0]).position === 'sticky' : false,
            table_width: Number(table.getBoundingClientRect().width.toFixed(2)),
            columns: cells.map((cell) => Number(cell.getBoundingClientRect().width.toFixed(2))),
          });
        }
        return {
          viewport: innerWidth,
          shell_outer: shell ? Number(shell.getBoundingClientRect().width.toFixed(2)) : null,
          shell_padding_inline: shell ? getComputedStyle(shell).paddingLeft : null,
          tables,
        };
      });
      await context.close();
    }
  }
} finally {
  await browser.close();
}
process.stdout.write(JSON.stringify(report, null, 1) + '\n');
