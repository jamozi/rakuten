# ST-1704 WordPress publication operator v2

This additive slice extends the bounded ST-1506 plugin with one closed operation:
`PUBLISH_ST1704_ARTICLE`. It can represent only the four new articles in the
ST-1704 v1 publication plan, one at a time.

The builder verifies pinned v1/editorial inputs, generates the fixed binding,
injects the v2 controller into package bytes without editing v1 source, and
produces a deterministic `ZIP_STORED` package in an owner-private directory.
The tracked runtime manifest binds every runtime source and each packaged file.
The generated package advertises WordPress 7.1 and the v2 controller also
refuses to initialize outside the 7.1.x release line.

Execution still requires two default-off host gates and a distinct wp-admin
human approval of the exact proposal hash. There is no REST approval route, no
generic post or taxonomy surface, no content/media mutation, and no Codex
self-approval. Nothing in this directory is a live publication or Production
readiness claim.

Run from the repository root:

```sh
make -f changes/st-1704/publication-operator-v2/Makefile check
```
