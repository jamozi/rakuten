import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { createPublicShellCandidate } from '../../packages/web-ui/src/public-shell.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = readFileSync(resolve(repositoryRoot, 'packages/web-ui/src/public-shell.ts'), 'utf8');

const expectedBoundaryReasons = {
  routeRegistered: 'NO_RUNTIME_ROUTE_REGISTERED',
  ssr: 'SSR_EXECUTION_NOT_IMPLEMENTED',
  browser: 'BROWSER_EXECUTION_NOT_PERFORMED',
  accessibility: 'ACCESSIBILITY_EXECUTION_NOT_PERFORMED',
  formalTst022: 'FORMAL_TST_022_NOT_EXECUTED',
  formalTst023: 'FORMAL_TST_023_NOT_EXECUTED',
  live: 'LIVE_EXECUTION_NOT_AUTHORIZED',
  staging: 'STAGING_EXECUTION_NOT_AUTHORIZED',
  release: 'RELEASE_NOT_AUTHORIZED',
  production: 'PRODUCTION_NOT_AUTHORIZED',
  externalPublication: 'EXTERNAL_PUBLICATION_NOT_AUTHORIZED',
  publicationAuthorization: 'PUBLICATION_APPROVAL_NOT_GRANTED',
  domainApproval: 'OD_002_DOMAIN_UNRESOLVED',
  operatorApproval: 'OD_002_OPERATOR_UNRESOLVED',
  consentApproval: 'OD_012_CONSENT_UNRESOLVED',
  legalApproval: 'LEGAL_REVIEW_NOT_GRANTED',
  tracking: 'OD_012_NONESSENTIAL_TRACKING_DISABLED',
  firstPartyEvent: 'EVENT_INSTRUMENTATION_OUT_OF_SCOPE',
  wcagConformanceClaim: 'WCAG_CONFORMANCE_NOT_VERIFIED',
  localEligibility: 'ROUTE_SSR_BROWSER_AND_APPROVAL_GATES_UNSATISFIED',
} as const;

describe('public-shell execution and authority boundaries', () => {
  it('keeps every execution, approval and eligibility boundary false and NOT_EXECUTED', () => {
    const candidate = createPublicShellCandidate({ screenId: 'PUB-005' });
    assert.deepEqual(
      Object.keys(candidate.boundaries).sort(),
      Object.keys(expectedBoundaryReasons).sort(),
    );
    for (const [name, reason] of Object.entries(expectedBoundaryReasons)) {
      assert.deepEqual(candidate.boundaries[name as keyof typeof candidate.boundaries], {
        value: false,
        status: 'NOT_EXECUTED',
        reason,
      });
    }
    assert.deepEqual(candidate.actions, []);
  });

  it('keeps policy-page rendering copy unavailable and nonessential tracking disabled', () => {
    const affiliate = createPublicShellCandidate({ screenId: 'PUB-005' });
    const privacy = createPublicShellCandidate({ screenId: 'PUB-006' });
    const about = createPublicShellCandidate({ screenId: 'PUB-007' });
    for (const candidate of [affiliate, privacy, about]) {
      for (const slot of candidate.contentSlots) {
        assert.equal(slot.renderedCopy, null);
      }
    }
    assert.equal(
      privacy.contentSlots.find(({ topicCode }) => topicCode === 'PRIVACY_NONESSENTIAL_TRACKING')
        ?.principleCode,
      'NONESSENTIAL_TRACKING_DISABLED',
    );
    assert.equal(privacy.boundaries.tracking.value, false);
    assert.equal(privacy.boundaries.firstPartyEvent.value, false);
  });

  it('contains no runtime framework, router, browser, I/O, clock, random, database or provider API', () => {
    assert.deepEqual(
      [...source.matchAll(/^import .* from ['"]([^'"]+)['"];$/gm)].map((match) => match[1]),
      ['./serializable.ts'],
    );
    assert.doesNotMatch(source, /from ['"](?:react|react-dom|next(?:\/|['"])|node:)/i);
    assert.doesNotMatch(
      source,
      /\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|localStorage|sessionStorage|indexedDB)\b/,
    );
    assert.doesNotMatch(source, /\b(?:process\.env|import\.meta\.env|Date\.now|Math\.random)\b/);
    assert.doesNotMatch(
      source,
      /\b(?:readFile|writeFile|openSync|createServer|createRouter|registerRoute)\s*\(/,
    );
    assert.doesNotMatch(source, /\b(?:sql|sqlalchemy|prisma|drizzle|postgres|mysql|sqlite)\b/i);
    assert.doesNotMatch(source, /from ['"](?:openai|@aws-sdk\/|playwright|next\/router)/i);
    assert.doesNotMatch(source, /changes\/st-1701|ST-1701/);
  });

  it('does not implement homepage, category, article, 404, status, banner, CTA or outbound link models', () => {
    const candidate = createPublicShellCandidate({ screenId: 'PUB-004' });
    const serialized = JSON.stringify(candidate);
    assert.deepEqual(
      candidate.shell.header.navigationItems.map(({ route }) => route),
      ['/editorial-policy', '/affiliate-disclosure', '/privacy', '/about'],
    );
    assert.doesNotMatch(serialized, /"route":"\/(?:categories|articles|404|status)(?:\/|\")/);
    assert.doesNotMatch(
      serialized,
      /articleBody|articleId|disclosureBanner|affiliateLink|outboundLink|"cta"/i,
    );
    assert.doesNotMatch(serialized, /https?:\/\//i);
  });
});
