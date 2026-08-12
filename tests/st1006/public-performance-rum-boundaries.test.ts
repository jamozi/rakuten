import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { createPublicPerformanceRumCandidate } from '../../packages/web-ui/src/public-performance-rum.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = readFileSync(
  resolve(repositoryRoot, 'packages/web-ui/src/public-performance-rum.ts'),
  'utf8',
);
const HASH = 'f'.repeat(64);

function candidate() {
  return createPublicPerformanceRumCandidate({
    screenId: 'PUB-003',
    route: '/articles/{slug}',
    coordinate: {
      kind: 'SYNTHETIC_ST1006_PERFORMANCE_REQUIREMENTS_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  });
}

describe('ST-1006 protected performance and RUM boundaries', () => {
  it('keeps every runtime, privacy, formal, and authority boundary closed', () => {
    const value = candidate();
    for (const boundary of Object.values(value.boundaries)) {
      assert.deepEqual(
        { value: boundary.value, status: boundary.status },
        { value: false, status: 'NOT_EXECUTED' },
      );
      assert.ok(boundary.reason.length > 0);
    }
    assert.equal(value.conditionalLocalEligibility, false);
    assert.deepEqual(value.authorization, {
      approval: false,
      publication: false,
      release: false,
      production: false,
      formalEvidence: false,
    });
  });

  it('emits no observations, events, actions, effects, or selected transport', () => {
    const value = candidate();
    assert.deepEqual(value.observations.metricValues, []);
    assert.deepEqual(value.observations.emittedEvents, []);
    assert.deepEqual(value.events, []);
    assert.deepEqual(value.actions, []);
    assert.deepEqual(value.effects, []);
    assert.equal(value.rumRequirements.transport, null);
    assert.equal(value.rumRequirements.eventEmissionEnabled, false);
  });

  it('uses no runtime, browser, clock, randomness, I/O, or provider dependency', () => {
    assert.deepEqual(
      [...source.matchAll(/^import .* from ['"]([^'"]+)['"];$/gm)].map((match) => match[1]),
      ['./serializable.ts'],
    );
    assert.doesNotMatch(source, /from ['"](?:react|react-dom|next(?:\/|['"])|node:)/i);
    assert.doesNotMatch(source, /\bnew\s+PerformanceObserver\s*\(/);
    assert.doesNotMatch(source, /\bnavigator\s*\.\s*sendBeacon\s*\(/);
    assert.doesNotMatch(source, /\bfetch\s*\(/);
    assert.doesNotMatch(source, /\b(?:localStorage|sessionStorage|indexedDB)\s*\./);
    assert.doesNotMatch(source, /\b(?:document\.cookie|process\.env|Date\.now|Math\.random)\b/);
    assert.doesNotMatch(
      source,
      /\b(?:readFile|writeFile|openSync|createServer|createRouter|registerRoute)\s*\(/,
    );
  });
});
