# ST-0703 DESIGN_HANDOFF_V1 V5 D5 correction request

Status: `PROPOSAL_PENDING_EXACT_HANDOFF_APPROVAL`

Story: `ST-0703`

Candidate commit inspected by the advisory review:
`f251edb31c52c775c46bcca8f4af26f6d8cdb5eb`

Comparison base:
`48a807672caa845df8e0251782f00bce8040663b`

## Authority boundary

The existing V4 handoff, reconciliation, and approval remain immutable. V4
grants `ST0703_RECORDED_SCOPE_ONLY`; it does not grant an ST-0204 semantic
change. This request proposes an append-only V5 correction to D5 only.

The manually returned `PRO_ADVICE_V1` selected Option 2 and remains
`UNAPPROVED_ADVICE`. It is evidence for this proposal, not implementation
authority. No raw prompt or browser response is committed.

## Blocking contradiction found during implementation preflight

The base Makefile defines the ST-0204 owner target as:

```make
config-check: | python-sync
	PYTHONDONTWRITEBYTECODE=1 $(UV_READONLY_RUN) python \
		scripts/build_st0204_config_loader.py --check
```

The V4 implementation candidate removed the `python-sync` order-only
prerequisite so that `openai-recorded-gate`, which depended on `config-check`,
would remain no-sync. That one-line change and the corresponding ST-0204 README
claim are semantic ST-0204 command-contract changes outside V4 authority.

Restoring the ST-0204 target to base while retaining the V4 composite target
would make `openai-recorded-gate` hydrate implicitly, contradicting V4 D5 and
the ST-0703 read-only gate contract.

The implementation worker stopped without editing when this contradiction was
observed.

## Proposed V5 decision

Create one corrected decision identity:
`ST0703-V5-D5-CORRECTION`.

V5 inherits V4 and V3 D1 through D4 without semantic change. It replaces only
D5 with this exact arrangement:

1. Restore the Makefile `config-check: | python-sync` target header and its
   owner-generator recipe exactly to base.
2. Restore `changes/st-0204/README.md` exactly to base; it must have no final
   diff.
3. Remove `config-check` from the `openai-recorded-gate` prerequisite list.
4. Keep the prerequisite list limited to `ai-registry-check`,
   `openai-recorded-check`, `openai-recorded-static`, and
   `openai-recorded-test`.
5. Add exactly one recipe command to `openai-recorded-gate`:

   ```make
	PYTHONDONTWRITEBYTECODE=1 $(UV_READONLY_RUN) python \
		scripts/build_st0204_config_loader.py --check
   ```

6. Hydration remains an explicit operation executed before the read-only gate;
   the gate itself must not invoke hydration or synchronization.
7. Update only ST-0703-owned README, contract, generator, tests, registry, and
   manifest for this D5 correction and V5 authority binding.

## Rejected alternatives

- Retain the no-sync `config-check` target: rejected because it is an ST-0204
  semantic change and would put two semantic Stories in one PR.
- Permit hydration from `openai-recorded-gate`: rejected because it violates
  the offline/no-cache/no-sync/read-only D5 boundary.
- Add a separate ST-0204 maintenance Story first: safe but rejected as
  unnecessary because the existing owner generator already exposes a
  deterministic read-only `--check` operation.

## Required invariants

- Exactly one semantic Story, ST-0703, in the final PR.
- `scripts/build_st0204_config_loader.py` and ST-0204 contracts, tests, schema,
  and README semantics remain unchanged from base.
- Generated artifacts are changed only through their owner generators.
- The only cross-Story output changes allowed are metadata-only owner-generated
  manifests for ST-0204, ST-0701, and ST-0801.
- ST-0106, ST-0107, ST-0202, ST-1203, and ST-1204 are not changed.
- ST-1203/ST-1204 predecessor debt remains unresolved and unwaived.
- No network, credential, Secret, environment credential read, cache sync,
  dependency sync, live provider call, database, queue, object store, or other
  external service is used by the read-only gate.
- Formal TST-017, live provider validation, staging, release, and production
  remain `NOT_EXECUTED`.

## Required V5 evidence

- Exact V4 source hashes and D1-through-D4 semantic parity.
- Exact Make target-structure tests for the restored ST-0204 target and the
  direct ST-0703-owned predecessor command.
- Negative tests rejecting hydration, sync, install, recursive Make, network,
  environment/credential access, cache writes, and extra gate commands.
- ST-0204 owner `--check` under `UV_READONLY_RUN` with before/after filesystem
  no-write evidence.
- Isolated ST-0102, ST-0204, ST-0701, ST-0703, and ST-0801 suites.
- Ruff, format, strict mypy, canonical import, workspace drift, generator
  no-write checks, manifest semantic-projection checks, `git diff --check`, and
  post-test clean-diff verification.

## Approval boundary

The V5 handoff and reconciliation produced from this request are proposals.
Implementation remains stopped until the repository owner explicitly approves
the exact SHA-256 of both files and a separate immutable
`DESIGN-HANDOFF-APPROVAL-v5.yaml` records
`ST0703_RECORDED_SCOPE_ONLY`.
