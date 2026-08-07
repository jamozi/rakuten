# ST-0801 Content AST types and validator

This Story implements approved slice `CONT-SLICE-002`: a strict Python domain
boundary around the frozen Content AST v1 schema and the generated ST-0105
bindings. It reuses the installed Python and TypeScript types; no generated
binding or source contract is rewritten.

The loader validates hash- and size-pinned contract inputs, parses JSON with
duplicate-member and non-finite-number rejection, applies the frozen Draft
2020-12 schema, projects through the generated Pydantic model, and enforces
unique article-local block IDs. Errors do not echo rejected caller content.
Serialization is deterministic and revalidates a serialized snapshot before
returning it.

The schema is hash-checked before use. Selected generated files are checked
for disk parity at each load/dump call, after normal Python import; this is not
a pre-execution integrity mechanism. That trust boundary remains with the
ST-0105 deployment/codegen gate. This Story's manifest generator verifies the
bytes and SHA-256 of every output declared by the pinned ST-0105 manifest.

The frozen inputs contain 24 block variants, five valid article fixtures, ten
schema-invalid fixtures, one AST-local duplicate-ID fixture, and four fixtures
reserved for later article-template policy. Script- and iframe-like strings
remain ordinary text for a later renderer to escape. This slice does not claim
renderer safety, article-template rules, Claim/Evidence or Recommendation
semantics, review or Disclosure policy, persistence, publication, or provider
integration.

The frozen schema accepts syntactically valid RFC 3339 leap seconds. The
current generated ST-0105 `AwareDatetime` model cannot represent them, so the
loader fails closed with a redacted model error and does not normalize the
timestamp.

Generate and verify the deterministic, content-addressed Story manifest and
run the isolated suite through the pinned environment:

```bash
uv run --locked --no-sync --no-env-file python scripts/build_st0801_content_ast.py
uv run --locked --no-sync --no-env-file python scripts/build_st0801_content_ast.py --check
uv run --locked --no-sync --no-env-file pytest -p no:cacheprovider -q tests/st0801
```

These commands produce local implementation evidence only. Formal CI-only
`TST-020` remains `NOT_EXECUTED`, and effective canonical ST-0801 status remains
unchanged until governed evidence is reviewed and applied.
