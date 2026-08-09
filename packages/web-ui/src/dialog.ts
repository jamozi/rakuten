import { createJsonValue } from './serializable.ts';

export type DialogPhase = 'OPEN' | 'CANCELLED' | 'CONFIRMED';
export type DialogEvent =
  | { readonly type: 'TAB_FORWARD' }
  | { readonly type: 'TAB_REVERSE' }
  | { readonly type: 'ESCAPE' }
  | { readonly type: 'CANCEL' }
  | { readonly type: 'CONFIRM' };

export interface DialogActionInput {
  readonly actionId: unknown;
  readonly targetId: unknown;
  readonly impact: unknown;
  readonly reversible: unknown;
  readonly critical: unknown;
}

export interface DialogInput {
  readonly dialogId: unknown;
  readonly openerFocusId: unknown;
  readonly initialFocusId: unknown;
  readonly focusableIds: unknown;
  readonly action: unknown;
}

export interface ConfirmationIntent {
  readonly kind: 'CONFIRMATION_INTENT';
  readonly actionId: string;
  readonly targetId: string;
  readonly impact: string;
  readonly reversible: boolean;
  readonly availability: 'INTENT_ONLY' | 'BLOCKED_STEP_UP_UNAVAILABLE';
  readonly executionAuthorized: false;
  readonly effectPerformed: false;
}

export interface DialogState {
  readonly componentId: 'UI-C012';
  readonly dialogId: string;
  readonly phase: DialogPhase;
  readonly openerFocusId: string;
  readonly returnFocusTargetId: string;
  readonly initialFocusId: string;
  readonly focusableIds: readonly string[];
  readonly activeFocusId: string;
  readonly closedBy: 'ESCAPE' | 'CANCEL' | 'CONFIRM' | null;
  readonly action: {
    readonly actionId: string;
    readonly targetId: string;
    readonly impact: string;
    readonly reversible: boolean;
    readonly critical: boolean;
  };
  readonly stepUp: 'NOT_REQUIRED' | 'UNAVAILABLE';
}

export interface DialogTransition {
  readonly code:
    | 'FOCUS_MOVED'
    | 'CANCELLED'
    | 'CONFIRM_INTENT_CREATED'
    | 'BLOCKED_STEP_UP_UNAVAILABLE'
    | 'NO_OP_CLOSED';
  readonly state: DialogState;
  readonly intent: ConfirmationIntent | null;
  readonly effectPerformed: false;
}

export const DIALOG_ERROR_CODES = [
  'DIALOG_INPUT_INVALID',
  'DIALOG_ID_INVALID',
  'DIALOG_FOCUS_INVALID',
  'DIALOG_ACTION_INVALID',
  'DIALOG_EVENT_INVALID',
] as const;

export type DialogErrorCode = (typeof DIALOG_ERROR_CODES)[number];

export class DialogStateError extends TypeError {
  readonly code: DialogErrorCode;

  constructor(code: DialogErrorCode) {
    super(code);
    this.name = 'DialogStateError';
    this.code = code;
    Object.freeze(this);
  }
}

const STABLE_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;

function reject(code: DialogErrorCode): never {
  throw new DialogStateError(code);
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
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function stableId(value: unknown): string {
  if (typeof value !== 'string' || !STABLE_ID.test(value) || value.length > 80) {
    return reject('DIALOG_ID_INVALID');
  }
  return value;
}

function visibleText(value: unknown): string {
  if (
    typeof value !== 'string' ||
    value.length < 1 ||
    value.length > 500 ||
    value !== value.trim()
  ) {
    return reject('DIALOG_ACTION_INVALID');
  }
  return value;
}

function stateCopy(state: DialogState, changes: Partial<DialogState>): DialogState {
  return createJsonValue({ ...state, ...changes }) as unknown as DialogState;
}

function transition(
  code: DialogTransition['code'],
  state: DialogState,
  intent: ConfirmationIntent | null,
): DialogTransition {
  return createJsonValue({
    code,
    state,
    intent,
    effectPerformed: false,
  }) as unknown as DialogTransition;
}

export function createDialogState(input: DialogInput): DialogState {
  if (
    !isPlainRecord(input) ||
    !hasExactKeys(input, [
      'action',
      'dialogId',
      'focusableIds',
      'initialFocusId',
      'openerFocusId',
    ]) ||
    !Array.isArray(input.focusableIds) ||
    input.focusableIds.length === 0 ||
    !isPlainRecord(input.action) ||
    !hasExactKeys(input.action, ['actionId', 'critical', 'impact', 'reversible', 'targetId'])
  ) {
    return reject('DIALOG_INPUT_INVALID');
  }
  const dialogId = stableId(input.dialogId);
  const openerFocusId = stableId(input.openerFocusId);
  const initialFocusId = stableId(input.initialFocusId);
  const focusableIds = input.focusableIds.map(stableId);
  if (
    new Set(focusableIds).size !== focusableIds.length ||
    !focusableIds.includes(initialFocusId) ||
    focusableIds.includes(openerFocusId)
  ) {
    return reject('DIALOG_FOCUS_INVALID');
  }
  if (
    typeof input.action['critical'] !== 'boolean' ||
    typeof input.action['reversible'] !== 'boolean'
  ) {
    return reject('DIALOG_ACTION_INVALID');
  }
  const action = {
    actionId: stableId(input.action['actionId']),
    targetId: stableId(input.action['targetId']),
    impact: visibleText(input.action['impact']),
    reversible: input.action['reversible'],
    critical: input.action['critical'],
  };
  return createJsonValue({
    componentId: 'UI-C012',
    dialogId,
    phase: 'OPEN',
    openerFocusId,
    returnFocusTargetId: openerFocusId,
    initialFocusId,
    focusableIds,
    activeFocusId: initialFocusId,
    closedBy: null,
    action,
    stepUp: action.critical ? 'UNAVAILABLE' : 'NOT_REQUIRED',
  }) as unknown as DialogState;
}

export function transitionDialog(state: DialogState, event: DialogEvent): DialogTransition {
  if (
    !isPlainRecord(event) ||
    !hasExactKeys(event, ['type']) ||
    typeof event.type !== 'string' ||
    !['TAB_FORWARD', 'TAB_REVERSE', 'ESCAPE', 'CANCEL', 'CONFIRM'].includes(event.type)
  ) {
    return reject('DIALOG_EVENT_INVALID');
  }
  if (state.phase !== 'OPEN') {
    return transition('NO_OP_CLOSED', state, null);
  }

  if (event.type === 'TAB_FORWARD' || event.type === 'TAB_REVERSE') {
    const current = state.focusableIds.indexOf(state.activeFocusId);
    if (current < 0) {
      return reject('DIALOG_FOCUS_INVALID');
    }
    const delta = event.type === 'TAB_FORWARD' ? 1 : -1;
    const next = (current + delta + state.focusableIds.length) % state.focusableIds.length;
    const activeFocusId = state.focusableIds[next];
    if (activeFocusId === undefined) {
      return reject('DIALOG_FOCUS_INVALID');
    }
    return transition('FOCUS_MOVED', stateCopy(state, { activeFocusId }), null);
  }

  if (event.type === 'ESCAPE' || event.type === 'CANCEL') {
    return transition(
      'CANCELLED',
      stateCopy(state, {
        phase: 'CANCELLED',
        activeFocusId: state.returnFocusTargetId,
        closedBy: event.type,
      }),
      null,
    );
  }

  const blocked = state.action.critical;
  const intent = createJsonValue({
    kind: 'CONFIRMATION_INTENT',
    actionId: state.action.actionId,
    targetId: state.action.targetId,
    impact: state.action.impact,
    reversible: state.action.reversible,
    availability: blocked ? 'BLOCKED_STEP_UP_UNAVAILABLE' : 'INTENT_ONLY',
    executionAuthorized: false,
    effectPerformed: false,
  }) as unknown as ConfirmationIntent;
  if (blocked) {
    return transition('BLOCKED_STEP_UP_UNAVAILABLE', state, intent);
  }
  return transition(
    'CONFIRM_INTENT_CREATED',
    stateCopy(state, {
      phase: 'CONFIRMED',
      activeFocusId: state.returnFocusTargetId,
      closedBy: 'CONFIRM',
    }),
    intent,
  );
}
