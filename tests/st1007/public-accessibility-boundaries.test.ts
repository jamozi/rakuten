import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { createPublicAccessibilityAcceptanceCandidate } from '../../packages/web-ui/src/public-accessibility-acceptance.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const source = readFileSync(
  resolve(repositoryRoot, 'packages/web-ui/src/public-accessibility-acceptance.ts'),
  'utf8',
);
const HASH = 'f'.repeat(64);

function candidate() {
  return createPublicAccessibilityAcceptanceCandidate({
    storyId: 'ST-1007',
    coordinate: {
      kind: 'SYNTHETIC_ST1007_ACCESSIBILITY_REQUIREMENTS_FIXTURE',
      expectedSha256: HASH,
      observedSha256: HASH,
    },
  });
}

describe('ST-1007 protected accessibility acceptance boundaries', () => {
  it('keeps every runtime, formal, and authority boundary closed', () => {
    const value = candidate();
    for (const boundary of Object.values(value.boundaries)) {
      assert.deepEqual(
        { value: boundary.value, status: boundary.status },
        { value: false, status: 'NOT_EXECUTED' },
      );
      assert.ok(boundary.reason.length > 0);
    }
    assert.deepEqual(value.aggregate, {
      p0ChecklistPass: false,
      allItemsVerified: false,
      conditionalLocalEligibility: false,
      reasons: [
        'PUBLIC_RUNTIME_DOM_ABSENT',
        'CHECKLIST_APPLICABILITY_NOT_EVALUATED',
        'AUTOMATED_AUDIT_NOT_EXECUTED',
        'KEYBOARD_ZOOM_SCREEN_READER_COGNITIVE_REVIEW_NOT_EXECUTED',
        'FORMAL_TST_023_NOT_EXECUTED',
        'FORMAL_TST_024_NOT_EXECUTED',
      ],
    });
    assert.equal(value.authorization.accessibilityConformance, false);
    assert.equal(value.authorization.formalEvidence, false);
  });

  it('accepts no claimed evidence and emits no events, actions, or effects', () => {
    const value = candidate();
    assert.equal(value.evidenceState.acceptsClaimedEvidence, false);
    assert.equal(value.evidenceState.browserExecuted, false);
    assert.equal(value.evidenceState.automatedAuditExecuted, false);
    assert.equal(value.evidenceState.screenReaderExecuted, false);
    assert.equal(value.evidenceState.wcagConformanceClaim, false);
    assert.deepEqual(value.evidenceState.evidenceRefs, []);
    assert.deepEqual(value.events, []);
    assert.deepEqual(value.actions, []);
    assert.deepEqual(value.effects, []);
  });

  it('uses no DOM, browser, accessibility runner, clock, randomness, I/O, or provider dependency', () => {
    assert.deepEqual(
      [...source.matchAll(/^import .* from ['"]([^'"]+)['"];$/gm)].map((match) => match[1]),
      ['./serializable.ts'],
    );
    assert.doesNotMatch(source, /from ['"](?:react|react-dom|next(?:\/|['"])|node:)/i);
    assert.doesNotMatch(source, /\b(?:axe|playwright|puppeteer)\s*\(/i);
    assert.doesNotMatch(source, /\b(?:document|window|navigator)\s*\./);
    assert.doesNotMatch(source, /\bfetch\s*\(/);
    assert.doesNotMatch(source, /\b(?:process\.env|Date\.now|Math\.random)\b/);
    assert.doesNotMatch(
      source,
      /\b(?:readFile|writeFile|openSync|createServer|createRouter|registerRoute)\s*\(/,
    );
  });
});
