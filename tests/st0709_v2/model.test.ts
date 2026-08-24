import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  AI_GOVERNANCE_RECORDED_FIXTURE_V2,
  createAiGovernanceWorkspaceModelV2,
} from '../../packages/web-ui/src/index.ts';
import { evaluateAdminRoute } from '../../packages/web-ui/src/route-guard.ts';
import type { JsonObject } from '../../packages/web-ui/src/serializable.ts';

function rows(sectionIndex: number): readonly JsonObject[] {
  const section = AI_GOVERNANCE_RECORDED_FIXTURE_V2.sections[sectionIndex];
  assert.ok(section);
  return section.table.rows;
}

describe('ST-0709 V2 recorded governance model', () => {
  it('returns deterministic detached deeply frozen JSON models', () => {
    const first = createAiGovernanceWorkspaceModelV2({ screenId: 'GOV-001' });
    const second = createAiGovernanceWorkspaceModelV2({ screenId: 'GOV-001' });
    assert.deepEqual(first, second);
    assert.notEqual(first, second);
    assert.notEqual(first.sections, AI_GOVERNANCE_RECORDED_FIXTURE_V2.sections);
    assert.deepEqual(JSON.parse(JSON.stringify(first)), first);
    assert.ok(Object.isFrozen(first));
    assert.ok(Object.isFrozen(first.sections));
    assert.ok(Object.isFrozen(first.sections[0]?.table));
    assert.ok(Object.isFrozen(first.sections[0]?.table.rows));
    assert.ok(Object.isFrozen(first.sections[0]?.table.rows[0]));
  });

  it('provides semantic table and non-color-only status metadata for every section', () => {
    for (const section of AI_GOVERNANCE_RECORDED_FIXTURE_V2.sections) {
      assert.equal(section.mode, 'READ_ONLY');
      assert.deepEqual(section.actions, []);
      assert.ok(section.table.caption.length > 0);
      assert.ok(section.table.columns.length > 0);
      assert.ok(section.table.columns.some(({ key }) => key === section.table.rowHeaderKey));
      for (const column of section.table.columns) {
        assert.equal(column.semanticRole, 'COLUMN_HEADER');
      }
      for (const row of section.table.rows) {
        assert.equal(typeof row[section.table.rowHeaderKey], 'string');
      }
    }
    for (const row of [...rows(0), ...rows(1), ...rows(2)]) {
      const status = row['status'] as JsonObject;
      assert.equal(status['colorOnly'], false);
      assert.equal(typeof status['text'], 'string');
      assert.equal(typeof status['code'], 'string');
      assert.equal(typeof status['icon'], 'string');
    }
  });

  it('shows exact recorded evaluation and refusal proposal without granting authority', () => {
    const evaluation = rows(3)[0];
    const release = rows(4)[0];
    assert.ok(evaluation);
    assert.ok(release);
    assert.equal(evaluation['outcome'], 'REFUSED_INCOMPLETE_EVIDENCE');
    assert.equal(
      evaluation['reportSha256'],
      'e16248e167bf267645ebdbf25ca7e7e9b2e220925bd8461566cc07a9ba3b381d',
    );
    assert.equal(release['outcome'], 'REFUSED_INCOMPLETE_EVIDENCE');
    assert.equal(
      release['reportSha256'],
      'a2931f453f4beb6c028babec25194cbfe8c2571e37f08950fa1af669224543a8',
    );
    assert.equal(release['authority'], 'NONE');
    assert.equal(release['approvalAuthority'], 'HUMAN_ONLY');
    assert.equal(release['directActivation'], false);
    assert.ok(
      Object.values(release['operationalAuthority'] as JsonObject).every(
        (value) => value === false,
      ),
    );
    assert.ok(
      Object.values(AI_GOVERNANCE_RECORDED_FIXTURE_V2.authority).every((value) => value === false),
    );
  });

  it('shows configured candidate ceilings while retaining unknown actual costs', () => {
    for (const cost of rows(5)) {
      assert.equal(typeof cost['configuredCandidateCeilingJpy'], 'number');
      assert.equal(cost['configuredUnit'], 'JPY_PER_TASK_CANDIDATE_LIMIT');
      assert.equal(cost['observedActualCostJpy'], null);
      assert.equal(cost['unknownTreatedAsZero'], false);
      assert.equal(cost['od009Resolution'], 'UNRESOLVED');
      const status = cost['observedCostStatus'] as JsonObject;
      assert.equal(status['code'], 'UNAVAILABLE');
      assert.equal(status['colorOnly'], false);
    }
  });

  it('keeps GOV-001 unregistered under the disabled ST-1101 route boundary', () => {
    const decision = evaluateAdminRoute({
      path: '/admin/governance/ai',
      authenticated: true,
      siteScope: 'synthetic-site',
      roles: ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'SECURITY_AUDITOR'],
    });
    assert.equal(decision.code, 'UNREGISTERED_ROUTE');
    assert.deepEqual(AI_GOVERNANCE_RECORDED_FIXTURE_V2.route, {
      authentication: 'NOT_EXECUTED',
      authorizationGranted: false,
      navigation: 'DISABLED',
      path: '/admin/governance/ai',
      registration: 'UNREGISTERED',
      rendering: 'NOT_EXECUTED',
    });
  });
});
