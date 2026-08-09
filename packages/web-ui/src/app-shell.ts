import { evaluateAdminRoute, type AdminRouteRequest, type RouteDecision } from './route-guard.ts';
import { createJsonValue } from './serializable.ts';

export const APP_SHELL_IDS = Object.freeze({
  skipLink: 'raos-admin-skip-link',
  header: 'raos-admin-header',
  navigation: 'raos-admin-navigation',
  main: 'raos-admin-main',
});

export const APP_SHELL_ERROR_CODES = [
  'APP_SHELL_INPUT_INVALID',
  'APP_SHELL_TITLE_INVALID',
  'APP_SHELL_HEADING_INVALID',
  'APP_SHELL_NAVIGATION_INVALID',
  'APP_SHELL_DUPLICATE_ID',
  'APP_SHELL_DUPLICATE_PATH',
] as const;

export type AppShellErrorCode = (typeof APP_SHELL_ERROR_CODES)[number];

export class AppShellError extends TypeError {
  readonly code: AppShellErrorCode;

  constructor(code: AppShellErrorCode) {
    super(code);
    this.name = 'AppShellError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface AppShellNavigationInput {
  readonly focusId: unknown;
  readonly label: unknown;
  readonly path: unknown;
}

export interface AppShellInput {
  readonly documentTitle: unknown;
  readonly heading: unknown;
  readonly authenticated: unknown;
  readonly siteScope: unknown;
  readonly roles: unknown;
  readonly navigationItems: unknown;
}

export interface AppShellNavigationItem {
  readonly focusId: string;
  readonly label: string;
  readonly path: string;
  readonly routeDecision: RouteDecision;
}

export interface AppShellModel {
  readonly componentId: 'UI-C001';
  readonly document: { readonly title: string };
  readonly skipLink: {
    readonly id: 'raos-admin-skip-link';
    readonly label: 'Skip to main content';
    readonly targetId: 'raos-admin-main';
  };
  readonly landmarks: readonly [
    {
      readonly id: 'raos-admin-header';
      readonly kind: 'header';
      readonly label: 'Admin header';
    },
    {
      readonly id: 'raos-admin-navigation';
      readonly kind: 'navigation';
      readonly label: 'Admin navigation';
    },
    {
      readonly id: 'raos-admin-main';
      readonly kind: 'main';
      readonly heading: string;
    },
  ];
  readonly navigationItems: readonly AppShellNavigationItem[];
  readonly focusOrder: readonly string[];
}

const STABLE_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const SAFE_PATH = /^\/[a-z0-9]*(?:[/-][a-z0-9]+)*$/;

function reject(code: AppShellErrorCode): never {
  throw new AppShellError(code);
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  return actual.length === keys.length && actual.every((key, index) => key === keys[index]);
}

function descriptiveText(value: unknown, code: AppShellErrorCode): string {
  if (
    typeof value !== 'string' ||
    value.length < 1 ||
    value.length > 160 ||
    value !== value.trim()
  ) {
    return reject(code);
  }
  return value;
}

function navigationItem(value: unknown): AppShellNavigationInput {
  if (!isPlainRecord(value) || !hasExactKeys(value, ['focusId', 'label', 'path'].sort())) {
    return reject('APP_SHELL_NAVIGATION_INVALID');
  }
  return value as unknown as AppShellNavigationInput;
}

export function createAppShellModel(input: AppShellInput): AppShellModel {
  if (
    !isPlainRecord(input) ||
    !hasExactKeys(
      input,
      ['authenticated', 'documentTitle', 'heading', 'navigationItems', 'roles', 'siteScope'].sort(),
    ) ||
    !Array.isArray(input.navigationItems)
  ) {
    return reject('APP_SHELL_INPUT_INVALID');
  }

  const documentTitle = descriptiveText(input.documentTitle, 'APP_SHELL_TITLE_INVALID');
  const heading = descriptiveText(input.heading, 'APP_SHELL_HEADING_INVALID');
  const seenIds = new Set<string>(Object.values(APP_SHELL_IDS));
  const seenPaths = new Set<string>();
  const navigationItems: AppShellNavigationItem[] = [];

  for (const rawItem of input.navigationItems) {
    const item = navigationItem(rawItem);
    const focusId = item.focusId;
    const path = item.path;
    if (typeof focusId !== 'string' || !STABLE_ID.test(focusId)) {
      return reject('APP_SHELL_NAVIGATION_INVALID');
    }
    if (seenIds.has(focusId)) {
      return reject('APP_SHELL_DUPLICATE_ID');
    }
    if (typeof path !== 'string' || !SAFE_PATH.test(path)) {
      return reject('APP_SHELL_NAVIGATION_INVALID');
    }
    if (seenPaths.has(path)) {
      return reject('APP_SHELL_DUPLICATE_PATH');
    }
    seenIds.add(focusId);
    seenPaths.add(path);

    const request: AdminRouteRequest = {
      path,
      authenticated: input.authenticated,
      siteScope: input.siteScope,
      roles: input.roles,
    };
    navigationItems.push({
      focusId,
      label: descriptiveText(item.label, 'APP_SHELL_NAVIGATION_INVALID'),
      path,
      routeDecision: evaluateAdminRoute(request),
    });
  }

  const eligibleFocusIds = navigationItems
    .filter((item) => item.routeDecision.navigationEligible)
    .map((item) => item.focusId);
  return createJsonValue({
    componentId: 'UI-C001',
    document: { title: documentTitle },
    skipLink: {
      id: APP_SHELL_IDS.skipLink,
      label: 'Skip to main content',
      targetId: APP_SHELL_IDS.main,
    },
    landmarks: [
      { id: APP_SHELL_IDS.header, kind: 'header', label: 'Admin header' },
      {
        id: APP_SHELL_IDS.navigation,
        kind: 'navigation',
        label: 'Admin navigation',
      },
      { id: APP_SHELL_IDS.main, kind: 'main', heading },
    ],
    navigationItems,
    focusOrder: [APP_SHELL_IDS.skipLink, ...eligibleFocusIds, APP_SHELL_IDS.main],
  }) as unknown as AppShellModel;
}
