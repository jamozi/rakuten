import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  PUBLIC_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION,
  PUBLIC_ACCESSIBILITY_ACCEPTANCE_ERROR_CODES,
  PUBLIC_ACCESSIBILITY_CHECKLIST,
  PUBLIC_ACCESSIBILITY_COMPONENTS,
  PUBLIC_ACCESSIBILITY_EVIDENCE_SUITES,
  PUBLIC_ACCESSIBILITY_SCREENS,
  createPublicAccessibilityAcceptanceCandidate,
} from '../../packages/web-ui/src/index.ts';

const HASH = 'a'.repeat(64);
const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

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

describe('ST-1007 disabled accessibility evidence requirements contract', () => {
  it('pins the exact thirty-item canonical checklist without a pass result', () => {
    assert.equal(PUBLIC_ACCESSIBILITY_CHECKLIST.length, 30);
    assert.deepEqual(
      PUBLIC_ACCESSIBILITY_CHECKLIST.map(({ id }) => id),
      Array.from({ length: 30 }, (_, index) => `A11Y-${String(index + 1).padStart(3, '0')}`),
    );
    assert.deepEqual(
      Object.fromEntries(
        ['automated', 'automated+manual', 'manual', 'screen-reader'].map((method) => [
          method,
          PUBLIC_ACCESSIBILITY_CHECKLIST.filter(({ verification }) => verification === method)
            .length,
        ]),
      ),
      { automated: 2, 'automated+manual': 6, manual: 20, 'screen-reader': 2 },
    );
    for (const item of PUBLIC_ACCESSIBILITY_CHECKLIST) {
      assert.equal(item.implementationStatus, 'NOT_STARTED');
      assert.equal(item.testStatus, 'NOT_EXECUTED');
    }
  });

  it('matches every canonical checklist field byte-for-field after CSV decoding', () => {
    const rows = readFileSync(
      resolve(repositoryRoot, 'docs/canonical/02_ui/RAOS_08_accessibility_checklist_v1.0.csv'),
      'utf8',
    )
      .replace(/^\uFEFF/, '')
      .trimEnd()
      .split('\n')
      .slice(1)
      .map((line) => line.replace(/\r$/, '').split(','));
    assert.deepEqual(
      PUBLIC_ACCESSIBILITY_CHECKLIST.map((item) => [
        item.id,
        item.requirement,
        item.reference,
        item.verification,
        item.designStatus,
        item.implementationStatus,
        item.testStatus,
      ]),
      rows,
    );
  });

  it('pins the exact public screen catalog and bounded component inventory', () => {
    assert.deepEqual(
      PUBLIC_ACCESSIBILITY_SCREENS.map((screen) => screen['id']),
      Array.from({ length: 10 }, (_, index) => `PUB-${String(index + 1).padStart(3, '0')}`),
    );
    assert.deepEqual(
      PUBLIC_ACCESSIBILITY_COMPONENTS.map((component) => component['id']),
      ['UI-C002', 'UI-C003', 'UI-C004', 'UI-C031', 'UI-C032', 'UI-C033', 'UI-C034', 'UI-C036'],
    );
    for (const screen of PUBLIC_ACCESSIBILITY_SCREENS) {
      assert.equal(screen['runtimeVerification'], 'NOT_EXECUTED');
    }
    for (const component of PUBLIC_ACCESSIBILITY_COMPONENTS) {
      assert.equal(component['runtimeVerification'], 'NOT_EXECUTED');
    }
  });

  it('pins TST-023 to CI and TST-024 to staging without executing either', () => {
    assert.deepEqual(
      PUBLIC_ACCESSIBILITY_EVIDENCE_SUITES.map((suite) => ({
        id: suite['id'],
        environments: suite['environments'],
        executionStatus: suite['executionStatus'],
      })),
      [
        { id: 'TST-023', environments: ['CI'], executionStatus: 'NOT_EXECUTED' },
        { id: 'TST-024', environments: ['staging'], executionStatus: 'NOT_EXECUTED' },
      ],
    );
  });

  it('uses a stable closed classification and error vocabulary', () => {
    assert.equal(candidate().classification, PUBLIC_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION);
    assert.equal(
      candidate().classification,
      'UNREGISTERED_DISABLED_HEADLESS_ST1007_ACCESSIBILITY_EVIDENCE_REQUIREMENTS_CANDIDATE',
    );
    assert.equal(PUBLIC_ACCESSIBILITY_ACCEPTANCE_ERROR_CODES.length, 14);
    assert.equal(new Set(PUBLIC_ACCESSIBILITY_ACCEPTANCE_ERROR_CODES).size, 14);
  });
});
