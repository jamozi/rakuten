import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION,
  ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS,
  ADMIN_VISUAL_ACCESSIBILITY_V2_CHECKLIST,
  ADMIN_VISUAL_ACCESSIBILITY_V2_CLASSIFICATION,
  ADMIN_VISUAL_ACCESSIBILITY_V2_COMPONENT_INVENTORY,
  ADMIN_VISUAL_ACCESSIBILITY_V2_CRITICAL_WORKFLOWS,
  ADMIN_VISUAL_ACCESSIBILITY_V2_FORMAL_SUITES,
  ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_IDS,
  PUBLICATION_REVIEW_COMPONENT_IDS,
  createAdminVisualAccessibilityV2Candidate,
  createArticleWorkspaceV2,
  createEvidenceWorkspaceModelV2,
  createFreshnessOperationsWorkspaceV2,
} from '../../packages/web-ui/src/index.ts';

interface GeneratedScreen {
  readonly screen_id: string;
  readonly component_ids: readonly string[];
  readonly component_exposure_kind: string;
  readonly story_component_ids: readonly string[];
}

interface GeneratedInventory {
  readonly screens: readonly GeneratedScreen[];
}

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const generated = JSON.parse(
  readFileSync(
    resolve(
      repositoryRoot,
      'changes/st-1105/generated/admin-visual-accessibility-recorded.v2.json',
    ),
    'utf8',
  ),
) as GeneratedInventory;

describe('ST-1105 additive V2 inventory and evidence boundary', () => {
  it('preserves V1 and completes the exact dependency-exposed screen scope additively', () => {
    assert.equal(
      ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_CLASSIFICATION,
      'INCOMPLETE_DISABLED_HEADLESS_ST1105_ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_CANDIDATE',
    );
    assert.equal(
      ADMIN_VISUAL_ACCESSIBILITY_V2_CLASSIFICATION,
      'MAXIMUM_SAFE_LOCAL_RECORDED_SYNTHETIC_ADMIN_VISUAL_ACCESSIBILITY_ACCEPTANCE_V2',
    );
    assert.deepEqual(
      ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_IDS,
      ADMIN_VISUAL_ACCESSIBILITY_SCREEN_IDS,
    );
    assert.equal(ADMIN_VISUAL_ACCESSIBILITY_V2_SCREEN_IDS.length, 44);
    assert.equal(ADMIN_VISUAL_ACCESSIBILITY_V2_COMPONENT_INVENTORY.length, 29);
    assert.equal(ADMIN_VISUAL_ACCESSIBILITY_V2_CRITICAL_WORKFLOWS.length, 10);
    assert.equal(ADMIN_VISUAL_ACCESSIBILITY_V2_CHECKLIST.length, 30);
  });

  it('binds per-screen component exposure to executable dependency projections', () => {
    const byScreen = new Map(generated.screens.map((screen) => [screen.screen_id, screen]));
    for (const screenId of ['EVD-001', 'EVD-002', 'EVD-003', 'EVD-004']) {
      const dependency = createEvidenceWorkspaceModelV2({ screenId });
      assert.deepEqual(byScreen.get(screenId)?.component_ids, dependency.screen.components);
    }
    for (const screenId of [
      'FRESH-001',
      'FRESH-002',
      'FRESH-003',
      'OPS-001',
      'OPS-002',
      'OPS-003',
      'OPS-004',
      'OPS-005',
    ]) {
      const dependency = createFreshnessOperationsWorkspaceV2({
        screenId: screenId as Parameters<
          typeof createFreshnessOperationsWorkspaceV2
        >[0]['screenId'],
      });
      assert.deepEqual(byScreen.get(screenId)?.component_ids, dependency.projection.components);
    }
    for (const screenId of ['EDT-002', 'EDT-003', 'EDT-005', 'EDT-006', 'EDT-007', 'EDT-009']) {
      const dependency = createArticleWorkspaceV2({
        screenId: screenId as Parameters<typeof createArticleWorkspaceV2>[0]['screenId'],
      });
      const exposed = new Set<string>(['UI-C014']);
      for (const pane of dependency.panes) {
        for (const componentId of pane.componentIds) exposed.add(componentId);
      }
      assert.deepEqual(byScreen.get(screenId)?.component_ids, [...exposed].sort());
    }
    const publication = byScreen.get('REV-001');
    assert.equal(publication?.component_exposure_kind, 'DEPENDENCY_STORY_LEVEL_INVENTORY');
    assert.deepEqual(publication?.story_component_ids, PUBLICATION_REVIEW_COMPONENT_IDS);
  });

  it('projects all ten canonical critical workflows without executing business actions', () => {
    assert.deepEqual(
      ADMIN_VISUAL_ACCESSIBILITY_V2_CRITICAL_WORKFLOWS.map((workflow) => workflow['workflow_id']),
      Array.from({ length: 10 }, (_, index) => `UI-WF-${String(index + 1).padStart(3, '0')}`),
    );
    for (const workflow of ADMIN_VISUAL_ACCESSIBILITY_V2_CRITICAL_WORKFLOWS) {
      assert.equal(workflow['business_action_executed'], false);
      assert.equal(workflow['formal_execution_status'], 'NOT_EXECUTED');
    }
  });

  it('keeps every formal suite and manual boundary NOT_EXECUTED', () => {
    assert.deepEqual(
      ADMIN_VISUAL_ACCESSIBILITY_V2_FORMAL_SUITES.map((suite) => suite['id']),
      ['TST-023', 'TST-024', 'TST-025'],
    );
    assert.equal(
      ADMIN_VISUAL_ACCESSIBILITY_V2_FORMAL_SUITES.every(
        (suite) => suite['execution_status'] === 'NOT_EXECUTED',
      ),
      true,
    );
    const candidate = createAdminVisualAccessibilityV2Candidate({ screenId: 'PUBA-004' });
    assert.equal(candidate.screenInventory.completeness, 'COMPLETE_DEPENDENCY_EXPOSED_SCOPE');
    assert.equal(candidate.criticalWorkflowCompleteness, 'COMPLETE_CANONICAL_CATALOG_SCOPE');
    assert.equal(candidate.formalAcceptanceAchieved, false);
    assert.equal(candidate.productionEligible, false);
    assert.equal(candidate.formalBoundary['TST-023'], 'NOT_EXECUTED');
    assert.equal(candidate.formalBoundary['TST-024'], 'NOT_EXECUTED');
    assert.equal(candidate.formalBoundary['TST-025'], 'NOT_EXECUTED');
    assert.equal(candidate.formalBoundary['screen_reader'], 'NOT_EXECUTED');
    assert.equal(candidate.visualBaseline['approved'], false);
  });

  it('records local synthetic browser success separately from dependency findings and formal evidence', () => {
    const evidence = JSON.parse(
      readFileSync(
        resolve(repositoryRoot, 'changes/st-1105/evidence/local-browser-automated.v2.json'),
        'utf8',
      ),
    );
    const baseline = JSON.parse(
      readFileSync(
        resolve(repositoryRoot, 'changes/st-1105/baselines/admin-visual.synthetic.v2.json'),
        'utf8',
      ),
    );
    assert.equal(evidence.synthetic_fixture.result, 'LOCAL_AUTOMATED_PASS_SYNTHETIC_FIXTURE_ONLY');
    assert.equal(evidence.synthetic_fixture.screen_count, 44);
    assert.equal(
      evidence.dependency_renderer.result,
      'LOCAL_AUTOMATED_REVIEW_REQUIRED_DEPENDENCY_RENDERER_ONLY',
    );
    assert.equal(evidence.formal_boundary['TST-023'], 'NOT_EXECUTED');
    assert.equal(evidence.formal_boundary['TST-024'], 'NOT_EXECUTED');
    assert.equal(evidence.formal_boundary['TST-025'], 'NOT_EXECUTED');
    assert.equal(evidence.wcag_conformance, 'NOT_CLAIMED');
    assert.equal(baseline.approved, false);
    assert.equal(baseline.formal_TST_025, 'NOT_EXECUTED');
    assert.equal(baseline.screenshots.length, 44);
    assert.equal(
      new Set(
        (baseline.screenshots as readonly { readonly screen_id: string }[]).map(
          (item) => item.screen_id,
        ),
      ).size,
      44,
    );
    assert.equal(
      (baseline.screenshots as readonly { readonly sha256: string }[]).every((item) =>
        /^[0-9a-f]{64}$/u.test(item.sha256),
      ),
      true,
    );
  });
});
