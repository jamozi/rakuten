import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { createPublicArticleRendererCandidate } from '../../packages/web-ui/src/public-article-renderer.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = readFileSync(
  resolve(repositoryRoot, 'packages/web-ui/src/public-article-renderer.ts'),
  'utf8',
);
const HASH = 'b'.repeat(64);

function candidate() {
  return createPublicArticleRendererCandidate({
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_PUBLIC_PROJECTION_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
    slots: [],
  });
}

const expectedReasons = {
  routeRegistered: 'NO_RUNTIME_ROUTE_REGISTERED',
  interactive: 'INTERACTION_DISABLED',
  dom: 'DOM_NOT_IMPLEMENTED',
  react: 'REACT_NOT_IMPLEMENTED',
  ssr: 'SSR_NOT_IMPLEMENTED',
  api: 'PUBLIC_API_NOT_CONNECTED',
  network: 'NETWORK_NOT_USED',
  database: 'DATABASE_NOT_USED',
  publicReadModel: 'PUBLIC_READMODEL_NOT_CONNECTED',
  executableProjection: 'ST_0904_EXECUTABLE_PROJECTION_ABSENT',
  authoritativeSnapshot: 'AUTHORITATIVE_SNAPSHOT_ABSENT',
  contentRendering: 'CONTENT_MAPPING_NOT_AUTHORIZED',
  htmlRendering: 'HTML_RENDERING_PROHIBITED',
  schemaMarkup: 'STRUCTURED_DATA_OUT_OF_SCOPE',
  browser: 'BROWSER_NOT_EXECUTED',
  accessibility: 'ACCESSIBILITY_NOT_EXECUTED',
  formalTst021: 'FORMAL_TST_021_NOT_EXECUTED',
  formalTst022: 'FORMAL_TST_022_NOT_EXECUTED',
  formalTst023: 'FORMAL_TST_023_NOT_EXECUTED',
  live: 'LIVE_NOT_AUTHORIZED',
  staging: 'STAGING_NOT_AUTHORIZED',
  publicationAuthorization: 'PUBLICATION_NOT_AUTHORIZED',
  release: 'RELEASE_NOT_AUTHORIZED',
  production: 'PRODUCTION_NOT_AUTHORIZED',
  localEligibility: 'CONTENT_ROUTE_AND_RUNTIME_GATES_UNSATISFIED',
} as const;

describe('ST-1002 execution and authority boundaries', () => {
  it('keeps every execution, authority, and eligibility boundary closed', () => {
    const value = candidate();
    assert.deepEqual(Object.keys(value.boundaries).sort(), Object.keys(expectedReasons).sort());
    for (const [name, reason] of Object.entries(expectedReasons)) {
      assert.deepEqual(value.boundaries[name as keyof typeof value.boundaries], {
        value: false,
        status: 'NOT_EXECUTED',
        reason,
      });
    }
    assert.deepEqual(value.actions, []);
  });

  it('uses no runtime, framework, browser, I/O, clock, random, database, or provider import', () => {
    assert.deepEqual(
      [...source.matchAll(/^import .* from ['"]([^'"]+)['"];$/gm)].map((match) => match[1]),
      ['./serializable.ts', './public-article-recorded.v2.ts'],
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
    assert.doesNotMatch(source, /from ['"](?:openai|@aws-sdk\/|playwright|next\/router)/i);
  });

  it('contains no public article data, links, products, CTA, disclosure, or structured output', () => {
    const value = candidate();
    const serialized = JSON.stringify(value);
    assert.doesNotMatch(serialized, /https?:\/\//i);
    assert.doesNotMatch(
      serialized,
      /"(?:articleId|publicationId|approvalIds|claimIds|inputHashes|qualityResultId|sourcePacket|evidence|finance|rawPrompt)"/i,
    );
    assert.doesNotMatch(
      serialized,
      /"(?:productCards|offers|affiliateUrl|cta|disclosureText|structuredData)"/i,
    );
    assert.deepEqual(value.metadata.robots, {
      index: false,
      follow: false,
      directive: 'noindex,nofollow',
    });
  });
});
