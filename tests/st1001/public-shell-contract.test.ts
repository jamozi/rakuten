import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_SHELL_COMPONENT_IDS,
  PUBLIC_SHELL_COMPONENTS,
  PUBLIC_SHELL_CONTENT,
  PUBLIC_SHELL_SCREEN_IDS,
  PUBLIC_SHELL_SCREENS,
} from '../../packages/web-ui/src/index.ts';

describe('ST-1001 canonical public-shell contract', () => {
  it('preserves the exact four policy screen records and no other public route', () => {
    assert.deepEqual(PUBLIC_SHELL_SCREEN_IDS, ['PUB-004', 'PUB-005', 'PUB-006', 'PUB-007']);
    assert.deepEqual(
      PUBLIC_SHELL_SCREENS.map(({ id, name, route, purpose }) => ({ id, name, route, purpose })),
      [
        {
          id: 'PUB-004',
          name: '編集方針',
          route: '/editorial-policy',
          purpose: '比較・推薦・根拠・AI利用方針を説明',
        },
        {
          id: 'PUB-005',
          name: '広告・Affiliate開示',
          route: '/affiliate-disclosure',
          purpose: '広告関係と送客先を説明',
        },
        {
          id: 'PUB-006',
          name: 'Privacy Policy',
          route: '/privacy',
          purpose: '取得データ、目的、保持、問い合わせを説明',
        },
        {
          id: 'PUB-007',
          name: '運営者・問い合わせ',
          route: '/about',
          purpose: '運営主体と連絡経路を表示',
        },
      ],
    );
    assert.equal(new Set(PUBLIC_SHELL_SCREEN_IDS).size, 4);
    assert.equal(new Set(PUBLIC_SHELL_SCREENS.map(({ route }) => route)).size, 4);
    for (const screen of PUBLIC_SHELL_SCREENS) {
      assert.equal(screen.area, 'public');
      assert.deepEqual(screen.roles, []);
      assert.equal(screen.mvp, true);
      assert.equal(screen.criticalAction, false);
      assert.deepEqual(screen.apiDependencies, []);
      assert.equal(screen.designStatus, 'APPROVED_FOR_IMPLEMENTATION');
      assert.equal(screen.implementationStatus, 'NOT_STARTED');
      assert.equal(screen.runtimeVerification, 'NOT_EXECUTED');
    }
  });

  it('preserves exactly UI-C002, UI-C003 and UI-C004 as metadata-only candidates', () => {
    assert.deepEqual(PUBLIC_SHELL_COMPONENT_IDS, ['UI-C002', 'UI-C003', 'UI-C004']);
    assert.deepEqual(
      PUBLIC_SHELL_COMPONENTS.map(({ id, name, area, purpose }) => ({
        id,
        name,
        area,
        purpose,
      })),
      [
        {
          id: 'UI-C002',
          name: 'PublicHeader',
          area: 'public',
          purpose: 'Brand、Breadcrumb入口、Primary navigation',
        },
        {
          id: 'UI-C003',
          name: 'PublicFooter',
          area: 'public',
          purpose: '運営者、Policy、Disclosure',
        },
        {
          id: 'UI-C004',
          name: 'Breadcrumbs',
          area: 'shared',
          purpose: '階層と現在位置',
        },
      ],
    );
    for (const component of PUBLIC_SHELL_COMPONENTS) {
      assert.equal(component.keyboardRequired, true);
      assert.equal(component.screenReaderRequired, true);
      assert.equal(component.designStatus, 'APPROVED_FOR_IMPLEMENTATION');
      assert.equal(component.implementationStatus, 'NOT_STARTED');
      assert.equal(component.runtimeVerification, 'NOT_EXECUTED');
    }
  });

  it('represents only the exact structured policy topics with closed states', () => {
    assert.deepEqual(
      Object.fromEntries(
        PUBLIC_SHELL_SCREEN_IDS.map((screenId) => [
          screenId,
          PUBLIC_SHELL_CONTENT[screenId].map(({ topicCode }) => topicCode),
        ]),
      ),
      {
        'PUB-004': [
          'EDITORIAL_SELECTION',
          'EDITORIAL_EVIDENCE',
          'EDITORIAL_AI_USE',
          'EDITORIAL_HUMAN_CHECK',
          'EDITORIAL_SOURCE_TREATMENT',
        ],
        'PUB-005': ['AFFILIATE_AD_RELATIONSHIP', 'AFFILIATE_DESTINATION', 'AFFILIATE_LEGAL_REVIEW'],
        'PUB-006': [
          'PRIVACY_NONESSENTIAL_TRACKING',
          'PRIVACY_COOKIES_AND_CONSENT',
          'PRIVACY_EXTERNAL_TRANSFER',
          'PRIVACY_RETENTION',
          'PRIVACY_CONTACT',
        ],
        'PUB-007': ['ABOUT_OPERATOR', 'ABOUT_CONTACT'],
      },
    );
    assert.deepEqual(
      Object.fromEntries(
        PUBLIC_SHELL_SCREEN_IDS.map((screenId) => [
          screenId,
          PUBLIC_SHELL_CONTENT[screenId].map(
            ({ id, state, principleCode, renderedCopy, sourceRef }) => [
              id,
              state,
              principleCode,
              renderedCopy,
              sourceRef,
            ],
          ),
        ]),
      ),
      {
        'PUB-004': [
          [
            'editorial-selection',
            'CANONICAL_PRINCIPLE',
            'FINANCE_NOT_EDITORIAL_INPUT',
            null,
            'docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md :: section 2 item 5',
          ],
          [
            'editorial-evidence',
            'CANONICAL_PRINCIPLE',
            'UNKNOWN_IS_VISIBLE',
            null,
            'docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md :: section 2 item 2',
          ],
          [
            'editorial-ai-use',
            'CANONICAL_PRINCIPLE',
            'AI_IS_A_PROPOSAL',
            null,
            'docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md :: section 2 item 4',
          ],
          [
            'editorial-human-check',
            'CANONICAL_PRINCIPLE',
            'HUMAN_APPROVAL_NOT_AUTOMATION',
            null,
            'docs/canonical/08_codex/RAOS_14_codex_implementation_handbook_v1.0.md :: section 2',
          ],
          [
            'editorial-source-treatment',
            'CANONICAL_PRINCIPLE',
            'UNTRUSTED_SOURCE_TREATMENT',
            null,
            'docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml :: SEC-AI-001',
          ],
        ],
        'PUB-005': [
          [
            'affiliate-ad-relationship',
            'CANONICAL_PRINCIPLE',
            'DISCLOSE_AD_RELATIONSHIP',
            null,
            'docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml :: PUB-005',
          ],
          [
            'affiliate-destination',
            'CANONICAL_PRINCIPLE',
            'DISCLOSE_DESTINATION',
            null,
            'docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml :: PUB-005',
          ],
          [
            'affiliate-legal-review',
            'BLOCKED_OWNER_COPY',
            'LEGAL_OWNER_COPY_REQUIRED',
            null,
            'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-008 decision_needed',
          ],
        ],
        'PUB-006': [
          [
            'privacy-nonessential-tracking',
            'CANONICAL_PRINCIPLE',
            'NONESSENTIAL_TRACKING_DISABLED',
            null,
            'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-012 default_behavior',
          ],
          [
            'privacy-cookies',
            'BLOCKED_OWNER_COPY',
            'PRIVACY_OWNER_COPY_REQUIRED',
            null,
            'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-012 decision_needed',
          ],
          [
            'privacy-external-transfer',
            'BLOCKED_OWNER_COPY',
            'PRIVACY_OWNER_COPY_REQUIRED',
            null,
            'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-013 decision_needed',
          ],
          [
            'privacy-retention',
            'BLOCKED_OWNER_COPY',
            'PRIVACY_OWNER_COPY_REQUIRED',
            null,
            'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-014 decision_needed',
          ],
          [
            'privacy-contact',
            'BLOCKED_OWNER_COPY',
            'OPERATOR_OWNER_COPY_REQUIRED',
            null,
            'docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml :: PUB-006',
          ],
        ],
        'PUB-007': [
          [
            'about-operator',
            'BLOCKED_OWNER_COPY',
            'OPERATOR_OWNER_COPY_REQUIRED',
            null,
            'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-002 decision_needed',
          ],
          [
            'about-contact',
            'BLOCKED_OWNER_COPY',
            'OPERATOR_OWNER_COPY_REQUIRED',
            null,
            'docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml :: PUB-007',
          ],
        ],
      },
    );
    const slots = PUBLIC_SHELL_SCREEN_IDS.flatMap((screenId) => PUBLIC_SHELL_CONTENT[screenId]);
    assert.equal(new Set(slots.map(({ id }) => id)).size, slots.length);
    for (const slot of slots) {
      assert.deepEqual(Object.keys(slot).sort(), [
        'id',
        'principleCode',
        'renderedCopy',
        'sourceRef',
        'state',
        'topicCode',
      ]);
      assert.match(slot.id, /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/);
      assert.match(slot.topicCode, /^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$/);
      assert.match(slot.principleCode, /^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$/);
      assert.ok(['CANONICAL_PRINCIPLE', 'BLOCKED_OWNER_COPY'].includes(slot.state));
      assert.equal(slot.renderedCopy, null);
      assert.match(
        slot.sourceRef,
        /^docs\/canonical\/.+ :: (?:section [0-9]+(?: item [0-9]+)?|[A-Z0-9-]+(?: [a-z_]+)?)$/,
      );
      assert.doesNotMatch(slot.sourceRef, /changes\/st-1701|https?:\/\//i);
    }
    assert.doesNotMatch(JSON.stringify(PUBLIC_SHELL_CONTENT), /[\u3040-\u30ff\u3400-\u9fff]/u);
  });

  it('deep-freezes every exported authority record', () => {
    assert.ok(Object.isFrozen(PUBLIC_SHELL_SCREEN_IDS));
    assert.ok(Object.isFrozen(PUBLIC_SHELL_SCREENS));
    assert.ok(Object.isFrozen(PUBLIC_SHELL_SCREENS[0]));
    assert.ok(Object.isFrozen(PUBLIC_SHELL_SCREENS[0]?.roles));
    assert.ok(Object.isFrozen(PUBLIC_SHELL_COMPONENT_IDS));
    assert.ok(Object.isFrozen(PUBLIC_SHELL_COMPONENTS));
    assert.ok(Object.isFrozen(PUBLIC_SHELL_CONTENT));
    assert.ok(Object.isFrozen(PUBLIC_SHELL_CONTENT['PUB-004']));
    assert.ok(Object.isFrozen(PUBLIC_SHELL_CONTENT['PUB-004'][0]));
  });
});
