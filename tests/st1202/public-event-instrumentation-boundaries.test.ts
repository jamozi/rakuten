import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { createPublicEventInstrumentationCandidate } from '../../packages/web-ui/src/public-event-instrumentation.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = readFileSync(
  resolve(repositoryRoot, 'packages/web-ui/src/public-event-instrumentation.ts'),
  'utf8',
);
const HASH = 'f'.repeat(64);

function candidate() {
  return createPublicEventInstrumentationCandidate({
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1202_INSTRUMENTATION_REQUIREMENTS_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  });
}

describe('ST-1202 protected instrumentation boundaries', () => {
  it('keeps every runtime, formal, live, and authority boundary closed', () => {
    const value = candidate();
    for (const boundary of Object.values(value.boundaries)) {
      assert.deepEqual(
        { value: boundary.value, status: boundary.status },
        { value: false, status: 'NOT_EXECUTED' },
      );
      assert.ok(boundary.reason.length > 0);
    }
    assert.deepEqual(value.authorization, {
      approval: false,
      publication: false,
      release: false,
      production: false,
      formalEvidence: false,
    });
  });

  it('constructs or emits no event, action, effect, identity, or transport', () => {
    const value = candidate();
    assert.deepEqual(value.events, []);
    assert.deepEqual(value.actions, []);
    assert.deepEqual(value.effects, []);
    assert.equal(value.navigation.selectedTransport, null);
    assert.equal(value.privacy.sessionPseudonym, null);
    assert.ok(value.eventRequirements.every((event) => event.identity.value === null));
    assert.ok(value.eventRequirements.every((event) => event.eventValues.value === null));
  });

  it('imports only the strict JSON utility and has no executable runtime surface', () => {
    assert.deepEqual(
      [...source.matchAll(/^import .* from ['"]([^'"]+)['"];$/gm)].map((match) => match[1]),
      ['./serializable.ts'],
    );
    assert.doesNotMatch(source, /from ['"](?:react|react-dom|next(?:\/|['"])|node:)/i);
    assert.doesNotMatch(source, /\bnew\s+PerformanceObserver\s*\(/);
    assert.doesNotMatch(source, /\bnavigator\s*\.\s*sendBeacon\s*\(/);
    assert.doesNotMatch(source, /\bfetch\s*\(/);
    assert.doesNotMatch(source, /\b(?:localStorage|sessionStorage|indexedDB)\s*\./);
    assert.doesNotMatch(
      source,
      /\b(?:document\.cookie|process\.env|import\.meta\.env|Date\.now|Math\.random)\b/,
    );
    assert.doesNotMatch(
      source,
      /\b(?:createRoot|createRouter|registerRoute|addEventListener|dispatchEvent)\s*\(/,
    );
  });

  it('does not import or bind any predecessor runtime implementation', () => {
    assert.doesNotMatch(source, /public-article-renderer/);
    assert.doesNotMatch(source, /disclosure-affiliate-cta/);
    assert.doesNotMatch(source, /public-performance-rum/);
    assert.doesNotMatch(source, /event_collector/);
    assert.doesNotMatch(source, /PUB-004/);
  });
});
