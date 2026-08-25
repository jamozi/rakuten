import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

const read = (path: string) => readFileSync(path, 'utf8');

describe('ST-1005 V2 static SEO boundary', () => {
  it('keeps the article and root layout noindex', () => {
    const article = read('apps/web/app/articles/[slug]/page.tsx');
    const layout = read('apps/web/app/layout.tsx');
    for (const source of [article, layout]) {
      assert.match(source, /index:\s*false/u);
      assert.match(source, /follow:\s*false/u);
    }
  });

  it('registers only deterministic Next metadata routes', () => {
    const robotsSource = read('apps/web/app/robots.ts');
    const sitemapSource = read('apps/web/app/sitemap.ts');
    assert.match(robotsSource, /createLocalRobotsRuntimePolicy/u);
    assert.match(sitemapSource, /createLocalSitemapRuntimeEntries/u);
    assert.doesNotMatch(
      `${robotsSource}\n${sitemapSource}`,
      /fetch|axios|http:|https:|process\.env/iu,
    );
  });

  it('has no origin, canonical, redirect, provider, or effect source', () => {
    const source = read('apps/web/src/local-seo-runtime.ts');
    assert.doesNotMatch(
      source,
      /process\.env|globalThis|window|document|fetch|sendBeacon|redirect\s*\(|provider|affiliate_url/iu,
    );
    assert.match(source, /canonicalUrl:\s*null/u);
    assert.match(source, /publicationAuthorized:\s*false/u);
    assert.match(source, /productionAuthorized:\s*false/u);
  });
});
