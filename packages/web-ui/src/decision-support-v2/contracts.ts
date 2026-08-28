export const DECISION_SUPPORT_V2_RESULT_STATES = Object.freeze([
  'PASS',
  'FAIL',
  'UNKNOWN',
  'STALE',
  'BLOCKED',
  'NO_MATCH',
] as const);

export type DecisionSupportV2ResultState = (typeof DECISION_SUPPORT_V2_RESULT_STATES)[number];

export const DECISION_SUPPORT_V2_PAGE_TEMPLATES = Object.freeze([
  'HOME',
  'HUB',
  'GUIDE',
  'COMPARISON',
  'DIFFERENCE',
  'TOOL',
  'POLICY',
] as const);

export type DecisionSupportV2PageTemplate = (typeof DECISION_SUPPORT_V2_PAGE_TEMPLATES)[number];

export interface DecisionSupportV2Route {
  readonly route: string;
  readonly template: DecisionSupportV2PageTemplate;
  readonly articleId: string;
  readonly publicationState: 'LOCAL_PREVIEW' | 'PLANNED_LOCKED' | 'FIXTURE_ONLY';
  readonly publicCandidate: boolean;
  readonly intendedIndexCandidate: boolean;
  readonly previewRobots: 'noindex,nofollow';
}

export const DECISION_SUPPORT_V2_ROUTES = Object.freeze([
  {
    route: '/',
    template: 'HOME',
    articleId: 'HOME',
    publicationState: 'LOCAL_PREVIEW',
    publicCandidate: true,
    intendedIndexCandidate: true,
    previewRobots: 'noindex,nofollow',
  },
  {
    route: '/carry-on/',
    template: 'HUB',
    articleId: 'A01',
    publicationState: 'LOCAL_PREVIEW',
    publicCandidate: true,
    intendedIndexCandidate: true,
    previewRobots: 'noindex,nofollow',
  },
  {
    route: '/tools/carry-on-size-checker/',
    template: 'TOOL',
    articleId: 'A02',
    publicationState: 'LOCAL_PREVIEW',
    publicCandidate: true,
    intendedIndexCandidate: true,
    previewRobots: 'noindex,nofollow',
  },
  {
    route: '/guides/carry-on-baggage-rules/',
    template: 'GUIDE',
    articleId: 'A03',
    publicationState: 'LOCAL_PREVIEW',
    publicCandidate: true,
    intendedIndexCandidate: true,
    previewRobots: 'noindex,nofollow',
  },
  {
    route: '/guides/low-cost-carrier-7kg-packing/',
    template: 'GUIDE',
    articleId: 'A04',
    publicationState: 'PLANNED_LOCKED',
    publicCandidate: false,
    intendedIndexCandidate: false,
    previewRobots: 'noindex,nofollow',
  },
  {
    route: '/carry-on-suitcase-comparison/',
    template: 'COMPARISON',
    articleId: 'A05',
    publicationState: 'LOCAL_PREVIEW',
    publicCandidate: true,
    intendedIndexCandidate: true,
    previewRobots: 'noindex,nofollow',
  },
  {
    route: '/guides/carry-on-bag-measurement/',
    template: 'GUIDE',
    articleId: 'A06',
    publicationState: 'PLANNED_LOCKED',
    publicCandidate: false,
    intendedIndexCandidate: false,
    previewRobots: 'noindex,nofollow',
  },
  {
    route: '/policy/how-we-compare-carry-on-products/',
    template: 'POLICY',
    articleId: 'A25',
    publicationState: 'LOCAL_PREVIEW',
    publicCandidate: true,
    intendedIndexCandidate: true,
    previewRobots: 'noindex,nofollow',
  },
  {
    route: '/differences/ace-cresta-vs-difference-vs-maxpass4/',
    template: 'DIFFERENCE',
    articleId: 'A19',
    publicationState: 'FIXTURE_ONLY',
    publicCandidate: false,
    intendedIndexCandidate: false,
    previewRobots: 'noindex,nofollow',
  },
] as const satisfies readonly DecisionSupportV2Route[]);

export const DECISION_SUPPORT_V2_TOKENS = Object.freeze({
  color: Object.freeze({
    ink: '#17213A',
    paper: '#FBF8F1',
    surface: '#FFFFFF',
    muted: '#F1F5F4',
    indigo: '#243B6B',
    indigoDark: '#172A52',
    accent: '#A4492C',
    success: '#216E5A',
    warning: '#8A5A00',
    danger: '#A23434',
    focus: '#005FCC',
    border: '#D9D5CB',
  }),
  radiusPx: Object.freeze([6, 12, 20] as const),
  spacingPx: Object.freeze([4, 8, 12, 16, 24, 32, 48, 64, 96] as const),
  readingWidthPx: 720,
  wideWidthPx: 1120,
  shellWidthPx: 1280,
  targetSizePx: 44,
});

export const DECISION_SUPPORT_V2_COMPONENTS = Object.freeze([
  'DisclosureBar',
  'DecisionHero',
  'ConditionForm',
  'ResultPanel',
  'GuideCard',
  'TrustStrip',
  'SourceChip',
  'ComparisonMatrix',
  'ProductCard',
  'AffiliateCTA',
  'ChangeLog',
  'CorrectionLink',
  'ConsentSurface',
] as const);

export const DECISION_SUPPORT_V2_BOUNDARIES = Object.freeze({
  analyticsSender: 'OFF',
  checkerExecution: 'BROWSER_LOCAL_ONLY',
  cookieUse: false,
  externalFonts: false,
  persistence: false,
  serviceWorker: false,
  thirdPartyRuntime: false,
  wordpressWrite: 'DISABLED_DRY_RUN',
});
