# ST-0105 generated contract types and clients

This Story generates language bindings only from the verified ST-0104
repository at `contracts/raos-v0.4`. The installed contract repository remains
the source of truth; generated files are disposable projections and must never
be edited by hand.

`scripts/build_st0105_generated_contracts.py` creates:

- Pydantic v2 models under `python/raos/generated/` for every standalone JSON
  Schema;
- TypeScript schema types and separate Public/Admin/Internal OpenAPI clients
  under `packages/web-contracts/src/generated/`;
- an AsyncAPI message/channel/operation registry without a broker runtime; and
- `changes/st-0105/manifest.json`, which binds every input, tool version, type
  name, operation ID, and generated file hash.

The install command mutates only the three generated outputs above. Before any
namespace change it durably publishes `.install-transaction.v1`, stages both
trees through repository-root-pinned directory descriptors, and records
`STAGING`, `PREPARED`, `COMMITTED`, or `ROLLED_BACK`. A later install
automatically rolls an interrupted pre-commit transaction back or completes
post-commit cleanup. Terminal cleanup atomically renames the complete journal
to `.install-transaction.v1.cleanup`, fsyncs the parent, and only then removes
its entries; a later install removes any partial cleanup tombstone without
parsing it. A recovery error preserves the journal and every stage that might
hold the only old tree; never delete them by hand. `--check` regenerates in a
private temporary directory and compares bytes without writing to the
repository. Network retrieval is forbidden; all generator inputs are copied
from the manifest-owned contract repository after full integrity verification.

Recorded operations use the fail-closed combined wrapper:

```bash
scripts/codegen_toolchain.sh \
  --uv /absolute/path/to/uv \
  --node /absolute/path/to/node \
  --npm-cli /absolute/path/to/npm-cli.js hydrate
scripts/codegen_toolchain.sh \
  --uv /absolute/path/to/uv \
  --node /absolute/path/to/node \
  --npm-cli /absolute/path/to/npm-cli.js install
scripts/codegen_toolchain.sh \
  --uv /absolute/path/to/uv \
  --node /absolute/path/to/node \
  --npm-cli /absolute/path/to/npm-cli.js check
scripts/codegen_toolchain.sh \
  --uv /absolute/path/to/uv \
  --node /absolute/path/to/node \
  --npm-cli /absolute/path/to/npm-cli.js gate
```

`hydrate` is the separately named environment mutation. `install` changes only
the generated outputs; `check`, `test`, `typecheck`, and `gate` validate the
already-installed exact tools offline, without cache use, synchronization,
`npm ci`, or repository writes. A pending journal makes read-only commands fail
closed and requires `install` recovery. The official `install` target performs
pending-tolerant `.venv` and Node storage checks, then recovery, then exact-tool
verification and generation. The generator rejects symlinks in every ancestor
of its datamodel, Node, OpenAPI, and TypeScript tool paths. The wrapper recovery
integration test runs against a disposable temporary repository, so `test` and
`gate` do not replace real generated outputs.

`contract-codegen-gate` includes the complete read-only ST-0104 contract gate, two fresh
no-write generations, the isolated local TST-004 suite, and TypeScript
compilation. Generated files are externally formatted projections: do not edit
or reformat them. Python validation uses exact hashes, compile/import, all 224
Pydantic `model_json_schema()` calls, and Ruff lint. The generated TypeScript
package inherits strict root checks while isolating the external fetch client's
`exactOptionalPropertyTypes=false` compatibility requirement.

Runtime Content AST policy validation, a queue/broker client, HTTP handlers,
domain mappings, CI workflow installation, publishing, and deployment are not
part of ST-0105.

Local implementation evidence can propose only
`IMPLEMENTED_NOT_VALIDATED / NOT_EXECUTED`. The canonical backlog remains
`NOT_STARTED / NOT_EXECUTED`; formal TST-004 execution and base CI remain
ST-0106 scope.
