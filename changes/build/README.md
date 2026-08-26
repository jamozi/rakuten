# Build manifest v2

`manifest.v2.json` is the active generator registry and integrity manifest. Every
generated output has exactly one owner. Canonical packages, dependency locks, and
container images may be checksum-bound; ordinary tracked inputs use a repository URI,
semantic ID, and owner version without a digest.

Story-local v1 manifests remain historical compatibility snapshots. They are not active
build authority, are not consulted by `make generate` or `make check`, and their source,
approval, handoff, command, or commit bindings do not stop current development.
