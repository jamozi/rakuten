import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION,
  ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST,
  ADMIN_VISUAL_ACCESSIBILITY_ERROR_CODES,
  ADMIN_VISUAL_ACCESSIBILITY_SCREEN_GROUPS,
  ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS,
  ADMIN_VISUAL_ACCESSIBILITY_SUITES,
  createAdminVisualAccessibilityCandidate,
} from '../../packages/web-ui/src/index.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

describe('ST-1105 incomplete admin visual/accessibility contract', () => {
  it('pins exactly 44 dependency-exposed screen IDs in approved group order', () => {
    assert.deepEqual(ADMIN_VISUAL_ACCESSIBILITY_SCREEN_GROUPS, [
      {
        storyId: 'ST-0506',
        screenIds: [
          'PORT-001',
          'PORT-002',
          'PORT-003',
          'PORT-004',
          'PORT-005',
          'PORT-006',
          'CAT-001',
          'CAT-002',
          'CAT-003',
          'CAT-004',
          'CAT-005',
          'CAT-006',
        ],
      },
      { storyId: 'ST-0606', screenIds: ['EVD-001', 'EVD-002', 'EVD-003', 'EVD-004'] },
      { storyId: 'ST-0709', screenIds: ['GOV-001'] },
      {
        storyId: 'ST-0906',
        screenIds: [
          'REV-001',
          'REV-002',
          'REV-003',
          'PUBA-001',
          'PUBA-002',
          'PUBA-003',
          'PUBA-004',
        ],
      },
      {
        storyId: 'ST-1102',
        screenIds: ['EDT-002', 'EDT-003', 'EDT-005', 'EDT-006', 'EDT-007', 'EDT-009'],
      },
      {
        storyId: 'ST-1103',
        screenIds: [
          'FRESH-001',
          'FRESH-002',
          'FRESH-003',
          'OPS-001',
          'OPS-002',
          'OPS-003',
          'OPS-004',
          'OPS-005',
        ],
      },
      {
        storyId: 'ST-1104',
        screenIds: ['ANA-001', 'ANA-002', 'ANA-003', 'FIN-001', 'FIN-002', 'FIN-003'],
      },
    ]);
    assert.equal(ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS.length, 44);
    assert.equal(new Set(ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS).size, 44);
    assert.deepEqual(
      ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS,
      ADMIN_VISUAL_ACCESSIBILITY_SCREEN_GROUPS.flatMap(({ screenIds }) => screenIds),
    );
  });

  it('matches all thirty canonical accessibility rows exactly after CSV decoding', () => {
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
      ADMIN_VISUAL_ACCESSIBILITY_CHECKLIST.map((item) => [
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

  it('pins the complete canonical TST-023, TST-024, and TST-025 metadata', () => {
    assert.deepEqual(ADMIN_VISUAL_ACCESSIBILITY_SUITES, [
      {
        id: 'TST-023',
        name: 'Accessibility automated',
        layer: 'ui',
        purpose: 'axe等による機械検査',
        candidateTools: ['axe-core', 'Playwright'],
        releaseBlocking: true,
        environments: ['CI'],
        owner: 'Engineering',
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        executionStatus: 'NOT_EXECUTED',
      },
      {
        id: 'TST-024',
        name: 'Accessibility manual',
        layer: 'ui',
        purpose: 'Keyboard、Zoom、Screen reader、cognitive checks',
        candidateTools: ['NVDA/VoiceOver', 'manual checklist'],
        releaseBlocking: true,
        environments: ['staging'],
        owner: 'QA/Accessibility',
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        executionStatus: 'NOT_EXECUTED',
      },
      {
        id: 'TST-025',
        name: 'Visual regression',
        layer: 'ui',
        purpose: '主要Template/Component差分',
        candidateTools: ['Playwright screenshots'],
        releaseBlocking: false,
        environments: ['CI'],
        owner: 'Engineering',
        designStatus: 'APPROVED_FOR_IMPLEMENTATION',
        implementationStatus: 'NOT_STARTED',
        executionStatus: 'NOT_EXECUTED',
      },
    ]);
  });

  it('exports a closed classification and unique error vocabulary', () => {
    const candidate = createAdminVisualAccessibilityCandidate({ screenId: 'PORT-001' });
    assert.equal(candidate.classification, ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION);
    assert.equal(
      candidate.classification,
      'INCOMPLETE_DISABLED_HEADLESS_ST1105_ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_CANDIDATE',
    );
    assert.equal(
      new Set(ADMIN_VISUAL_ACCESSIBILITY_ERROR_CODES).size,
      ADMIN_VISUAL_ACCESSIBILITY_ERROR_CODES.length,
    );
  });
});
