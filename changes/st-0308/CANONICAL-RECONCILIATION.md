# ST-0308 canonical reconciliation

Status: `MATERIAL_CONFLICT_REQUIRES_REAPPROVAL`

Authority: `INFORMATIONAL_RECONCILIATION_EVIDENCE_ONLY`

Observed at: `2026-08-05T02:20:56Z`

This record compares the user-approved public ST-0308 design advisory with the
current repository bytes. It is not a `DESIGN_HANDOFF_V1`, does not set
`open_decisions: []`, and must not be passed to `implementation_worker` as
implementation authority.

## Approval and advisory identity

- Public share:
  `https://chatgpt.com/share/6a729b32-7e0c-83ee-88a9-f36973413690`
- Normalized advisory SHA-256:
  `464e6be81e27adfe45143b089219dfcde66f6887288e6a97c73686246d029af8`
- Normalized one-line user approval statement SHA-256:
  `5d523223d929e391bb0fc4ffe17e7b442588e5435e539001be1e600e52645e6d`
- The user approval is sufficient only if canonical reconciliation introduces
  no substantive change to the approved advisory.
- The advisory requires a mismatch to reopen the affected decision rather than
  allowing Codex to choose a preferred interpretation.

## Reconciled repository inputs

| Input | SHA-256 | Reconciliation role |
|---|---|---|
| `docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md` | `540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a` | canonical precedence |
| `docs/canonical/01_integration/RAOS_07_canonical_contract_overlay_v1.0.yaml` | `f9080e1744096b743b2ada2261d2a023cebf310a08cf3a9fc2d14a53ac56cf3e` | accepted overlay ordering |
| `docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml` | `4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d` | approved ST-0308 Story |
| `docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml` | `c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8` | security controls |
| `docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml` | `7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b` | test-suite authority |
| `changes/st-0105/README.md` | `15adf4e461592453f78a363ccba411c861f476aeaf58444039c6eaff12ade8de` | generated-binding ownership boundary |
| `changes/st-0303/contracts/iam-ops-schema.v1.yaml` | `af80127539a9c2c27fb0c63b7ef09c477380f90e94fedc408c5cd9a83036271b` | current IAM/OPS physical candidate |
| `changes/st-0303/generated/iam-ops-catalog.v1.json` | `0cab8decf1a9a874248ef16a5b1bfd01c19d1babbf45bb0f73eb42b89913720a` | current IAM/OPS exact catalog |
| `changes/st-0304/contracts/domain-schema.v1.yaml` | `8030f28f59124686c2fb975b507f66e70640b529ff5769666f88202628e19122` | declared predecessor physical candidate |
| `changes/st-0304/generated/domain-catalog.v1.json` | `41d0c9c4ba94aaf65587687a31bbab1caa05a8fed1d323d99991363013258208` | current six-schema exact catalog |
| `changes/st-0306/contracts/database-roles-grants.v1.yaml` | `1155942168373361579bd157b19be0d7babc7c260eb3389df21688eb455a567b` | candidate role evidence only |

The ST-0303 and ST-0304 artifacts remain local implementation candidates.
Their local bytes and results are not formal TST, staging, production, or
canonical-apply evidence.

## Decision reconciliation

| Decision | Result | Finding |
|---|---|---|
| `ST0308-D1` | `FAIL_MATERIAL` | The advisory approves an expected 91-table cut. The current selected-schema predecessor catalogs contain 103 tables: 17 from ST-0303 and 86 from ST-0304. |
| `ST0308-D2` | `FAIL_MATERIAL` | Eight approved Repository targets have no current table, twenty current overlay tables have no exact approved Repository ownership/signatures, and the exact optimistic-version contract conflicts with two named mutable roots. |
| `ST0308-D3` | `FAIL_MATERIAL` | A 91-table generated ORM manifest cannot satisfy two-way parity against the current 103-table predecessor catalogs; choosing either inventory changes the approved generator contract. |
| `ST0308-D4` | `PASS` | The framework-neutral transaction boundary, internal synchronous Session, single outer commit owner, no savepoints, and READ COMMITTED assumptions do not conflict with canonical boundaries. |
| `ST0308-D5` | `FAIL_INCOMPLETE` | The coordination and ST-1404 boundary reconcile, but the advisory leaves expired-idempotency replacement as “remove or replace” and does not select one behavior permitted by the current physical contract. |
| `ST0308-D6` | `PASS_CONDITIONAL` | The eight candidate group-role names match ST-0306 exactly. ST-0306 remains evidence rather than an ST-0308 dependency, and ST-0308 receives only a prevalidated provider. |

## Exact D1 inventory delta

The advisory inventory is 91 tables:

- `ops`: 16
- `iam`: 9
- baseline `portfolio` through `policy`: 66

The current predecessor inventory is 103 tables:

- ST-0303 `ops` and `iam`: 17
- ST-0304 `portfolio` through `policy`: 86

Tables present in the advisory but absent from the current physical catalogs:

```text
ops.audit_export
ops.alert
ops.incident
ops.incident_event
ops.kill_switch
ops.kill_switch_change
ops.retention_policy
ops.release
```

Tables present in the current physical catalogs but absent from the advisory:

```text
evidence.first_hand_experience_asset
evidence.first_hand_experience_record
editorial.article_disclosure_context
editorial.article_methodology_binding
editorial.article_template_version
editorial.article_type_version
editorial.content_schema_version
editorial.editorial_methodology_version
editorial.media_asset
editorial.seo_metadata_version
editorial.structured_data_manifest
ai.evaluation_case
ai.evaluation_case_result
ai.evaluation_dataset_version
ai.evaluation_run
ai.evaluation_suite
ai.human_evaluation
ai.judge_calibration
ai.release_approval
ai.release_decision
```

The current catalog also contains the read-only
`catalog.v_safe_offer_current` view. Treating the 12-table net increase as a
mechanical count correction would hide the eight removals and twenty additions.

## Exact D2/D3 conflicts

- The advisory declares `Finding` and `Waiver` mutable roots using the common
  `save(..., expected_version=...)` form and requires every mutable aggregate
  to start with and atomically increment `lock_version`.
- The current `policy.finding` and `policy.waiver` tables contain no
  `lock_version` column. ST-0308 is not authorized to alter their schema.
- The twenty current-only tables require an explicit decision about whether
  each is aggregate-owned metadata only, an existing aggregate child, a
  read-only Port, an append-only Port, or a new mutable Repository root.
- The eight advisory-only OPS protocols cannot have a SQLAlchemy row model or
  working database adapter without a separately authorized schema Story.
- The D3 two-way drift rule rejects both an approved model missing a current
  table and a model for a table absent from the approved physical contract.

## Minimum authority required to resume

A revised, separately approved `DESIGN_HANDOFF_V1` must resolve all of the
following without schema, migration, role, grant, RLS, or runtime expansion:

1. Select and hash-pin the exact physical inventory: the advisory 91-table cut,
   the current 103-table predecessor cut, or another explicitly enumerated cut.
2. Give exact Repository ownership and Port treatment for every selected table,
   including the eight missing OPS tables and twenty current-only overlay tables.
3. Reconcile `Finding` and `Waiver` mutation semantics with their lack of
   `lock_version`, or remove them from the common versioned-save contract.
4. Select the exact authoritative generator inputs and the table/view parity
   behavior.
5. Select the one expired-idempotency replacement operation that ST-0308 must
   implement.
6. Preserve D4 and D6 as reconciled above, preserve the strict ST-1404 boundary,
   and keep ST-0306 as candidate evidence rather than a dependency.

Until that artifact is approved with every mandatory field and
`open_decisions: []`, implementation remains stopped at the design boundary.
