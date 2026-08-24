import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  ADMIN_ROUTE_REGISTRY,
  PUBLICATION_REVIEW_SCREEN_IDS,
  createPublicationReviewWorkspaceV2,
  evaluateAdminRouteContext,
} from '../../packages/web-ui/src/index.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

describe('ST-0906 V2 route, authority and command boundaries', () => {
  it('keeps every publication-review catalog route non-routable and unregistered', () => {
    const registered = new Set<string>(ADMIN_ROUTE_REGISTRY.map(({ path }) => path));
    for (const screenId of PUBLICATION_REVIEW_SCREEN_IDS) {
      const model = createPublicationReviewWorkspaceV2({ screenId });
      assert.equal(registered.has(model.route.catalogPath), false);
      assert.equal(
        evaluateAdminRouteContext({
          path: model.route.catalogPath,
          authenticated: true,
          siteScope: 'synthetic-site',
          roles: model.screen.roles,
        }).code,
        'UNREGISTERED_ROUTE',
      );
      assert.deepEqual(model.route, {
        registered: false,
        routable: false,
        renderEnabled: false,
        navigationEligible: false,
        status: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED_OD_010',
        catalogPath: model.screen.route,
        roleMetadataOnly: true,
      });
    }
  });

  it('denies UI effects and preserves every external authority gate', () => {
    const model = createPublicationReviewWorkspaceV2({ screenId: 'PUBA-003' });
    assert.deepEqual(model.authority, {
      authenticationEstablished: false,
      authorizationGranted: false,
      stepUpEstablished: false,
      backendReauthorizationRequired: true,
      dataFetchEnabled: false,
      mutationEnabled: false,
      networkEnabled: false,
      persistenceEnabled: false,
      databaseWriteEnabled: false,
      cmsWriteEnabled: false,
      eventEmissionEnabled: false,
      outboxWriteEnabled: false,
      publicStateChangeEnabled: false,
      publicationAuthorized: false,
      rollbackAuthorized: false,
      releaseAuthorized: false,
      productionAuthorized: false,
    });
    assert.deepEqual(
      model.commands.map(({ actionCode, uiAvailability, effectPerformedByUi }) => [
        actionCode,
        uiAvailability,
        effectPerformedByUi,
      ]),
      [
        ['PUBLISH', 'DISABLED_AUTH_ROUTE_STEP_UP_UNAVAILABLE', false],
        ['UNPUBLISH', 'DENIED_DEFAULT_NO_CANONICAL_ROLE_ACTION', false],
        ['ROLLBACK', 'DISABLED_AUTH_ROUTE_STEP_UP_UNAVAILABLE', false],
      ],
    );
    assert.ok(model.commands.every(({ persisted, eventEmitted }) => !persisted && !eventEmitted));
  });

  it('binds any future local call to the exact ST-0905 adapter and complete human gates', () => {
    const model = createPublicationReviewWorkspaceV2({ screenId: 'PUBA-004' });
    assert.deepEqual(model.commandBoundary, {
      uiDispatch: 'DISABLED_AUTH_ROUTE_STEP_UP_UNAVAILABLE',
      onlyFutureAdapter: 'python.raos.adapters.publishing.recorded_publication_commands_v2',
      onlyFutureProfile: 'ST0905_PUBLICATION_COMMANDS_RECORDED_LOCAL_V2',
      allowedEnvironments: ['ENV-DEV', 'CI'],
      activeHumanRequired: true,
      allowedRoles: ['MANAGING_EDITOR', 'OPERATOR'],
      mfaRequired: true,
      stepUpRequired: true,
      siteScopeRequired: true,
      serverReauthorizationRequired: true,
      finalApprovalRequired: true,
      separationOfDutiesPublishRequired: true,
      exactSnapshotRequired: true,
      exactSourceBindingRequired: true,
      killSwitchSafeStateRequired: true,
      reasonRequired: true,
      idempotencyRequired: true,
      auditRequired: true,
      publishEnabled: false,
      rollbackEnabled: false,
      unpublishEnabled: false,
    });
  });

  it('imports no browser, framework, transport, database, CMS or command adapter', () => {
    const source = readFileSync(
      resolve(repositoryRoot, 'packages/web-ui/src/publication-review-workspace-v2.ts'),
      'utf8',
    );
    assert.doesNotMatch(
      source,
      /(?:from\s*|import\s*\(|require\s*\()['"](?:react|next)(?:\/|['"])/u,
    );
    assert.doesNotMatch(source, /(?:\b|\.)(?:fetch|sendBeacon)\s*\(/u);
    assert.doesNotMatch(
      source,
      /\b(?:window|document|navigator|localStorage|sessionStorage|indexedDB|caches|WebSocket|XMLHttpRequest|EventSource)\s*(?:\.[A-Za-z_$]|\[['"])/u,
    );
    assert.doesNotMatch(source, /\bnew\s+(?:WebSocket|XMLHttpRequest|EventSource)\s*\(/u);
    assert.doesNotMatch(source, /['"]node:(?:http|https|net|tls|dns|dgram)['"]/u);
    assert.doesNotMatch(source, /from ['"].*(?:adapter|repository|database|api-client)/u);
    assert.doesNotMatch(source, /publication_commands_v2/u);
  });

  it('keeps formal, browser, live and operational evidence explicitly unexecuted', () => {
    const model = createPublicationReviewWorkspaceV2({ screenId: 'REV-001' });
    assert.equal(model.verification.localModelAndRenderer, 'EXECUTABLE');
    for (const [key, status] of Object.entries(model.verification)) {
      if (key !== 'localModelAndRenderer') {
        assert.equal(status, 'NOT_EXECUTED', key);
      }
    }
    assert.equal(model.accessibility.browserVerified, false);
    assert.equal(model.accessibility.screenReaderVerified, false);
    assert.equal(model.accessibility.formalConformanceClaimed, false);
    assert.equal(model.formalAcceptanceAchieved, false);
    assert.equal(model.productionEligible, false);
  });
});
