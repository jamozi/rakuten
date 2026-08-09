# ST-0404 framework-neutral HTTP security baseline

Status: `LOCAL_IMPLEMENTATION_CANDIDATE`

This Story implements the reversible local portion of the approved ST-0404
security boundary. It provides strict HTTP request metadata, caller-supplied
default-deny policy values, a pre-handler guard, deterministic conservative
response headers, CSRF proof comparison, and a closed RFC 9457 Problem Details
surface without activating an HTTP framework or external endpoint.

## Implemented safe boundary

- Origins are exact canonical ASCII values. HTTPS is required except for
  explicitly supplied `localhost` or `127.0.0.1` synthetic HTTP origins.
  Wildcards, `null`, user information, paths, queries, fragments, controls,
  noncanonical hosts, and ambiguous ports are rejected.
- All origin, method, content-type, request-header, content-length, credential,
  and HSTS behavior is supplied explicitly through `HttpSecurityPolicy`.
  Empty allowlists deny; there is no production domain, origin, size, timeout,
  rate, or HSTS default in this candidate.
- Unsafe cookie-authenticated commands require an exact allowed origin and two
  canonical 256-bit CSRF proofs that match through constant-time comparison.
  The seam defines no cookie/header names and selects no cookie-versus-bearer
  authentication transport.
- Request metadata intentionally contains no raw body, cookie value, bearer
  token, Secret, or personal data. Rejected requests invoke the handler zero
  times; accepted requests invoke it exactly once. Handler exceptions are
  replaced by one sanitized failure without exception chaining.
- Response headers are deterministic and conservative: deny-by-default CSP,
  `nosniff`, frame denial, `no-referrer`, restrictive Permissions Policy, and
  `no-store`. CORS echoes only an exact allowed origin and cannot express a
  credentialed wildcard.
- `ProblemDetails` serializes only its closed allowlist of type, title, status,
  stable code, and correlation ID. Raw exception text and uncontrolled
  extensions are not accepted.

## Local commands

After the locked Python environment has been hydrated, run the isolated Story
suite and static checks through the pinned repository uv in offline/no-sync
mode:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st0404
```

Ruff lint/format and strict mypy use the same uv prefix and only
`python/raos/domain/http`, `python/raos/application/http`, and `tests/st0404`.
The Story intentionally adds no Make target while shared Makefile provenance is
open integration debt.

## Evidence and deferred boundaries

The local candidate does not choose a real public or Admin origin, HTTP
framework, endpoint, cookie/header name, authentication transport, production
CSP nonce/hash/reporting source, HSTS duration, request/rate/timeout limit,
durable CSRF replay state, or deployment configuration. It does not activate
`apps/api`, `apps/web`, OIDC callback delivery, CORS for a real domain, or a
public route.

Local pytest/static results are not formal `TST-012` or `TST-026` evidence and
do not represent hosted CI, browser/runtime, staging, publication, release,
deployment, or Production readiness. These boundaries are recorded as
`DEBT-W1-007` and `DEBT-W1-008` in the implementation-first ledger.
