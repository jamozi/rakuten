# ST-0701 AI contract registry loader

ST-0701 compiles the four exact ST-0003 Task, Prompt, Schema, and Route
registries installed by ST-0104 into one deterministic runtime projection:

```text
changes/st-0701/generated/ai-task-registry.v1.json
```

The generated JSON matches the strict standard-library adapter contract in
`python/raos/adapters/ai_contract_registry.py`. It contains 12 sorted task
bindings. Every binding carries the complete Task entry, the Prompt registry
entry and parsed prompt frontmatter, the task-output Schema registry entry,
the exact Route entry, and canonical SHA-256 values for the Task, Route, and
complete binding.

Prompt Markdown and JSON Schema bytes are not duplicated in the projection.
The generator verifies their exact installed path, size, and SHA-256 through
`ContractRepository`; the runtime adapter reads and rechecks the selected
bytes through the same repository before returning an immutable contract.
Unknown task codes, compiled-artifact drift, source-byte drift, duplicate
identifiers, and broken or conflicting cross-references fail closed. No
network retrieval is available.

## Commands

Hydration is a separate, explicit mutating step. Run it once with the pinned uv
before generation or read-only verification; `ai-registry-check` and
`ai-registry-test` do not depend on `python-sync` and fail if the locked
environment is not already hydrated:

```bash
make python-sync UV=/absolute/path/to/uv
make ai-registry-generate UV=/absolute/path/to/uv
make ai-registry-check UV=/absolute/path/to/uv
make ai-registry-test UV=/absolute/path/to/uv
```

The direct generator and read-only check/test equivalents are:

```bash
uv run --locked --no-sync --no-env-file python scripts/build_st0701_ai_registry.py
PYTHONDONTWRITEBYTECODE=1 uv run --locked --offline --no-cache --no-sync \
  --no-env-file --no-python-downloads \
  python scripts/build_st0701_ai_registry.py --check
PYTHONDONTWRITEBYTECODE=1 uv run --locked --offline --no-cache --no-sync \
  --no-env-file --no-python-downloads \
  pytest -p no:cacheprovider -q tests/st0701
```

`ai-registry-generate` is the only mutating command. `ai-registry-check`
reconstructs both generated artifacts in memory and compares their exact bytes
without writing; both read-only commands disable bytecode writes, network and
cache access, environment synchronization, environment-file loading, and
Python downloads. `changes/st-0701/manifest.yaml` is generated from the
current source inventory; do not edit either generated artifact by hand.

## Runtime construction

`CompiledTaskRegistry` requires an absolute, normalized path to the compiled
registry and the generated artifact SHA-256 pinned by
`changes/st-0701/manifest.yaml`. Resolve the repository-relative path before
constructing the adapter:

```python
from pathlib import Path

from raos.adapters.ai_contract_registry import CompiledTaskRegistry
from raos.shared import ContractRepository

repository_root = Path("/absolute/path/to/raos").resolve()
compiled_registry_path = (
    repository_root / "changes/st-0701/generated/ai-task-registry.v1.json"
).resolve()
compiled_registry_sha256 = (
    "33bbb3601aae2e02d37bf995a2522e67684befcd9a43ba4375b4a7685aedef07"
)

task_registry = CompiledTaskRegistry(
    ContractRepository(repository_root / "contracts/raos-v0.4"),
    compiled_registry_path,
    expected_sha256=compiled_registry_sha256,
)
```

The SHA value above is the `generated_artifacts` entry from the generated
manifest, not a caller-selected digest. Construction verifies and loads
immutable candidate metadata only; it does not activate any task or select,
configure, or call a provider.

## Boundary

This Story loads immutable candidate metadata only. It does not activate or
seed tasks, select or call a provider, execute a route, evaluate output,
connect to a database, spend a budget, approve content, publish, or release.
Local tests are implementation-candidate evidence only. Formal TST-001 and
TST-017, hosted CI, human review, canonical status changes, staging, and
production remain `NOT_EXECUTED` or unchanged.
