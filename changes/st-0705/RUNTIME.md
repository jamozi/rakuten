# ST-0705 deterministic AI-output validation runtime

The runtime is a pure post-response evaluator for recorded ENV-DEV/CI evidence.
It performs the closed AIOV-000 through AIOV-010 sequence using the exact
AIT-001 through AIT-012 profiles generated from the ST-0701 registry, frozen
output schemas, the ST-0004 alignment contract, and this Story's owner contract.

The trust boundary is content-addressed.  Callers load the generated profile
registry through `load_trusted_ai_output_validation_profiles`; an arbitrary
caller-created profile is never authoritative.  `RecordedOutputEnvelope` keeps
the ST-0703 provider-exchange digest separate from the raw-output digest and
from the canonical-output digest.  A valid output must already be canonical
JSON object bytes.  JSON Schema uses Draft 2020-12 with a format checker, and
UUID/resource, scalar, order, policy, taint, review, sensitive-data, and
semantic checks use explicit profile locators and hash-bound receipts.

ST-0605 evidence coverage is accepted only through an exact binding of the
output, Article Version, Article body, Source Packet version/content, complete
Claim set, evaluation input, and validated report hashes.  A valid blocked
coverage report blocks the candidate; corrupt or incomplete coverage evidence
is unevaluable.  AI-output AST is not converted to Content AST here.

The following frozen-schema limitations intentionally remain fail closed:

- AIT-004 block content is an unconstrained object until ST-0806 supplies an
  exact Article/body/Claim-inventory binding.
- AIT-005 lacks alignment-required subject, evidence-requirement, and temporal
  fields.
- AIT-009 lacks alignment-required primary-decision, primary-intent-cluster,
  and merge-candidate fields.
- AIT-011 and AIT-012 remain recorded, proposed/default-disabled profiles.

Only AI-OUT-001 and AI-OUT-002 may be classified as eligible for one external
same-input repair.  The validator itself never calls a provider or repairs an
output.  Oversize, fact/identity, policy, secret, resource, and semantic
failures are terminal.  Formal TST-019/TST-020, live provider, staging, release,
and Production remain `NOT_EXECUTED`.

Local owner commands:

```text
PYTHONPATH=python .venv/bin/python scripts/build_st0705_ai_output_validation_runtime.py
PYTHONPATH=python .venv/bin/python scripts/build_st0705_ai_output_validation_runtime.py --check
PYTHONPATH=python .venv/bin/pytest -q tests/st0705_runtime
```
