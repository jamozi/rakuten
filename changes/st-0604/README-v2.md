# ST-0604 V2 — Source Packet lifecycle runtime

This additive runtime implements the local `Draft → review → human decision →
lock → generation input` boundary. It consumes exact ST-0602 persisted Facts,
requires the exact ST-0603 scan for the same Fact membership, and refuses a
packet when that scan contains any open Conflict or queue record.

Human approve and reject decisions are accepted only after an already-recorded
ST-0403 `PUBADM-004` allow is recovered through the active session. The target
must be the packet's immutable `REVIEW_ASSIGNMENT` in `IN_PROGRESS`. The
approval record binds the exact content hash, Fact membership hash, Conflict
scan hash, authorization audit digest, and reviewer-session fingerprint.

`ApprovedLockedGenerationInputV2` is deliberately separate from ordinary
packet state. It revalidates a current `APPROVED` Version, its exact approval,
its exact lock, and the no-open-conflict content. Building, in-review, rejected,
unlocked, non-current, or superseded Versions cannot produce it. Editing always
creates a new immutable Version and supersedes the prior current Version while
preserving historical approval and lock evidence.

The persistence adapter uses a created-only owner-private SQLite database,
rejects symlink ancestors and hardlinks, and pins its file inode for the
process lifetime. Exact SQLite schema/PRAGMA inventory, STRICT tables, foreign
keys, canonical decoding, append-only lifecycle/review/lock/command/audit
journals, a hash chain, CAS revisions, and exact command recovery without blind
retry are enforced. Its identity/head/prefix anchor detects rollback during
one process lifetime. There is no external monotonic anchor, so
privileged rollback across process restarts is explicitly not claimed.

The runtime has no AI, provider, browser, credential, network, ranking,
recommendation, revenue, publication, staging, release, or Production action.
Local checks are not formal TST-012/TST-020 or Production evidence.

Owner generation:

```text
python scripts/build_st0604_source_packet_lifecycle_runtime.py
python scripts/build_st0604_source_packet_lifecycle_runtime.py --check
```
