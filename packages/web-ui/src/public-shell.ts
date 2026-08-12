import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const PUBLIC_SHELL_SCREEN_IDS = Object.freeze([
  'PUB-004',
  'PUB-005',
  'PUB-006',
  'PUB-007',
] as const);

export type PublicShellScreenId = (typeof PUBLIC_SHELL_SCREEN_IDS)[number];

export const PUBLIC_SHELL_COMPONENT_IDS = Object.freeze(['UI-C002', 'UI-C003', 'UI-C004'] as const);

export type PublicShellComponentId = (typeof PUBLIC_SHELL_COMPONENT_IDS)[number];

export const PUBLIC_SHELL_IDS = Object.freeze({
  skipLink: 'public-shell-skip-link',
  header: 'public-shell-header',
  navigation: 'public-shell-navigation',
  breadcrumb: 'public-shell-breadcrumb',
  main: 'public-shell-main',
  heading: 'public-shell-heading',
  footer: 'public-shell-footer',
});

export const PUBLIC_SHELL_ERROR_CODES = Object.freeze([
  'PUBLIC_SHELL_INPUT_INVALID',
  'PUBLIC_SHELL_SCREEN_UNKNOWN',
  'PUBLIC_SHELL_CANDIDATE_INVALID',
  'PUBLIC_SHELL_DUPLICATE_ID',
  'PUBLIC_SHELL_DUPLICATE_ROUTE',
  'PUBLIC_SHELL_METADATA_INVALID',
  'PUBLIC_SHELL_ACCESSIBILITY_INVALID',
  'PUBLIC_SHELL_CONTENT_INVALID',
  'PUBLIC_SHELL_AUTHORITY_INVALID',
  'PUBLIC_SHELL_PROHIBITED_SURFACE',
] as const);

export type PublicShellErrorCode = (typeof PUBLIC_SHELL_ERROR_CODES)[number];

export class PublicShellError extends TypeError {
  readonly code: PublicShellErrorCode;

  constructor(code: PublicShellErrorCode) {
    super(code);
    this.name = 'PublicShellError';
    this.code = code;
    Object.freeze(this);
  }
}

export interface PublicShellScreenMetadata {
  readonly id: PublicShellScreenId;
  readonly name: '編集方針' | '広告・Affiliate開示' | 'Privacy Policy' | '運営者・問い合わせ';
  readonly route: '/editorial-policy' | '/affiliate-disclosure' | '/privacy' | '/about';
  readonly area: 'public';
  readonly roles: readonly [];
  readonly purpose: string;
  readonly mvp: true;
  readonly criticalAction: false;
  readonly apiDependencies: readonly [];
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly runtimeVerification: 'NOT_EXECUTED';
}

const screenSource = [
  {
    id: 'PUB-004',
    name: '編集方針',
    route: '/editorial-policy',
    area: 'public',
    roles: [],
    purpose: '比較・推薦・根拠・AI利用方針を説明',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PUB-005',
    name: '広告・Affiliate開示',
    route: '/affiliate-disclosure',
    area: 'public',
    roles: [],
    purpose: '広告関係と送客先を説明',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PUB-006',
    name: 'Privacy Policy',
    route: '/privacy',
    area: 'public',
    roles: [],
    purpose: '取得データ、目的、保持、問い合わせを説明',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'PUB-007',
    name: '運営者・問い合わせ',
    route: '/about',
    area: 'public',
    roles: [],
    purpose: '運営主体と連絡経路を表示',
    mvp: true,
    criticalAction: false,
    apiDependencies: [],
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
] as const;

export const PUBLIC_SHELL_SCREENS = createJsonValue(
  screenSource,
) as unknown as readonly PublicShellScreenMetadata[];

export interface PublicShellComponentMetadata {
  readonly id: PublicShellComponentId;
  readonly name: 'PublicHeader' | 'PublicFooter' | 'Breadcrumbs';
  readonly area: 'public' | 'shared';
  readonly purpose: string;
  readonly keyboardRequired: true;
  readonly screenReaderRequired: true;
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly implementationStatus: 'NOT_STARTED';
  readonly runtimeVerification: 'NOT_EXECUTED';
}

const componentSource = [
  {
    id: 'UI-C002',
    name: 'PublicHeader',
    area: 'public',
    purpose: 'Brand、Breadcrumb入口、Primary navigation',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'UI-C003',
    name: 'PublicFooter',
    area: 'public',
    purpose: '運営者、Policy、Disclosure',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
  {
    id: 'UI-C004',
    name: 'Breadcrumbs',
    area: 'shared',
    purpose: '階層と現在位置',
    keyboardRequired: true,
    screenReaderRequired: true,
    designStatus: 'APPROVED_FOR_IMPLEMENTATION',
    implementationStatus: 'NOT_STARTED',
    runtimeVerification: 'NOT_EXECUTED',
  },
] as const;

export const PUBLIC_SHELL_COMPONENTS = createJsonValue(
  componentSource,
) as unknown as readonly PublicShellComponentMetadata[];

export type PublicShellContentState = 'CANONICAL_PRINCIPLE' | 'BLOCKED_OWNER_COPY';

export interface PublicShellContentSlot {
  readonly id: string;
  readonly topicCode: string;
  readonly state: PublicShellContentState;
  readonly principleCode: string;
  readonly renderedCopy: null;
  readonly sourceRef: string;
}

const contentSource: Readonly<Record<PublicShellScreenId, readonly PublicShellContentSlot[]>> = {
  'PUB-004': [
    {
      id: 'editorial-selection',
      topicCode: 'EDITORIAL_SELECTION',
      state: 'CANONICAL_PRINCIPLE',
      principleCode: 'FINANCE_NOT_EDITORIAL_INPUT',
      renderedCopy: null,
      sourceRef: 'docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md :: section 2 item 5',
    },
    {
      id: 'editorial-evidence',
      topicCode: 'EDITORIAL_EVIDENCE',
      state: 'CANONICAL_PRINCIPLE',
      principleCode: 'UNKNOWN_IS_VISIBLE',
      renderedCopy: null,
      sourceRef: 'docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md :: section 2 item 2',
    },
    {
      id: 'editorial-ai-use',
      topicCode: 'EDITORIAL_AI_USE',
      state: 'CANONICAL_PRINCIPLE',
      principleCode: 'AI_IS_A_PROPOSAL',
      renderedCopy: null,
      sourceRef: 'docs/canonical/02_ui/RAOS_08_ui_ux_design_v1.0.md :: section 2 item 4',
    },
    {
      id: 'editorial-human-check',
      topicCode: 'EDITORIAL_HUMAN_CHECK',
      state: 'CANONICAL_PRINCIPLE',
      principleCode: 'HUMAN_APPROVAL_NOT_AUTOMATION',
      renderedCopy: null,
      sourceRef:
        'docs/canonical/08_codex/RAOS_14_codex_implementation_handbook_v1.0.md :: section 2',
    },
    {
      id: 'editorial-source-treatment',
      topicCode: 'EDITORIAL_SOURCE_TREATMENT',
      state: 'CANONICAL_PRINCIPLE',
      principleCode: 'UNTRUSTED_SOURCE_TREATMENT',
      renderedCopy: null,
      sourceRef:
        'docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml :: SEC-AI-001',
    },
  ],
  'PUB-005': [
    {
      id: 'affiliate-ad-relationship',
      topicCode: 'AFFILIATE_AD_RELATIONSHIP',
      state: 'CANONICAL_PRINCIPLE',
      principleCode: 'DISCLOSE_AD_RELATIONSHIP',
      renderedCopy: null,
      sourceRef: 'docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml :: PUB-005',
    },
    {
      id: 'affiliate-destination',
      topicCode: 'AFFILIATE_DESTINATION',
      state: 'CANONICAL_PRINCIPLE',
      principleCode: 'DISCLOSE_DESTINATION',
      renderedCopy: null,
      sourceRef: 'docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml :: PUB-005',
    },
    {
      id: 'affiliate-legal-review',
      topicCode: 'AFFILIATE_LEGAL_REVIEW',
      state: 'BLOCKED_OWNER_COPY',
      principleCode: 'LEGAL_OWNER_COPY_REQUIRED',
      renderedCopy: null,
      sourceRef:
        'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-008 decision_needed',
    },
  ],
  'PUB-006': [
    {
      id: 'privacy-nonessential-tracking',
      topicCode: 'PRIVACY_NONESSENTIAL_TRACKING',
      state: 'CANONICAL_PRINCIPLE',
      principleCode: 'NONESSENTIAL_TRACKING_DISABLED',
      renderedCopy: null,
      sourceRef:
        'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-012 default_behavior',
    },
    {
      id: 'privacy-cookies',
      topicCode: 'PRIVACY_COOKIES_AND_CONSENT',
      state: 'BLOCKED_OWNER_COPY',
      principleCode: 'PRIVACY_OWNER_COPY_REQUIRED',
      renderedCopy: null,
      sourceRef:
        'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-012 decision_needed',
    },
    {
      id: 'privacy-external-transfer',
      topicCode: 'PRIVACY_EXTERNAL_TRANSFER',
      state: 'BLOCKED_OWNER_COPY',
      principleCode: 'PRIVACY_OWNER_COPY_REQUIRED',
      renderedCopy: null,
      sourceRef:
        'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-013 decision_needed',
    },
    {
      id: 'privacy-retention',
      topicCode: 'PRIVACY_RETENTION',
      state: 'BLOCKED_OWNER_COPY',
      principleCode: 'PRIVACY_OWNER_COPY_REQUIRED',
      renderedCopy: null,
      sourceRef:
        'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-014 decision_needed',
    },
    {
      id: 'privacy-contact',
      topicCode: 'PRIVACY_CONTACT',
      state: 'BLOCKED_OWNER_COPY',
      principleCode: 'OPERATOR_OWNER_COPY_REQUIRED',
      renderedCopy: null,
      sourceRef: 'docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml :: PUB-006',
    },
  ],
  'PUB-007': [
    {
      id: 'about-operator',
      topicCode: 'ABOUT_OPERATOR',
      state: 'BLOCKED_OWNER_COPY',
      principleCode: 'OPERATOR_OWNER_COPY_REQUIRED',
      renderedCopy: null,
      sourceRef:
        'docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml :: OD-002 decision_needed',
    },
    {
      id: 'about-contact',
      topicCode: 'ABOUT_CONTACT',
      state: 'BLOCKED_OWNER_COPY',
      principleCode: 'OPERATOR_OWNER_COPY_REQUIRED',
      renderedCopy: null,
      sourceRef: 'docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml :: PUB-007',
    },
  ],
};

export const PUBLIC_SHELL_CONTENT = createJsonValue(contentSource) as unknown as Readonly<
  Record<PublicShellScreenId, readonly PublicShellContentSlot[]>
>;

export interface PublicShellInput {
  readonly screenId: PublicShellScreenId;
}

export interface PublicShellBoundaryResult {
  readonly value: false;
  readonly status: 'NOT_EXECUTED';
  readonly reason: string;
}

export interface PublicShellCandidate {
  readonly classification: 'UNBRANDED_DISABLED_HEADLESS_PUBLIC_SHELL_CANDIDATE';
  readonly screen: PublicShellScreenMetadata;
  readonly components: readonly PublicShellComponentMetadata[];
  readonly contentSlots: readonly PublicShellContentSlot[];
  readonly metadata: {
    readonly title: PublicShellScreenMetadata['name'];
    readonly description: null;
    readonly canonicalUrl: null;
    readonly robots: {
      readonly index: false;
      readonly follow: false;
      readonly directive: 'noindex,nofollow';
    };
  };
  readonly shell: {
    readonly language: 'ja';
    readonly skipLink: {
      readonly id: 'public-shell-skip-link';
      readonly label: 'Skip to main content';
      readonly targetId: 'public-shell-main';
    };
    readonly header: {
      readonly componentId: 'UI-C002';
      readonly id: 'public-shell-header';
      readonly brandState: 'PROVISIONAL_UNBRANDED_OD_002';
      readonly brandLabel: null;
      readonly navigationId: 'public-shell-navigation';
      readonly navigationLabel: 'Primary navigation';
      readonly navigationItems: readonly PublicShellNavigationItem[];
    };
    readonly breadcrumb: {
      readonly componentId: 'UI-C004';
      readonly id: 'public-shell-breadcrumb';
      readonly label: 'Breadcrumbs';
      readonly items: readonly [PublicShellBreadcrumbItem];
    };
    readonly main: {
      readonly id: 'public-shell-main';
      readonly headingId: 'public-shell-heading';
      readonly headingLevel: 1;
      readonly heading: PublicShellScreenMetadata['name'];
      readonly h1Count: 1;
    };
    readonly footer: {
      readonly componentId: 'UI-C003';
      readonly id: 'public-shell-footer';
      readonly operatorState: 'BLOCKED_OWNER_COPY';
      readonly operatorLabel: null;
    };
    readonly landmarkOrder: readonly ['header', 'navigation', 'main', 'footer'];
    readonly focusOrder: readonly ['public-shell-skip-link', 'public-shell-main'];
    readonly minimumWidth: {
      readonly cssPixels: 320;
      readonly status: 'NOT_EXECUTED';
      readonly reason: 'MINIMUM_WIDTH_BROWSER_CHECK_NOT_EXECUTED';
    };
    readonly motion: {
      readonly animation: 'NONE';
      readonly reducedMotion: 'NO_ANIMATION_TO_REDUCE';
      readonly status: 'NOT_EXECUTED';
    };
  };
  readonly boundaries: PublicShellBoundaries;
  readonly actions: readonly [];
}

export interface PublicShellNavigationItem {
  readonly id: string;
  readonly screenId: PublicShellScreenId;
  readonly label: PublicShellScreenMetadata['name'];
  readonly route: PublicShellScreenMetadata['route'];
  readonly routeRegistered: false;
  readonly interactive: false;
  readonly focusable: false;
}

export interface PublicShellBreadcrumbItem {
  readonly id: string;
  readonly label: PublicShellScreenMetadata['name'];
  readonly currentPage: true;
  readonly interactive: false;
}

export interface PublicShellBoundaries {
  readonly routeRegistered: PublicShellBoundaryResult;
  readonly ssr: PublicShellBoundaryResult;
  readonly browser: PublicShellBoundaryResult;
  readonly accessibility: PublicShellBoundaryResult;
  readonly formalTst022: PublicShellBoundaryResult;
  readonly formalTst023: PublicShellBoundaryResult;
  readonly live: PublicShellBoundaryResult;
  readonly staging: PublicShellBoundaryResult;
  readonly release: PublicShellBoundaryResult;
  readonly production: PublicShellBoundaryResult;
  readonly externalPublication: PublicShellBoundaryResult;
  readonly publicationAuthorization: PublicShellBoundaryResult;
  readonly domainApproval: PublicShellBoundaryResult;
  readonly operatorApproval: PublicShellBoundaryResult;
  readonly consentApproval: PublicShellBoundaryResult;
  readonly legalApproval: PublicShellBoundaryResult;
  readonly tracking: PublicShellBoundaryResult;
  readonly firstPartyEvent: PublicShellBoundaryResult;
  readonly wcagConformanceClaim: PublicShellBoundaryResult;
  readonly localEligibility: PublicShellBoundaryResult;
}

const boundaryReasons = {
  routeRegistered: 'NO_RUNTIME_ROUTE_REGISTERED',
  ssr: 'SSR_EXECUTION_NOT_IMPLEMENTED',
  browser: 'BROWSER_EXECUTION_NOT_PERFORMED',
  accessibility: 'ACCESSIBILITY_EXECUTION_NOT_PERFORMED',
  formalTst022: 'FORMAL_TST_022_NOT_EXECUTED',
  formalTst023: 'FORMAL_TST_023_NOT_EXECUTED',
  live: 'LIVE_EXECUTION_NOT_AUTHORIZED',
  staging: 'STAGING_EXECUTION_NOT_AUTHORIZED',
  release: 'RELEASE_NOT_AUTHORIZED',
  production: 'PRODUCTION_NOT_AUTHORIZED',
  externalPublication: 'EXTERNAL_PUBLICATION_NOT_AUTHORIZED',
  publicationAuthorization: 'PUBLICATION_APPROVAL_NOT_GRANTED',
  domainApproval: 'OD_002_DOMAIN_UNRESOLVED',
  operatorApproval: 'OD_002_OPERATOR_UNRESOLVED',
  consentApproval: 'OD_012_CONSENT_UNRESOLVED',
  legalApproval: 'LEGAL_REVIEW_NOT_GRANTED',
  tracking: 'OD_012_NONESSENTIAL_TRACKING_DISABLED',
  firstPartyEvent: 'EVENT_INSTRUMENTATION_OUT_OF_SCOPE',
  wcagConformanceClaim: 'WCAG_CONFORMANCE_NOT_VERIFIED',
  localEligibility: 'ROUTE_SSR_BROWSER_AND_APPROVAL_GATES_UNSATISFIED',
} as const;

function reject(code: PublicShellErrorCode): never {
  throw new PublicShellError(code);
}

function isStrictPlainTree(value: unknown, ancestors = new WeakSet<object>()): boolean {
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'boolean' ||
    (typeof value === 'number' && Number.isFinite(value))
  ) {
    return true;
  }
  if (typeof value !== 'object') {
    return false;
  }
  if (ancestors.has(value)) {
    return false;
  }
  ancestors.add(value);
  try {
    const isArray = Array.isArray(value);
    if (Object.getPrototypeOf(value) !== (isArray ? Array.prototype : Object.prototype)) {
      return false;
    }
    const keys = Reflect.ownKeys(value);
    if (keys.some((key) => typeof key !== 'string')) {
      return false;
    }
    if (isArray && keys[keys.length - 1] !== 'length') {
      return false;
    }
    for (const key of keys) {
      if (key === 'length') {
        continue;
      }
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (
        descriptor === undefined ||
        !descriptor.enumerable ||
        !Object.hasOwn(descriptor, 'value') ||
        !isStrictPlainTree(descriptor.value, ancestors)
      ) {
        return false;
      }
    }
    return true;
  } catch {
    return false;
  } finally {
    ancestors.delete(value);
  }
}

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function plainInput(input: PublicShellInput): Readonly<Record<string, JsonValue>> {
  if (!isStrictPlainTree(input)) {
    reject('PUBLIC_SHELL_INPUT_INVALID');
  }
  let value: JsonValue;
  try {
    value = createJsonValue(input);
  } catch {
    reject('PUBLIC_SHELL_INPUT_INVALID');
  }
  if (!isJsonObject(value)) {
    reject('PUBLIC_SHELL_INPUT_INVALID');
  }
  const keys = Object.keys(value);
  if (keys.length !== 1 || keys[0] !== 'screenId') {
    reject('PUBLIC_SHELL_INPUT_INVALID');
  }
  return value;
}

function validatedScreenId(input: PublicShellInput): PublicShellScreenId {
  const value = plainInput(input);
  const screenId = value['screenId'];
  if (typeof screenId !== 'string') {
    return reject('PUBLIC_SHELL_INPUT_INVALID');
  }
  if (!(PUBLIC_SHELL_SCREEN_IDS as readonly string[]).includes(screenId)) {
    return reject('PUBLIC_SHELL_SCREEN_UNKNOWN');
  }
  return screenId as PublicShellScreenId;
}

function makeBoundaries(): PublicShellBoundaries {
  return Object.fromEntries(
    Object.entries(boundaryReasons).map(([key, reason]) => [
      key,
      { value: false, status: 'NOT_EXECUTED', reason },
    ]),
  ) as unknown as PublicShellBoundaries;
}

function buildCandidate(screenId: PublicShellScreenId): PublicShellCandidate {
  const screen = PUBLIC_SHELL_SCREENS.find((item) => item.id === screenId);
  const contentSlots = PUBLIC_SHELL_CONTENT[screenId];
  if (screen === undefined || contentSlots === undefined) {
    return reject('PUBLIC_SHELL_SCREEN_UNKNOWN');
  }
  const navigationItems = PUBLIC_SHELL_SCREENS.map((item) => ({
    id: `public-shell-nav-${item.id.toLowerCase()}`,
    screenId: item.id,
    label: item.name,
    route: item.route,
    routeRegistered: false,
    interactive: false,
    focusable: false,
  }));
  return createJsonValue({
    classification: 'UNBRANDED_DISABLED_HEADLESS_PUBLIC_SHELL_CANDIDATE',
    screen,
    components: PUBLIC_SHELL_COMPONENTS,
    contentSlots,
    metadata: {
      title: screen.name,
      description: null,
      canonicalUrl: null,
      robots: { index: false, follow: false, directive: 'noindex,nofollow' },
    },
    shell: {
      language: 'ja',
      skipLink: {
        id: PUBLIC_SHELL_IDS.skipLink,
        label: 'Skip to main content',
        targetId: PUBLIC_SHELL_IDS.main,
      },
      header: {
        componentId: 'UI-C002',
        id: PUBLIC_SHELL_IDS.header,
        brandState: 'PROVISIONAL_UNBRANDED_OD_002',
        brandLabel: null,
        navigationId: PUBLIC_SHELL_IDS.navigation,
        navigationLabel: 'Primary navigation',
        navigationItems,
      },
      breadcrumb: {
        componentId: 'UI-C004',
        id: PUBLIC_SHELL_IDS.breadcrumb,
        label: 'Breadcrumbs',
        items: [
          {
            id: `public-shell-current-${screen.id.toLowerCase()}`,
            label: screen.name,
            currentPage: true,
            interactive: false,
          },
        ],
      },
      main: {
        id: PUBLIC_SHELL_IDS.main,
        headingId: PUBLIC_SHELL_IDS.heading,
        headingLevel: 1,
        heading: screen.name,
        h1Count: 1,
      },
      footer: {
        componentId: 'UI-C003',
        id: PUBLIC_SHELL_IDS.footer,
        operatorState: 'BLOCKED_OWNER_COPY',
        operatorLabel: null,
      },
      landmarkOrder: ['header', 'navigation', 'main', 'footer'],
      focusOrder: [PUBLIC_SHELL_IDS.skipLink, PUBLIC_SHELL_IDS.main],
      minimumWidth: {
        cssPixels: 320,
        status: 'NOT_EXECUTED',
        reason: 'MINIMUM_WIDTH_BROWSER_CHECK_NOT_EXECUTED',
      },
      motion: {
        animation: 'NONE',
        reducedMotion: 'NO_ANIMATION_TO_REDUCE',
        status: 'NOT_EXECUTED',
      },
    },
    boundaries: makeBoundaries(),
    actions: [],
  }) as unknown as PublicShellCandidate;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function candidateNavigationItems(value: JsonValue | undefined): readonly JsonValue[] | null {
  if (!isJsonObject(value)) {
    return null;
  }
  const header = value['header'];
  if (!isJsonObject(header)) {
    return null;
  }
  const items = header['navigationItems'];
  return Array.isArray(items) ? items : null;
}

function hasDuplicateNavigationField(
  items: readonly JsonValue[] | null,
  field: 'id' | 'route',
): boolean {
  if (items === null) {
    return false;
  }
  const seen = new Set<string>();
  for (const item of items) {
    if (!isJsonObject(item)) {
      continue;
    }
    const candidate = item[field];
    if (typeof candidate === 'string') {
      if (seen.has(candidate)) {
        return true;
      }
      seen.add(candidate);
    }
  }
  return false;
}

const PROHIBITED_KEY_NAMES = new Set([
  'affiliatelink',
  'analytics',
  'articlebody',
  'articleid',
  'articleslug',
  'articlesnapshot',
  'articletitle',
  'beacon',
  'callback',
  'cookie',
  'cookies',
  'cta',
  'onclick',
  'onsubmit',
  'script',
  'scripts',
]);
const ABSOLUTE_SCHEME = /^(?:(?:https?|ftp|file|mailto|tel):|\/\/)/i;

function normalizedKey(key: string): string {
  return key.replace(/[\s_-]+/g, '').toLowerCase();
}

function hasProhibitedSurface(value: JsonValue): boolean {
  if (typeof value === 'string') {
    return ABSOLUTE_SCHEME.test(value);
  }
  if (value === null || typeof value !== 'object') {
    return false;
  }
  if (Array.isArray(value)) {
    return value.some((item) => hasProhibitedSurface(item));
  }
  return Object.entries(value).some(
    ([key, item]) => PROHIBITED_KEY_NAMES.has(normalizedKey(key)) || hasProhibitedSurface(item),
  );
}

function candidateDomIds(value: JsonValue | undefined): readonly string[] {
  if (!isJsonObject(value)) {
    return [];
  }
  const ids: string[] = [];
  const add = (record: JsonValue | undefined, key: string): void => {
    if (!isJsonObject(record)) {
      return;
    }
    const candidate = record[key];
    if (typeof candidate === 'string') {
      ids.push(candidate);
    }
  };
  const skipLink = value['skipLink'];
  const header = value['header'];
  const breadcrumb = value['breadcrumb'];
  const main = value['main'];
  const footer = value['footer'];
  add(skipLink, 'id');
  add(header, 'id');
  add(header, 'navigationId');
  for (const item of candidateNavigationItems(value) ?? []) {
    add(item, 'id');
  }
  add(breadcrumb, 'id');
  if (isJsonObject(breadcrumb) && Array.isArray(breadcrumb['items'])) {
    for (const item of breadcrumb['items']) {
      add(item, 'id');
    }
  }
  add(main, 'id');
  add(main, 'headingId');
  add(footer, 'id');
  return ids;
}

function hasDuplicate(values: readonly string[]): boolean {
  return new Set(values).size !== values.length;
}

function classifyCandidateFailure(
  value: Readonly<Record<string, JsonValue>>,
  expected: PublicShellCandidate,
): PublicShellErrorCode {
  const metadata = value['metadata'];
  const shell = value['shell'];
  const contentSlots = value['contentSlots'];
  const boundaries = value['boundaries'];
  if (hasProhibitedSurface(value)) {
    return 'PUBLIC_SHELL_PROHIBITED_SURFACE';
  }
  if (hasDuplicate(candidateDomIds(shell))) {
    return 'PUBLIC_SHELL_DUPLICATE_ID';
  }
  const navigationItems = candidateNavigationItems(shell);
  if (hasDuplicateNavigationField(navigationItems, 'id')) {
    return 'PUBLIC_SHELL_DUPLICATE_ID';
  }
  if (hasDuplicateNavigationField(navigationItems, 'route')) {
    return 'PUBLIC_SHELL_DUPLICATE_ROUTE';
  }
  if (
    metadata === null ||
    typeof metadata !== 'object' ||
    Array.isArray(metadata) ||
    !jsonEqual(metadata, expected.metadata)
  ) {
    return 'PUBLIC_SHELL_METADATA_INVALID';
  }
  if (
    shell === null ||
    typeof shell !== 'object' ||
    Array.isArray(shell) ||
    !jsonEqual(shell, expected.shell)
  ) {
    return 'PUBLIC_SHELL_ACCESSIBILITY_INVALID';
  }
  if (!Array.isArray(contentSlots) || !jsonEqual(contentSlots, expected.contentSlots)) {
    return 'PUBLIC_SHELL_CONTENT_INVALID';
  }
  if (
    boundaries === null ||
    typeof boundaries !== 'object' ||
    Array.isArray(boundaries) ||
    !jsonEqual(boundaries, expected.boundaries)
  ) {
    return 'PUBLIC_SHELL_AUTHORITY_INVALID';
  }
  return 'PUBLIC_SHELL_CANDIDATE_INVALID';
}

export function validatePublicShellCandidate(value: unknown): PublicShellCandidate {
  if (!isStrictPlainTree(value)) {
    return reject('PUBLIC_SHELL_CANDIDATE_INVALID');
  }
  let clone: JsonValue;
  try {
    clone = createJsonValue(value);
  } catch {
    return reject('PUBLIC_SHELL_CANDIDATE_INVALID');
  }
  if (!isJsonObject(clone)) {
    return reject('PUBLIC_SHELL_CANDIDATE_INVALID');
  }
  const screen = clone['screen'];
  if (!isJsonObject(screen)) {
    return reject('PUBLIC_SHELL_CANDIDATE_INVALID');
  }
  const screenId = screen['id'];
  if (
    typeof screenId !== 'string' ||
    !(PUBLIC_SHELL_SCREEN_IDS as readonly string[]).includes(screenId)
  ) {
    return reject('PUBLIC_SHELL_SCREEN_UNKNOWN');
  }
  const expected = buildCandidate(screenId as PublicShellScreenId);
  if (!jsonEqual(clone, expected)) {
    return reject(classifyCandidateFailure(clone, expected));
  }
  return clone as unknown as PublicShellCandidate;
}

export function createPublicShellCandidate(input: PublicShellInput): PublicShellCandidate {
  return validatePublicShellCandidate(buildCandidate(validatedScreenId(input)));
}
