# ST-0205 synthetic data factory

This Story owns a pure, deterministic fixture factory and one versioned seed
scenario bundle for the 13 canonical schema domains. The semantic source is
`changes/st-0205/contracts/synthetic-data-factory.v1.yaml`; generated files
are `generated/synthetic-fixtures.v1.json`,
`generated/fixture-catalog.v1.json`, and `manifest.yaml`.

The factory accepts only an approved domain/scenario pair and a bounded seed.
It does not accept arbitrary payloads, read environment configuration, use a
provider SDK, open a network connection, or write PostgreSQL/S3. Exact
domain-specific payload allowlists make review bodies and personal fields
unrepresentable. Missing classification defaults to `CONFIDENTIAL`; the four
canonical classification labels are recognized, but `RESTRICTED` fixture data
fails closed and arbitrary labels are rejected separately.

Every fixture records the deterministic factory origin, the repository's
authoritative `UNLICENSED` package metadata, and a SHA-256 over canonical JSON
bytes in the generated catalog. The generator binds both current dependency
manifests: ST-0201
`fce4b7f18cec09425264a1058bda59759e081be0c04826ffa3eae433a68fcda3`
and ST-0202
`d6add6c501bd5eb199ce8db0311ae750583d244eb1c3a717c3fc536d38a099e4`.
Any drift fails before output generation.

The seed bundle covers Time, Currency, Locale, Unicode, large integer values,
DST, JST, duplicate delivery, and out-of-order delivery. All data is authored
synthetically; no live/recorded provider payload, production/staging row,
Rakuten review body, poster/customer field, email, raw IP/User-Agent,
credential, or raw prompt is used.

Generate, check without writing, and test with the pinned environment:

```bash
uv run --locked --no-sync python scripts/build_st0205_synthetic_data.py
uv run --locked --no-sync python scripts/build_st0205_synthetic_data.py --check
uv run --locked --no-sync pytest -p no:cacheprovider -q tests/st0205
```

The root aliases are `make synthetic-data-generate`,
`make synthetic-data-check`, and `make synthetic-data-test`.

Local output is candidate implementation evidence only. Formal TST-005,
TST-031, privacy/security review, hosted CI, staging, production, and canonical
status application remain `NOT_EXECUTED` or forbidden. OD-014 remains open;
this Story defines no retention period, deletion job, database schema, or
storage seeding operation.
