# ADR-001: hash-bound ST-1704 publication execution

Status: accepted for the local v2 slice.

The operator may expose one new mutation: publish one of the exact four ST-1704
`PUBLISH_NEW` review drafts. The client builds a canonical request from the
owner-private committed Review Draft journal; `proposal_id` is the SHA-256 of
those exact bytes. The server independently derives and verifies the same draft,
snapshot, content, slug, and category bindings before accepting or applying it.

Approval is deliberately outside REST. A different cookie-authenticated
`manage_options` human reauthenticates in wp-admin and approves the immutable
hash. Codex may later send the matching apply command, but cannot approve,
weaken, replace, or infer that approval. This is deterministic execution of a
human decision, not automatic publication authority.

Only status, exact proposal creation, exact proposal readback, and exact apply
are added. The transition changes status, slug, and assignment to the one
already-existing `暮らしの道具` category. It cannot create terms or change
title, excerpt, body, snapshot meta, media, tags, or arbitrary metadata. The
existing suitcase update is not representable.

Both host constants must be strictly true. The package is deterministic and
derived from pinned ST-1506 v1 bytes plus generated bindings and a reviewed v2
controller. The v1 REST surface and identity confinement remain intact. Local
evidence does not establish formal validation, staging, release, or Production
readiness.
