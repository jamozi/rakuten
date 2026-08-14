# ST-0106 hosted Secrets high-confidence classifier V3

## Purpose

V3 closes two security defects found only after the exact V2 implementation
reached its non-shallow full-worktree and full-Git-history gate. V1 and V2 stay
immutable as audit history and have no implementation commit. This V3 is not
implementation authority until the repository owner approves the exact
SHA-256 of its handoff and a detached approval record binds that hash.

## Sanitized contradiction

The candidate-overlay scan returned nine location-and-rule-only generic
findings: four maintained occurrences and five historical blobs. They reduce
to four unique bare captures. Each capture satisfies the approved digit-bearing
family, but the unchanged matcher stops at an internal delimiter before the
complete same-line source expression. The truncated bytes must not be declared
safe, while path, value, operation-name, expected-count, and blob exemptions
are forbidden.

Separately, the uncommitted floating Shannon-entropy helper used Counter
insertion order and left-to-right summation. Permuting identical histograms
could straddle each inclusive threshold: 3.5, 3.75, and 3.3. No candidate,
assignment, source line, histogram, or secret bytes were exposed.

## Selected RHS rule

V3 does not relax the incomplete capture. Only an otherwise live
digit-bearing bare finding whose exact candidate is ASCII and syntactically
incomplete may attempt reconstruction. The scanner uses the original value
start and exact raw bytes through the end of the same physical line; it does
not search for a different start, path, file type, operation, or value.

The reconstructed bytes must be one bounded printable-ASCII Python 3.10 eval
expression with exact token coverage. Comments, semicolons, trailing
whitespace, residual bytes, multiple expressions, assignments, continuation,
multiline material, unmatched delimiters, non-ASCII, and every limit defect
fail closed. The full expression is then passed through exactly the existing
V1/V2 closed AST and suspicious-literal validator. No new AST node, callable,
attribute, operator, literal form, or source-operation marker is admitted.

On success only the original generic finding is suppressed. On refusal its
original span, line, rule, redaction, and exit effect remain unchanged.
Provider, private-key, and independent generic findings remain unaffected.

## Selected entropy rule

Floating entropy is removed. For candidate length `n`, positive byte counts
`c_i`, and an approved reduced rational threshold `a/b`, V3 compares:

```text
n ** (b*n) >= 2 ** (a*n) * product(c_i ** (b*c_i))
```

Equality is included. The only constants are `7/2` for the existing 3.5
digit-bearing family, `15/4` for the existing 3.75 digit-free opaque family,
and `33/10` for the existing 3.3 lower-case passphrase family. A fixed
256-slot byte histogram and exact Python integer power, multiplication, shift,
and comparison make the result independent of byte first-occurrence order,
hash seed, summation order, and libm.

The helper does not alter candidate bytes, thresholds, family predicates,
length gates, or the distinct-byte gate. Empty input is false. Invalid internal
constants, impossible histogram state, arithmetic/resource failure, or an
unknown family fail through the existing sanitized nonzero internal-error
boundary. There is no float, logarithm, Decimal, epsilon, tolerance, or
fallback path.

## Authority and file boundary

The exact base remains commit
`6f8dafb511ed9492a51d7c831a3c212f8f52deae`, tree
`9f263246f5aca387d30f6050b508c209eb148f1c`. V3 retains all six immutable
V1/V2 records. It adds only this companion, the V3 handoff, and the detached
V3 approval created after exact owner approval. The implementation payload is
still limited to the same six V2 paths:

- `scripts/scan_secrets.py`
- `tests/st0106/test_secret_scanner.py`
- `changes/st-0106/README.md`
- `docs/execplans/ST-0106.md`
- `docs/worklogs/ST-0106.md`
- `README.md`

The final authorized cut is therefore fifteen paths: nine authority records
and six mutable implementation/documentation paths. Every other path is
protected. No workflow, Make, lockfile, network wrapper, ST-0101 selector,
Canonical, upstream, ST-0005 status, provider, release, or Production behavior
is in scope.

## Evidence and non-claims

Required evidence includes hostile reconstruction boundaries, exact entropy
equality/below/above and histogram permutations, all V1/V2 regressions,
archives and Git-history parity, system Python 3.10, pinned Ruff, full isolated
ST-0106, hosted-like ST-0101, protected-tree and sensitive scans, and the
existing denied-network scanner in a disposable clean non-shallow clone. The
frozen result must be one commit over the exact base and pass an independent
review.

The two Pro runs were gated advisory inputs only. Both were manually imported
from the same once-submitted bound conversations, created no browser call at
import, and were not resubmitted. Their algorithms were reconciled with
Canonical, exact local evidence, and integer algebra; neither response is
authority. Local success will not constitute a GitHub-hosted run, formal
TST-001/TST-002, a status transition, release, or Production approval.
