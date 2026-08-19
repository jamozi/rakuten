# Minimum Start runbook — no AWS

## Goal

Operate the first revenue-learning MVP from the owner workstation with no AWS dependency:

`Rakuten -> deterministic content -> WordPress.com draft -> human review -> human publish`

This runbook never authorizes automatic publication. The repository's existing ST-1703 WordPress.com implementation hard-codes `draft`, `publicize=false`, zero retry, a fixed numeric-site API route, and a durable intent/commit journal.

## Infrastructure boundary

Minimum Start does **not** require Terraform, ECS, RDS, S3, SQS, CloudFront, AWS IAM, GitHub OIDC, an AWS staging account, or an AWS Production account. Those components are post-MVP scaling options.

The owner workstation and WordPress.com are the runtime boundary for the first launch. GitHub remains source control; hosted CI availability is not an activation switch for live providers.

## 1. Offline readiness

From the exact repository checkout:

```bash
.venv/bin/python -I scripts/minimum_start_readiness.py
```

The command performs no network request and does not read credential values. It checks:

- the required ST-1703 WordPress.com runtime files are present as regular non-symlink files;
- the fixed WordPress.com secret directory/files, when present, have owner-private metadata;
- the bounded Rakuten live boundary has been integrated into the current checkout;
- AWS is not required.

Exit `0` means repository/credential metadata are ready for the next manual gates. Exit `2` means one or more value-free blocking reason codes remain.

`READY` is not permission to contact Rakuten or WordPress.com. It is only a local configuration result.

## 2. WordPress.com OAuth

When the readiness receipt reports `WORDPRESS_OAUTH_SETUP_REQUIRED`, use only the existing reviewed command:

```bash
make wordpresscom-oauth-setup
```

The implementation uses WordPress.com's Authorization Code flow and stores the three fixed aliases under `.secrets/wordpresscom-review-draft` with owner-only permissions. Do not pass a client secret, token, site ID, endpoint, or password on the command line.

## 3. Preview WordPress MVP state

Before any remote write:

```bash
make wordpresscom-preview-mvp
```

Treat the existing Wave 3 preview/journal result as authoritative for replay, pending intent, ambiguity, or mismatch. Do not delete or edit journal files to force a retry.

## 4. Rakuten live boundary

The Rakuten live implementation is separately gated. A real call is allowed only after its exact main-based implementation, approved secret/configuration boundary, and explicit operator authority are present.

Required operational behavior remains:

- one manually initiated request;
- page 1 and bounded hits;
- zero retry;
- zero background scheduling;
- zero persistence/publication side effect;
- no credential in CLI arguments, URLs, logs, receipts, or repository files;
- sanitized receipt only.

A timeout or ambiguous request attempt is terminal for that invocation. Do not automatically retry.

## 5. Prepare WordPress.com MVP drafts

After reviewing the content packet and confirming no other remote writer is active, use the existing reviewed command:

```bash
make wordpresscom-prepare-mvp-drafts
```

The command intentionally requires the exact remote-writer quiescence affirmation. The journal must be allowed to classify existing committed or ambiguous operations before any network request.

No automation may substitute `publish`, `schedule`, `delete`, media upload, taxonomy mutation, sharing/publicize activation, or a generic WordPress command.

## 6. Human review and publication

Review the resulting drafts in WordPress.com. Check at minimum:

- title/content and links;
- affiliate disclosure and affiliate destinations;
- product facts against current source evidence;
- layout on mobile and desktop;
- `draft` state;
- comments/pings policy required by the current Wave 3 contract.

Publication is a separate human WordPress.com action. The Minimum Start operator does not publish automatically.

## Recovery rules

- `COMMITTED` exact replay: use the existing receipt; no second POST.
- `INTENT` or ambiguous network outcome: stop and inspect; never retry automatically.
- credential metadata invalid: fix file ownership/permissions without printing values.
- source/runtime binding invalid: reconcile the exact repository revision; do not bypass checks.
- Rakuten ambiguous attempt: stop; no automatic second provider request.
- WordPress 401/403/404/redirect/schema failure: stop before mutation or leave the journal state intact according to the existing adapter.

## MVP exit criterion

Minimum Start is operational when one authorized Rakuten acquisition can feed reviewed deterministic content, the existing ST-1703 path creates/replays a real WordPress.com draft, the owner verifies it, and publication can be performed manually without AWS infrastructure.
