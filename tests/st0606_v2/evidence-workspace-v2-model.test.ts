import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  EVIDENCE_WORKSPACE_V2_SCREEN_IDS,
  createEvidenceWorkspaceModelV2,
  evaluateAdminRoute,
} from '../../packages/web-ui/src/index.ts';

describe('ST-0606 V2 headless evidence workspace model', () => {
  it('projects all four canonical screens deterministically and immutably', () => {
    for (const screenId of EVIDENCE_WORKSPACE_V2_SCREEN_IDS) {
      const first = createEvidenceWorkspaceModelV2({ screenId });
      const second = createEvidenceWorkspaceModelV2({ screenId });
      assert.deepEqual(first, second);
      assert.notEqual(first, second);
      assert.equal(first.screen.screen_id, screenId);
      assert.deepEqual(first.screenOrder, EVIDENCE_WORKSPACE_V2_SCREEN_IDS);
      assert.equal(first.localImplementationComplete, true);
      assert.equal(first.formalAcceptanceAchieved, false);
      assert.equal(first.productionEligible, false);
      assert.equal(Object.isFrozen(first), true);
      assert.equal(Object.isFrozen(first.screen), true);
      assert.equal(Object.isFrozen(first.sources), true);
      assert.equal(Object.isFrozen(first.attestations), true);
    }
  });

  it('keeps every EVD route unregistered under the disabled ST-1101 boundary', () => {
    for (const screenId of EVIDENCE_WORKSPACE_V2_SCREEN_IDS) {
      const model = createEvidenceWorkspaceModelV2({ screenId });
      assert.deepEqual(model.screen.route, {
        registered: false,
        render_enabled: false,
        status: 'UNREGISTERED_AUTH_TRANSPORT_UNRESOLVED',
      });
      const decision = evaluateAdminRoute({
        path: model.screen.route_pattern,
        authenticated: true,
        siteScope: 'recorded-synthetic-site',
        roles: ['EDITOR'],
      });
      assert.equal(decision.code, 'UNREGISTERED_ROUTE');
      assert.equal(decision.navigationEligible, false);
      assert.equal(decision.renderEligible, false);
      assert.equal(decision.authorizationGranted, false);
      assert.equal(
        Object.values(model.authority).every((value) => value === false),
        true,
      );
    }
  });

  it('defines semantic keyboard/table/status contracts without claiming browser evidence', () => {
    for (const screenId of EVIDENCE_WORKSPACE_V2_SCREEN_IDS) {
      const { screen, verification } = createEvidenceWorkspaceModelV2({ screenId });
      assert.equal(screen.semantic_view.main_landmark.role, 'main');
      assert.equal(screen.semantic_view.main_landmark.labelled_by, screen.semantic_view.h1.id);
      assert.equal(screen.semantic_view.h1.count, 1);
      assert.equal(
        screen.semantic_view.skip_link.href,
        `#${screen.semantic_view.main_landmark.id}`,
      );
      assert.deepEqual(screen.semantic_view.keyboard_contract, [
        'Tab',
        'Shift+Tab',
        'ArrowUp',
        'ArrowDown',
      ]);
      assert.equal(screen.semantic_view.status_cue.color_only, false);
      assert.notEqual(screen.semantic_view.status_cue.text, '');
      assert.notEqual(screen.table.caption, '');
      assert.equal(screen.table.row_header_scope, 'row');
      assert.equal(
        screen.table.columns.every((column) => column.scope === 'col'),
        true,
      );
      assert.equal(screen.semantic_view.rendered, false);
      assert.equal(screen.semantic_view.browser_verified, false);
      assert.equal(verification['TST-022'], 'NOT_EXECUTED');
      assert.equal(verification['TST-024'], 'NOT_EXECUTED');
    }
  });

  it('makes every displayed fact and matrix row source-reachable within two semantic steps', () => {
    const model = createEvidenceWorkspaceModelV2({ screenId: 'EVD-002' });
    const sourceIds = new Set(model.sources.map((source) => source.source_id));
    const paths = new Map(model.sourceAccess.paths.map((path) => [path.path_id, path]));
    for (const row of [...model.facts, ...model.matrix.rows]) {
      const path = paths.get(row.source_access_path_id);
      assert.ok(path);
      assert.equal(path.maximum_steps, 2);
      assert.equal(path.step_count, 2);
      assert.equal(path.steps.length, 2);
      assert.equal(path.effect, 'NONE');
      assert.equal(path.dispatch, 'NOT_EXECUTED');
      assert.equal(sourceIds.has(path.source_id), true);
    }
  });

  it('keeps missing/live values explicit while distinguishing a known recorded empty set', () => {
    const model = createEvidenceWorkspaceModelV2({ screenId: 'EVD-004' });
    assert.equal(model.lifecycle.availability, 'UNAVAILABLE');
    assert.equal(model.lifecycle.packet_count, null);
    assert.equal(model.lifecycle.version_count, null);
    assert.equal(model.unknownPolicy.unknown_as_zero_allowed, false);
    assert.equal(model.unknownPolicy.unknown_as_pass_allowed, false);
    assert.equal(model.conflicts.availability, 'AVAILABLE_RECORDED_SYNTHETIC_EMPTY');
    assert.equal(model.conflicts.known_recorded_count, 0);
    assert.equal(model.conflicts.live_count, null);
    assert.equal(model.conflicts.live_state, 'UNKNOWN');
    assert.equal(
      model.sources.every((source) => source.live_freshness === 'UNKNOWN'),
      true,
    );
    assert.equal(
      model.sources.every((source) => source.live_checked_at === null),
      true,
    );
  });
});
