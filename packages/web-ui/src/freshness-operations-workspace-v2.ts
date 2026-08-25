import {
  ST1103_RECORDED_PROJECTION_V2_JSON,
  ST1103_RECORDED_PROJECTION_V2_SHA256,
} from './freshness-operations-recorded.v2.ts';
import {
  FRESHNESS_OPERATIONS_SCREEN_IDS,
  FRESHNESS_OPERATIONS_SCREENS,
  type FreshnessOperationsScreenId,
  type FreshnessOperationsScreenMetadata,
} from './freshness-operations-workspace.ts';
import { createJsonValue, type JsonObject, type JsonValue } from './serializable.ts';

export const FRESHNESS_OPERATIONS_WORKSPACE_V2_CLASSIFICATION =
  'LOCAL_EXECUTABLE_RECORDED_FRESHNESS_OPERATIONS_WORKSPACE_V2' as const;

export const FRESHNESS_OPERATIONS_WORKSPACE_V2_ERROR_CODES = createJsonValue([
  'FRESHNESS_OPERATIONS_V2_INPUT_INVALID',
  'FRESHNESS_OPERATIONS_V2_SCREEN_UNKNOWN',
  'FRESHNESS_OPERATIONS_V2_FIXTURE_INVALID',
  'FRESHNESS_OPERATIONS_V2_BINDING_INVALID',
  'FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID',
  'FRESHNESS_OPERATIONS_V2_CANDIDATE_INVALID',
  'FRESHNESS_OPERATIONS_V2_ACTION_UNKNOWN',
  'FRESHNESS_OPERATIONS_V2_ACTION_BLOCKED',
  'FRESHNESS_OPERATIONS_V2_TARGET_INVALID',
  'FRESHNESS_OPERATIONS_V2_REASON_INVALID',
  'FRESHNESS_OPERATIONS_V2_REQUEST_ID_INVALID',
  'FRESHNESS_OPERATIONS_V2_INTENT_INVALID',
]) as unknown as readonly [
  'FRESHNESS_OPERATIONS_V2_INPUT_INVALID',
  'FRESHNESS_OPERATIONS_V2_SCREEN_UNKNOWN',
  'FRESHNESS_OPERATIONS_V2_FIXTURE_INVALID',
  'FRESHNESS_OPERATIONS_V2_BINDING_INVALID',
  'FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID',
  'FRESHNESS_OPERATIONS_V2_CANDIDATE_INVALID',
  'FRESHNESS_OPERATIONS_V2_ACTION_UNKNOWN',
  'FRESHNESS_OPERATIONS_V2_ACTION_BLOCKED',
  'FRESHNESS_OPERATIONS_V2_TARGET_INVALID',
  'FRESHNESS_OPERATIONS_V2_REASON_INVALID',
  'FRESHNESS_OPERATIONS_V2_REQUEST_ID_INVALID',
  'FRESHNESS_OPERATIONS_V2_INTENT_INVALID',
];

export type FreshnessOperationsWorkspaceV2ErrorCode =
  (typeof FRESHNESS_OPERATIONS_WORKSPACE_V2_ERROR_CODES)[number];

export class FreshnessOperationsWorkspaceV2Error extends TypeError {
  readonly code: FreshnessOperationsWorkspaceV2ErrorCode;

  constructor(code: FreshnessOperationsWorkspaceV2ErrorCode) {
    const closed = (FRESHNESS_OPERATIONS_WORKSPACE_V2_ERROR_CODES as readonly unknown[]).includes(
      code,
    )
      ? code
      : 'FRESHNESS_OPERATIONS_V2_CANDIDATE_INVALID';
    super(closed);
    this.name = 'FreshnessOperationsWorkspaceV2Error';
    this.code = closed;
    Object.freeze(this);
  }
}

export interface FreshnessOperationsWorkspaceV2Input {
  readonly screenId: FreshnessOperationsScreenId;
}

export interface FreshnessOperationsStatusCueV2 {
  readonly code: string;
  readonly text: string;
  readonly icon: string;
  readonly colorOnly: false;
}

export interface FreshnessOperationsTableColumnV2 {
  readonly id: string;
  readonly label: string;
  readonly scope: 'col';
}

export interface FreshnessOperationsTableV2 {
  readonly state: 'AVAILABLE_RECORDED' | 'UNAVAILABLE_DEPENDENCY';
  readonly caption: string;
  readonly rowHeaderColumn: string;
  readonly columns: readonly FreshnessOperationsTableColumnV2[];
  readonly rows: readonly JsonObject[];
  readonly emptyState: FreshnessOperationsStatusCueV2 | null;
}

export interface FreshnessOperationsDependencyV2 {
  readonly storyId: string;
  readonly status:
    'LOCAL_RECORDED_INPUT' | 'DISABLED_HEADLESS_FOUNDATION' | 'UNAVAILABLE_UNDECLARED_DEPENDENCY';
  readonly sourceSha256: string | null;
  readonly authority: false;
}

export interface FreshnessOperationsActionDescriptorV2 {
  readonly actionCode: string;
  readonly label: string;
  readonly availability: 'LOCAL_REVIEW_PROPOSAL_ONLY' | 'BLOCKED_DEPENDENCY';
  readonly targetFingerprints: readonly string[];
  readonly reasonCodes: readonly string[];
  readonly futureEffectRequirements: {
    readonly humanApprovalRequired: true;
    readonly reasonRequired: true;
    readonly impactPreviewRequired: true;
    readonly idempotencyRequired: true;
    readonly auditRequired: true;
    readonly stepUpRequired: boolean;
  };
  readonly effect: 'NONE';
  readonly dispatch: 'NOT_EXECUTED';
  readonly persistence: 'NOT_EXECUTED';
}

export interface FreshnessOperationsScreenProjectionV2 {
  readonly screenId: FreshnessOperationsScreenId;
  readonly dataStatus: 'AVAILABLE_RECORDED' | 'UNAVAILABLE_DEPENDENCY';
  readonly sourceStoryIds: readonly string[];
  readonly components: readonly string[];
  readonly summaryStatus: FreshnessOperationsStatusCueV2;
  readonly dependencies: readonly FreshnessOperationsDependencyV2[];
  readonly table: FreshnessOperationsTableV2;
  readonly actionDescriptors: readonly FreshnessOperationsActionDescriptorV2[];
  readonly dataClassification: 'INTERNAL_METADATA_ONLY';
  readonly unknownAsZeroAllowed: false;
  readonly rawPayloadPresent: false;
}

export interface FreshnessOperationsWorkspaceV2Model {
  readonly classification: typeof FRESHNESS_OPERATIONS_WORKSPACE_V2_CLASSIFICATION;
  readonly storyId: 'ST-1103';
  readonly localStatus: 'LOCAL_IMPLEMENTATION_COMPLETE';
  readonly canonicalStatus: {
    readonly implementation: 'NOT_STARTED';
    readonly verification: 'NOT_EXECUTED';
  };
  readonly screen: FreshnessOperationsScreenMetadata;
  readonly screenOrder: typeof FRESHNESS_OPERATIONS_SCREEN_IDS;
  readonly sourceFixtureSha256: string;
  readonly sourceMode: 'RECORDED_SYNTHETIC_DEV_CI_ONLY';
  readonly projection: FreshnessOperationsScreenProjectionV2;
  readonly route: {
    readonly registered: false;
    readonly renderEnabled: false;
    readonly status: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED';
    readonly roleMetadataOnly: true;
  };
  readonly accessibility: {
    readonly statusNotColorOnly: true;
    readonly statusTextPresent: true;
    readonly statusCodePresent: true;
    readonly statusIconPresent: true;
    readonly tableCaptionPresent: true;
    readonly columnHeadersPresent: true;
    readonly rowHeaderDeclared: true;
    readonly keyboardModel: readonly ['Tab', 'Shift+Tab', 'ArrowUp', 'ArrowDown'];
    readonly zoomTargetPercent: 200;
    readonly rendered: false;
    readonly browserVerified: false;
    readonly screenReaderVerified: false;
  };
  readonly authority: {
    readonly authenticationEstablished: false;
    readonly authorizationGranted: false;
    readonly stepUpEstablished: false;
    readonly mutationEnabled: false;
    readonly retryEnabled: false;
    readonly cancellationEnabled: false;
    readonly redriveEnabled: false;
    readonly killSwitchEnabled: false;
    readonly networkEnabled: false;
    readonly persistenceEnabled: false;
    readonly publicationAuthorized: false;
    readonly activationAuthorized: false;
    readonly releaseAuthorized: false;
    readonly productionAuthorized: false;
  };
  readonly verification: {
    readonly localModel: 'EXECUTED';
    readonly TST_022: 'NOT_EXECUTED';
    readonly TST_024: 'NOT_EXECUTED';
    readonly live: 'NOT_EXECUTED';
    readonly staging: 'NOT_EXECUTED';
    readonly release: 'NOT_EXECUTED';
    readonly publication: 'NOT_EXECUTED';
    readonly production: 'NOT_EXECUTED';
  };
  readonly localImplementationComplete: true;
  readonly formalAcceptanceAchieved: false;
  readonly productionEligible: false;
}

export interface FreshnessOperationsReviewIntentInputV2 {
  readonly screenId: FreshnessOperationsScreenId;
  readonly actionCode: string;
  readonly targetFingerprint: string;
  readonly reasonCode: string;
  readonly requestId: string;
}

export interface FreshnessOperationsReviewIntentV2 {
  readonly classification: 'LOCAL_EFFECT_FREE_HUMAN_REVIEW_INTENT_V2';
  readonly storyId: 'ST-1103';
  readonly requestId: string;
  readonly screenId: FreshnessOperationsScreenId;
  readonly actionCode: string;
  readonly targetFingerprint: string;
  readonly reasonCode: string;
  readonly sourceFixtureSha256: string;
  readonly intentKind: 'HUMAN_REVIEW_REQUEST_ONLY';
  readonly effect: 'NONE';
  readonly dispatch: 'NOT_EXECUTED';
  readonly persistence: 'NOT_EXECUTED';
  readonly authenticationEstablished: false;
  readonly authorizationGranted: false;
  readonly stepUpEstablished: false;
  readonly mutationAuthorized: false;
  readonly publicationAuthorized: false;
  readonly productionAuthorized: false;
}

const SHA256 = /^[0-9a-f]{64}$/u;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const CODE = /^[A-Z][A-Z0-9_.:-]{0,79}$/u;
const COMPONENT = /^UI-C0(?:0[1-9]|[1-3][0-9]|4[0-6])$/u;
const dangerousKeys = new Set(['__proto__', 'constructor', 'prototype']);

const expectedBindings = createJsonValue({
  canonical: {
    integration: '540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a',
    uiDesign: '0cec24c40dfa69c14d51fb73e56977790ee19ed0ad5ed74d0339553ff25b860e',
    screenCatalog: 'dae723c7e423febe4abc0ab8752420411e6e95586069b75186bda7e92de85050',
    componentCatalog: '986ed1682b0f6b48c7e9fab04ff51229c000f4673e3cc3981e50903832f208f2',
    securityCatalog: 'c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8',
    testCatalog: '7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b',
    operationsDesign: '894a4520a54fe1a5391f5bdd7ebfd3fdacf745604d1245e20b139315eabad9c8',
    storyBacklog: '4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d',
  },
  dependencies: {
    st1401Completion: '37be7ef769384885aafb802f6c69bb15dc8d7cb0aeaf15dff013144526b6f866',
    st1401Domain: '3a33b44d99f92fce6417257de8c170d4622dd900fe7cc7cbac0b67494469dd95',
    st1401Adapter: '0b4cff4e9c0d22311604abb4c756d63a72d63269073bf1dea1e4cec032639de6',
    st1404Domain: '3c9e4266aa2ad76acb0d87d64e0989f974dfceac611bec23a409c9cf027d515b',
    st1404Application: 'b1ea28fcc6b0e051b5f4a7ba0ae09d1628b4ed9f0400fd747fa7c2f032dc0403',
    st1404Adapter: '89db55e209caed06b0be29f95b7b165ded6e9acd9153e01ac54a8e8c51790064',
    st1101Serializable: '56adb1e0356fba66e147be4c055b7a40f1115608a3e29bbee4584234f8b3273d',
    st1101RouteGuard: '8395f542c7c65445fa3d1bec4a0e037c96610da8589e1807604b4fb3fa6a584f',
    st1101DataTable: 'bb999786019d1c01ece36929124359af00c5362134c4ee4faf50ce496d3689f4',
    st1101Dialog: '494ac8b9e2a4087de2d003dd6c28bfcab7c85961f418a5892453c865058724bc',
  },
});

function reject(code: FreshnessOperationsWorkspaceV2ErrorCode): never {
  throw new FreshnessOperationsWorkspaceV2Error(code);
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
      if (dangerousKeys.has(key)) {
        return false;
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

function strictClone(value: unknown, code: FreshnessOperationsWorkspaceV2ErrorCode): JsonValue {
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
  const expectedKeys = new Set(expected);
  return (
    expectedKeys.size === expected.length &&
    keys.length === expected.length &&
    keys.every((key) => expectedKeys.has(key))
  );
}

function safeText(value: JsonValue | undefined, maximum = 240): value is string {
  return (
    typeof value === 'string' &&
    value.length > 0 &&
    value.length <= maximum &&
    !/[\u0000-\u001f\u007f]/u.test(value)
  );
}

function statusCue(value: JsonValue | undefined): FreshnessOperationsStatusCueV2 {
  if (
    !isObject(value) ||
    !exactKeys(value, ['code', 'text', 'icon', 'colorOnly']) ||
    typeof value['code'] !== 'string' ||
    !CODE.test(value['code']) ||
    !safeText(value['text']) ||
    typeof value['icon'] !== 'string' ||
    !CODE.test(value['icon']) ||
    value['colorOnly'] !== false
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  return value as unknown as FreshnessOperationsStatusCueV2;
}

function stringArray(
  value: JsonValue | undefined,
  predicate: (item: string) => boolean,
  maximum: number,
): readonly string[] {
  if (
    !Array.isArray(value) ||
    value.length > maximum ||
    !value.every((item) => typeof item === 'string' && predicate(item)) ||
    new Set(value).size !== value.length
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  return value as readonly string[];
}

function dependency(value: JsonValue): FreshnessOperationsDependencyV2 {
  if (
    !isObject(value) ||
    !exactKeys(value, ['storyId', 'status', 'sourceSha256', 'authority']) ||
    typeof value['storyId'] !== 'string' ||
    !/^ST-[0-9]{4}$/u.test(value['storyId']) ||
    ![
      'LOCAL_RECORDED_INPUT',
      'DISABLED_HEADLESS_FOUNDATION',
      'UNAVAILABLE_UNDECLARED_DEPENDENCY',
    ].includes(String(value['status'])) ||
    !(
      value['sourceSha256'] === null ||
      (typeof value['sourceSha256'] === 'string' && SHA256.test(value['sourceSha256']))
    ) ||
    value['authority'] !== false
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  if (
    (value['status'] === 'UNAVAILABLE_UNDECLARED_DEPENDENCY') !==
    (value['sourceSha256'] === null)
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  return value as unknown as FreshnessOperationsDependencyV2;
}

function table(value: JsonValue | undefined): FreshnessOperationsTableV2 {
  if (
    !isObject(value) ||
    !exactKeys(value, ['state', 'caption', 'rowHeaderColumn', 'columns', 'rows', 'emptyState']) ||
    !['AVAILABLE_RECORDED', 'UNAVAILABLE_DEPENDENCY'].includes(String(value['state'])) ||
    !safeText(value['caption']) ||
    typeof value['rowHeaderColumn'] !== 'string' ||
    !CODE.test(value['rowHeaderColumn']) ||
    !Array.isArray(value['columns']) ||
    value['columns'].length === 0 ||
    value['columns'].length > 20 ||
    !Array.isArray(value['rows']) ||
    value['rows'].length > 100
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  const columns = value['columns'];
  const columnIds: string[] = [];
  for (const column of columns) {
    if (
      !isObject(column) ||
      !exactKeys(column, ['id', 'label', 'scope']) ||
      typeof column['id'] !== 'string' ||
      !CODE.test(column['id']) ||
      !safeText(column['label'], 120) ||
      column['scope'] !== 'col'
    ) {
      return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
    }
    columnIds.push(column['id']);
  }
  if (
    new Set(columnIds).size !== columnIds.length ||
    !columnIds.includes(value['rowHeaderColumn'])
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  for (const row of value['rows']) {
    if (!isObject(row) || !safeText(row['rowKey'], 120)) {
      return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
    }
    statusCue(row['status']);
  }
  const unavailable = value['state'] === 'UNAVAILABLE_DEPENDENCY';
  if (
    unavailable !== (value['rows'].length === 0) ||
    (unavailable && value['emptyState'] === null) ||
    (!unavailable && value['emptyState'] !== null)
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  if (value['emptyState'] !== null) {
    statusCue(value['emptyState']);
  }
  return value as unknown as FreshnessOperationsTableV2;
}

function actionDescriptor(value: JsonValue): FreshnessOperationsActionDescriptorV2 {
  if (
    !isObject(value) ||
    !exactKeys(value, [
      'actionCode',
      'label',
      'availability',
      'targetFingerprints',
      'reasonCodes',
      'futureEffectRequirements',
      'effect',
      'dispatch',
      'persistence',
    ]) ||
    typeof value['actionCode'] !== 'string' ||
    !CODE.test(value['actionCode']) ||
    !safeText(value['label'], 120) ||
    !['LOCAL_REVIEW_PROPOSAL_ONLY', 'BLOCKED_DEPENDENCY'].includes(String(value['availability'])) ||
    value['effect'] !== 'NONE' ||
    value['dispatch'] !== 'NOT_EXECUTED' ||
    value['persistence'] !== 'NOT_EXECUTED'
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  const targets = stringArray(value['targetFingerprints'], (item) => SHA256.test(item), 100);
  const reasons = stringArray(value['reasonCodes'], (item) => CODE.test(item), 20);
  if (reasons.length === 0) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  const requirements = value['futureEffectRequirements'];
  if (
    !isObject(requirements) ||
    !exactKeys(requirements, [
      'humanApprovalRequired',
      'reasonRequired',
      'impactPreviewRequired',
      'idempotencyRequired',
      'auditRequired',
      'stepUpRequired',
    ]) ||
    requirements['humanApprovalRequired'] !== true ||
    requirements['reasonRequired'] !== true ||
    requirements['impactPreviewRequired'] !== true ||
    requirements['idempotencyRequired'] !== true ||
    requirements['auditRequired'] !== true ||
    typeof requirements['stepUpRequired'] !== 'boolean'
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  if (
    (value['availability'] === 'LOCAL_REVIEW_PROPOSAL_ONLY' && targets.length === 0) ||
    (value['availability'] === 'BLOCKED_DEPENDENCY' && targets.length !== 0)
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  return value as unknown as FreshnessOperationsActionDescriptorV2;
}

function projection(
  value: JsonValue | undefined,
  screenId: FreshnessOperationsScreenId,
): FreshnessOperationsScreenProjectionV2 {
  if (
    !isObject(value) ||
    !exactKeys(value, [
      'screenId',
      'dataStatus',
      'sourceStoryIds',
      'components',
      'summaryStatus',
      'dependencies',
      'table',
      'actionDescriptors',
      'dataClassification',
      'unknownAsZeroAllowed',
      'rawPayloadPresent',
    ]) ||
    value['screenId'] !== screenId ||
    !['AVAILABLE_RECORDED', 'UNAVAILABLE_DEPENDENCY'].includes(String(value['dataStatus'])) ||
    value['dataClassification'] !== 'INTERNAL_METADATA_ONLY' ||
    value['unknownAsZeroAllowed'] !== false ||
    value['rawPayloadPresent'] !== false
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  stringArray(value['sourceStoryIds'], (item) => /^ST-[0-9]{4}$/u.test(item), 8);
  stringArray(value['components'], (item) => COMPONENT.test(item), 20);
  statusCue(value['summaryStatus']);
  if (
    !Array.isArray(value['dependencies']) ||
    value['dependencies'].length === 0 ||
    value['dependencies'].length > 8 ||
    !Array.isArray(value['actionDescriptors']) ||
    value['actionDescriptors'].length > 8
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  value['dependencies'].forEach(dependency);
  table(value['table']);
  const actions = value['actionDescriptors'].map(actionDescriptor);
  if (new Set(actions.map((item) => item.actionCode)).size !== actions.length) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  const typedTable = value['table'] as JsonObject;
  if (
    (value['dataStatus'] === 'AVAILABLE_RECORDED') !==
    (typedTable['state'] === 'AVAILABLE_RECORDED')
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_PROJECTION_INVALID');
  }
  return value as unknown as FreshnessOperationsScreenProjectionV2;
}

interface FixtureV2 {
  readonly bindings: JsonObject;
  readonly projections: Readonly<Record<FreshnessOperationsScreenId, JsonValue>>;
}

let parsedFixture: FixtureV2 | undefined;

function fixture(): FixtureV2 {
  if (parsedFixture !== undefined) {
    return parsedFixture;
  }
  if (!SHA256.test(ST1103_RECORDED_PROJECTION_V2_SHA256)) {
    return reject('FRESHNESS_OPERATIONS_V2_FIXTURE_INVALID');
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(ST1103_RECORDED_PROJECTION_V2_JSON);
  } catch {
    return reject('FRESHNESS_OPERATIONS_V2_FIXTURE_INVALID');
  }
  const cloned = strictClone(parsed, 'FRESHNESS_OPERATIONS_V2_FIXTURE_INVALID');
  if (
    !isObject(cloned) ||
    !exactKeys(cloned, [
      'schemaVersion',
      'storyId',
      'classification',
      'environment',
      'evaluatedAt',
      'bindings',
      'projections',
    ]) ||
    cloned['schemaVersion'] !== 2 ||
    cloned['storyId'] !== 'ST-1103' ||
    cloned['classification'] !== 'RECORDED_SYNTHETIC_FRESHNESS_OPERATIONS_PROJECTION_V2' ||
    cloned['environment'] !== 'CI' ||
    cloned['evaluatedAt'] !== '2026-08-24T00:00:00Z' ||
    !isObject(cloned['bindings']) ||
    JSON.stringify(cloned['bindings']) !== JSON.stringify(expectedBindings) ||
    !isObject(cloned['projections']) ||
    !exactKeys(cloned['projections'], FRESHNESS_OPERATIONS_SCREEN_IDS)
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_BINDING_INVALID');
  }
  for (const screenId of FRESHNESS_OPERATIONS_SCREEN_IDS) {
    projection(cloned['projections'][screenId], screenId);
  }
  parsedFixture = {
    bindings: cloned['bindings'],
    projections: cloned['projections'] as unknown as Readonly<
      Record<FreshnessOperationsScreenId, JsonValue>
    >,
  };
  return parsedFixture;
}

function validatedScreenId(
  input: FreshnessOperationsWorkspaceV2Input,
): FreshnessOperationsScreenId {
  const cloned = strictClone(input, 'FRESHNESS_OPERATIONS_V2_INPUT_INVALID');
  if (!isObject(cloned) || !exactKeys(cloned, ['screenId'])) {
    return reject('FRESHNESS_OPERATIONS_V2_INPUT_INVALID');
  }
  const value = cloned['screenId'];
  if (typeof value !== 'string') {
    return reject('FRESHNESS_OPERATIONS_V2_INPUT_INVALID');
  }
  if (!(FRESHNESS_OPERATIONS_SCREEN_IDS as readonly string[]).includes(value)) {
    return reject('FRESHNESS_OPERATIONS_V2_SCREEN_UNKNOWN');
  }
  return value as FreshnessOperationsScreenId;
}

function buildWorkspace(
  screenId: FreshnessOperationsScreenId,
): FreshnessOperationsWorkspaceV2Model {
  const screen = FRESHNESS_OPERATIONS_SCREENS.find((candidate) => candidate.id === screenId);
  if (screen === undefined) {
    return reject('FRESHNESS_OPERATIONS_V2_SCREEN_UNKNOWN');
  }
  const source = fixture();
  const selected = projection(source.projections[screenId], screenId);
  return createJsonValue({
    classification: FRESHNESS_OPERATIONS_WORKSPACE_V2_CLASSIFICATION,
    storyId: 'ST-1103',
    localStatus: 'LOCAL_IMPLEMENTATION_COMPLETE',
    canonicalStatus: { implementation: 'NOT_STARTED', verification: 'NOT_EXECUTED' },
    screen,
    screenOrder: FRESHNESS_OPERATIONS_SCREEN_IDS,
    sourceFixtureSha256: ST1103_RECORDED_PROJECTION_V2_SHA256,
    sourceMode: 'RECORDED_SYNTHETIC_DEV_CI_ONLY',
    projection: selected,
    route: {
      registered: false,
      renderEnabled: false,
      status: 'DISABLED_AUTH_TRANSPORT_UNRESOLVED',
      roleMetadataOnly: true,
    },
    accessibility: {
      statusNotColorOnly: true,
      statusTextPresent: true,
      statusCodePresent: true,
      statusIconPresent: true,
      tableCaptionPresent: true,
      columnHeadersPresent: true,
      rowHeaderDeclared: true,
      keyboardModel: ['Tab', 'Shift+Tab', 'ArrowUp', 'ArrowDown'],
      zoomTargetPercent: 200,
      rendered: false,
      browserVerified: false,
      screenReaderVerified: false,
    },
    authority: {
      authenticationEstablished: false,
      authorizationGranted: false,
      stepUpEstablished: false,
      mutationEnabled: false,
      retryEnabled: false,
      cancellationEnabled: false,
      redriveEnabled: false,
      killSwitchEnabled: false,
      networkEnabled: false,
      persistenceEnabled: false,
      publicationAuthorized: false,
      activationAuthorized: false,
      releaseAuthorized: false,
      productionAuthorized: false,
    },
    verification: {
      localModel: 'EXECUTED',
      TST_022: 'NOT_EXECUTED',
      TST_024: 'NOT_EXECUTED',
      live: 'NOT_EXECUTED',
      staging: 'NOT_EXECUTED',
      release: 'NOT_EXECUTED',
      publication: 'NOT_EXECUTED',
      production: 'NOT_EXECUTED',
    },
    localImplementationComplete: true,
    formalAcceptanceAchieved: false,
    productionEligible: false,
  }) as unknown as FreshnessOperationsWorkspaceV2Model;
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function validateFreshnessOperationsWorkspaceV2(
  value: unknown,
): FreshnessOperationsWorkspaceV2Model {
  const cloned = strictClone(value, 'FRESHNESS_OPERATIONS_V2_CANDIDATE_INVALID');
  if (!isObject(cloned) || !isObject(cloned['screen'])) {
    return reject('FRESHNESS_OPERATIONS_V2_CANDIDATE_INVALID');
  }
  const screenId = cloned['screen']['id'];
  if (
    typeof screenId !== 'string' ||
    !(FRESHNESS_OPERATIONS_SCREEN_IDS as readonly string[]).includes(screenId)
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_SCREEN_UNKNOWN');
  }
  const expected = buildWorkspace(screenId as FreshnessOperationsScreenId);
  if (!jsonEqual(cloned, expected)) {
    return reject('FRESHNESS_OPERATIONS_V2_CANDIDATE_INVALID');
  }
  return cloned as unknown as FreshnessOperationsWorkspaceV2Model;
}

export function createFreshnessOperationsWorkspaceV2(
  input: FreshnessOperationsWorkspaceV2Input,
): FreshnessOperationsWorkspaceV2Model {
  return validateFreshnessOperationsWorkspaceV2(buildWorkspace(validatedScreenId(input)));
}

function actionInput(value: FreshnessOperationsReviewIntentInputV2): {
  readonly screenId: FreshnessOperationsScreenId;
  readonly actionCode: string;
  readonly targetFingerprint: string;
  readonly reasonCode: string;
  readonly requestId: string;
} {
  const cloned = strictClone(value, 'FRESHNESS_OPERATIONS_V2_INPUT_INVALID');
  if (
    !isObject(cloned) ||
    !exactKeys(cloned, ['screenId', 'actionCode', 'targetFingerprint', 'reasonCode', 'requestId'])
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_INPUT_INVALID');
  }
  const screenId = cloned['screenId'];
  const actionCode = cloned['actionCode'];
  const targetFingerprint = cloned['targetFingerprint'];
  const reasonCode = cloned['reasonCode'];
  const requestId = cloned['requestId'];
  if (
    typeof screenId !== 'string' ||
    !(FRESHNESS_OPERATIONS_SCREEN_IDS as readonly string[]).includes(screenId)
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_SCREEN_UNKNOWN');
  }
  if (typeof actionCode !== 'string' || !CODE.test(actionCode)) {
    return reject('FRESHNESS_OPERATIONS_V2_ACTION_UNKNOWN');
  }
  if (typeof targetFingerprint !== 'string' || !SHA256.test(targetFingerprint)) {
    return reject('FRESHNESS_OPERATIONS_V2_TARGET_INVALID');
  }
  if (typeof reasonCode !== 'string' || !CODE.test(reasonCode)) {
    return reject('FRESHNESS_OPERATIONS_V2_REASON_INVALID');
  }
  if (typeof requestId !== 'string' || !UUID.test(requestId)) {
    return reject('FRESHNESS_OPERATIONS_V2_REQUEST_ID_INVALID');
  }
  return {
    screenId: screenId as FreshnessOperationsScreenId,
    actionCode,
    targetFingerprint,
    reasonCode,
    requestId,
  };
}

function buildReviewIntent(
  input: ReturnType<typeof actionInput>,
): FreshnessOperationsReviewIntentV2 {
  const model = buildWorkspace(input.screenId);
  const descriptor = model.projection.actionDescriptors.find(
    (candidate) => candidate.actionCode === input.actionCode,
  );
  if (descriptor === undefined) {
    return reject('FRESHNESS_OPERATIONS_V2_ACTION_UNKNOWN');
  }
  if (descriptor.availability !== 'LOCAL_REVIEW_PROPOSAL_ONLY') {
    return reject('FRESHNESS_OPERATIONS_V2_ACTION_BLOCKED');
  }
  if (!descriptor.targetFingerprints.includes(input.targetFingerprint)) {
    return reject('FRESHNESS_OPERATIONS_V2_TARGET_INVALID');
  }
  if (!descriptor.reasonCodes.includes(input.reasonCode)) {
    return reject('FRESHNESS_OPERATIONS_V2_REASON_INVALID');
  }
  return createJsonValue({
    classification: 'LOCAL_EFFECT_FREE_HUMAN_REVIEW_INTENT_V2',
    storyId: 'ST-1103',
    requestId: input.requestId,
    screenId: input.screenId,
    actionCode: input.actionCode,
    targetFingerprint: input.targetFingerprint,
    reasonCode: input.reasonCode,
    sourceFixtureSha256: ST1103_RECORDED_PROJECTION_V2_SHA256,
    intentKind: 'HUMAN_REVIEW_REQUEST_ONLY',
    effect: 'NONE',
    dispatch: 'NOT_EXECUTED',
    persistence: 'NOT_EXECUTED',
    authenticationEstablished: false,
    authorizationGranted: false,
    stepUpEstablished: false,
    mutationAuthorized: false,
    publicationAuthorized: false,
    productionAuthorized: false,
  }) as unknown as FreshnessOperationsReviewIntentV2;
}

export function validateFreshnessOperationsReviewIntentV2(
  value: unknown,
): FreshnessOperationsReviewIntentV2 {
  const cloned = strictClone(value, 'FRESHNESS_OPERATIONS_V2_INTENT_INVALID');
  if (
    !isObject(cloned) ||
    !exactKeys(cloned, [
      'classification',
      'storyId',
      'requestId',
      'screenId',
      'actionCode',
      'targetFingerprint',
      'reasonCode',
      'sourceFixtureSha256',
      'intentKind',
      'effect',
      'dispatch',
      'persistence',
      'authenticationEstablished',
      'authorizationGranted',
      'stepUpEstablished',
      'mutationAuthorized',
      'publicationAuthorized',
      'productionAuthorized',
    ])
  ) {
    return reject('FRESHNESS_OPERATIONS_V2_INTENT_INVALID');
  }
  let rebuilt: FreshnessOperationsReviewIntentV2;
  try {
    rebuilt = buildReviewIntent(
      actionInput({
        screenId: cloned['screenId'] as FreshnessOperationsScreenId,
        actionCode: cloned['actionCode'] as string,
        targetFingerprint: cloned['targetFingerprint'] as string,
        reasonCode: cloned['reasonCode'] as string,
        requestId: cloned['requestId'] as string,
      }),
    );
  } catch {
    return reject('FRESHNESS_OPERATIONS_V2_INTENT_INVALID');
  }
  if (!jsonEqual(cloned, rebuilt)) {
    return reject('FRESHNESS_OPERATIONS_V2_INTENT_INVALID');
  }
  return cloned as unknown as FreshnessOperationsReviewIntentV2;
}

export function createFreshnessOperationsReviewIntentV2(
  input: FreshnessOperationsReviewIntentInputV2,
): FreshnessOperationsReviewIntentV2 {
  return validateFreshnessOperationsReviewIntentV2(buildReviewIntent(actionInput(input)));
}
