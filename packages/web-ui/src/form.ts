import { createJsonValue } from './serializable.ts';

export interface FormFieldMetadataInput<FieldId extends string = string> {
  readonly id: FieldId;
  readonly label: unknown;
  readonly instructions: unknown;
  readonly required: unknown;
  readonly error: unknown;
}

export interface FormMetadataInput<FieldId extends string = string> {
  readonly formId: unknown;
  readonly fields: readonly FormFieldMetadataInput<FieldId>[];
}

export interface FormFieldMetadata<FieldId extends string = string> {
  readonly fieldId: FieldId;
  readonly label: {
    readonly id: string;
    readonly text: string;
    readonly forFieldId: FieldId;
  };
  readonly instructions: { readonly id: string; readonly text: string } | null;
  readonly required: boolean;
  readonly error: {
    readonly id: string;
    readonly text: string;
    readonly describesFieldId: FieldId;
  } | null;
  readonly describedByIds: readonly string[];
}

export interface FormMetadata<FieldId extends string = string> {
  readonly bindings: readonly ['UI-C011', 'A11Y-012', 'A11Y-013'];
  readonly formId: string;
  readonly fields: readonly FormFieldMetadata<FieldId>[];
  readonly errorSummary: {
    readonly componentId: 'UI-C011';
    readonly present: boolean;
    readonly summaryId: string;
    readonly headingId: string;
    readonly heading: 'There is a problem';
    readonly entries: readonly {
      readonly fieldId: FieldId;
      readonly text: string;
      readonly linkTargetId: FieldId;
    }[];
    readonly nextFocusTargetId: string | null;
  };
}

export const FORM_ERROR_CODES = [
  'FORM_INPUT_INVALID',
  'FORM_ID_INVALID',
  'FORM_FIELD_INVALID',
  'FORM_DUPLICATE_FIELD_ID',
  'FORM_TEXT_INVALID',
] as const;

export type FormErrorCode = (typeof FORM_ERROR_CODES)[number];

export class FormMetadataError extends TypeError {
  readonly code: FormErrorCode;

  constructor(code: FormErrorCode) {
    super(code);
    this.name = 'FormMetadataError';
    this.code = code;
    Object.freeze(this);
  }
}

const STABLE_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;

function reject(code: FormErrorCode): never {
  throw new FormMetadataError(code);
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
    return reject('FORM_ID_INVALID');
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
    return reject('FORM_TEXT_INVALID');
  }
  return value;
}

function optionalText(value: unknown): string | null {
  return value === null ? null : visibleText(value);
}

export function createFormMetadata<FieldId extends string>(
  input: FormMetadataInput<FieldId>,
): FormMetadata<FieldId> {
  if (
    !isPlainRecord(input) ||
    !hasExactKeys(input, ['fields', 'formId']) ||
    !Array.isArray(input.fields) ||
    input.fields.length === 0
  ) {
    return reject('FORM_INPUT_INVALID');
  }
  const formId = stableId(input.formId);
  const seen = new Set<string>();
  const fields: FormFieldMetadata<FieldId>[] = [];

  for (const rawField of input.fields) {
    if (
      !isPlainRecord(rawField) ||
      !hasExactKeys(rawField, ['error', 'id', 'instructions', 'label', 'required']) ||
      typeof rawField['required'] !== 'boolean'
    ) {
      return reject('FORM_FIELD_INVALID');
    }
    const fieldId = stableId(rawField['id']) as FieldId;
    if (seen.has(fieldId)) {
      return reject('FORM_DUPLICATE_FIELD_ID');
    }
    seen.add(fieldId);
    const instructions = optionalText(rawField['instructions']);
    const error = optionalText(rawField['error']);
    const labelId = `${formId}--field-${fieldId}--label`;
    const instructionsId = `${formId}--field-${fieldId}--instructions`;
    const errorId = `${formId}--field-${fieldId}--error`;
    fields.push({
      fieldId,
      label: {
        id: labelId,
        text: visibleText(rawField['label']),
        forFieldId: fieldId,
      },
      instructions: instructions === null ? null : { id: instructionsId, text: instructions },
      required: rawField['required'],
      error: error === null ? null : { id: errorId, text: error, describesFieldId: fieldId },
      describedByIds: [
        ...(instructions === null ? [] : [instructionsId]),
        ...(error === null ? [] : [errorId]),
      ],
    });
  }

  const summaryId = `${formId}--error-summary`;
  const entries = fields
    .filter(
      (
        field,
      ): field is FormFieldMetadata<FieldId> & {
        readonly error: NonNullable<FormFieldMetadata<FieldId>['error']>;
      } => field.error !== null,
    )
    .map((field) => ({
      fieldId: field.fieldId,
      text: field.error.text,
      linkTargetId: field.fieldId,
    }));

  return createJsonValue({
    bindings: ['UI-C011', 'A11Y-012', 'A11Y-013'],
    formId,
    fields,
    errorSummary: {
      componentId: 'UI-C011',
      present: entries.length > 0,
      summaryId,
      headingId: `${summaryId}--heading`,
      heading: 'There is a problem',
      entries,
      nextFocusTargetId: entries.length > 0 ? summaryId : null,
    },
  }) as unknown as FormMetadata<FieldId>;
}
