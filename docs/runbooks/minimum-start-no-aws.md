# Minimum Start runbook — no AWS

> This historical runbook operates the WordPress.com target
> `kurashierabinote.wordpress.com`. The owner-selected self-hosted target
> `https://kurashinoshirube.com` is a separate provider/authentication/journal
> boundary. For that path use
> `docs/runbooks/self-hosted-minimum-start.md` and only the distinct
> Story-local commands under
> `make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile <target>`.
> The root Makefile intentionally has no self-hosted target because its bytes
> are bound by the historical WordPress.com runtime inventory. Do not
> substitute the custom domain into any `wordpresscom-*` command.

## Goal

Operate the first revenue-learning MVP from the owner workstation with no AWS dependency:

`approved fixed content -> WordPress.com draft -> affiliate slot completion -> validation -> human review -> human publish`

The first article/content packet already exists in ST-1703 Wave 3, including three product comparison slots. Therefore live Rakuten API automation is useful post-launch work, but is **not required to create and publish the first reviewed article**.

This runbook never authorizes automatic publication. The repository's existing ST-1703 WordPress.com implementation hard-codes `draft`, `publicize=false`, zero retry, a fixed numeric-site API route, and a durable intent/commit journal.

## Infrastructure boundary

Minimum Start does **not** require Terraform, ECS, RDS, S3, SQS, CloudFront, AWS IAM, GitHub OIDC, an AWS staging account, or an AWS Production account. Those components are post-MVP scaling options.

The owner workstation and WordPress.com are the runtime boundary for the first launch. GitHub remains source control; hosted CI availability is not an activation switch for the existing manual WordPress.com workflow.

## 1. Offline readiness

Run the operator command only from the exact launcher-bound repository root `/home/minami/rakuten`, not from a linked worktree, copied checkout, or alternate path:

```bash
.venv/bin/python -I scripts/minimum_start_readiness.py
```

The command performs no network request and does not read credential values. It checks:

- the physical repository root is exactly `/home/minami/rakuten`, is owner-owned, is not a symlink, and the fixed secret path has no symlinked ancestor;
- every required ST-1703 WordPress.com runtime path has no symlinked ancestor and
  ends in a regular non-symlink file;
- `.secrets` and `.secrets/wordpresscom-review-draft`, when present, are owner-owned non-symlink directories with mode `0700`;
- all three fixed OAuth aliases, when present, are owner-owned regular non-symlink files with mode `0600` and a metadata-known size between 1 and 4097 bytes;
- AWS is not required;
- Rakuten live availability is reported separately as optional post-launch capability.

Exit `0` means the local WordPress minimum-start prerequisites represented by this check are ready. Exit `2` means a value-free WordPress/runtime blocker remains.

The receipt's `next_commands` is deliberately state-aware:

- missing OAuth setup metadata, with a valid local runtime and no malformed secret-store structure: only `make wordpresscom-oauth-setup`;
- repository-root mismatch (`WORDPRESS_REPOSITORY_ROOT_INVALID`) or invalid runtime/secret-store structure: no next command;
- `READY`: only the read-only `make wordpresscom-preview-mvp` command.

There is no command-line or environment override for the expected repository root. The test API injects an expected root only for isolated fixtures; non-test `main()` always supplies `/home/minami/rakuten`. The receipt never recommends draft preparation from readiness alone. `READY` is not permission to contact WordPress.com or perform a remote write; it is only local configuration evidence. The counters remain zero for network requests, secret-value reads, external writes, and publication actions.

## 2. WordPress.com OAuth

When the readiness receipt reports `WORDPRESS_OAUTH_SETUP_REQUIRED` and lists the following exact command, use only the existing reviewed setup path:

```bash
make wordpresscom-oauth-setup
```

The implementation uses WordPress.com's Authorization Code flow and stores the three fixed aliases under `.secrets/wordpresscom-review-draft` with owner-only permissions. Do not pass a client secret, token, site ID, endpoint, or password on the command line.

OAuth setup is an external/browser operation and remains separately owner-controlled. Do not run it when the receipt has an invalid runtime or secret-store reason and an empty `next_commands` list.

## 3. Preview WordPress MVP state

Before any remote write:

```bash
make wordpresscom-preview-mvp
```

This is the sole command listed by a fully `READY` offline receipt. Treat the existing Wave 3 preview/journal result as authoritative for replay, pending intent, ambiguity, or mismatch. Do not delete or edit journal files to force a retry.

## 4. Prepare the existing MVP drafts

Review the committed Wave 3 content packet first. It contains the initial suitcase comparison article plus the required policy/support pages. The article has three explicit affiliate slots for:

- ACE クレスタ 06316
- ace.TOKYO LABEL ディフェレンス 05721
- PROTECA マックスパス4 01471

The existing contract keeps ranking independent from affiliate commission, price, points, and inventory.

Draft preparation is not authorized by the offline readiness receipt or by preview readiness. After separately reviewing the read-only preview and confirming no other remote writer is active, use the existing gated command only under its own remote-write authority:

```bash
make wordpresscom-prepare-mvp-drafts
```

The command intentionally requires the exact remote-writer quiescence affirmation. The journal must classify existing committed or ambiguous operations before any network request.

No automation may substitute `publish`, `schedule`, `delete`, media upload, taxonomy mutation, sharing/publicize activation, or a generic WordPress command.

## 5. Complete affiliate slots manually for launch

Use the official Rakuten affiliate tooling to generate the approved affiliate HTML for the three named products and paste it only inside the marked Wave 3 affiliate slots. Do not change the surrounding reviewed article bytes.

The existing Wave 3 validator accepts a filled article only when all three slot interiors match its closed grammar and the hash of every byte outside those slots remains unchanged. A valid filled article is treated as an exact acceptable state rather than being overwritten back to placeholders.

After filling the slots, run the read-only preview again:

```bash
make wordpresscom-preview-mvp
```

Do not publish unless the preview recognizes the filled article without object drift, affiliate validation failure, journal ambiguity, or discussion/sharing drift.

Before publication, verify each link reaches the intended product and that no commission/rate value influenced product ordering or evaluation.

Automating affiliate-link generation and product freshness through Rakuten API is post-launch optimization, not a blocker for the first article.

## 6. Final public-domain check

Resolve issue #91 before the human publication action. The repository currently uses one exact WordPress.com response host; do not widen it to multiple guessed hosts. Confirm the intended custom domain, HTTPS behavior, and the exact hostname WordPress returns for the numeric site.

## 7. Human review and publication

Review the resulting drafts in WordPress.com. Check at minimum:

- title/content and the three affiliate destinations;
- affiliate disclosure;
- product facts against the committed/current primary-source evidence;
- layout on mobile and desktop;
- `draft` state before the human action;
- comments/pings policy required by the current Wave 3 contract.

Publication is a separate human WordPress.com action. The Minimum Start operator does not publish automatically.

## 8. Post-launch Rakuten automation

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
- affiliate validation/object drift after manual fill: fix only the three slot interiors; do not edit surrounding reviewed article content.
- WordPress 401/403/404/redirect/schema failure: stop according to the existing adapter/journal state.
- future Rakuten ambiguous attempt: stop; no automatic second provider request.

## MVP exit criterion

Minimum Start is operational when the existing ST-1703 Wave 3 content is prepared as real WordPress.com drafts, the three affiliate slots are completed with official Rakuten affiliate links and pass read-only preview validation, the final public-domain binding is confirmed, the owner reviews the article/pages, and publication can be performed manually without AWS infrastructure or live Rakuten API automation.
