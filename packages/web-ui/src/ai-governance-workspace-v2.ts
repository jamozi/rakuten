import {
  AI_GOVERNANCE_RECORDED_V2_JSON,
  AI_GOVERNANCE_RECORDED_V2_SHA256,
} from './ai-governance-recorded.v2.ts';
import { createJsonValue } from './serializable.ts';
import type { JsonObject, JsonValue } from './serializable.ts';

const EXPECTED_RECORDED_FIXTURE_SHA256 =
  '6474385496e433271246db91010f75b331c44f1432852de6848ed0fa991983cc';

export const AI_GOVERNANCE_V2_SECTION_IDS = createJsonValue([
  'TASK',
  'PROMPT',
  'ROUTE',
  'EVALUATION',
  'RELEASE',
  'COST',
]) as unknown as readonly ['TASK', 'PROMPT', 'ROUTE', 'EVALUATION', 'RELEASE', 'COST'];

export type AiGovernanceSectionIdV2 = (typeof AI_GOVERNANCE_V2_SECTION_IDS)[number];

export interface AiGovernanceStatusV2 {
  readonly code: string;
  readonly colorOnly: false;
  readonly icon: string;
  readonly text: string;
}

export interface AiGovernanceTableColumnV2 {
  readonly key: string;
  readonly label: string;
  readonly semanticRole: 'COLUMN_HEADER';
}

export interface AiGovernanceTableV2 {
  readonly caption: string;
  readonly columns: readonly AiGovernanceTableColumnV2[];
  readonly rowHeaderKey: string;
  readonly rows: readonly JsonObject[];
}

export interface AiGovernanceSectionV2 {
  readonly actions: readonly [];
  readonly availability:
    | 'AVAILABLE_RECORDED_CONFIGURATION'
    | 'AVAILABLE_RECORDED_SYNTHETIC'
    | 'AVAILABLE_REFUSAL_PROPOSAL'
    | 'PARTIAL_CONFIGURED_LIMITS_ONLY';
  readonly id: AiGovernanceSectionIdV2;
  readonly label: 'Task' | 'Prompt' | 'Route' | 'Evaluation' | 'Release' | 'Cost';
  readonly mode: 'READ_ONLY';
  readonly recordCount: number;
  readonly source: 'ST-0701' | 'ST-0707' | 'ST-0708' | 'ST-0701+ST-0706';
  readonly table: AiGovernanceTableV2;
}

export interface AiGovernanceScreenV2 {
  readonly apiDependencies: readonly [];
  readonly area: 'governance';
  readonly canonicalImplementationStatus: 'NOT_STARTED';
  readonly canonicalRuntimeVerification: 'NOT_EXECUTED';
  readonly criticalAction: false;
  readonly designStatus: 'APPROVED_FOR_IMPLEMENTATION';
  readonly id: 'GOV-001';
  readonly mvp: true;
  readonly name: 'AI Governance';
  readonly purpose: 'Task/Prompt/Route/Evaluation/Releaseを表示';
  readonly roles: readonly ['PRODUCT_OWNER', 'MANAGING_EDITOR', 'SECURITY_AUDITOR'];
  readonly route: '/admin/governance/ai';
  readonly storyObjective: 'Task/Prompt/Route/Eval/Costを表示';
}

export interface AiGovernanceSourceBindingV2 {
  readonly code: string;
  readonly path: string;
  readonly scope: 'CANONICAL' | 'DEPENDENCIES' | 'HELPER';
  readonly sha256: string;
}

export interface AiGovernanceWorkspaceModelV2 {
  readonly accessibility: JsonObject;
  readonly authority: JsonObject;
  readonly document: JsonObject;
  readonly formalStatus: JsonObject;
  readonly releaseGuard: JsonObject;
  readonly route: JsonObject;
  readonly screen: AiGovernanceScreenV2;
  readonly sectionOrder: readonly AiGovernanceSectionIdV2[];
  readonly sections: readonly AiGovernanceSectionV2[];
  readonly sourceBindings: readonly AiGovernanceSourceBindingV2[];
}

export interface AiGovernanceWorkspaceInputV2 {
  readonly screenId: 'GOV-001';
}

export const AI_GOVERNANCE_V2_ERROR_CODES = createJsonValue([
  'AI_GOVERNANCE_V2_ARTIFACT_INVALID',
  'AI_GOVERNANCE_V2_CANDIDATE_INVALID',
  'AI_GOVERNANCE_V2_INPUT_INVALID',
  'AI_GOVERNANCE_V2_SCREEN_UNKNOWN',
]) as unknown as readonly [
  'AI_GOVERNANCE_V2_ARTIFACT_INVALID',
  'AI_GOVERNANCE_V2_CANDIDATE_INVALID',
  'AI_GOVERNANCE_V2_INPUT_INVALID',
  'AI_GOVERNANCE_V2_SCREEN_UNKNOWN',
];

export type AiGovernanceWorkspaceErrorCodeV2 = (typeof AI_GOVERNANCE_V2_ERROR_CODES)[number];

export class AiGovernanceWorkspaceErrorV2 extends TypeError {
  readonly code: AiGovernanceWorkspaceErrorCodeV2;

  constructor(code: AiGovernanceWorkspaceErrorCodeV2) {
    super(code);
    this.name = 'AiGovernanceWorkspaceErrorV2';
    this.code = code;
    Object.freeze(this);
  }
}

function reject(code: AiGovernanceWorkspaceErrorCodeV2): never {
  throw new AiGovernanceWorkspaceErrorV2(code);
}

function isJsonArray(value: JsonValue): value is readonly JsonValue[] {
  return Array.isArray(value);
}

function record(value: JsonValue | undefined): JsonObject {
  if (value === null || typeof value !== 'object' || isJsonArray(value)) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  return value;
}

function array(value: JsonValue | undefined): readonly JsonValue[] {
  if (value === undefined || !isJsonArray(value)) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  return value;
}

function exactKeys(value: JsonObject, expected: readonly string[]): void {
  const observed = Object.keys(value);
  if (
    observed.length !== expected.length ||
    observed.some((key, index) => key !== [...expected].sort()[index])
  ) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
}

function stringValue(value: JsonValue | undefined): string {
  if (typeof value !== 'string' || value.length === 0 || value !== value.trim()) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  return value;
}

function falseValue(value: JsonValue | undefined): false {
  if (value !== false) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  return false;
}

function status(value: JsonValue | undefined): AiGovernanceStatusV2 {
  const candidate = record(value);
  exactKeys(candidate, ['code', 'colorOnly', 'icon', 'text']);
  stringValue(candidate['code']);
  falseValue(candidate['colorOnly']);
  stringValue(candidate['icon']);
  stringValue(candidate['text']);
  return candidate as unknown as AiGovernanceStatusV2;
}

function canonicalJson(value: JsonValue): string {
  return JSON.stringify(value);
}

function validateNoRestrictedProjectionKeys(value: JsonValue): void {
  if (Array.isArray(value)) {
    for (const item of value) {
      validateNoRestrictedProjectionKeys(item);
    }
    return;
  }
  if (value === null || typeof value !== 'object') {
    return;
  }
  const forbidden = new Set([
    'credential',
    'jobArtifact',
    'personalData',
    'promptBody',
    'providerResponse',
    'rawPrompt',
    'rawSource',
    'reviewBody',
    'secret',
  ]);
  for (const [key, item] of Object.entries(value)) {
    if (forbidden.has(key)) {
      return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
    }
    validateNoRestrictedProjectionKeys(item);
  }
}

function validateTrustedFixture(value: JsonValue): AiGovernanceWorkspaceModelV2 {
  const candidate = record(value);
  exactKeys(candidate, [
    'accessibility',
    'authority',
    'document',
    'formalStatus',
    'releaseGuard',
    'route',
    'screen',
    'sectionOrder',
    'sections',
    'sourceBindings',
  ]);

  const document = record(candidate['document']);
  if (
    document['id'] !== 'RAOS-ST0709-AI-GOVERNANCE-WORKSPACE-002' ||
    document['version'] !== '2.0.0' ||
    document['storyId'] !== 'ST-0709' ||
    document['status'] !== 'LOCAL_IMPLEMENTATION_COMPLETE' ||
    document['authority'] !== 'NONE' ||
    document['environment'] !== 'LOCAL_RECORDED_ONLY' ||
    document['defaultEnabled'] !== false
  ) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }

  const screen = record(candidate['screen']);
  if (
    screen['id'] !== 'GOV-001' ||
    screen['name'] !== 'AI Governance' ||
    screen['route'] !== '/admin/governance/ai' ||
    screen['purpose'] !== 'Task/Prompt/Route/Evaluation/Releaseを表示' ||
    screen['storyObjective'] !== 'Task/Prompt/Route/Eval/Costを表示' ||
    screen['criticalAction'] !== false ||
    screen['canonicalImplementationStatus'] !== 'NOT_STARTED' ||
    screen['canonicalRuntimeVerification'] !== 'NOT_EXECUTED'
  ) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }

  const expectedOrder = [...AI_GOVERNANCE_V2_SECTION_IDS];
  const observedOrder = array(candidate['sectionOrder']);
  if (
    observedOrder.length !== expectedOrder.length ||
    observedOrder.some((item, index) => item !== expectedOrder[index])
  ) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }

  const expectedCounts = [12, 12, 5, 1, 1, 12];
  const sections = array(candidate['sections']);
  if (sections.length !== expectedOrder.length) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  for (const [index, item] of sections.entries()) {
    const section = record(item);
    if (
      section['id'] !== expectedOrder[index] ||
      section['mode'] !== 'READ_ONLY' ||
      section['recordCount'] !== expectedCounts[index] ||
      array(section['actions']).length !== 0
    ) {
      return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
    }
    const table = record(section['table']);
    stringValue(table['caption']);
    const rowHeaderKey = stringValue(table['rowHeaderKey']);
    const columns = array(table['columns']);
    const rows = array(table['rows']);
    if (rows.length !== expectedCounts[index] || columns.length === 0) {
      return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
    }
    const columnKeys = columns.map((raw) => {
      const column = record(raw);
      exactKeys(column, ['key', 'label', 'semanticRole']);
      if (column['semanticRole'] !== 'COLUMN_HEADER') {
        return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
      }
      stringValue(column['label']);
      return stringValue(column['key']);
    });
    if (!columnKeys.includes(rowHeaderKey)) {
      return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
    }
    for (const rowValue of rows) {
      const row = record(rowValue);
      stringValue(row[rowHeaderKey]);
    }
  }

  for (const row of array(record(record(sections[0])['table'])['rows'])) {
    status(record(row)['status']);
  }
  for (const row of array(record(record(sections[1])['table'])['rows'])) {
    const prompt = record(row);
    status(prompt['status']);
    falseValue(prompt['activationAuthorized']);
  }
  for (const row of array(record(record(sections[2])['table'])['rows'])) {
    const route = record(row);
    status(route['status']);
    falseValue(route['activationAuthorized']);
    falseValue(route['releaseAuthorized']);
  }
  const evaluation = record(array(record(record(sections[3])['table'])['rows'])[0]);
  if (
    evaluation['outcome'] !== 'REFUSED_INCOMPLETE_EVIDENCE' ||
    evaluation['authority'] !== 'NONE'
  ) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  status(evaluation['status']);
  const release = record(array(record(record(sections[4])['table'])['rows'])[0]);
  if (
    release['outcome'] !== 'REFUSED_INCOMPLETE_EVIDENCE' ||
    release['authority'] !== 'NONE' ||
    release['approvalAuthority'] !== 'HUMAN_ONLY' ||
    release['directActivation'] !== false
  ) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  status(release['status']);
  for (const authority of Object.values(record(release['operationalAuthority']))) {
    falseValue(authority);
  }
  for (const row of array(record(record(sections[5])['table'])['rows'])) {
    const cost = record(row);
    if (
      cost['observedActualCostJpy'] !== null ||
      cost['unknownTreatedAsZero'] !== false ||
      cost['od009Resolution'] !== 'UNRESOLVED'
    ) {
      return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
    }
    status(cost['observedCostStatus']);
  }

  const guard = record(candidate['releaseGuard']);
  if (
    guard['direct_activation'] !== false ||
    guard['action_count'] !== 0 ||
    guard['approval_required'] !== true ||
    guard['approval_authority'] !== 'HUMAN_ONLY'
  ) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  for (const [key, authority] of Object.entries(record(candidate['authority']))) {
    void key;
    falseValue(authority);
  }
  const route = record(candidate['route']);
  if (
    route['registration'] !== 'UNREGISTERED' ||
    route['navigation'] !== 'DISABLED' ||
    route['authentication'] !== 'NOT_EXECUTED' ||
    route['authorizationGranted'] !== false ||
    route['rendering'] !== 'NOT_EXECUTED'
  ) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  for (const executionStatus of Object.values(record(candidate['formalStatus']))) {
    if (executionStatus !== 'NOT_EXECUTED') {
      return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
    }
  }

  const bindings = array(candidate['sourceBindings']);
  if (bindings.length < 20) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  for (const item of bindings) {
    const binding = record(item);
    exactKeys(binding, ['code', 'path', 'scope', 'sha256']);
    stringValue(binding['code']);
    stringValue(binding['path']);
    if (!['CANONICAL', 'DEPENDENCIES', 'HELPER'].includes(stringValue(binding['scope']))) {
      return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
    }
    if (!/^[0-9a-f]{64}$/.test(stringValue(binding['sha256']))) {
      return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
    }
  }
  validateNoRestrictedProjectionKeys(candidate);
  return candidate as unknown as AiGovernanceWorkspaceModelV2;
}

function loadTrustedFixture(): AiGovernanceWorkspaceModelV2 {
  if (AI_GOVERNANCE_RECORDED_V2_SHA256 !== EXPECTED_RECORDED_FIXTURE_SHA256) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(AI_GOVERNANCE_RECORDED_V2_JSON) as unknown;
  } catch {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  let value: JsonValue;
  try {
    value = createJsonValue(parsed);
  } catch {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  if (canonicalJson(value) !== AI_GOVERNANCE_RECORDED_V2_JSON) {
    return reject('AI_GOVERNANCE_V2_ARTIFACT_INVALID');
  }
  return validateTrustedFixture(value);
}

export const AI_GOVERNANCE_RECORDED_FIXTURE_V2 = loadTrustedFixture();

export function validateAiGovernanceWorkspaceCandidateV2(
  candidate: unknown,
): AiGovernanceWorkspaceModelV2 {
  let value: JsonValue;
  try {
    value = createJsonValue(candidate);
  } catch {
    return reject('AI_GOVERNANCE_V2_CANDIDATE_INVALID');
  }
  if (canonicalJson(value) !== AI_GOVERNANCE_RECORDED_V2_JSON) {
    return reject('AI_GOVERNANCE_V2_CANDIDATE_INVALID');
  }
  return value as unknown as AiGovernanceWorkspaceModelV2;
}

function validateInput(input: AiGovernanceWorkspaceInputV2): void {
  let value: JsonValue;
  try {
    value = createJsonValue(input);
  } catch {
    return reject('AI_GOVERNANCE_V2_INPUT_INVALID');
  }
  if (value === null || typeof value !== 'object' || isJsonArray(value)) {
    return reject('AI_GOVERNANCE_V2_INPUT_INVALID');
  }
  const inputRecord = value as JsonObject;
  const keys = Object.keys(inputRecord);
  if (keys.length !== 1 || keys[0] !== 'screenId') {
    return reject('AI_GOVERNANCE_V2_INPUT_INVALID');
  }
  if (typeof inputRecord['screenId'] !== 'string') {
    return reject('AI_GOVERNANCE_V2_INPUT_INVALID');
  }
  if (inputRecord['screenId'] !== 'GOV-001') {
    return reject('AI_GOVERNANCE_V2_SCREEN_UNKNOWN');
  }
}

export function createAiGovernanceWorkspaceModelV2(
  input: AiGovernanceWorkspaceInputV2,
): AiGovernanceWorkspaceModelV2 {
  validateInput(input);
  return validateAiGovernanceWorkspaceCandidateV2(AI_GOVERNANCE_RECORDED_FIXTURE_V2);
}
