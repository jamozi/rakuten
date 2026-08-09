import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  DialogStateError,
  createDialogState,
  transitionDialog,
} from '../../packages/web-ui/src/dialog.ts';
import { FormMetadataError, createFormMetadata } from '../../packages/web-ui/src/form.ts';

describe('UI-C011/A11Y-012/A11Y-013 form metadata', () => {
  it('binds labels, instructions, required state, errors, summary links, and next focus', () => {
    const model = createFormMetadata({
      formId: 'article-form',
      fields: [
        {
          id: 'title',
          label: 'Title',
          instructions: 'Use a descriptive title',
          required: true,
          error: 'Title is required',
        },
        {
          id: 'summary',
          label: 'Summary',
          instructions: null,
          required: false,
          error: null,
        },
      ],
    });

    assert.deepEqual(model.bindings, ['UI-C011', 'A11Y-012', 'A11Y-013']);
    const title = model.fields[0];
    assert.equal(title?.label.forFieldId, 'title');
    assert.deepEqual(title?.describedByIds, [
      'article-form--field-title--instructions',
      'article-form--field-title--error',
    ]);
    assert.equal(title?.required, true);
    assert.deepEqual(model.errorSummary.entries, [
      { fieldId: 'title', text: 'Title is required', linkTargetId: 'title' },
    ]);
    assert.equal(model.errorSummary.nextFocusTargetId, 'article-form--error-summary');
    assert.deepEqual(JSON.parse(JSON.stringify(model)), model);
    assert.doesNotMatch(JSON.stringify(model), /submittedValue|fieldValue|transport|callback/i);
  });

  it('omits summary focus when there are no errors and rejects duplicates/extras', () => {
    const model = createFormMetadata({
      formId: 'clean-form',
      fields: [{ id: 'name', label: 'Name', instructions: null, required: true, error: null }],
    });
    assert.equal(model.errorSummary.present, false);
    assert.equal(model.errorSummary.nextFocusTargetId, null);

    assert.throws(
      () =>
        createFormMetadata({
          formId: 'bad-form',
          fields: [
            { id: 'name', label: 'One', instructions: null, required: true, error: null },
            { id: 'name', label: 'Two', instructions: null, required: false, error: null },
          ],
        }),
      (error) => error instanceof FormMetadataError && error.code === 'FORM_DUPLICATE_FIELD_ID',
    );
    assert.throws(
      () =>
        createFormMetadata({
          formId: 'bad-form',
          fields: [
            {
              id: 'name',
              label: 'Name',
              instructions: null,
              required: true,
              error: null,
              value: 'must-not-be-accepted',
            },
          ],
        }),
      (error) => error instanceof FormMetadataError && error.code === 'FORM_FIELD_INVALID',
    );
  });
});

function dialog(critical = false) {
  return createDialogState({
    dialogId: 'confirm-dialog',
    openerFocusId: 'open-dialog',
    initialFocusId: 'cancel-action',
    focusableIds: ['cancel-action', 'confirm-action', 'details-link'],
    action: {
      actionId: 'archive-draft',
      targetId: 'draft-one',
      impact: 'Archive the selected draft',
      reversible: true,
      critical,
    },
  });
}

describe('UI-C012 dialog state machine', () => {
  it('starts at explicit initial focus and wraps forward and reverse Tab', () => {
    const initial = dialog();
    assert.equal(initial.activeFocusId, 'cancel-action');
    const reverse = transitionDialog(initial, { type: 'TAB_REVERSE' });
    assert.equal(reverse.code, 'FOCUS_MOVED');
    assert.equal(reverse.state.activeFocusId, 'details-link');
    const forwardWrap = transitionDialog(reverse.state, { type: 'TAB_FORWARD' });
    assert.equal(forwardWrap.state.activeFocusId, 'cancel-action');
    assert.equal(forwardWrap.effectPerformed, false);
  });

  it('cancels on Escape and returns focus to the opener', () => {
    const escaped = transitionDialog(dialog(), { type: 'ESCAPE' });
    assert.equal(escaped.code, 'CANCELLED');
    assert.equal(escaped.state.phase, 'CANCELLED');
    assert.equal(escaped.state.closedBy, 'ESCAPE');
    assert.equal(escaped.state.activeFocusId, 'open-dialog');
    assert.equal(escaped.state.returnFocusTargetId, 'open-dialog');
    assert.equal(transitionDialog(escaped.state, { type: 'CONFIRM' }).code, 'NO_OP_CLOSED');
  });

  it('creates a serializable non-authorizing intent and performs no effect', () => {
    const confirmed = transitionDialog(dialog(), { type: 'CONFIRM' });
    assert.equal(confirmed.code, 'CONFIRM_INTENT_CREATED');
    assert.equal(confirmed.state.phase, 'CONFIRMED');
    assert.equal(confirmed.state.activeFocusId, 'open-dialog');
    assert.deepEqual(confirmed.intent, {
      kind: 'CONFIRMATION_INTENT',
      actionId: 'archive-draft',
      targetId: 'draft-one',
      impact: 'Archive the selected draft',
      reversible: true,
      availability: 'INTENT_ONLY',
      executionAuthorized: false,
      effectPerformed: false,
    });
    assert.equal(confirmed.effectPerformed, false);
    assert.deepEqual(JSON.parse(JSON.stringify(confirmed)), confirmed);
  });

  it('blocks every critical confirmation when step-up is unavailable', () => {
    const initial = dialog(true);
    assert.equal(initial.stepUp, 'UNAVAILABLE');
    const blocked = transitionDialog(initial, { type: 'CONFIRM' });
    assert.equal(blocked.code, 'BLOCKED_STEP_UP_UNAVAILABLE');
    assert.equal(blocked.state.phase, 'OPEN');
    assert.equal(blocked.intent?.availability, 'BLOCKED_STEP_UP_UNAVAILABLE');
    assert.equal(blocked.intent?.executionAuthorized, false);
    assert.equal(blocked.effectPerformed, false);
    assert.doesNotMatch(JSON.stringify(blocked), /UI-C013/);
  });

  it('rejects duplicate focus targets, missing initial focus, and callback fields', () => {
    assert.throws(
      () =>
        createDialogState({
          dialogId: 'bad-dialog',
          openerFocusId: 'open-dialog',
          initialFocusId: 'missing-action',
          focusableIds: ['cancel-action', 'cancel-action'],
          action: {
            actionId: 'archive',
            targetId: 'draft-one',
            impact: 'Archive draft',
            reversible: true,
            critical: false,
          },
        }),
      (error) => error instanceof DialogStateError && error.code === 'DIALOG_FOCUS_INVALID',
    );
    assert.throws(
      () =>
        createDialogState({
          dialogId: 'bad-dialog',
          openerFocusId: 'open-dialog',
          initialFocusId: 'cancel-action',
          focusableIds: ['cancel-action'],
          action: {
            actionId: 'archive',
            targetId: 'draft-one',
            impact: 'Archive draft',
            reversible: true,
            critical: false,
            execute: () => undefined,
          },
        }),
      (error) => error instanceof DialogStateError && error.code === 'DIALOG_INPUT_INVALID',
    );
  });
});
