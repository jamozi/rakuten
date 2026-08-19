# Minimum Start runbook — no AWS

## Goal

Operate the first revenue-learning MVP from the owner workstation with no AWS dependency:

`approved fixed content -> WordPress.com draft -> affiliate slot completion -> human review -> human publish`

The first article/content packet already exists in ST-1703 Wave 3, including three product comparison slots. Therefore live Rakuten API automation is useful post-launch work, but is **not required to create and publish the first reviewed article**.

This runbook never authorizes automatic publication. The repository's existing ST-1703 WordPress.com implementation hard-codes `draft`, `publicize=false`, zero retry, a fixed numeric-site API route, and a durable intent/commit journal.

## Infrastructure boundary

Minimum Start does **not** require Terraform, ECS, RDS, S3, SQS, CloudFront, AWS IAM, GitHub OIDC, an AWS staging account, or an AWS Production account. Those components are post-MVP scaling options.

The owner workstation and WordPress.com are the runtime boundary for the first launch. GitHub remains source control; hosted CI availability is not an activation switch for the existing manual WordPress.com workflow.

## 1. Offline readiness

From the exact repository checkout:

```bash
.venv/bin/python -I scripts/minimum_start_readiness.py
```

The command performs no network request and does not read credential values. It checks:

- the required ST-1703 WordPress.com runtime files are regular non-symlink files;
- the fixed WordPress.com secret directory/files, when present, have owner-private metadata;
- AWS is not required;
- Rakuten live availability is reported separately as optional post-launch capability.

Exit `0` means the local WordPress minimum-start prerequisites represented by this check are ready. Exit `2` means a value-free WordPress/runtime blocker remains.

`READY` is not permission to contact WordPress.com. It is only local configuration evidence.

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

## 4. Prepare the existing MVP drafts

Review the committed Wave 3 content packet first. It contains the initial suitcase comparison article plus the required policy/support pages. The article has three explicit affiliate slots for:

- ACE クレスタ 06316
- ace.TOKYO LABEL ディフェレンス 05721
- PROTECA マックスパス4 01471

The existing contract keeps ranking independent from affiliate commission, price, points, and inventory.

After confirming no other remote writer is active, use:

```bash
make wordpresscom-prepare-mvp-drafts
```

The command intentionally requires the exact remote-writer quiescence affirmation. The journal must classify existing committed or ambiguous operations before any network request.

No automation may substitute `publish`, `schedule`, `delete`, media upload, taxonomy mutation, sharing/publicize activation, or a generic WordPress command.

## 5. Complete affiliate slots manually for launch

For Minimum Start, use the official Rakuten affiliate tooling to generate the approved affiliate HTML for the three named products and paste it only into the marked Wave 3 affiliate slots. Do not change the surrounding reviewed article bytes during this step.

Before publication, verify each link reaches the intended product and that no commission/rate value has influenced product ordering or evaluation.

Automating affiliate-link generation and product freshness through Rakuten API is post-launch optimization, not a blocker for the first article.

## 6. Human review and publication

Review the resulting drafts in WordPress.com. Check at minimum:

- title/content and the three affiliate destinations;
- affiliate disclosure;
- product facts against the committed/current primary-source evidence;
- layout on mobile and desktop;
- `draft` state before the human action;
- comments/pings policy required by the current Wave 3 contract.

Publication is a separate human WordPress.com action. The Minimum Start operator does not publish automatically.

## 7. Post-launch Rakuten automation

After the first article is live, integrate the bounded Rakuten live path for freshness and lower manual maintenance. A real Rakuten API call remains separately gated and must preserve:

- one manually initiated bounded request while the feature is introduced;
- zero retry after timeout/ambiguity;
- no background scheduling until separately reviewed;
- no credential in CLI arguments, URLs, logs, receipts, or repository files;
- no review-body ingestion;
- canonical item fields only for later content/freshness logic.

Rakuten automation must not become publication authority.

## Recovery rules

- `COMMITTED` exact WordPress replay: use the existing receipt; no second POST.
- `INTENT` or ambiguous WordPress network outcome: stop and inspect; never retry automatically.
- credential metadata invalid: fix file ownership/permissions without printing values.
- source/runtime binding invalid: reconcile the exact repository revision; do not bypass checks.
- WordPress 401/403/404/redirect/schema failure: stop according to the existing adapter/journal state.
- future Rakuten ambiguous attempt: stop; no automatic second provider request.

## MVP exit criterion

Minimum Start is operational when the existing ST-1703 Wave 3 content is prepared as real WordPress.com drafts, the three affiliate slots are completed with official Rakuten affiliate links, the owner reviews the article/pages, and publication can be performed manually without AWS infrastructure or live Rakuten API automation.
