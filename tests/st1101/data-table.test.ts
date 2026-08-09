import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  DataTableError,
  createDataTableModel,
  type DataTableInput,
} from '../../packages/web-ui/src/data-table.ts';

const columns = [
  { id: 'name', header: 'Name', kind: 'text', sortable: true },
  { id: 'score', header: 'Score', kind: 'number', sortable: true },
  { id: 'state', header: 'State', kind: 'status', sortable: false },
] as const;

function row(id: string, name: string, score: number | null) {
  return {
    id,
    cells: [
      { columnId: 'name', cell: { kind: 'text', text: name } },
      {
        columnId: 'score',
        cell:
          score === null
            ? { kind: 'unknown', reason: 'NOT_REPORTED' }
            : { kind: 'number', value: score, text: String(score) },
      },
      {
        columnId: 'state',
        cell: { kind: 'status', color: '#19743B', text: 'Ready', icon: 'circle-check' },
      },
    ],
  } as const;
}

const rows = [
  row('row-one', 'Alpha', 2),
  row('row-two', 'Beta', 1),
  row('row-three', 'Gamma', 1),
  row('row-four', 'Delta', null),
];

function input(overrides: Partial<DataTableInput> = {}): DataTableInput {
  return {
    tableId: 'candidate-table',
    caption: 'Candidate results',
    state: 'ROWS',
    columns,
    rows,
    sort: { columnId: 'score', direction: 'ASC' },
    pagination: { page: 1, pageSize: 3 },
    focus: { kind: 'CELL', rowId: 'row-two', columnId: 'score' },
    ...overrides,
  };
}

describe('UI-C007 DataTable model', () => {
  it('uses stable allowlisted sorting, bounded pagination, and explicit focus', () => {
    const model = createDataTableModel(input());
    assert.deepEqual(
      model.rows.map((candidate) => candidate.id),
      ['row-two', 'row-three', 'row-one'],
    );
    assert.deepEqual(model.pagination, {
      page: 1,
      pageSize: 3,
      totalRows: 4,
      totalPages: 2,
      startIndex: 1,
      endIndex: 3,
      hasPrevious: false,
      hasNext: true,
    });
    assert.deepEqual(model.focus, {
      kind: 'CELL',
      targetId: 'candidate-table--row-row-two--column-score',
    });
    assert.deepEqual(JSON.parse(JSON.stringify(model)), model);
    assert.ok(Object.isFrozen(model));
  });

  it('preserves caption, col scope, and cell-to-header relationships', () => {
    const model = createDataTableModel(input());
    assert.equal(model.caption, 'Candidate results');
    for (const column of model.columns) {
      assert.equal(column.scope, 'col');
      for (const record of model.rows) {
        const cell = record.cells.find((candidate) => candidate['columnId'] === column.id);
        assert.deepEqual(cell?.['headers'], [column.headerId]);
      }
    }
    const status = model.rows[0]?.cells.find((cell) => cell['kind'] === 'status');
    assert.deepEqual(
      { color: status?.['color'], text: status?.['text'], icon: status?.['icon'] },
      { color: '#19743B', text: 'Ready', icon: 'circle-check' },
    );
  });

  it('keeps unknowns explicit and paginates them without coercion', () => {
    const model = createDataTableModel(
      input({
        pagination: { page: 2, pageSize: 3 },
        focus: { kind: 'CELL', rowId: 'row-four', columnId: 'score' },
      }),
    );
    const unknown = model.rows[0]?.cells.find((cell) => cell['columnId'] === 'score');
    assert.equal(unknown?.['kind'], 'unknown');
    assert.equal(unknown?.['reason'], 'NOT_REPORTED');
    assert.equal(unknown?.['text'], 'Unknown');
    assert.equal(unknown?.['icon'], 'circle-help');
  });

  it('distinguishes every non-row state', () => {
    for (const state of ['EMPTY', 'NOT_LOADED', 'LOAD_FAILED', 'FORBIDDEN'] as const) {
      const model = createDataTableModel(
        input({
          state,
          rows: [],
          sort: null,
          pagination: { page: 1, pageSize: 25 },
          focus: { kind: 'TABLE' },
        }),
      );
      assert.equal(model.state.code, state);
      assert.notEqual(model.state.text, 'Rows available');
      assert.deepEqual(model.rows, []);
      assert.equal(model.pagination.totalRows, 0);
    }
  });

  it('rejects duplicate IDs and incomplete or arbitrary cell records', () => {
    assert.throws(
      () => createDataTableModel(input({ columns: [columns[0], columns[0]] })),
      (error) => error instanceof DataTableError && error.code === 'DATA_TABLE_DUPLICATE_COLUMN',
    );
    assert.throws(
      () => createDataTableModel(input({ rows: [rows[0], rows[0]] })),
      (error) => error instanceof DataTableError && error.code === 'DATA_TABLE_DUPLICATE_ROW',
    );
    assert.throws(
      () =>
        createDataTableModel(
          input({
            rows: [
              {
                id: 'bad-row',
                cells: [{ columnId: 'name', cell: { kind: 'text', text: 'Only one' } }],
              },
            ],
          }),
        ),
      (error) => error instanceof DataTableError && error.code === 'DATA_TABLE_CELL_INVALID',
    );
    assert.throws(
      () =>
        createDataTableModel(
          input({
            rows: [
              {
                id: 'bad-row',
                cells: [
                  { columnId: 'name', cell: { kind: 'text', text: 'Bad', renderCell: () => 'x' } },
                  { columnId: 'score', cell: { kind: 'number', value: 1, text: '1' } },
                  {
                    columnId: 'state',
                    cell: { kind: 'status', color: '#19743B', text: 'Ready', icon: 'circle-check' },
                  },
                ],
              },
            ],
          }),
        ),
      (error) => error instanceof DataTableError && error.code === 'DATA_TABLE_CELL_INVALID',
    );
  });

  it('rejects unallowlisted sort, unbounded pages, off-page focus, and empty captions', () => {
    assert.throws(
      () => createDataTableModel(input({ sort: { columnId: 'state', direction: 'ASC' } })),
      (error) => error instanceof DataTableError && error.code === 'DATA_TABLE_SORT_INVALID',
    );
    assert.throws(
      () => createDataTableModel(input({ pagination: { page: 1, pageSize: 101 } })),
      (error) => error instanceof DataTableError && error.code === 'DATA_TABLE_PAGINATION_INVALID',
    );
    assert.throws(
      () =>
        createDataTableModel(
          input({ focus: { kind: 'CELL', rowId: 'row-four', columnId: 'score' } }),
        ),
      (error) => error instanceof DataTableError && error.code === 'DATA_TABLE_FOCUS_INVALID',
    );
    assert.throws(
      () => createDataTableModel(input({ caption: '' })),
      (error) => error instanceof DataTableError && error.code === 'DATA_TABLE_CAPTION_INVALID',
    );
  });
});
