# RAOS V2 full-redesign Pro packet

This directory owns the versioned request and the declarative repository-input
allowlist for a whole-product redesign review. It does not contain Pro output and
does not authorize implementation, publication, deployment, credentials, spending,
or a Production change.

The private audit archive is generated outside Git at:

```text
.secrets/full-redesign-audit/RAOS_FULL_REDESIGN_AUDIT_PACKET_v1.tar.gz
```

The archive combines explicitly allowlisted repository files, tracked-source
inventory, sanitized Git state, fixed public-URL captures, and four separately
captured browser screenshots. It excludes `.secrets` generally, Git internals,
caches, virtual environments, dependency trees, raw provider material, and raw Pro
session data. The only private inputs read are the four exact screenshots under the
dedicated `.secrets/full-redesign-audit/browser-source/` directory.

Generate the packet after collecting those screenshots:

```bash
.venv/bin/python -B scripts/prepare_full_redesign_audit_packet.py build \
  --capture-public
```

Validate the archive without network access or extraction:

```bash
.venv/bin/python -B scripts/prepare_full_redesign_audit_packet.py check
```

Successful generation also writes owner-private companion metadata and a member
checksum file beside the archive. The archive is evidence for Pro design work only.
Any returned design remains an unapproved proposal until reconciled with current
repository requirements and explicitly accepted by the owner.

The existing automated ChatGPT Pro path accepts text only and cannot attach this
archive. Do not submit the request through that path without the packet. Use a Pro
session that supports attaching the generated archive, then paste
`PRO_FULL_REDESIGN_PROMPT.md` exactly.
