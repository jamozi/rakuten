import { createJsonValue } from './serializable.ts';

export const DATA_TABLE_STATES = [
  'EMPTY',
  'NOT_LOADED',
  'LOAD_FAILED',
  'FORBIDDEN',
  'ROWS',
] as const;

export type DataTableState = (typeof DATA_TABLE_STATES)[number];
export type DataTableColumnKind = 'text' | 'number' | 'status';
export type DataTableSortDirection = 'ASC' | 'DESC';
export type UnknownCellReason = 'NOT_AVAILABLE' | 'NOT_APPLICABLE' | 'NOT_REPORTED';

export type DataTableCellInput =
  | { readonly kind: 'text'; readonly text: string }
  | { readonly kind: 'number'; readonly value: number; readonly text: string }
  | {
      readonly kind: 'status';
      readonly color: string;
      readonly text: string;
      readonly icon: string;
    }
  | { readonly kind: 'unknown'; readonly reason: UnknownCellReason };

export interface DataTableColumnInput {
  readonly id: string;
  readonly header: string;
  readonly kind: DataTableColumnKind;
  readonly sortable: boolean;
}

export interface DataTableCellEntryInput {
  readonly columnId: string;
  readonly cell: DataTableCellInput;
}

export interface DataTableRowInput {
  readonly id: string;
  readonly cells: readonly DataTableCellEntryInput[];
}

export type DataTableFocusInput =
  | { readonly kind: 'TABLE' }
  | { readonly kind: 'COLUMN_HEADER'; readonly columnId: string }
  | { readonly kind: 'CELL'; readonly rowId: string; readonly columnId: string };

export interface DataTableInput {
  readonly tableId: unknown;
  readonly caption: unknown;
  readonly state: unknown;
  readonly columns: unknown;
  readonly rows: unknown;
  readonly sort: unknown;
  readonly pagination: unknown;
  readonly focus: unknown;
}

export interface DataTableModel {
  readonly componentId: 'UI-C007';
  readonly tableId: string;
  readonly caption: string;
  readonly state: {
    readonly code: DataTableState;
    readonly text: string;
    readonly icon: string;
  };
  readonly columns: readonly {
    readonly id: string;
    readonly headerId: string;
    readonly header: string;
    readonly kind: DataTableColumnKind;
    readonly sortable: boolean;
    readonly scope: 'col';
  }[];
  readonly rows: readonly {
    readonly id: string;
    readonly cells: readonly Record<string, unknown>[];
  }[];
  readonly sort: {
    readonly columnId: string;
    readonly direction: DataTableSortDirection;
  } | null;
  readonly pagination: {
    readonly page: number;
    readonly pageSize: number;
    readonly totalRows: number;
    readonly totalPages: number;
    readonly startIndex: number;
    readonly endIndex: number;
    readonly hasPrevious: boolean;
    readonly hasNext: boolean;
  };
  readonly focus: {
    readonly kind: DataTableFocusInput['kind'];
    readonly targetId: string;
  };
}

export const DATA_TABLE_ERROR_CODES = [
  'DATA_TABLE_INPUT_INVALID',
  'DATA_TABLE_CAPTION_INVALID',
  'DATA_TABLE_ID_INVALID',
  'DATA_TABLE_COLUMN_INVALID',
  'DATA_TABLE_DUPLICATE_COLUMN',
  'DATA_TABLE_ROW_INVALID',
  'DATA_TABLE_DUPLICATE_ROW',
  'DATA_TABLE_CELL_INVALID',
  'DATA_TABLE_SORT_INVALID',
  'DATA_TABLE_PAGINATION_INVALID',
  'DATA_TABLE_FOCUS_INVALID',
  'DATA_TABLE_STATE_ROWS_MISMATCH',
] as const;

export type DataTableErrorCode = (typeof DATA_TABLE_ERROR_CODES)[number];

export class DataTableError extends TypeError {
  readonly code: DataTableErrorCode;

  constructor(code: DataTableErrorCode) {
    super(code);
    this.name = 'DataTableError';
    this.code = code;
    Object.freeze(this);
  }
}

type NormalizedCell = DataTableCellInput;
type NormalizedRow = {
  readonly id: string;
  readonly originalIndex: number;
  readonly cells: ReadonlyMap<string, NormalizedCell>;
};

const STABLE_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const ICON_NAME = /^[a-z]+(?:-[a-z]+)*$/;
const COLOR = /^#[0-9A-F]{6}$/;
const MAX_PAGE_SIZE = 100;
const STATE_PRESENTATION: Readonly<
  Record<DataTableState, { readonly text: string; readonly icon: string }>
> = Object.freeze({
  EMPTY: { text: 'No rows', icon: 'table-empty' },
  NOT_LOADED: { text: 'Not loaded', icon: 'cloud-off' },
  LOAD_FAILED: { text: 'Load failed', icon: 'circle-alert' },
  FORBIDDEN: { text: 'Access forbidden', icon: 'lock-closed' },
  ROWS: { text: 'Rows available', icon: 'table-rows' },
});

function reject(code: DataTableErrorCode): never {
  throw new DataTableError(code);
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
    return reject('DATA_TABLE_ID_INVALID');
  }
  return value;
}

function visibleText(value: unknown, code: DataTableErrorCode): string {
  if (
    typeof value !== 'string' ||
    value.length < 1 ||
    value.length > 240 ||
    value !== value.trim()
  ) {
    return reject(code);
  }
  return value;
}

function normalizeColumn(value: unknown): DataTableColumnInput {
  if (
    !isPlainRecord(value) ||
    !hasExactKeys(value, ['id', 'header', 'kind', 'sortable']) ||
    typeof value['kind'] !== 'string' ||
    !['text', 'number', 'status'].includes(value['kind']) ||
    typeof value['sortable'] !== 'boolean'
  ) {
    return reject('DATA_TABLE_COLUMN_INVALID');
  }
  return {
    id: stableId(value['id']),
    header: visibleText(value['header'], 'DATA_TABLE_COLUMN_INVALID'),
    kind: value['kind'] as DataTableColumnKind,
    sortable: value['sortable'],
  };
}

function normalizeCell(value: unknown, columnKind: DataTableColumnKind): NormalizedCell {
  if (!isPlainRecord(value) || typeof value['kind'] !== 'string') {
    return reject('DATA_TABLE_CELL_INVALID');
  }
  switch (value['kind']) {
    case 'text':
      if (!hasExactKeys(value, ['kind', 'text']) || columnKind !== 'text') {
        return reject('DATA_TABLE_CELL_INVALID');
      }
      return { kind: 'text', text: visibleText(value['text'], 'DATA_TABLE_CELL_INVALID') };
    case 'number':
      if (
        !hasExactKeys(value, ['kind', 'text', 'value']) ||
        columnKind !== 'number' ||
        typeof value['value'] !== 'number' ||
        !Number.isFinite(value['value'])
      ) {
        return reject('DATA_TABLE_CELL_INVALID');
      }
      return {
        kind: 'number',
        value: Object.is(value['value'], -0) ? 0 : value['value'],
        text: visibleText(value['text'], 'DATA_TABLE_CELL_INVALID'),
      };
    case 'status':
      if (
        !hasExactKeys(value, ['color', 'icon', 'kind', 'text']) ||
        columnKind !== 'status' ||
        typeof value['color'] !== 'string' ||
        !COLOR.test(value['color']) ||
        typeof value['icon'] !== 'string' ||
        !ICON_NAME.test(value['icon'])
      ) {
        return reject('DATA_TABLE_CELL_INVALID');
      }
      return {
        kind: 'status',
        color: value['color'],
        text: visibleText(value['text'], 'DATA_TABLE_CELL_INVALID'),
        icon: value['icon'],
      };
    case 'unknown':
      if (
        !hasExactKeys(value, ['kind', 'reason']) ||
        typeof value['reason'] !== 'string' ||
        !['NOT_AVAILABLE', 'NOT_APPLICABLE', 'NOT_REPORTED'].includes(value['reason'])
      ) {
        return reject('DATA_TABLE_CELL_INVALID');
      }
      return { kind: 'unknown', reason: value['reason'] as UnknownCellReason };
    default:
      return reject('DATA_TABLE_CELL_INVALID');
  }
}

function normalizeRow(
  value: unknown,
  originalIndex: number,
  columns: readonly DataTableColumnInput[],
): NormalizedRow {
  if (
    !isPlainRecord(value) ||
    !hasExactKeys(value, ['cells', 'id']) ||
    !Array.isArray(value['cells'])
  ) {
    return reject('DATA_TABLE_ROW_INVALID');
  }
  const rowId = stableId(value['id']);
  const columnById = new Map(columns.map((column) => [column.id, column]));
  const cells = new Map<string, NormalizedCell>();
  for (const rawEntry of value['cells']) {
    if (!isPlainRecord(rawEntry) || !hasExactKeys(rawEntry, ['cell', 'columnId'])) {
      return reject('DATA_TABLE_CELL_INVALID');
    }
    const columnId = stableId(rawEntry['columnId']);
    const column = columnById.get(columnId);
    if (column === undefined || cells.has(columnId)) {
      return reject('DATA_TABLE_CELL_INVALID');
    }
    cells.set(columnId, normalizeCell(rawEntry['cell'], column.kind));
  }
  if (cells.size !== columns.length) {
    return reject('DATA_TABLE_CELL_INVALID');
  }
  return { id: rowId, originalIndex, cells };
}

function normalizeSort(
  value: unknown,
  columns: readonly DataTableColumnInput[],
): { readonly columnId: string; readonly direction: DataTableSortDirection } | null {
  if (value === null) {
    return null;
  }
  if (!isPlainRecord(value) || !hasExactKeys(value, ['columnId', 'direction'])) {
    return reject('DATA_TABLE_SORT_INVALID');
  }
  const columnId = stableId(value['columnId']);
  const column = columns.find((candidate) => candidate.id === columnId);
  if (
    column === undefined ||
    !column.sortable ||
    (value['direction'] !== 'ASC' && value['direction'] !== 'DESC')
  ) {
    return reject('DATA_TABLE_SORT_INVALID');
  }
  return { columnId, direction: value['direction'] };
}

function compareText(left: string, right: string): number {
  if (left === right) {
    return 0;
  }
  return left < right ? -1 : 1;
}

function compareCells(left: NormalizedCell, right: NormalizedCell): number {
  if (left.kind === 'unknown' && right.kind === 'unknown') {
    return 0;
  }
  if (left.kind === 'unknown') {
    return 1;
  }
  if (right.kind === 'unknown') {
    return -1;
  }
  if (left.kind === 'number' && right.kind === 'number') {
    return left.value === right.value ? 0 : left.value < right.value ? -1 : 1;
  }
  return compareText(left.text, right.text);
}

function sortedRows(
  rows: readonly NormalizedRow[],
  sort: { readonly columnId: string; readonly direction: DataTableSortDirection } | null,
): readonly NormalizedRow[] {
  if (sort === null) {
    return rows;
  }
  return [...rows].sort((left, right) => {
    const leftCell = left.cells.get(sort.columnId);
    const rightCell = right.cells.get(sort.columnId);
    if (leftCell === undefined || rightCell === undefined) {
      return left.originalIndex - right.originalIndex;
    }
    const compared = compareCells(leftCell, rightCell);
    if (compared === 0) {
      return left.originalIndex - right.originalIndex;
    }
    return sort.direction === 'ASC' ? compared : -compared;
  });
}

function normalizePagination(value: unknown): { readonly page: number; readonly pageSize: number } {
  if (!isPlainRecord(value) || !hasExactKeys(value, ['page', 'pageSize'])) {
    return reject('DATA_TABLE_PAGINATION_INVALID');
  }
  const page = value['page'];
  const pageSize = value['pageSize'];
  if (
    typeof page !== 'number' ||
    !Number.isSafeInteger(page) ||
    page < 1 ||
    typeof pageSize !== 'number' ||
    !Number.isSafeInteger(pageSize) ||
    pageSize < 1 ||
    pageSize > MAX_PAGE_SIZE
  ) {
    return reject('DATA_TABLE_PAGINATION_INVALID');
  }
  return { page, pageSize };
}

function normalizeFocus(value: unknown): DataTableFocusInput {
  if (!isPlainRecord(value) || typeof value['kind'] !== 'string') {
    return reject('DATA_TABLE_FOCUS_INVALID');
  }
  if (value['kind'] === 'TABLE' && hasExactKeys(value, ['kind'])) {
    return { kind: 'TABLE' };
  }
  if (value['kind'] === 'COLUMN_HEADER' && hasExactKeys(value, ['columnId', 'kind'])) {
    return { kind: 'COLUMN_HEADER', columnId: stableId(value['columnId']) };
  }
  if (value['kind'] === 'CELL' && hasExactKeys(value, ['columnId', 'kind', 'rowId'])) {
    return {
      kind: 'CELL',
      rowId: stableId(value['rowId']),
      columnId: stableId(value['columnId']),
    };
  }
  return reject('DATA_TABLE_FOCUS_INVALID');
}

export function createDataTableModel(input: DataTableInput): DataTableModel {
  if (
    !isPlainRecord(input) ||
    !hasExactKeys(input, [
      'caption',
      'columns',
      'focus',
      'pagination',
      'rows',
      'sort',
      'state',
      'tableId',
    ]) ||
    !Array.isArray(input.columns) ||
    !Array.isArray(input.rows) ||
    !DATA_TABLE_STATES.includes(input.state as DataTableState)
  ) {
    return reject('DATA_TABLE_INPUT_INVALID');
  }

  const tableId = stableId(input.tableId);
  const caption = visibleText(input.caption, 'DATA_TABLE_CAPTION_INVALID');
  const state = input.state as DataTableState;
  if (input.columns.length === 0) {
    return reject('DATA_TABLE_COLUMN_INVALID');
  }
  const columns = input.columns.map(normalizeColumn);
  const columnIds = new Set<string>();
  for (const column of columns) {
    if (columnIds.has(column.id)) {
      return reject('DATA_TABLE_DUPLICATE_COLUMN');
    }
    columnIds.add(column.id);
  }

  const rows = input.rows.map((row, index) => normalizeRow(row, index, columns));
  const rowIds = new Set<string>();
  for (const row of rows) {
    if (rowIds.has(row.id)) {
      return reject('DATA_TABLE_DUPLICATE_ROW');
    }
    rowIds.add(row.id);
  }
  if ((state === 'ROWS') !== rows.length > 0) {
    return reject('DATA_TABLE_STATE_ROWS_MISMATCH');
  }

  const sort = normalizeSort(input.sort, columns);
  if (state !== 'ROWS' && sort !== null) {
    return reject('DATA_TABLE_SORT_INVALID');
  }
  const paginationInput = normalizePagination(input.pagination);
  const totalRows = rows.length;
  const totalPages = totalRows === 0 ? 0 : Math.ceil(totalRows / paginationInput.pageSize);
  if (
    (totalPages === 0 && paginationInput.page !== 1) ||
    (totalPages > 0 && paginationInput.page > totalPages)
  ) {
    return reject('DATA_TABLE_PAGINATION_INVALID');
  }
  const startOffset = (paginationInput.page - 1) * paginationInput.pageSize;
  const visibleRows = sortedRows(rows, sort).slice(
    startOffset,
    startOffset + paginationInput.pageSize,
  );

  const focus = normalizeFocus(input.focus);
  let focusTargetId = tableId;
  if (focus.kind === 'COLUMN_HEADER') {
    if (!columnIds.has(focus.columnId)) {
      return reject('DATA_TABLE_FOCUS_INVALID');
    }
    focusTargetId = `${tableId}--column-${focus.columnId}`;
  } else if (focus.kind === 'CELL') {
    if (!columnIds.has(focus.columnId) || !visibleRows.some((row) => row.id === focus.rowId)) {
      return reject('DATA_TABLE_FOCUS_INVALID');
    }
    focusTargetId = `${tableId}--row-${focus.rowId}--column-${focus.columnId}`;
  }

  const outputColumns = columns.map((column) => ({
    ...column,
    headerId: `${tableId}--column-${column.id}`,
    scope: 'col',
  }));
  const outputRows = visibleRows.map((row) => ({
    id: row.id,
    cells: columns.map((column) => {
      const cell = row.cells.get(column.id);
      if (cell === undefined) {
        return reject('DATA_TABLE_CELL_INVALID');
      }
      const relationship = {
        columnId: column.id,
        cellId: `${tableId}--row-${row.id}--column-${column.id}`,
        headers: [`${tableId}--column-${column.id}`],
      };
      if (cell.kind === 'unknown') {
        return {
          ...relationship,
          kind: 'unknown',
          reason: cell.reason,
          text: 'Unknown',
          icon: 'circle-help',
        };
      }
      return { ...relationship, ...cell };
    }),
  }));
  const presentation = STATE_PRESENTATION[state];
  const startIndex = totalRows === 0 ? 0 : startOffset + 1;
  const endIndex = totalRows === 0 ? 0 : startOffset + visibleRows.length;

  return createJsonValue({
    componentId: 'UI-C007',
    tableId,
    caption,
    state: { code: state, ...presentation },
    columns: outputColumns,
    rows: outputRows,
    sort,
    pagination: {
      page: paginationInput.page,
      pageSize: paginationInput.pageSize,
      totalRows,
      totalPages,
      startIndex,
      endIndex,
      hasPrevious: paginationInput.page > 1,
      hasNext: totalPages > 0 && paginationInput.page < totalPages,
    },
    focus: { kind: focus.kind, targetId: focusTargetId },
  }) as unknown as DataTableModel;
}
