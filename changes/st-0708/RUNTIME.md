# ST-0708 runtime boundary

Status: `LOCAL_IMPLEMENTATION_COMPLETE`

The runtime is default-disabled and supports exactly one local recorded request:
`st0708-recorded-synthetic-ait004-v2`. Its values are identifiers and SHA-256
digests only. Unknown requests, changed artifacts, duplicate JSON keys,
non-canonical generated JSON, schema/catalog drift, mismatched ST-0703 bindings,
or a changed ST-0707 report fail closed before a decision candidate is returned.

`ENV-DEV` and `CI` are the only accepted runtime environments. The adapter has no
live provider, network, secret, database, queue, publication, activation, or
release port. The report is always a `PROPOSAL` with `authority=NONE` and all
operational action fields false.

The installed recorded evidence is incomplete and the deterministic outcome is
`REFUSED_INCOMPLETE_EVIDENCE`. This status is not formal TST-018, staging, live,
release, or Production evidence.
