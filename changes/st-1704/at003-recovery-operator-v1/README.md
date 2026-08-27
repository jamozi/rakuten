# ST-1704 AT-003 recovery operator v1

This additive operator exists only for the observed recovery state in which the
fixed AT-003 target post `19` is a Draft while the immutable Review Draft remains
post `26`. It does not add REST, AJAX, cron, CLI, term creation, arbitrary post
selection, or generic publication capability.

The sole cookie-authenticated Tools action is bound to the fixed article, post IDs,
slug, packet/request/payload hashes, exact existing category name, source snapshot,
and target pre-state. It requires a `manage_options` human who can publish and edit
both posts to enter a 10–300 character reason, the final 12 operation-hash
characters, and the current WordPress password. The strict host constant
`RAOS_AT003_RECOVERY_WRITES_ENABLED === true` is required for both rendering and
submission and is disabled by default.

The action writes a durable non-autoloaded rollback record before mutation, copies
only the reviewed title/excerpt/content/snapshot, and performs the target
Draft-to-Publish transition in the same `wp_update_post` call. The already-correct
single category is preserved and verified. A failed readback restores the exact
Draft fields, timestamps, snapshot, and taxonomy state; the durable record remains
for audit and prevents automatic retries.
