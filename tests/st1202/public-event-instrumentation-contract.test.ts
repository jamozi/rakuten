import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_EVENT_INSTRUMENTATION_CLASSIFICATION,
  PUBLIC_EVENT_INSTRUMENTATION_ERROR_CODES,
  PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS,
  PUBLIC_EVENT_INSTRUMENTATION_PROHIBITED_PARAMETERS,
  PUBLIC_EVENT_INSTRUMENTATION_SCREEN,
  createPublicEventInstrumentationCandidate,
} from '../../packages/web-ui/src/index.ts';

const HASH = 'a'.repeat(64);

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

describe('ST-1202 disabled instrumentation contract', () => {
  it('pins the unregistered PUB-003 boundary and AN-SLICE-002 metadata', () => {
    const value = candidate();
    assert.equal(value.classification, PUBLIC_EVENT_INSTRUMENTATION_CLASSIFICATION);
    assert.equal(PUBLIC_EVENT_INSTRUMENTATION_SCREEN.id, 'PUB-003');
    assert.equal(PUBLIC_EVENT_INSTRUMENTATION_SCREEN.route, '/articles/{slug}');
    assert.deepEqual(value.route, {
      template: '/articles/{slug}',
      registered: false,
      rendererConnected: false,
      interactive: false,
    });
    assert.deepEqual(value.slice, {
      id: 'AN-SLICE-002',
      name: 'Public event instrumentation',
      dependsOn: ['AN-SLICE-001'],
      deliverables: ['article view', 'CTA impression/click', 'comparison', 'RUM'],
      implementationStatus: 'NOT_STARTED',
      runtimeVerification: 'NOT_EXECUTED',
    });
  });

  it('projects exactly the six approved MVP instrumentation event IDs', () => {
    assert.deepEqual(PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS, [
      'EVT-001',
      'EVT-002',
      'EVT-003',
      'EVT-004',
      'EVT-006',
      'EVT-012',
    ]);
    assert.deepEqual(
      candidate().eventRequirements.map(({ id, eventName, source, mvp }) => ({
        id,
        eventName,
        source,
        mvp,
      })),
      [
        { id: 'EVT-001', eventName: 'article_view', source: 'public_web', mvp: true },
        {
          id: 'EVT-002',
          eventName: 'qualified_decision_engagement',
          source: 'public_web',
          mvp: true,
        },
        {
          id: 'EVT-003',
          eventName: 'affiliate_cta_impression',
          source: 'public_web',
          mvp: true,
        },
        { id: 'EVT-004', eventName: 'affiliate_click', source: 'public_web', mvp: true },
        {
          id: 'EVT-006',
          eventName: 'comparison_interaction',
          source: 'public_web',
          mvp: true,
        },
        { id: 'EVT-012', eventName: 'web_vital', source: 'public_web', mvp: true },
      ],
    );
  });

  it('pins the exact PII and sensitive-data prohibition vocabulary', () => {
    assert.deepEqual(PUBLIC_EVENT_INSTRUMENTATION_PROHIBITED_PARAMETERS, [
      'email',
      'phone',
      'raw_ip',
      'full_user_agent',
      'raw_search_query',
      'article_body',
      'source_packet_text',
      'affiliate_url_query_secret',
    ]);
    for (const event of candidate().eventRequirements) {
      assert.deepEqual(
        event.prohibitedParameters,
        PUBLIC_EVENT_INSTRUMENTATION_PROHIBITED_PARAMETERS,
      );
    }
  });

  it('keeps exported metadata frozen and error vocabulary closed', () => {
    assert.ok(Object.isFrozen(PUBLIC_EVENT_INSTRUMENTATION_SCREEN));
    assert.ok(Object.isFrozen(PUBLIC_EVENT_INSTRUMENTATION_SCREEN.roles));
    assert.ok(Object.isFrozen(PUBLIC_EVENT_INSTRUMENTATION_EVENT_IDS));
    assert.ok(Object.isFrozen(PUBLIC_EVENT_INSTRUMENTATION_PROHIBITED_PARAMETERS));
    assert.equal(PUBLIC_EVENT_INSTRUMENTATION_ERROR_CODES.length, 12);
    assert.equal(new Set(PUBLIC_EVENT_INSTRUMENTATION_ERROR_CODES).size, 12);
  });
});
