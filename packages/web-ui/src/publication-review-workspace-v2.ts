import {
  ST0906_RECORDED_WORKSPACE_V2_JSON,
  ST0906_RECORDED_WORKSPACE_V2_SHA256,
} from './publication-review-recorded.v2.ts';
import {
  PUBLICATION_REVIEW_SCREEN_IDS,
  PUBLICATION_REVIEW_SCREENS,
  type PublicationReviewScreenId,
  type PublicationReviewScreenMetadata,
} from './publication-review-workspace.ts';
import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const PUBLICATION_REVIEW_WORKSPACE_V2_CLASSIFICATION =
  'LOCAL_EXECUTABLE_RECORDED_PUBLICATION_REVIEW_WORKSPACE_V2' as const;

export const PUBLICATION_REVIEW_WORKSPACE_V2_SECTION_IDS = createJsonValue([
  'publication-review-v2-context',
  'publication-review-v2-approval',
  'publication-review-v2-snapshot',
  'publication-review-v2-diff',
  'publication-review-v2-preview',
  'publication-review-v2-audit',
  'publication-review-v2-commands',
]) as unknown as readonly [
  'publication-review-v2-context',
  'publication-review-v2-approval',
  'publication-review-v2-snapshot',
  'publication-review-v2-diff',
  'publication-review-v2-preview',
  'publication-review-v2-audit',
  'publication-review-v2-commands',
];

export const PUBLICATION_REVIEW_WORKSPACE_V2_ERROR_CODES = createJsonValue([
  'PUBLICATION_REVIEW_V2_INPUT_INVALID',
  'PUBLICATION_REVIEW_V2_SCREEN_UNKNOWN',
  'PUBLICATION_REVIEW_V2_FIXTURE_INVALID',
  'PUBLICATION_REVIEW_V2_BINDING_INVALID',
  'PUBLICATION_REVIEW_V2_CANDIDATE_INVALID',
  'PUBLICATION_REVIEW_V2_RENDER_INPUT_INVALID',
]) as unknown as readonly [
  'PUBLICATION_REVIEW_V2_INPUT_INVALID',
  'PUBLICATION_REVIEW_V2_SCREEN_UNKNOWN',
  'PUBLICATION_REVIEW_V2_FIXTURE_INVALID',
  'PUBLICATION_REVIEW_V2_BINDING_INVALID',
  'PUBLICATION_REVIEW_V2_CANDIDATE_INVALID',
  'PUBLICATION_REVIEW_V2_RENDER_INPUT_INVALID',
];

export type PublicationReviewWorkspaceV2ErrorCode =
  (typeof PUBLICATION_REVIEW_WORKSPACE_V2_ERROR_CODES)[number];

export class PublicationReviewWorkspaceV2Error extends TypeError {
  readonly code: PublicationReviewWorkspaceV2ErrorCode;

  constructor(code: PublicationReviewWorkspaceV2ErrorCode) {
    const closed = (PUBLICATION_REVIEW_WORKSPACE_V2_ERROR_CODES as readonly unknown[]).includes(
      code,
    )
      ? code
      : 'PUBLICATION_REVIEW_V2_CANDIDATE_INVALID';
    super(closed);
    this.name = 'PublicationReviewWorkspaceV2Error';
    this.code = closed;
    Object.freeze(this);
  }
}

export interface PublicationReviewWorkspaceV2Input {
  readonly screenId: PublicationReviewScreenId;
}

export interface PublicationReviewRecordedReviewV2 {
  readonly assignmentId: string;
  readonly assignmentState: 'COMPLETED';
  readonly reviewDecisionId: string;
  readonly reviewDecision: 'APPROVE';
  readonly reviewDecidedAt: string;
  readonly checklistVersion: string;
  readonly checklistSha256: string;
  readonly checklistStatus: 'ALL_PASS';
  readonly reviewAuditRecordId: string;
  readonly recordedSyntheticOnly: true;
  readonly finalApprovalAuthorizedByReview: false;
}

export interface PublicationReviewFinalApprovalV2 {
  readonly state: 'RECORDED_SYNTHETIC_APPROVED';
  readonly approvalId: string;
  readonly approvedAt: string;
  readonly auditRecordId: string;
  readonly articleVersionId: string;
  readonly articleVersionNo: number;
  readonly articleBodySha256: string;
  readonly canonicalAstSha256: string;
  readonly gateBundleSha256: string;
  readonly findingSnapshotSha256: string;
  readonly openBlockingFindingIds: readonly string[];
  readonly actorKind: 'HUMAN';
  readonly actorStatus: 'ACTIVE';
  readonly actorRole: 'MANAGING_EDITOR';
  readonly mfaState: 'SATISFIED_RECORDED_SYNTHETIC';
  readonly stepUpState: 'SATISFIED_RECORDED_SYNTHETIC';
  readonly reauthenticatedAt: string;
  readonly separationOfDutiesVerifiedRecorded: true;
  readonly realFinalApprovalAuthorized: false;
  readonly publicationAuthorized: false;
}

export interface PublicationReviewSnapshotV2 {
  readonly state: 'IMMUTABLE_RECORDED_CANDIDATE';
  readonly publicationId: string;
  readonly publicationVersion: number;
  readonly snapshotId: string;
  readonly snapshotSha256: string;
  readonly snapshotArtifactSha256: string;
  readonly contentManifestSha256: string;
  readonly inputBundleSha256: string;
  readonly sourcePacketSha256: string;
  readonly immutable: true;
  readonly compatibility: 'CONTENT_AST_V1_BOUND_LEGACY_SCHEMA_RECONCILIATION_REQUIRED';
  readonly readiness: 'NOT_READY';
  readonly persisted: false;
  readonly publicationAuthorized: false;
}

export interface PublicationReviewDiffRowV2 {
  readonly position: number;
  readonly sourceBlockId: string;
  readonly sourceType: string;
  readonly projectedBlockKey: string | null;
  readonly projectedType: string;
  readonly textFragmentCount: number;
  readonly state: 'PROJECTED_TO_ARTICLE_FIELD' | 'RECORDED_TRANSFORMATION';
}

export interface PublicationReviewDiffV2 {
  readonly fromLabel: string;
  readonly toLabel: string;
  readonly fromSha256: string;
  readonly toSha256: string;
  readonly bindingIntegrity: 'EXACT_RECORDED_BINDINGS_VERIFIED';
  readonly contentHashEquality: 'NOT_ESTABLISHED_RECONCILIATION_REQUIRED';
  readonly rows: readonly PublicationReviewDiffRowV2[];
}

export interface PublicationReviewPreviewBlockV2 {
  readonly position: number;
  readonly blockKey: string;
  readonly blockType: string;
  readonly sourceType: string;
  readonly text: readonly string[];
}

export interface PublicationReviewPreviewV2 {
  readonly state: 'RECORDED_PUBLIC_READ_SHAPE_NO_ROUTE';
  readonly articleId: string;
  readonly publicationId: string;
  readonly snapshotId: string;
  readonly projectionGeneration: number;
  readonly title: string;
  readonly languageTag: 'ja-JP';
  readonly canonicalPath: string;
  readonly isIndexable: false;
  readonly disclosureText: string;
  readonly freshnessStatus: 'UNKNOWN';
  readonly metaDescription: string;
  readonly blocks: readonly PublicationReviewPreviewBlockV2[];
  readonly productCardCount: number;
  readonly offerCount: number;
  readonly routeHttpStatus: number;
  readonly routeActivated: false;
  readonly publicReadServed: false;
}

export interface PublicationReviewAuditEntryV2 {
  readonly sequence: number;
  readonly kind: 'FINAL_APPROVAL' | 'PUBLISH_RECORDED_INTENT' | 'ROLLBACK_RECORDED_INTENT';
  readonly recordId: string;
  readonly occurredAt: string;
  readonly correlationId: string | null;
  readonly recordSha256: string | null;
  readonly state:
    'PROCESS_LOCAL_IMMUTABLE_REFERENCE_NOT_DURABLE' | 'PROCESS_LOCAL_NOT_PERSISTED_NOT_EMITTED';
  readonly persisted: false;
  readonly eventEmitted: false;
}

export interface PublicationReviewCommandV2 {
  readonly actionCode: 'PUBLISH' | 'UNPUBLISH' | 'ROLLBACK';
  readonly label: string;
  readonly uiAvailability:
    'DISABLED_AUTH_ROUTE_STEP_UP_UNAVAILABLE' | 'DENIED_DEFAULT_NO_CANONICAL_ROLE_ACTION';
  readonly recordedResultState:
    'RECORDED_SYNTHETIC_PROCESS_LOCAL' | 'DENIED_DEFAULT_NO_CANONICAL_ROLE_ACTION';
  readonly commandSha256: string | null;
  readonly resultSha256: string | null;
  readonly idempotencyKeySha256: string | null;
  readonly authorizationSha256: string | null;
  readonly killSwitchStateSha256: string | null;
  readonly correlationId: string | null;
  readonly auditRecordId: string | null;
  readonly auditSha256: string | null;
  readonly eventSha256: string | null;
  readonly outboxSha256: string | null;
  readonly generation: number | null;
  readonly fromSnapshotId: string | null;
  readonly toSnapshotId: string | null;
  readonly effectPerformedByUi: false;
  readonly persisted: false;
  readonly eventEmitted: false;
}

export interface PublicationReviewRecordedFixtureV2 {
  readonly schemaVersion: 2;
  readonly storyId: 'ST-0906';
  readonly classification: 'RECORDED_SYNTHETIC_PUBLICATION_REVIEW_WORKSPACE_V2';
  readonly profile: 'ST0906_PUBLICATION_REVIEW_RECORDED_LOCAL_V2';
  readonly environment: 'CI';
  readonly capturedAt: string;
  readonly bindings: {
    readonly canonical: Readonly<Record<string, string>>;
    readonly dependencies: Readonly<Record<string, string>>;
  };
  readonly review: PublicationReviewRecordedReviewV2;
  readonly finalApproval: PublicationReviewFinalApprovalV2;
  readonly snapshot: PublicationReviewSnapshotV2;
  readonly diff: PublicationReviewDiffV2;
  readonly preview: PublicationReviewPreviewV2;
  readonly auditTimeline: readonly PublicationReviewAuditEntryV2[];
  readonly commands: readonly PublicationReviewCommandV2[];
  readonly idempotencyEvidence: Readonly<Record<string, JsonValue>>;
  readonly commandBoundary: Readonly<Record<string, JsonValue>>;
  readonly route: Readonly<Record<string, JsonValue>>;
  readonly authority: Readonly<Record<string, JsonValue>>;
  readonly verification: Readonly<Record<string, JsonValue>>;
  readonly rawPayloadPresent: false;
  readonly financeDataPresent: false;
  readonly credentialDataPresent: false;
}

export interface PublicationReviewWorkspaceV2Model {
  readonly classification: typeof PUBLICATION_REVIEW_WORKSPACE_V2_CLASSIFICATION;
  readonly storyId: 'ST-0906';
  readonly localStatus: 'LOCAL_IMPLEMENTATION_COMPLETE';
  readonly canonicalStatus: {
    readonly implementation: 'NOT_STARTED';
    readonly verification: 'NOT_EXECUTED';
  };
  readonly screen: PublicationReviewScreenMetadata;
  readonly screenOrder: typeof PUBLICATION_REVIEW_SCREEN_IDS;
  readonly sourceFixtureSha256: typeof ST0906_RECORDED_WORKSPACE_V2_SHA256;
  readonly sourceMode: 'RECORDED_SYNTHETIC_DEV_CI_ONLY';
  readonly sectionIds: typeof PUBLICATION_REVIEW_WORKSPACE_V2_SECTION_IDS;
  readonly review: PublicationReviewRecordedReviewV2;
  readonly finalApproval: PublicationReviewFinalApprovalV2;
  readonly snapshot: PublicationReviewSnapshotV2;
  readonly diff: PublicationReviewDiffV2;
  readonly preview: PublicationReviewPreviewV2;
  readonly auditTimeline: readonly PublicationReviewAuditEntryV2[];
  readonly commands: readonly PublicationReviewCommandV2[];
  readonly idempotencyEvidence: Readonly<Record<string, JsonValue>>;
  readonly commandBoundary: Readonly<Record<string, JsonValue>>;
  readonly route: {
    readonly registered: false;
    readonly routable: false;
    readonly renderEnabled: false;
    readonly navigationEligible: false;
    readonly status: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED_OD_010';
    readonly catalogPath: string;
    readonly roleMetadataOnly: true;
  };
  readonly authority: {
    readonly authenticationEstablished: false;
    readonly authorizationGranted: false;
    readonly stepUpEstablished: false;
    readonly backendReauthorizationRequired: true;
    readonly dataFetchEnabled: false;
    readonly mutationEnabled: false;
    readonly networkEnabled: false;
    readonly persistenceEnabled: false;
    readonly databaseWriteEnabled: false;
    readonly cmsWriteEnabled: false;
    readonly eventEmissionEnabled: false;
    readonly outboxWriteEnabled: false;
    readonly publicStateChangeEnabled: false;
    readonly publicationAuthorized: false;
    readonly rollbackAuthorized: false;
    readonly releaseAuthorized: false;
    readonly productionAuthorized: false;
  };
  readonly accessibility: {
    readonly renderedSemanticHtmlAvailable: true;
    readonly formalConformanceClaimed: false;
    readonly documentLanguage: 'ja-JP';
    readonly skipLinkId: 'publication-review-v2-skip-link';
    readonly mainId: 'publication-review-v2-main';
    readonly h1Id: 'publication-review-v2-heading';
    readonly h1Count: 1;
    readonly sectionNavigationLabel: 'Publication review sections';
    readonly sectionIds: typeof PUBLICATION_REVIEW_WORKSPACE_V2_SECTION_IDS;
    readonly focusOrder: readonly string[];
    readonly statusTextPresent: true;
    readonly statusCodePresent: true;
    readonly statusColorOnly: false;
    readonly diffCaptionPresent: true;
    readonly diffColumnHeadersPresent: true;
    readonly diffRowHeadersPresent: true;
    readonly disabledActionReasonPresent: true;
    readonly keyboardModel: readonly ['Tab', 'Shift+Tab', 'Enter'];
    readonly zoomTargetPercent: 200;
    readonly visibleFocusRequired: true;
    readonly motion: 'NONE';
    readonly browserVerified: false;
    readonly screenReaderVerified: false;
  };
  readonly verification: {
    readonly localModelAndRenderer: 'EXECUTABLE';
    readonly TST_022: 'NOT_EXECUTED';
    readonly TST_024: 'NOT_EXECUTED';
    readonly browser: 'NOT_EXECUTED';
    readonly screenReader: 'NOT_EXECUTED';
    readonly authentication: 'NOT_EXECUTED';
    readonly authorization: 'NOT_EXECUTED';
    readonly stepUp: 'NOT_EXECUTED';
    readonly live: 'NOT_EXECUTED';
    readonly staging: 'NOT_EXECUTED';
    readonly publication: 'NOT_EXECUTED';
    readonly release: 'NOT_EXECUTED';
    readonly production: 'NOT_EXECUTED';
  };
  readonly rawPayloadPresent: false;
  readonly financeDataPresent: false;
  readonly credentialDataPresent: false;
  readonly localImplementationComplete: true;
  readonly formalAcceptanceAchieved: false;
  readonly productionEligible: false;
}

const SHA256 = /^[0-9a-f]{64}$/u;
const dangerousKeys = new Set(['__proto__', 'constructor', 'prototype']);

function reject(code: PublicationReviewWorkspaceV2ErrorCode): never {
  throw new PublicationReviewWorkspaceV2Error(code);
}

function isStrictPlainTree(value: unknown, ancestors = new WeakSet<object>()): boolean {
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'boolean' ||
    (typeof value === 'number' && Number.isSafeInteger(value))
  ) {
    return true;
  }
  if (typeof value !== 'object' || ancestors.has(value)) {
    return false;
  }
  ancestors.add(value);
  try {
    const isArray = Array.isArray(value);
    if (Object.getPrototypeOf(value) !== (isArray ? Array.prototype : Object.prototype)) {
      return false;
    }
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== 'string') {
        return false;
      }
      if (key === 'length') {
        continue;
      }
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (
        dangerousKeys.has(key) ||
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

function strictClone(value: unknown, code: PublicationReviewWorkspaceV2ErrorCode): JsonValue {
  if (!isStrictPlainTree(value)) {
    return reject(code);
  }
  try {
    return createJsonValue(value);
  } catch {
    return reject(code);
  }
}

function isObject(value: JsonValue | undefined): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function exactKeys(value: JsonObject, expected: readonly string[]): boolean {
  const keys = Object.keys(value);
  const expectedSet = new Set(expected);
  return (
    expected.length === expectedSet.size &&
    keys.length === expected.length &&
    keys.every((key) => expectedSet.has(key))
  );
}

function allFalse(value: JsonValue | undefined, keys: readonly string[]): boolean {
  return isObject(value) && keys.every((key) => value[key] === false);
}

function parseFixture(): PublicationReviewRecordedFixtureV2 {
  let parsed: unknown;
  try {
    parsed = JSON.parse(ST0906_RECORDED_WORKSPACE_V2_JSON);
  } catch {
    return reject('PUBLICATION_REVIEW_V2_FIXTURE_INVALID');
  }
  const clone = strictClone(parsed, 'PUBLICATION_REVIEW_V2_FIXTURE_INVALID');
  if (
    !isObject(clone) ||
    !exactKeys(clone, [
      'schemaVersion',
      'storyId',
      'classification',
      'profile',
      'environment',
      'capturedAt',
      'bindings',
      'review',
      'finalApproval',
      'snapshot',
      'diff',
      'preview',
      'auditTimeline',
      'commands',
      'idempotencyEvidence',
      'commandBoundary',
      'route',
      'authority',
      'verification',
      'rawPayloadPresent',
      'financeDataPresent',
      'credentialDataPresent',
    ]) ||
    clone['schemaVersion'] !== 2 ||
    clone['storyId'] !== 'ST-0906' ||
    clone['classification'] !== 'RECORDED_SYNTHETIC_PUBLICATION_REVIEW_WORKSPACE_V2' ||
    clone['profile'] !== 'ST0906_PUBLICATION_REVIEW_RECORDED_LOCAL_V2' ||
    clone['environment'] !== 'CI' ||
    clone['rawPayloadPresent'] !== false ||
    clone['financeDataPresent'] !== false ||
    clone['credentialDataPresent'] !== false ||
    !Array.isArray(clone['auditTimeline']) ||
    clone['auditTimeline'].length !== 3 ||
    !Array.isArray(clone['commands']) ||
    clone['commands'].length !== 3 ||
    !isObject(clone['snapshot']) ||
    clone['snapshot']['immutable'] !== true ||
    clone['snapshot']['readiness'] !== 'NOT_READY' ||
    clone['snapshot']['publicationAuthorized'] !== false ||
    !isObject(clone['diff']) ||
    clone['diff']['bindingIntegrity'] !== 'EXACT_RECORDED_BINDINGS_VERIFIED' ||
    clone['diff']['contentHashEquality'] !== 'NOT_ESTABLISHED_RECONCILIATION_REQUIRED' ||
    !isObject(clone['preview']) ||
    clone['preview']['routeActivated'] !== false ||
    clone['preview']['publicReadServed'] !== false ||
    !Array.isArray(clone['preview']['blocks']) ||
    !allFalse(clone['route'], ['registered', 'routable', 'renderEnabled', 'navigationEligible']) ||
    !allFalse(clone['authority'], [
      'authenticationEstablished',
      'authorizationGranted',
      'stepUpEstablished',
      'dataFetchEnabled',
      'mutationEnabled',
      'networkEnabled',
      'persistenceEnabled',
      'databaseWriteEnabled',
      'cmsWriteEnabled',
      'eventEmissionEnabled',
      'outboxWriteEnabled',
      'publicStateChangeEnabled',
      'publicationAuthorized',
      'rollbackAuthorized',
      'releaseAuthorized',
      'productionAuthorized',
    ])
  ) {
    return reject('PUBLICATION_REVIEW_V2_FIXTURE_INVALID');
  }
  const bindings = clone['bindings'];
  if (
    !isObject(bindings) ||
    !isObject(bindings['canonical']) ||
    !isObject(bindings['dependencies'])
  ) {
    return reject('PUBLICATION_REVIEW_V2_BINDING_INVALID');
  }
  const dependencies = bindings['dependencies'];
  for (const key of [
    'st0901ReviewFixture',
    'st0902FinalApprovalFixture',
    'st0903SnapshotFixture',
    'st0904ProjectionFixture',
    'st0905CommandFixture',
    'st0905RecordedAdapter',
    'st1101RouteGuard',
  ]) {
    const digest = dependencies[key];
    if (typeof digest !== 'string' || !SHA256.test(digest)) {
      return reject('PUBLICATION_REVIEW_V2_BINDING_INVALID');
    }
  }
  return clone as unknown as PublicationReviewRecordedFixtureV2;
}

const recordedFixture = parseFixture();

function validatedScreenId(input: PublicationReviewWorkspaceV2Input): PublicationReviewScreenId {
  const clone = strictClone(input, 'PUBLICATION_REVIEW_V2_INPUT_INVALID');
  if (!isObject(clone) || !exactKeys(clone, ['screenId'])) {
    return reject('PUBLICATION_REVIEW_V2_INPUT_INVALID');
  }
  const screenId = clone['screenId'];
  if (typeof screenId !== 'string') {
    return reject('PUBLICATION_REVIEW_V2_INPUT_INVALID');
  }
  if (!(PUBLICATION_REVIEW_SCREEN_IDS as readonly string[]).includes(screenId)) {
    return reject('PUBLICATION_REVIEW_V2_SCREEN_UNKNOWN');
  }
  return screenId as PublicationReviewScreenId;
}

function buildModel(screenId: PublicationReviewScreenId): PublicationReviewWorkspaceV2Model {
  const screen = PUBLICATION_REVIEW_SCREENS.find((candidate) => candidate.id === screenId);
  if (screen === undefined) {
    return reject('PUBLICATION_REVIEW_V2_SCREEN_UNKNOWN');
  }
  const focusOrder = [
    'publication-review-v2-skip-link',
    ...PUBLICATION_REVIEW_WORKSPACE_V2_SECTION_IDS.map((sectionId) => `${sectionId}-link`),
    'publication-review-v2-main',
  ];
  return createJsonValue({
    classification: PUBLICATION_REVIEW_WORKSPACE_V2_CLASSIFICATION,
    storyId: 'ST-0906',
    localStatus: 'LOCAL_IMPLEMENTATION_COMPLETE',
    canonicalStatus: { implementation: 'NOT_STARTED', verification: 'NOT_EXECUTED' },
    screen,
    screenOrder: PUBLICATION_REVIEW_SCREEN_IDS,
    sourceFixtureSha256: ST0906_RECORDED_WORKSPACE_V2_SHA256,
    sourceMode: 'RECORDED_SYNTHETIC_DEV_CI_ONLY',
    sectionIds: PUBLICATION_REVIEW_WORKSPACE_V2_SECTION_IDS,
    review: recordedFixture.review,
    finalApproval: recordedFixture.finalApproval,
    snapshot: recordedFixture.snapshot,
    diff: recordedFixture.diff,
    preview: recordedFixture.preview,
    auditTimeline: recordedFixture.auditTimeline,
    commands: recordedFixture.commands,
    idempotencyEvidence: recordedFixture.idempotencyEvidence,
    commandBoundary: recordedFixture.commandBoundary,
    route: {
      registered: false,
      routable: false,
      renderEnabled: false,
      navigationEligible: false,
      status: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED_OD_010',
      catalogPath: screen.route,
      roleMetadataOnly: true,
    },
    authority: recordedFixture.authority,
    accessibility: {
      renderedSemanticHtmlAvailable: true,
      formalConformanceClaimed: false,
      documentLanguage: 'ja-JP',
      skipLinkId: 'publication-review-v2-skip-link',
      mainId: 'publication-review-v2-main',
      h1Id: 'publication-review-v2-heading',
      h1Count: 1,
      sectionNavigationLabel: 'Publication review sections',
      sectionIds: PUBLICATION_REVIEW_WORKSPACE_V2_SECTION_IDS,
      focusOrder,
      statusTextPresent: true,
      statusCodePresent: true,
      statusColorOnly: false,
      diffCaptionPresent: true,
      diffColumnHeadersPresent: true,
      diffRowHeadersPresent: true,
      disabledActionReasonPresent: true,
      keyboardModel: ['Tab', 'Shift+Tab', 'Enter'],
      zoomTargetPercent: 200,
      visibleFocusRequired: true,
      motion: 'NONE',
      browserVerified: false,
      screenReaderVerified: false,
    },
    verification: {
      localModelAndRenderer: 'EXECUTABLE',
      TST_022: 'NOT_EXECUTED',
      TST_024: 'NOT_EXECUTED',
      browser: 'NOT_EXECUTED',
      screenReader: 'NOT_EXECUTED',
      authentication: 'NOT_EXECUTED',
      authorization: 'NOT_EXECUTED',
      stepUp: 'NOT_EXECUTED',
      live: 'NOT_EXECUTED',
      staging: 'NOT_EXECUTED',
      publication: 'NOT_EXECUTED',
      release: 'NOT_EXECUTED',
      production: 'NOT_EXECUTED',
    },
    rawPayloadPresent: false,
    financeDataPresent: false,
    credentialDataPresent: false,
    localImplementationComplete: true,
    formalAcceptanceAchieved: false,
    productionEligible: false,
  }) as unknown as PublicationReviewWorkspaceV2Model;
}

export function createPublicationReviewWorkspaceV2(
  input: PublicationReviewWorkspaceV2Input,
): PublicationReviewWorkspaceV2Model {
  return buildModel(validatedScreenId(input));
}

export function validatePublicationReviewWorkspaceV2(
  candidate: unknown,
): PublicationReviewWorkspaceV2Model {
  const clone = strictClone(candidate, 'PUBLICATION_REVIEW_V2_CANDIDATE_INVALID');
  if (!isObject(clone) || !isObject(clone['screen'])) {
    return reject('PUBLICATION_REVIEW_V2_CANDIDATE_INVALID');
  }
  const screenId = clone['screen']['id'];
  if (
    typeof screenId !== 'string' ||
    !(PUBLICATION_REVIEW_SCREEN_IDS as readonly string[]).includes(screenId)
  ) {
    return reject('PUBLICATION_REVIEW_V2_SCREEN_UNKNOWN');
  }
  const expected = buildModel(screenId as PublicationReviewScreenId);
  if (JSON.stringify(clone) !== JSON.stringify(expected)) {
    return reject('PUBLICATION_REVIEW_V2_CANDIDATE_INVALID');
  }
  return clone as unknown as PublicationReviewWorkspaceV2Model;
}

function escapeHtml(value: string | number): string {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function displayNullable(value: string | number | null): string {
  return value === null ? 'なし（未生成）' : escapeHtml(value);
}

function definition(term: string, value: string | number | null): string {
  return `<div><dt>${escapeHtml(term)}</dt><dd><code>${displayNullable(value)}</code></dd></div>`;
}

function sectionNavigation(model: PublicationReviewWorkspaceV2Model): string {
  const labels = [
    'Context',
    'Approval',
    'Snapshot',
    'Diff',
    'Preview',
    'Audit',
    'Commands',
  ] as const;
  const links = model.sectionIds
    .map(
      (sectionId, index) =>
        `<li><a id="${sectionId}-link" href="#${sectionId}">${escapeHtml(labels[index] ?? sectionId)}</a></li>`,
    )
    .join('');
  return `<nav aria-label="${escapeHtml(model.accessibility.sectionNavigationLabel)}"><ul class="section-nav">${links}</ul></nav>`;
}

function diffTable(model: PublicationReviewWorkspaceV2Model): string {
  const rows = model.diff.rows
    .map(
      (row) => `<tr>
        <th scope="row">${escapeHtml(row.position)}</th>
        <td><code>${escapeHtml(row.sourceBlockId)}</code></td>
        <td>${escapeHtml(row.sourceType)}</td>
        <td><code>${displayNullable(row.projectedBlockKey)}</code></td>
        <td>${escapeHtml(row.projectedType)}</td>
        <td>${escapeHtml(row.textFragmentCount)}</td>
        <td><span class="status status-info">${escapeHtml(row.state)}</span></td>
      </tr>`,
    )
    .join('');
  return `<div class="table-scroll" tabindex="0" aria-label="Snapshot and projection diff table scroll area">
    <table>
      <caption>ST-0903 immutable snapshot to ST-0904 public projection — text-labelled recorded diff</caption>
      <thead><tr>
        <th scope="col">位置</th><th scope="col">入力 block</th><th scope="col">入力 type</th>
        <th scope="col">投影 block</th><th scope="col">投影 type</th><th scope="col">text 数</th><th scope="col">状態</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

function previewArticle(model: PublicationReviewWorkspaceV2Model): string {
  const blocks = model.preview.blocks
    .map((block) => {
      const text = block.text.length
        ? `<ul>${block.text.map((fragment) => `<li>${escapeHtml(fragment)}</li>`).join('')}</ul>`
        : '<p class="muted">公開 text fragment なし（0 と推測しません）。</p>';
      return `<section aria-labelledby="preview-${escapeHtml(block.blockKey)}">
        <h4 id="preview-${escapeHtml(block.blockKey)}">${escapeHtml(block.position + 1)}. ${escapeHtml(block.blockType)}</h4>
        <p class="eyebrow">source: ${escapeHtml(block.sourceType)}</p>${text}
      </section>`;
    })
    .join('');
  return `<article class="preview" lang="${escapeHtml(model.preview.languageTag)}" aria-labelledby="recorded-preview-title">
    <p class="disclosure">${escapeHtml(model.preview.disclosureText)}</p>
    <h3 id="recorded-preview-title">${escapeHtml(model.preview.title)}</h3>
    <p>${escapeHtml(model.preview.metaDescription)}</p>
    <p class="status status-warning">Freshness: ${escapeHtml(model.preview.freshnessStatus)} · index: noindex · route: disabled</p>
    ${blocks}
  </article>`;
}

function auditTimeline(model: PublicationReviewWorkspaceV2Model): string {
  return `<ol class="timeline">${model.auditTimeline
    .map(
      (entry) => `<li>
        <h3>${escapeHtml(entry.sequence)}. ${escapeHtml(entry.kind)}</h3>
        <dl class="facts">${definition('record ID', entry.recordId)}${definition('occurred at', entry.occurredAt)}${definition('correlation ID', entry.correlationId)}${definition('record SHA-256', entry.recordSha256)}</dl>
        <p class="status status-blocked">${escapeHtml(entry.state)} · persisted: false · emitted: false</p>
      </li>`,
    )
    .join('')}</ol>`;
}

function commandPanels(model: PublicationReviewWorkspaceV2Model): string {
  return `<div class="command-list">${model.commands
    .map(
      (
        command,
      ) => `<section aria-labelledby="command-${escapeHtml(command.actionCode.toLowerCase())}">
        <h3 id="command-${escapeHtml(command.actionCode.toLowerCase())}">${escapeHtml(command.label)}</h3>
        <p id="command-${escapeHtml(command.actionCode.toLowerCase())}-reason" class="status status-blocked">${escapeHtml(command.uiAvailability)} — UI dispatch は無効です。</p>
        <dl class="facts">${definition('command SHA-256', command.commandSha256)}${definition('result SHA-256', command.resultSha256)}${definition('authorization SHA-256', command.authorizationSha256)}${definition('kill-switch state SHA-256', command.killSwitchStateSha256)}${definition('generation', command.generation)}${definition('to snapshot', command.toSnapshotId)}</dl>
        <button type="button" disabled aria-describedby="command-${escapeHtml(command.actionCode.toLowerCase())}-reason">${escapeHtml(command.label)}（無効）</button>
      </section>`,
    )
    .join('')}</div>`;
}

/**
 * Renders a standalone, script-free local document. It registers no route and
 * exposes no callback, form submission, transport, or command dispatcher.
 */
export function renderPublicationReviewWorkspaceHtmlV2(candidate: unknown): string {
  let model: PublicationReviewWorkspaceV2Model;
  try {
    model = validatePublicationReviewWorkspaceV2(candidate);
  } catch (error: unknown) {
    if (error instanceof PublicationReviewWorkspaceV2Error) {
      return reject('PUBLICATION_REVIEW_V2_RENDER_INPUT_INVALID');
    }
    throw error;
  }
  const screenRoles = model.screen.roles.map(escapeHtml).join(', ');
  return `<!doctype html>
<html lang="ja-JP">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'">
  <title>${escapeHtml(model.screen.name)} — ST-0906 local recorded review</title>
  <style>
    :root{color-scheme:light;--surface:#fff;--soft:#f5f7f9;--text:#1b1f23;--muted:#59636e;--border:#aeb8c3;--info:#0b63ce;--warning:#754b00;--danger:#9b2118;--focus:#0b63ce;font:100%/1.55 system-ui,sans-serif}
    *{box-sizing:border-box}body{margin:0;background:var(--soft);color:var(--text)}a{color:#064fa9}a:focus-visible,button:focus-visible,[tabindex]:focus-visible{outline:3px solid var(--focus);outline-offset:3px}.skip-link{position:absolute;left:1rem;top:-6rem;background:var(--text);color:#fff;padding:.75rem 1rem;z-index:10}.skip-link:focus{top:1rem}.shell{max-width:88rem;margin:auto;background:var(--surface);min-height:100vh}.top{padding:clamp(1rem,3vw,2.5rem);border-bottom:1px solid var(--border)}main{padding:clamp(1rem,3vw,2.5rem)}h1{font-size:clamp(1.8rem,4vw,3rem);line-height:1.15;margin:.3rem 0}h2{font-size:clamp(1.35rem,2.5vw,2rem)}h3,h4{font-size:1.08rem}.eyebrow{font-weight:700;color:var(--muted);letter-spacing:.04em;text-transform:uppercase}.lede{max-width:76ch}.section-nav{display:flex;gap:.5rem 1rem;flex-wrap:wrap;padding:0;list-style:none}.section-nav a{display:inline-block;padding:.5rem}.workspace-section{padding:1.5rem 0;border-top:2px solid var(--border);scroll-margin-top:1rem}.status{display:inline-block;border-left:.35rem solid currentColor;padding:.4rem .65rem;font-weight:650}.status-blocked{color:var(--danger);background:#fff2f0}.status-warning{color:var(--warning);background:#fff8e7}.status-info{color:var(--info);background:#eef6ff}.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr));gap:.65rem;margin:1rem 0}.facts div{min-width:0;background:var(--soft);padding:.75rem;border:1px solid var(--border)}dt{font-weight:700}dd{margin:.2rem 0 0}code{font-family:ui-monospace,monospace;overflow-wrap:anywhere;word-break:break-word}.table-scroll{overflow-x:auto;border:1px solid var(--border)}table{border-collapse:collapse;min-width:68rem;width:100%}caption{text-align:left;font-weight:700;padding:.8rem}th,td{padding:.65rem;text-align:left;border:1px solid var(--border);vertical-align:top}thead{background:var(--soft)}.preview{border:2px solid var(--border);padding:clamp(1rem,2vw,2rem);max-width:72rem}.preview section{border-top:1px solid var(--border);padding-top:.6rem}.disclosure{font-weight:700;background:#fff8e7;padding:.8rem}.muted{color:var(--muted)}.timeline,.command-list{display:grid;gap:1rem}.timeline li,.command-list>section{border-left:.3rem solid var(--border);padding:0 1rem}.command-list{grid-template-columns:repeat(auto-fit,minmax(min(100%,24rem),1fr))}button{font:inherit;padding:.7rem 1rem;border:2px solid var(--border);border-radius:.3rem}button:disabled{color:var(--muted);background:#e9edf1;cursor:not-allowed}.boundary{padding:1rem;border:2px solid var(--danger);background:#fff2f0}@media(max-width:48rem){.facts{grid-template-columns:1fr}.top,main{padding:1rem}.workspace-section{padding:1.1rem 0}}@media(prefers-reduced-motion:no-preference){html{scroll-behavior:auto}}
  </style>
</head>
<body>
  <a id="${model.accessibility.skipLinkId}" class="skip-link" href="#${model.accessibility.mainId}">本文へ移動</a>
  <div class="shell">
    <header class="top">
      <p class="eyebrow">ST-0906 · recorded synthetic · local only</p>
      <h1 id="${model.accessibility.h1Id}">${escapeHtml(model.screen.name)} — 公開レビュー</h1>
      <p class="lede">${escapeHtml(model.screen.purpose)}</p>
      <p role="status" aria-live="off" class="status status-blocked">BLOCKED · ${escapeHtml(model.route.status)} · publication authority: false</p>
      ${sectionNavigation(model)}
    </header>
    <main id="${model.accessibility.mainId}" tabindex="-1" aria-labelledby="${model.accessibility.h1Id}">
      <section id="publication-review-v2-context" class="workspace-section" aria-labelledby="publication-review-v2-context-heading">
        <h2 id="publication-review-v2-context-heading">対象と権限境界</h2>
        <dl class="facts">${definition('screen ID', model.screen.id)}${definition('catalog path (display only)', model.route.catalogPath)}${definition('role metadata (not authorization)', screenRoles)}${definition('fixture SHA-256', model.sourceFixtureSha256)}</dl>
        <p class="boundary">Route は未登録です。認証・認可・step-up・backend data access・command dispatch は成立していません。</p>
      </section>
      <section id="publication-review-v2-approval" class="workspace-section" aria-labelledby="publication-review-v2-approval-heading">
        <h2 id="publication-review-v2-approval-heading">Review と Final Approval</h2>
        <p class="status status-info">${escapeHtml(model.review.checklistStatus)} · review ${escapeHtml(model.review.reviewDecision)} · ${escapeHtml(model.finalApproval.state)}</p>
        <dl class="facts">${definition('approval ID', model.finalApproval.approvalId)}${definition('approved at', model.finalApproval.approvedAt)}${definition('article version', model.finalApproval.articleVersionId)}${definition('AST SHA-256', model.finalApproval.canonicalAstSha256)}${definition('gate bundle SHA-256', model.finalApproval.gateBundleSha256)}${definition('blocking findings', model.finalApproval.openBlockingFindingIds.length)}</dl>
        <p class="boundary">Recorded synthetic gate self-consistency only。real final approval: false · publication: false。</p>
      </section>
      <section id="publication-review-v2-snapshot" class="workspace-section" aria-labelledby="publication-review-v2-snapshot-heading">
        <h2 id="publication-review-v2-snapshot-heading">Immutable Snapshot</h2>
        <p class="status status-warning">${escapeHtml(model.snapshot.state)} · ${escapeHtml(model.snapshot.readiness)}</p>
        <dl class="facts">${definition('snapshot ID', model.snapshot.snapshotId)}${definition('snapshot SHA-256', model.snapshot.snapshotSha256)}${definition('artifact SHA-256', model.snapshot.snapshotArtifactSha256)}${definition('manifest SHA-256', model.snapshot.contentManifestSha256)}${definition('compatibility', model.snapshot.compatibility)}</dl>
      </section>
      <section id="publication-review-v2-diff" class="workspace-section" aria-labelledby="publication-review-v2-diff-heading">
        <h2 id="publication-review-v2-diff-heading">Snapshot / Projection 差分</h2>
        <p>${escapeHtml(model.diff.bindingIntegrity)}。content hash equality は <strong>${escapeHtml(model.diff.contentHashEquality)}</strong> です。</p>
        ${diffTable(model)}
      </section>
      <section id="publication-review-v2-preview" class="workspace-section" aria-labelledby="publication-review-v2-preview-heading">
        <h2 id="publication-review-v2-preview-heading">隔離 Preview</h2>
        <p class="boundary">ST-0904 の閉じた public read shape を text として表示します。route activation/public serving はありません。</p>
        ${previewArticle(model)}
      </section>
      <section id="publication-review-v2-audit" class="workspace-section" aria-labelledby="publication-review-v2-audit-heading">
        <h2 id="publication-review-v2-audit-heading">Audit Timeline</h2>
        ${auditTimeline(model)}
      </section>
      <section id="publication-review-v2-commands" class="workspace-section" aria-labelledby="publication-review-v2-commands-heading">
        <h2 id="publication-review-v2-commands-heading">Publish / Unpublish / Rollback</h2>
        <p class="boundary">全操作は無効です。将来の local effect も exact ST-0905 ENV-DEV/CI recorded adapter と全 human/security gate に限定されます。</p>
        ${commandPanels(model)}
      </section>
    </main>
  </div>
</body>
</html>`;
}
