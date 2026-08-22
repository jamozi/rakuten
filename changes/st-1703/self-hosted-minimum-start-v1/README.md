# ST-1703 — SELF_HOSTED_MINIMUM_START_V1

This directory owns one reversible, owner-local preparation slice for the
self-hosted site `https://kurashinoshirube.com` and brand
`暮らしのしるべ`. It is separate from the historical WordPress.com target
`kurashierabinote.wordpress.com` and does not change any historical exact-hash
handoff or artifact.

The durable design record is `DESIGN_HANDOFF_V1.yaml`. It records owner inputs
for this local slice but does not resolve the Canonical Open Decision registry,
complete ST-1703, authorize a provider call, or constitute staging, formal TST,
publication, release, or Production evidence.

## Owned boundaries

- `content/first-suitcase-comparison.v1.json` is the first self-hosted
  article packet. It is bound to the exact origin, draft-only authority, three
  pending official Rakuten affiliate slots, editorial/affiliate disclosure,
  source records, freshness caveats, and a closed SEO/structured-data policy.
- `theme/kurashinoshirube-child/` is the Twenty Twenty-Five child-theme source.
  It contains presentation only: no tracking, remote font/script/image load,
  publication, upload, taxonomy, plugin activation, or generic HTTP behavior.
- `theme/kurashinoshirube-child/raos-assets.v1.json` owns the two final image
  requirements and their closed prompts. Both images intentionally remain
  `PENDING_FINAL_ASSET`; no image provider was called by this slice.
- `generated/kurashinoshirube-child.zip` is the only theme package output. It
  is absent until both final images are present and SHA-256-bound.

The generated package identifies its owner through the embedded
`raos-assets.v1.json`:

- owner generator: `scripts/build_st1703_self_hosted_theme.py`
- generation command:
  `make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-package`
- no-write check:
  `make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-check`

Do not edit the zip by hand. Update the owned theme source/manifest, then run
the generator. The source-only check is available while final assets remain
pending:

```bash
make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile theme-source-check
```

The expected result in this slice is `SOURCE_VALID` with
`package_ready=false`. Package and package-check commands fail closed until the
final asset gate is completed.

## Runtime boundary

The implementation keeps `domain <- application <- adapters/framework`:

- domain/journal values can represent `CREATE_DRAFT` and an exact-positive-ID
  future `UPDATE_DRAFT`, always with `status=draft`. Update is
  `LOCAL_INTERFACE_ONLY_ACTIVATION_DISABLED` in this slice;
- the application port exposes one draft operation and no publish, schedule,
  delete, media, taxonomy, theme, plugin, or generic HTTP capability;
- the self-hosted create adapter reuses the existing pure official WordPress
  Posts REST request/response value boundary, while credentials, HTTPS, and
  the durable journal are independent
  of the WordPress.com OAuth/numeric-site runtime;
- the outward HTTPS adapter exposes create only and rejects update before
  credential access or network construction. It uses Application Password
  Basic authentication only for the exact origin, one direct POST, system TLS,
  bounded timeouts/response
  bytes, strict JSON, no redirect/proxy inheritance, and zero retry;
- the journal durably fsyncs `INTENT` before the sole attempt and `COMMITTED`
  after strict response validation. Exact committed replay reads no credential
  and performs no network operation. Pending, ambiguous, mismatched, or
  tampered state fails closed.

Credentials are accepted only through hidden `/dev/tty` input and stored at
`.secrets/wordpress-owner-local/credentials.v1.json`. The schema is exact and
the path requires owner/current-UID, regular non-symlink storage with `0700`
directories and a `0600` file. No credential value belongs in argv,
environment variables, logs, tracked files, or chat.

The WordPress principal must be a dedicated least-privilege draft writer, not
an owner/administrator/editor account: it must have only the capabilities
needed to create its own draft and must lack publish, edit-published, delete,
media-upload, plugin/theme and administration capabilities. Role/capability
proof is an external owner gate and is not claimed by offline code.

Operational commands and status layers are documented in
`docs/runbooks/self-hosted-minimum-start.md`.
They intentionally live in the Story-local Makefile because the root Makefile
is byte/hash-bound by the active historical WordPress.com runtime inventory.
This slice does not add or replace a root Make target.

## Explicit blockers and exclusions

- Three official Rakuten affiliate destinations remain pending. Each final
  anchor must be direct, match the named product, and carry
  `rel="sponsored nofollow"`; this slice supplies no fabricated link.
- Two final editorial WebP assets remain pending. Placeholder or synthetic
  test bytes do not satisfy package readiness.
- Live read-only credential proof, draft creation, theme activation,
  consent/analytics activation, human review/publication, formal
  TST-021/TST-022/TST-032, staging, release, and Production are not executed.
- The planned 14-day/five-article pilot belongs to ST-1704, not this slice.

Local unit tests and source checks are implementation evidence only. They do
not attest to the live site, external credentials, a public sitemap, theme
appearance, analytics, revenue, or Production readiness.
