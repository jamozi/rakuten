# ST-0505 — Rakuten owner-local one-call smoke

Classification: `SOURCE_DERIVED_EXPLICIT_LOCAL_RAKUTEN_LIVE_SMOKE_PLAN`.
Contract revision `2.2.0` implements an installable, owner-local, explicit
Rakuten Ichiba Item Search 2026-07-01 smoke. Default activation remains
disabled. This repository revision, its tests, and its generated plan contain
no live-provider execution evidence and do not satisfy formal TST-016,
staging, release, or Production.

## Fixed request and output boundary

- The outward adapter uses only stdlib `http.client` and `ssl`, direct TLS to
  `openapi.rakuten.co.jp:443`, and path
  `/ichibams/api/IchibaItem/Search/20260701`. Proxy discovery, TLS override
  environment, redirect following, endpoint override, retry, and pagination
  are rejected or absent.
- DNS is resolved exactly once. Every returned IPv4/IPv6 candidate must be a
  well-formed public address; one loopback, private, link-local, metadata,
  multicast, reserved, scoped, mapped, or otherwise non-public candidate
  rejects the whole set before socket creation. The first fully validated
  numeric address is pinned for the sole TCP attempt without fallback, while
  TLS SNI, certificate hostname verification, and HTTP `Host` remain fixed to
  `openapi.rakuten.co.jp`.
- One explicit invocation sends at most one GET. After all local preconditions
  pass, it sends exactly one GET with `keyword=収納`, `hits=1`,
  `page=1`, `format=json`, `formatVersion=2`, `sort=standard`, and the exact
  seven-element projection
  `count,page,first,last,hits,pageCount,affiliateUrl`.
  `applicationId` and `affiliateId` are query values; `accessKey` is sent only
  in the header named `accessKey`.
- The unchanged ST-0502 `RakutenItemSearchLiveRequestV1` remains the safe
  allowlist and zero-retry/zero-pagination predecessor. The ST-0505 report
  fingerprint binds both that policy fingerprint and the narrower wire
  projection.
- The response is capped at 2 MiB and validated as strict UTF-8 JSON. Duplicate
  keys, nonfinite numbers, excessive depth/nodes, unknown response keys,
  invalid summary cardinality, and missing/non-HTTPS `affiliateUrl` fail
  closed. Raw bodies, provider descriptions, product text, URLs, review data,
  affiliate rate, EPC/RPM, and revenue values are never reported.
- Report schema V2 records `response_sha256` over each complete bounded
  response-body byte sequence. The HTTP status line, headers, and transfer
  framing are excluded. Content-Length is parsed strictly and must match the
  observed body; chunked framing must be the sole transfer coding, and
  close-delimited EOF is the only no-length completion boundary. Malformed,
  conflicting, truncated, oversized, or otherwise incomplete reads do not
  claim a response-body digest. The body itself and all reflected provider
  material remain forbidden.
- HTTP 429 proves only `rate_classification=THROTTLED`; authentication remains
  `NOT_OBSERVED` unless a separate response establishes it.

Credentials are read only from
`.secrets/rakuten-live-smoke/credentials.v1.json`. The exact keys are
`schema_version: 1`, `application_id`, `access_key`, and `affiliate_id`.
The descriptor-bound reader requires current UID, non-symlinked ancestors,
private `0700` directories, a regular non-symlink mode-`0600` single-link
file, bounded bytes, and strict duplicate/unknown/missing/control/whitespace
validation. Two bounded reads from the same descriptor must be byte-identical,
and descriptor identity, size, modification-time, and change-time must remain
stable; credential rotation must use an atomic replacement. The reader never
creates or mutates the credential record.

The credential record is unusable without the separate owner-private
`.secrets/rakuten-live-smoke/staging-credential-binding.v1.json`. Its exact keys
are `schema_version: 1`, `environment: staging`, `credential_purpose:
DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC`, and
`credential_record_sha256`, which must equal SHA-256 of the exact credential
record bytes. The binding has the same descriptor-bound, current-UID,
non-symlink, mode-`0600`, single-link, bounded, double-read stability rules.
This repository never creates or mutates it. It must come from a separate
Operations process that establishes dedicated-test credential provenance;
self-labeling does not execute OD-015 or prove ENV-STAGING/TST-016.

Sanitized reports are atomically published mode `0600` at
`.secrets/rakuten-live-smoke/reports/<UTC-run-id>.json` from an anonymous
`O_TMPFILE` inode. A failed post-publication check rolls the target back. If
safe rollback itself fails, the writer attempts a fixed value-free mode-`0600`
`<UTC-run-id>.recovery-required` marker to record the recovery need. Report-store
failure retains the already-observed request/auth/schema/rate/affiliate/hash
metadata instead of falsely returning a zero request count.
Any recovery marker or abandoned preflight name blocks doctor, live preflight,
and every subsequent report publication until owner-side recovery.

## Independently installed entry

Repository scripts are not allowed to read credentials directly. Every install
and reinstall first binds the named stage through fd 4 with the root-owned
static BusyBox entry. Before hashing or parsing it, the outer gate requires the
opened stage and named path to identify the same current-UID, regular,
single-link, bounded, non-group/world-writable inode. Only after this check does
it authenticate the exact stage bytes. Only that authenticated static stage may
validate and start the exact root-owned `/usr/bin/python3.10` binary. Before
the dynamic exec it validates the fixed loader and `ld.so` configuration, the
root-owned OS runtime metadata closure for native libraries and stdlib, the
absence of loader/Python path shadows, and the exact installer bytes through
fd 6. Metadata trust here is deliberately not a byte-exact stdlib claim: the
root-owned OS runtime and package manager are trust anchors, root compromise is
out of scope, and any pinned interpreter or loader-configuration drift fails
closed pending review.

The authenticated Python installer then installs the exact reviewed payload
outside the repository. It uses a staged owner-private tree, file/directory
fsync, `renameat2(RENAME_NOREPLACE)`, inode verification, exact payload hashes,
directory mode `0700`, launcher mode `0500`, and payload/manifest mode `0400`.

```bash
/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC /usr/bin/busybox sh -c 'umask 077; p=/home/minami/rakuten/scripts/rakuten_live_smoke_runtime_install.sh; exec 4<"$p" || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; u=$(/usr/bin/busybox id -u 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; case "$u" in ""|*[!0-9]*) /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2;; esac; fm=$(/usr/bin/busybox stat -Lc "%d %i %f %u %a %h %s" /proc/self/fd/4 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; nm=$(/usr/bin/busybox stat -c "%d %i %f %u %a %h %s" -- "$p" 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; [ "$fm" = "$nm" ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; set -- $fm; [ "$#" -eq 7 ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; case "$1:$2:$3:$4:$5:$6:$7" in *[!0-9a-f:]*) /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2;; esac; v=$((0x$3)); [ $((v & 0xf000)) -eq 32768 ] && [ "$4" -eq "$u" ] && [ $((v & 18)) -eq 0 ] && [ "$6" -eq 1 ] && [ "$7" -ge 1 ] && [ "$7" -le 2097152 ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; h=$(/usr/bin/busybox sha256sum /proc/self/fd/4 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; [ "$h" = "9effd085052570cf943f311b012c6dcf7ac26c2514182513c1f52d33ca88d549  /proc/self/fd/4" ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; exec /usr/bin/busybox sh /proc/self/fd/4'
```

Direct repository-path execution of the Python installer refuses before
runtime mutation. Install and reinstall do not open, stat, list, read, write,
or mutate `.secrets`, the credential record, staging binding, or reports, even
when those paths already exist. Maintenance performs no network operation and
never chains doctor or run. An exact existing bundle is fully validated before
returning `ALREADY_INSTALLED`; a distinct reviewed bundle is installed
side-by-side. Neither path migrates, rebinds, or deletes credential, binding,
or report material.

Authenticated installation is credential-blind owner-local maintenance only.
Even a successful install proves only exact local-runtime installation: it
does not prove credential availability or provenance, resolve OD-015, grant
live-provider authority, execute a provider call or TST-016, establish
ENV-STAGING, accept or validate ST-0505, release, or reach Production. This
implementation does not run that installer; installed-runtime status is
`NOT_EXECUTED` and `NOT_EVIDENCED`. Disposable tests do not elevate that state.

The authoritative entries are the following two complete, fixed commands. The
root-owned static BusyBox process clears the inherited environment and verifies
the exact installed launcher bytes before that launcher body executes:

```bash
/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC /usr/bin/busybox sh -c 'umask 077; p=/home/minami/.local/share/raos/rakuten-live-smoke/runtime/94c256d8832167c6df89327fc2840bc6db6fc82af4c912286b95ee6e8084148d/bin/rakuten-live-smoke; exec 4<"$p" || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY; exit 2; }; h=$(/usr/bin/busybox sha256sum /proc/self/fd/4 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY; exit 2; }; [ "$h" = "9deabbf7dff82e43b87a793a27b0c7f0d7371e97559755484f0c5cba9ddeabed  /proc/self/fd/4" ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY; exit 2; }; exec "$p" doctor'

/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC /usr/bin/busybox sh -c 'umask 077; p=/home/minami/.local/share/raos/rakuten-live-smoke/runtime/94c256d8832167c6df89327fc2840bc6db6fc82af4c912286b95ee6e8084148d/bin/rakuten-live-smoke; exec 4<"$p" || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_FAIL; exit 2; }; h=$(/usr/bin/busybox sha256sum /proc/self/fd/4 2>/dev/null) || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_FAIL; exit 2; }; [ "$h" = "9deabbf7dff82e43b87a793a27b0c7f0d7371e97559755484f0c5cba9ddeabed  /proc/self/fd/4" ] || { /usr/bin/busybox printf "%s\n" RAKUTEN_LIVE_SMOKE_FAIL; exit 2; }; exec "$p" run'
```

The outer static, root-owned `/usr/bin/busybox` stage zero authenticates the
launcher SHA-256 before executing it. The authenticated launcher validates
secure ancestry, exact launcher/CLI/Python metadata, the CLI and Python hashes,
rejects `pyvenv.cfg`, other path-configuration or RPATH loader shadows, and
rejects unowned, non-regular, or group/world-writable stdlib material. It runs
Python with `-B -I -S` and passes a descriptor for the authenticated launcher.
The Python entry refuses direct payload invocation without that descriptor,
rejects every unmanifested runtime path (including `__pycache__` and package
initializers), and verifies the manifest and every installed payload through
descriptor-relative `O_NOFOLLOW` reads before importing RAOS code or
constructing the credential reader. Repository drift and other-UID writes
therefore cannot change the credential-bearing entry. The current-UID managed
Python/stdlib tree is trusted after the documented metadata and writable-bit
checks; same-UID replacement, hash-to-exec race, or deliberate stage-zero
descriptor forgery is explicitly out of scope.

A bare invocation of the installed launcher refuses before constructing the
credential reader unless it inherits the authenticated outer-gate descriptor
on fd 4. Direct Python payload invocation likewise refuses without the
launcher descriptor on fd 3.

Repository Make entrypoints are intentionally not provided. A writable
Makefile is outside the bootstrap authority for runtime installation and
secret-bearing execution; the complete reviewed direct install, doctor, and
live commands above are the only documented entries.
Doctor checks installed-runtime, staging-binding and credential-record
structure, and report-store metadata only; it checks report metadata before
reading the binding or credentials, does not construct a transport, and
performs no network or filesystem mutation. It is not provider auth/IP/schema
proof and does not prove the filesystem's actual anonymous publication
operation. Run first proves the exact anonymous inode,
link, identity, rollback, and directory-fsync path, before reading credentials
or attempting the GET, and always requires a fresh explicit invocation. In
particular, HTTP 403/authentication/IP mismatch is never retried; provider-side
configuration must be corrected before another owner invocation.

## Evidence boundary

The owner-local entry is a disabled, non-formal, non-attesting diagnostic
surface only. This artifact grants no live-provider execution authority. No
result from it, including `LIVE_SMOKE_PASS`, executes or satisfies TST-016 or
advances ST-0505 acceptance, adapter `VALIDATED` status, ENV-STAGING, release,
or Production. Formal TST-016 remains an Operations-owned ENV-STAGING execution
using dedicated test credentials backed by scoped account/permission/secret
evidence and its required immutable evidence record.

OD-015 remains `EXTERNAL_EVIDENCE_REQUIRED`, blocking, unresolved, and
default-safe as `Recorded fixtureのみ`. The local fake tests do not read the
owner credential record or make a provider request. Observation defaults,
formal TST-016, live auth/schema/rate, staging, release, and Production all
remain `NOT_EXECUTED`; Story acceptance and Production eligibility remain
false.

## Owner generation

Generated JSON and manifest output are owned only by the builder:

```bash
python3 scripts/build_st0505_rakuten_live_smoke_reference_plan.py
python3 scripts/build_st0505_rakuten_live_smoke_reference_plan.py --check
```
