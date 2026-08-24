import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function source(relative: string): string {
  return readFileSync(resolve(root, relative), 'utf8');
}

describe('ST-1004 V2 SSR, accessibility and security surface', () => {
  it('integrates a mandatory one-heading DisclosureBanner before lead and article body', () => {
    const page = source('apps/web/src/public-article-page.tsx');
    const componentStart = page.indexOf('export function DisclosureBanner');
    const componentEnd = page.indexOf('function AffiliateCtaUnavailableNotice');
    const component = page.slice(componentStart, componentEnd);
    assert.ok(componentStart >= 0 && componentEnd > componentStart);
    assert.equal((component.match(/<h2\b/gu) ?? []).length, 1);
    assert.match(component, /<aside\b/);
    assert.match(component, /aria-labelledby="article-disclosure-heading"/u);

    const routeStart = page.indexOf('export function PublicArticlePage');
    const route = page.slice(routeStart);
    const h1 = route.indexOf('<h1');
    const disclosure = route.indexOf('<DisclosureBanner');
    const lead = route.indexOf("className={styles['lead']}");
    const sections = route.indexOf("className={styles['articleSections']}");
    assert.ok(h1 >= 0 && disclosure > h1 && lead > disclosure && sections > lead);
  });

  it('defines a native direct anchor with exact rel/copy semantics but never renders it on route', () => {
    const page = source('apps/web/src/public-article-page.tsx');
    const componentStart = page.indexOf('export function AffiliateCTA');
    const componentEnd = page.indexOf('function disclosureAffiliateView');
    const component = page.slice(componentStart, componentEnd);
    assert.ok(componentStart >= 0 && componentEnd > componentStart);
    assert.match(component, /<a\b/);
    assert.match(component, /href=\{safeCta\.href\}/u);
    assert.match(component, /rel=\{safeCta\.rel\}/u);
    assert.match(component, /safeCta\.copy/u);
    assert.match(component, /safeCta\.destinationText/u);
    assert.doesNotMatch(component, /onClick|onMouse|onPointer|target=|redirect|returnUrl/u);

    const route = page.slice(page.indexOf('export function PublicArticlePage'));
    assert.doesNotMatch(route, /<AffiliateCTA\b/u);
    assert.match(route, /<AffiliateCtaUnavailableNotice\b/u);
  });

  it('provides visible focus and WCAG target-size rules for the synthetic component', () => {
    const css = source('apps/web/app/articles/[slug]/article.module.css');
    assert.match(css, /\.affiliateCta\s*\{[\s\S]*min-width:\s*2\.75rem/u);
    assert.match(css, /\.affiliateCta\s*\{[\s\S]*min-height:\s*2\.75rem/u);
    assert.match(css, /\.affiliateCta:focus-visible\s*\{[\s\S]*outline:/u);
    assert.match(css, /@media \(max-width: 24rem\)/u);
    assert.match(css, /\.ctaUnavailable/u);
  });

  it('contains no open redirect, client effect, provider, tracking or arbitrary URL surface', () => {
    const runtime = source('packages/web-ui/src/disclosure-affiliate-cta.ts');
    const route = source('apps/web/app/articles/[slug]/page.tsx');
    const page = source('apps/web/src/public-article-page.tsx');
    const combined = `${runtime}\n${route}\n${page}`;
    assert.equal((runtime.match(/https:\/\//gu) ?? []).length, 1);
    assert.match(runtime, /https:\/\/example\.invalid\/rakuten-marketplace\/item/u);
    assert.doesNotMatch(
      combined,
      /\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|localStorage|sessionStorage)\s*\(/u,
    );
    assert.doesNotMatch(combined, /['"]use client['"]|onClick=|dangerouslySetInnerHTML/u);
    assert.doesNotMatch(route, /redirect\(/u);
  });

  it('retains noindex and script/connect-none headers on the exact article route', () => {
    const proxy = source('apps/web/proxy.ts');
    const route = source('apps/web/app/articles/[slug]/page.tsx');
    assert.match(proxy, /matcher: \['\/articles\/:path\*'\]/u);
    assert.match(proxy, /script-src 'none'/u);
    assert.match(proxy, /connect-src 'none'/u);
    assert.match(proxy, /noindex, nofollow/u);
    assert.match(route, /resolveRecordedPublicArticleV2/u);
    assert.match(route, /\?\? notFound\(\)/u);
    assert.doesNotMatch(route, /generateStaticParams|redirect\(/u);
  });
});
