# ST-1001 — local SSR public shell V2

Local status: `LOCAL_IMPLEMENTATION_COMPLETE` after the recorded checks in the
completion file. Canonical Registry state is unchanged.

The historical V1 headless candidate remains intact. V2 adds the exact
`PUB-004` through `PUB-007` routes as Next.js App Router server components:

- `/editorial-policy`
- `/affiliate-disclosure`
- `/privacy`
- `/about`

Every route is force-dynamic SSR, noindex/nofollow, readable without client
JavaScript, and backed by the versioned recorded contract. The shared header,
navigation, breadcrumb, main, article, status notice, sections, and footer use
native semantic HTML. The design is mobile-first, uses the repository's
unbranded semantic colors and system fonts, preserves visible focus and text
status labels, has no animation, and reflows at 320 CSS px.

`OD-002` remains unresolved: no site name, domain, operator, contact,
`metadataBase`, canonical URL, social metadata, or external publication is
selected. `OD-012` remains unresolved: nonessential tracking, Analytics,
Beacon, Cookie writes, and first-party events are disabled. Legal/privacy/
retention/operator text that requires an owner is visibly marked as pending.
The local copy does not resolve those decisions.

The renderer consumes no request data, raw HTML, arbitrary URL, redirect,
provider input, event, credential, or internal projection. Exact route response
headers disable indexing and scripts, frame embedding, referrer leakage,
unneeded browser capabilities, and storage caching. Navigation consists only
of the four relative Story routes.

Generate and check owner artifacts with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  .venv/bin/python scripts/build_st1001_public_app_shell.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  .venv/bin/python scripts/build_st1001_public_app_shell.py --check
```

Local Next production build and loopback Chromium/axe evidence demonstrate the
implemented runtime in this worktree only. They do not satisfy formal
`TST-022` or `TST-023`, do not establish WCAG conformance, and grant no live,
staging, publication, release, or Production authority.
