# Strategy switching usage

All inputs are explicit files. The CLI does not read environment variables,
Secrets, browser state, provider configuration, or ambient approval state.

## Inspect a safe selection

```bash
python scripts/select_all_story_strategy.py \
  --boundary OD-001 \
  --profile changes/all-stories-switchable-strategies/profiles/safe-local.v1.json \
  --context /path/to/local-gate-context.json
```

A local empty gate context has the exact shape:

```json
{
  "environment": "local",
  "approvals": [],
  "evidence": [],
  "capabilities": []
}
```

The output contains the requested and selected strategy IDs, fallback chain,
catalog hash, gate-context hash, and missing requirements. It contains no input
payload content.

## Execute a deterministic or reviewed-local candidate

```bash
python scripts/select_all_story_strategy.py \
  --boundary ST-0703 \
  --profile /path/to/reviewed-profile.json \
  --context /path/to/reviewed-gate-context.json \
  --payload /path/to/explicit-input.json \
  --execute
```

Safe execution returns a deterministic content-free plan. Standard manual-input
execution requires a nonempty explicit payload and returns only acceptance and
the payload SHA-256. Advanced execution requires application wiring to inject
the exact adapter key; the standalone CLI intentionally has no external adapter
and therefore refuses with `STRATEGY_ADAPTER_MISSING` after all gates pass.

## Override one boundary

```bash
python scripts/select_all_story_strategy.py \
  --boundary OD-003 \
  --profile changes/all-stories-switchable-strategies/profiles/balanced-staging.v1.json \
  --context /path/to/local-gate-context.json \
  --override OD-003:synthetic-report
```

An override must belong to the selected boundary. Cross-boundary overrides,
unknown candidates, unknown fields, duplicate JSON keys, non-object payloads,
non-finite numbers, symlinked inputs, oversized inputs, and missing gate
material are rejected.

## Production behavior

Only advanced injected candidates are eligible for Production. They require the
candidate-specific approval, the literal `production-use` approval, required
evidence, required capabilities, and exact adapter wiring. A Production request
never falls back to a standard or safe candidate.

Supplying identifiers to `GateContext` does not create approval or evidence. The
caller is responsible for constructing the context only from separately
verified, authorized records. This implementation neither resolves Open
Decisions nor authorizes publication, infrastructure apply, release, or
Production activation.
