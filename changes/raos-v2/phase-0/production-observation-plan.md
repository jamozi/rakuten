# RAOS V2 production observation plan

Status: **NOT_EXECUTED**. This is a read-only plan, not permission to access an
admin surface or change production.

## Allowed public observation

- Credential- and cookie-free HTTPS GET/HEAD against `kurashinoshirube.com` only.
- Known public URLs and same-origin sitemap URLs, with a hard item/byte/time cap.
- Record status, one-hop redirect evidence, canonical, robots, one H1, sitemap
  membership, body SHA-256 and JST observation time. Never store the response body.
- Capture home and confirmed-public pilot reader surfaces at 390, 768 and 1440px.
  Policy pages receive metadata-only observation.

## Denied surfaces and actions

Admin/login/preview/private/query-bearing URLs, credentials, cookies, WordPress or
Yoast writes, plugin/theme changes, publication, deployment and provider writes are
denied. A changed live state never triggers delete, unpublish, noindex or redirect.

## Human/external boundary

WordPress inventory, backup/restore, deployment, credentials and production
analytics configuration remain `NOT_EXECUTED` until separately authorized. Local
fixtures and rollback simulation may be executed and labelled `PASSED_LOCAL`.

Backlog: B-V2-004. Tests: T-V2-004, T-V2-005, T-V2-039.
