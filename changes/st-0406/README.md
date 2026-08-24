# ST-0406 secure object/file intake

Status: `LOCAL_CODE_COMPLETE` (maximum-safe recorded implementation)

ST-0406 V2 implements a durable, owner-private quarantine and journal for
recorded/synthetic local intake. It does not provide upload HTTP, object export,
promotion, publication, retention, deletion, provider, credential, staging,
release, or Production authority. Formal `TST-014`, `TST-026`, and `TST-031`
remain `NOT_EXECUTED`.

## Authorization-first boundary

Every V2 command carries the exact ST-0403 `AuthorizationEvaluationCommand`,
returned `AuthorizationCommandResult`, and ST-0401 `SessionId`. Before source or
quarantine I/O, the runtime calls
`DurableAuthorizationService.recover_admin`, which rechecks the active session
and recovers the durable result. V2 then requires exact result equality,
recomputes the request digest with the recovered session fingerprint, and binds
the operation, action, target, site, resource, state, and descriptor.

The only successful recorded binding is canonical `ED-011` /
`edit_article_draft` / `ARTICLE_VERSION` / `DRAFT`, for `SOURCE_DOCUMENT` or
`MEDIA_ASSET`. `REVENUE_REPORT` remains denied because no non-ambiguous active
intake binding has been proven. A directly constructed decision/result/grant is
not service provenance, and the removed `artifact:upload` fiction is not V2
authority. The original process-local V1 remains compatibility-only and is not
elevated by this completion.

## Durable quarantine

- The absolute owner-private root is checked through no-follow directory file
  descriptors, must be owned by the process and mode `0700`, and contains one
  regular, owner-owned, single-link SQLite database at mode `0600`.
- Each command runs in `BEGIN IMMEDIATE`, stores bounded bytes as a SQLite BLOB,
  and binds exact descriptor and authorization digests. Versioned projection
  updates use compare-and-set.
- Command idempotency, intake-id collision rejection, exact SHA-256 duplicate
  indexing, append-only result rows, and an append-only global event hash chain
  survive restart. Schema shape, row hashes, result projections, the hash chain,
  and SQLite integrity are checked on every transaction.
- Before-commit and after-commit ambiguity are closed and recoverable without a
  blind retry. Recovered requests must match their exact request digest.
- The public port exposes begin/recover/append/seal/accept/reject transaction
  mechanics only. It has no raw-byte read, export, promote, release, delete,
  purge, restore, retention, or lifecycle operation.

## Bounded inspection

Streams enforce exact `bytes`, per-chunk, chunk-count, total-size, declared-size,
and declared SHA-256 bounds. ZIP, TAR, and TAR.GZ are inspected in memory without
extraction; traversal, absolute/drive paths, links, special files, encryption,
duplicates, nested archives, and entry/count/size/ratio bombs are rejected.
CSV requires strict UTF-8 without BOM, a closed rectangular shape, bounded
rows/columns/cells, unique trimmed headers, and formula-prefix protection. Image
and PDF inputs require an exact extension/MIME/magic combination.

Privacy and malware decisions are digest-scripted recorded fixtures. The only
accepting malware verdict is `CLEAN`; the disabled scanner returns
`UNAVAILABLE` and fails closed. All collaborators expose an exact
`action_count == 0`, and arbitrary collaborator exceptions are collapsed to a
closed failure code without persisting or returning exception text or secret
canaries.

## Generation and evidence boundary

`scripts/build_st0406_secure_object_intake_runtime.py` validates the canonical
Story row, ST-0202 dependency, exact ST-0403 trust/binding semantics, OD-014,
and test-suite identities, then deterministically owns the generated runtime
projection and manifest. Run it with `--check` for a no-write drift check.

OD-014 remains unresolved, so this implementation chooses no retention period
or automatic deletion behavior. Live object storage, native scanner, public
upload, real identity/provider, hosted CI, staging, publication, release,
Production, Security/Privacy owner review, and Canonical status `APPLY` remain
outside this local evidence and are not claimed.
