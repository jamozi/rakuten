import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLIC_SHELL_CONTENT,
  PUBLIC_SHELL_SCREEN_IDS,
  PUBLIC_SHELL_SCREENS,
  createPublicShellCandidate,
  validatePublicShellCandidate,
} from '../../packages/web-ui/src/public-shell.ts';

function assertDeepFrozen(value: unknown, visited = new Set<object>()): void {
  if (typeof value !== 'object' || value === null || visited.has(value)) {
    return;
  }
  visited.add(value);
  assert.ok(Object.isFrozen(value));
  for (const child of Object.values(value)) {
    assertDeepFrozen(child, visited);
  }
}

describe('disabled headless public-shell candidate', () => {
  it('creates deterministic detached deeply frozen JSON-safe candidates', () => {
    for (const screenId of PUBLIC_SHELL_SCREEN_IDS) {
      const first = createPublicShellCandidate({ screenId });
      const second = createPublicShellCandidate({ screenId });
      assert.deepEqual(first, second);
      assert.notEqual(first, second);
      assert.notEqual(
        first.screen,
        PUBLIC_SHELL_SCREENS.find(({ id }) => id === screenId),
      );
      assert.notEqual(first.contentSlots, PUBLIC_SHELL_CONTENT[screenId]);
      assert.deepEqual(JSON.parse(JSON.stringify(first)), first);
      assert.equal(first.classification, 'UNBRANDED_DISABLED_HEADLESS_PUBLIC_SHELL_CANDIDATE');
      assertDeepFrozen(first);
      assert.deepEqual(validatePublicShellCandidate(JSON.parse(JSON.stringify(first))), first);
    }
  });

  it('uses route-only metadata with exact screen title and fail-closed robots', () => {
    for (const screenId of PUBLIC_SHELL_SCREEN_IDS) {
      const candidate = createPublicShellCandidate({ screenId });
      assert.equal(candidate.metadata.title, candidate.screen.name);
      assert.equal(candidate.metadata.description, null);
      assert.equal(candidate.metadata.canonicalUrl, null);
      assert.deepEqual(candidate.metadata.robots, {
        index: false,
        follow: false,
        directive: 'noindex,nofollow',
      });
    }
  });

  it('models the fixed semantic shell, single H1 and current-page-only breadcrumb', () => {
    for (const screenId of PUBLIC_SHELL_SCREEN_IDS) {
      const candidate = createPublicShellCandidate({ screenId });
      assert.equal(candidate.shell.language, 'ja');
      assert.deepEqual(candidate.shell.landmarkOrder, ['header', 'navigation', 'main', 'footer']);
      assert.deepEqual(candidate.shell.skipLink, {
        id: 'public-shell-skip-link',
        label: 'Skip to main content',
        targetId: 'public-shell-main',
      });
      assert.equal(candidate.shell.main.headingLevel, 1);
      assert.equal(candidate.shell.main.h1Count, 1);
      assert.equal(candidate.shell.main.heading, candidate.screen.name);
      assert.deepEqual(candidate.shell.breadcrumb.items, [
        {
          id: `public-shell-current-${screenId.toLowerCase()}`,
          label: candidate.screen.name,
          currentPage: true,
          interactive: false,
        },
      ]);
      assert.equal(candidate.shell.header.brandState, 'PROVISIONAL_UNBRANDED_OD_002');
      assert.equal(candidate.shell.header.brandLabel, null);
      assert.equal(candidate.shell.footer.operatorState, 'BLOCKED_OWNER_COPY');
      assert.equal(candidate.shell.footer.operatorLabel, null);
    }
  });

  it('keeps navigation presentational, unregistered, noninteractive and out of focus order', () => {
    const candidate = createPublicShellCandidate({ screenId: 'PUB-004' });
    assert.deepEqual(
      candidate.shell.header.navigationItems.map(({ screenId, route }) => ({ screenId, route })),
      [
        { screenId: 'PUB-004', route: '/editorial-policy' },
        { screenId: 'PUB-005', route: '/affiliate-disclosure' },
        { screenId: 'PUB-006', route: '/privacy' },
        { screenId: 'PUB-007', route: '/about' },
      ],
    );
    for (const item of candidate.shell.header.navigationItems) {
      assert.equal(item.routeRegistered, false);
      assert.equal(item.interactive, false);
      assert.equal(item.focusable, false);
      assert.ok(!candidate.shell.focusOrder.includes(item.id as never));
    }
    assert.deepEqual(candidate.shell.focusOrder, ['public-shell-skip-link', 'public-shell-main']);
    assert.equal(new Set(candidate.shell.focusOrder).size, candidate.shell.focusOrder.length);
  });

  it('records 320px and reduced-motion properties only as unverified candidates', () => {
    const candidate = createPublicShellCandidate({ screenId: 'PUB-006' });
    assert.deepEqual(candidate.shell.minimumWidth, {
      cssPixels: 320,
      status: 'NOT_EXECUTED',
      reason: 'MINIMUM_WIDTH_BROWSER_CHECK_NOT_EXECUTED',
    });
    assert.deepEqual(candidate.shell.motion, {
      animation: 'NONE',
      reducedMotion: 'NO_ANIMATION_TO_REDUCE',
      status: 'NOT_EXECUTED',
    });
  });
});
