# ST-0308 handoff preflight

scripts/validate_st0308_design_handoff.py is a deterministic, read-only
AUTOMATED PREFLIGHT for a proposed DESIGN_HANDOFF_V1. It proves bounded
representation facts only:

- safe single-document UTF-8 YAML within the reviewed 8 MiB handoff limit;
  YAML depth 64 and node 100000 budgets are enforced by the parser/composer
  before Python containers are constructed, then checked again after
  construction. The node budget is global to the complete input, and a second
  document is rejected before its node graph is composed;
- the eleven repository-mandated top-level fields, ST-0308 identity,
  dependencies, required suites, and open_decisions: [];
- exact hash-pinned current V3 request, reconciliation, and readiness
  references plus the complete V2 archive closure; historical V2 request and
  reconciliation pins are trusted bundle provenance only, not candidate-
  required current design inputs;
- the approved-input archive member as
  archive_path/archive_sha256/member_path/member_sha256, including regular
  member, traversal, secret-path, and hash binding; and
- the V2 manifest's approved source_path and owner-approval statement digest
  against the declarative contract, plus the 5,679,757-byte derived regular
  member total under the reviewed 6 MiB cumulative limit; and
- the independently reconstructed 103-table, one-view inventory, the exact
  27-relation `lock_version` set, and the exact 24-relation physical
  `STATE_CAS_WITHOUT_LOCK_VERSION` set. The validator proves the state-CAS set
  exists in the physical inventory and is disjoint from the derived
  `lock_version` set before comparing candidate equality.

Repository paths are descriptor-safe and hash-pinned. An archive member path is
used only as a path inside the already verified in-memory V2 archive; it is
never interpreted as a repository path. The validator does not unpack, write,
execute candidate content, access the network, or inspect secrets.

## CLI

    python3 scripts/validate_st0308_design_handoff.py \
      --handoff PATH \
      --expected-sha256 LOWERCASE_64_HEX \
      [--repository-root PATH]

The command emits compact, sorted-key JSON to stdout only. Exit code 0 is
PASS_AUTOMATED_PREFLIGHT_ONLY; it is not approval or implementation authority.
Exit code 1 is candidate validation failure. Exit code 2 is usage or
trusted-environment/input-contract failure. For oversized input, the report
binds the bounded bytes actually read with candidate_sha256_complete: false.

Every report contains:

    implementation_authority: NOT_GRANTED
    exact_byte_owner_approval_required: true
    manual_canonical_reconciliation_required: true
    semantic_validation: MANUAL_REQUIRED

Exact-byte repository-owner approval and a fresh, conflict-free manual
canonical reconciliation remain mandatory after an automated success.

The optional `authority` and `approval` sections are mechanically bounded only
at the `DESIGN_HANDOFF_V1` payload root after case/separator normalization.
Each normalized root section must be a mapping or null; duplicate normalized
sections such as `approval` and `App-roval` fail. The contract supplies a finite
57-pattern grammar whose closure contains exactly 4893 generated aliases plus
four explicit irregular aliases, 4897 total, under
`max_generated_aliases: 8192` and an exact expected count. It covers all eleven
bounded base forms and their applicable status/by/at/timestamp suffix families,
including compound subjects and collision-safe reversed predicate-subject
forms. Every compiled alias is one rule binding a canonical field and its
`false_allowed` bit. The closure covers snake, kebab, space,
repeated-separator, camel, Pascal, uppercase, and concatenated surfaces.

The validator checks root claims and recursively traverses mappings/lists only
inside normalized `Authority`/`Approval` root boundary sections. It never
recurses through ordinary design sections such as `decision`, `approved_scope`,
`approved_story`, or `source_design_refs`, and it never scans prose values
lexically. Every recognized true or grant-like value fails; false is accepted
only by the compiled unsuffixed `is` or approved-result denial rule, while
status, approver, and time forms remain false-invalid. Proposal/pending/
blocked/not-granted/not-executed/null remain allowed only for their
contract-bound canonical fields.

## Manual boundary

The preflight does not validate the meaning of D2/D4/D5/D6. UoW protocol
surfaces and transaction lifecycle, shared infrastructure ownership,
idempotency claim/completion behavior, aggregate-version and event rules,
state-CAS predicates, Domain/value/mapper definitions, and the D6
prevalidated-provider identity boundary are reported as MANUAL_REQUIRED.
Weak lexical evidence, negative wording, or a prose stub cannot turn those
topics into an automated pass or rejection.

No-write coverage copies the exact trusted closure into a disposable
repository root, adds an unrelated sentinel, and snapshots the complete
temporary tree (path, type, mode, size, mtime, and hash) before and after
validation. Symlink and FIFO probes also run only in disposable roots.

## Verification

Run the isolated Story suite with the pinned offline toolchain:

    env -u VIRTUAL_ENV PYTHONDONTWRITEBYTECODE=1 /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv --config-file uv.toml run --locked --offline --no-cache --no-sync --no-env-file --no-python-downloads pytest -p no:cacheprovider -q tests/st0308

Run Ruff on the owned Python files:

    env -u VIRTUAL_ENV PYTHONDONTWRITEBYTECODE=1 /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv --config-file uv.toml run --locked --offline --no-cache --no-sync --no-env-file --no-python-downloads ruff check scripts/validate_st0308_design_handoff.py tests/st0308/conftest.py tests/st0308/test_handoff_contract.py tests/st0308/test_handoff_negative_cases.py tests/st0308/test_handoff_reconciliation.py
    env -u VIRTUAL_ENV PYTHONDONTWRITEBYTECODE=1 /home/minami/.local/share/raos-toolchains/uv/0.12.1/uv --config-file uv.toml run --locked --offline --no-cache --no-sync --no-env-file --no-python-downloads ruff format --check scripts/validate_st0308_design_handoff.py tests/st0308/conftest.py tests/st0308/test_handoff_contract.py tests/st0308/test_handoff_negative_cases.py tests/st0308/test_handoff_reconciliation.py

For a candidate, calculate its exact bytes first:

    HANDOFF_SHA256="$(sha256sum /path/to/DESIGN_HANDOFF_V1.yaml | awk '{print $1}')"
    python3 scripts/validate_st0308_design_handoff.py --handoff /path/to/DESIGN_HANDOFF_V1.yaml --expected-sha256 "$HANDOFF_SHA256"

The current tooling-only contract digest is
`ca814d0ccdd8b3375418c2e233360639f4d47fc0a17a95ba3af646de01c78c2a`, pinned
by the validator. The isolated Story suite passed 165 tests; Ruff check and
Ruff format check passed for the validator and four Python test files.

These are local automated-preflight checks only. Exact-byte owner approval,
fresh conflict-free canonical reconciliation, ST-0308 implementation, formal
TST-005/TST-008 evidence, runtime/database behavior, staging, production,
browser, network, MCP, and security review remain NOT_EXECUTED or otherwise
unverified and out of scope.
