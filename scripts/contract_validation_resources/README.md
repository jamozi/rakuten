# Pinned contract-validation resources

ST-0104 validates OpenAPI and AsyncAPI syntax without a network fetch. The
verifier checks the raw-byte SHA-256 of each schema before parsing or using it.

| Local file | Official source | Upstream revision | SHA-256 |
| --- | --- | --- | --- |
| `openapi-3.1-schema-2025-11-23.json` | `https://spec.openapis.org/oas/3.1/schema/2025-11-23` | OpenAPI 3.1 schema iteration `2025-11-23` | `1b8ccc6e34234b17536f2dd0eb3597142a32bd108438cd42471a5fca4c1a07ef` |
| `asyncapi-3.0.0-schema.json` | `https://raw.githubusercontent.com/asyncapi/spec-json-schemas/e609fc2341007395d75df5756fc6fccf662c2087/schemas/3.0.0.json` | `asyncapi/spec-json-schemas` tag `v6.11.1`, commit `e609fc2341007395d75df5756fc6fccf662c2087` | `d4571a420e6ffb7fcc7066c95a6db1202f299a3c51daa103d0706bf30f95e626` |

The OpenAPI schema validates the complete OpenAPI document structure. ST-0104
wraps it with the documents' declared JSON Schema Draft 2020-12 dialect so the
official schema's dynamic Schema Object hook also validates inline schemas.
The AsyncAPI artifact is the official bundled Draft-07 schema for AsyncAPI
3.0.0.

Both upstream projects publish these resources under Apache-2.0. The exact
license texts retrieved with the pinned resources are retained as
`OPENAPI-LICENSE.txt` and `ASYNCAPI-LICENSE.txt`.
