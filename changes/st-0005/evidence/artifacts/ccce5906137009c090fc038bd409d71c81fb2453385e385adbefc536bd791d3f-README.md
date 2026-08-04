# ST-0203 local queue abstraction

This Story adds a provider-neutral Python queue port and a deterministic,
in-memory fake for release-blocking suite `TST-013`. The fake reproduces the
delivery failures consumers must tolerate without starting a broker, thread,
timer, or network client.

The semantic source is
`changes/st-0203/contracts/local-queue.v1.yaml`. Generate and check the
content-addressed Story manifest with:

```bash
uv run --locked --no-sync python scripts/build_st0203_queue_fake.py
uv run --locked --no-sync python scripts/build_st0203_queue_fake.py --check
uv run --locked --no-sync pytest -p no:cacheprovider -q tests/st0203
```

`QueueMessage` carries provider-neutral identity, scheduling, retry-budget,
and caller-owned payload data. `QueuePort` exposes send, receive, acknowledge,
retry, and lease-extension operations. `QueueFake` uses an explicit aware
virtual clock and supports exact duplicate and pending-order injection.
Duplicates keep the same logical message and idempotency key but receive a
different occurrence-scoped receipt handle.

Lease expiry invalidates the old receipt and makes the occurrence available
again with an incremented delivery attempt. Explicit retry can add a virtual
delay. Retry or lease expiry at the configured maximum attempt writes an
inspectable DLQ record. Stale and never-issued receipt handles fail closed.
Timestamp arithmetic overflow is rejected before queue state is mutated.

This fake does not provide consumer idempotency storage, job-state mutation,
worker execution, durable persistence, provider IAM, SQS/LocalStack, or a
production broker adapter. `SEC-APP-011` remains a later consumer obligation,
and `SEC-INFRA-008` remains a later provider/IAM obligation. A local passing
suite is implementation evidence only; effective canonical status and formal
CI-only `TST-013` remain `NOT_STARTED / NOT_EXECUTED` until governed evidence
is reviewed and applied.
