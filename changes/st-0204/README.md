# ST-0204 configuration and Secret-reference loader

This Story defines a strict, provider-neutral runtime configuration boundary.
Its semantic source is
`changes/st-0204/contracts/runtime-config.v1.yaml`; the Python model generates
the language-neutral JSON Schema at
`changes/st-0204/generated/runtime-config.v1.schema.json`.

The loader accepts only `RAOS_ENVIRONMENT`, `RAOS_SERVICE_NAME`, optional
`RAOS_LOG_LEVEL`, and optional `RAOS_SECRET_REFERENCES`. The last value is a
bounded strict JSON object whose values are logical `secret://` references,
not Secret material. Caller-owned required aliases fail closed when absent.
Generated name/reference patterns assert absolute end in both ECMA-262 and the
repository's Python Draft 2020-12 validator, including for a trailing line feed.

Diagnostics contain an exact allowlist of non-secret runtime metadata, sorted
reference aliases, and a count. They never contain logical reference values,
arbitrary source keys/values, or parser input. Model and loader errors are
redacted as well, including Pydantic structured-error and generic pickle
surfaces. Generic serialization of the opaque reference and runtime model is
rejected. String subclasses are not treated as trusted configuration text.

Schema generation is reproducible only under the reviewed Python 3.14.6,
Pydantic 2.13.4, pydantic-core 2.46.4, PyYAML 6.0.3, and uv 0.12.1 toolchain.
The generator verifies those runtime/configuration pins before rendering and
the Story manifest records them together with the lock/configuration files and
the shared manifest-builder implementation.

Supported Pydantic surfaces are `RuntimeConfig(...)`, `model_validate()`, and
the 32-KiB-bounded `model_validate_json()`, which rejects duplicate members at
every JSON object depth before Pydantic validation and snapshots mutable
bytearray input for the complete parser pipeline. Direct low-level
`TypeAdapter` parsing and invoking `BaseModel` methods to bypass this model's
validation are not supported APIs. In particular, Pydantic parses malformed JSON before a
model schema can sanitize its parser error; callers must use
`model_validate_json()` when untrusted JSON needs a redacted domain error.
Even when trusted code deliberately forces invalid model state, the public
model serialization and diagnostic surfaces fail closed to fixed sentinels.
The runtime model and opaque reference cannot be subclassed; supported
validation revalidates existing model objects and retains only exact base
reference instances, preventing override-based display or pickle disclosure.

Generate/check the schema and Story manifest, then run the isolated suite:

```bash
uv run --locked --no-sync python scripts/build_st0204_config_loader.py
uv run --locked --no-sync python scripts/build_st0204_config_loader.py --check
uv run --locked --no-sync pytest -p no:cacheprovider -q tests/st0204
```

Hydration is an explicit prerequisite for the Make convenience commands: run
`python-sync` separately when needed. `config-check` is a read-only drift check
and does not synchronize or otherwise mutate the Python environment.

This implementation reads no `.env` file, arbitrary configuration file,
network endpoint, provider SDK, or Secret value. Provider resolution, workload
identity, rotation hooks, and production credentials remain ST-0407 scope.
Local results are candidate evidence only; formal `TST-005`/`TST-031` and
effective canonical status remain `NOT_EXECUTED` and unchanged.
