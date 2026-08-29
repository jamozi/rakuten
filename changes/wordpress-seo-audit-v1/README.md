# WordPress SEO audit v1

This change adds a bounded, read-only audit of the production WordPress public
surface. The closed inventory is the home page, the ten production slugs read
from Editorial V3, and the three fixed policy pages in the tracked contract.
Article URLs are not duplicated in another tracked list.

The audit checks a non-redirecting `200` response, self-canonical, index/follow
robots directives, title and description, Open Graph title/description/URL/image,
and the required JSON-LD types for each page role. `Product`, `Offer`, `Review`,
and `FAQPage` are rejected. `/llms.txt` must remain absent. The union of sitemap
content URLs must equal the ten articles plus the three fixed pages; the home page
is checked separately. `robots.txt` must not disallow any inventory URL.

All HTTP is anonymous and read-only. Redirect following is disabled, response
count and bytes are bounded, sitemap child URLs must be query-free and on the
exact production origin, and the report stores evidence hashes rather than HTML.

## Owner-private run

Use the repository virtual environment and write only below the ignored private
directory:

```sh
.venv/bin/python scripts/raos_wordpress_seo_audit.py \
  --output .secrets/wordpress-seo-audit-v1/report.json
```

The output directory must be mode `0700`; report and optional recorded index
input must be mode `0600`. To bind an owner-recorded GSC URL Inspection result:

```sh
.venv/bin/python scripts/raos_wordpress_seo_audit.py \
  --index-input .secrets/wordpress-seo-audit-v1/url-inspection.json \
  --output .secrets/wordpress-seo-audit-v1/report.json
```

The recorded input has schema `RAOS_OWNER_PRIVATE_URL_INSPECTION_V1`, an
`observed_at` UTC timestamp, and exactly fourteen `results` keyed by the clean
inventory URLs. Each result supplies `state` and an optional `last_crawl_at`.
No credential, raw search query, URL query string, or response body belongs in
tracked files or in the generated report. Without this input, every page reports
index state as `UNAVAILABLE`; public HTTP observations never imply GSC state.
