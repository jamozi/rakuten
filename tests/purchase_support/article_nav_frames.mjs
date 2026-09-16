// Measure how a published article's in-article navigation actually renders.
//
//   node tests/purchase_support/article_nav_frames.mjs <plan.json> [widths]
//
// The plan is written by the caller (tests/purchase_support/
// test_ks_n30_w0_article_nav_20260916.py) and holds, per slug, the body file the
// ledger publishes and the stylesheets the theme really enqueues for that post --
// the caller reads them out of the theme's own PHP, because a post outside the
// purchase-support runtime gets theme.css alone and nothing from
// purchase-support.css, where `.ps-article .ps-toc` gets its flex gap.
//
// The page is assembled the way the running site assembles it, the same shell
// tests/purchase_support/phone_table_frames.mjs uses:
//   * body{margin:0} -- WordPress global styles for a block theme.
//   * the enqueued sheets, in enqueue order.
//   * main.raos-article-shell > article.raos-article > .wp-block-post-content,
//     the structure of templates/single.html.
// For every navigation that holds two or more links it reports, per adjacent
// pair, whether the two sit on one line, the rendered gap between them and any
// visible text printed between them.
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const root = new URL('../../', import.meta.url).pathname;
const assets =
  root +
  'changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/';

const plan = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const widths = (process.argv[3] ?? '320,390,1440').split(',').map(Number);

const documentFor = (entry) => {
  const css = entry.sheets.map((name) => readFileSync(assets + name, 'utf8')).join('\n');
  const body = readFileSync(root + entry.body, 'utf8').replace(/<!--\s*\/?wp:[^>]*?-->/g, '');
  const editorialV2 = entry.sheets.includes('editorial-v2.css');
  return `<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>nav</title>
<style>body{margin:0}*{box-sizing:border-box}</style><style>${css}</style></head>
<body class="wp-singular${editorialV2 ? ' raos-editorial-v2-page' : ''}">
<div class="wp-site-blocks"><main id="main-content" class="wp-block-group raos-article-shell">
<article class="wp-block-group raos-article"><div class="entry-content wp-block-post-content">${body}</div>
</article></main></div></body></html>`;
};

const browser = await chromium.launch({ headless: true });
const report = {};
try {
  for (const [slug, entry] of Object.entries(plan)) {
    const html = documentFor(entry);
    report[slug] = { sheets: entry.sheets, widths: {} };
    for (const width of widths) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      const page = await context.newPage();
      await page.route('**/*', (route) => (route.request().isNavigationRequest()
        ? route.fulfill({ status: 200, contentType: 'text/html', body: html })
        : route.abort('blockedbyclient')));
      await page.goto('https://kurashinoshirube.com/measure/', { waitUntil: 'load' });
      report[slug].widths[width] = await page.evaluate(() => {
        const printedBetween = (first, second) => {
          const range = document.createRange();
          range.setStartAfter(first);
          range.setEndBefore(second);
          return range.toString().replace(/\s+/g, '');
        };
        const navigations = [];
        for (const nav of document.querySelectorAll('nav, .ps-toc')) {
          const links = [...nav.querySelectorAll('a')];
          if (links.length < 2) continue;
          const pairs = [];
          for (let index = 1; index < links.length; index += 1) {
            const first = links[index - 1].getBoundingClientRect();
            const second = links[index].getBoundingClientRect();
            const sameLine = first.top < second.bottom && second.top < first.bottom;
            pairs.push({
              texts: [links[index - 1].textContent.trim(), links[index].textContent.trim()],
              same_line: sameLine,
              gap: Number(
                (sameLine ? second.left - first.right : second.top - first.bottom).toFixed(2)
              ),
              printed_between: printedBetween(links[index - 1], links[index]),
            });
          }
          navigations.push({
            selector: (nav.getAttribute('class') || nav.tagName.toLowerCase()).trim(),
            label: nav.getAttribute('aria-label'),
            links: links.length,
            pairs,
          });
        }
        return navigations;
      });
      await context.close();
    }
  }
} finally {
  await browser.close();
}
process.stdout.write(JSON.stringify(report, null, 1) + '\n');
