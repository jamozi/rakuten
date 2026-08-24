import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import robots from '../../apps/web/app/robots.ts';
import sitemap from '../../apps/web/app/sitemap.ts';
import {
  createLocalRobotsRuntimePolicy,
  createLocalSitemapRuntimeEntries,
  LOCAL_SEO_RUNTIME_POLICY,
} from '../../apps/web/src/local-seo-runtime.ts';

describe('ST-1005 V2 fail-closed metadata runtime', () => {
  it('binds the exact local article without creating index authority', () => {
    assert.equal(
      LOCAL_SEO_RUNTIME_POLICY.exactArticlePath,
      '/articles/synthetic-recorded-policy-seo',
    );
    assert.equal(LOCAL_SEO_RUNTIME_POLICY.articleIndexState, 'NOINDEX_NOFOLLOW');
    assert.equal(LOCAL_SEO_RUNTIME_POLICY.originAuthority, 'UNAVAILABLE_UNRESOLVED_OD_002');
    assert.equal(LOCAL_SEO_RUNTIME_POLICY.canonicalUrl, null);
    assert.equal(LOCAL_SEO_RUNTIME_POLICY.canonicalActivated, false);
    assert.equal(LOCAL_SEO_RUNTIME_POLICY.publicationAuthorized, false);
    assert.equal(LOCAL_SEO_RUNTIME_POLICY.productionAuthorized, false);
    assert.ok(Object.values(LOCAL_SEO_RUNTIME_POLICY.sitemapEligibility).every((value) => !value));
  });

  it('serves a fresh disallow-all robots policy with no sitemap URL', () => {
    const first = createLocalRobotsRuntimePolicy();
    const second = robots();
    assert.deepEqual(first, { rules: { userAgent: '*', disallow: '/' } });
    assert.deepEqual(second, first);
    assert.notEqual(first, second);
    assert.doesNotMatch(JSON.stringify(second), /https?:|sitemap|host/iu);
  });

  it('serves no sitemap entry while all eligibility facts are unavailable', () => {
    const first = createLocalSitemapRuntimeEntries();
    first.push();
    assert.deepEqual(first, []);
    assert.deepEqual(sitemap(), []);
    assert.notEqual(first, sitemap());
  });
});
