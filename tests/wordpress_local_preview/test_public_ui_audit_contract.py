from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "scripts/wordpress_public_ui_audit.function.js"
LOCAL_AUDIT = (
    ROOT
    / "changes/wordpress-local-preview-v1/browser/wordpress_local_preview_audit.function.js"
)
SHELL = ROOT / "scripts/check_wordpress_public_ui_playwright.sh"
INVENTORY = (
    ROOT / "changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json"
)
NAVIGATION = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/editorial-navigation.v3.json"
)


def _node_executable() -> str:
    node = shutil.which("node")
    assert node is not None
    return node


def test_generated_audit_inventory_is_public_safe_exact_v3_projection() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    navigation = json.loads(NAVIGATION.read_text(encoding="utf-8"))
    article_surfaces = {
        row["article_id"]: row
        for row in inventory["surfaces"]
        if row["kind"] == "article"
    }

    assert (
        inventory["source_navigation_sha256"] == navigation["source_navigation_sha256"]
    )
    assert inventory["source_portfolio_sha256"] == navigation["source_portfolio_sha256"]
    assert list(article_surfaces) == [
        row["article_id"] for row in navigation["articles"]
    ]
    for article in navigation["articles"]:
        surface = article_surfaces[article["article_id"]]
        related_ids = [row["article_id"] for row in article["related_articles"]]
        contextual_id = next(
            row["article_id"]
            for row in article["related_articles"]
            if row["relationship"] == "same_cluster"
        )
        assert surface == {
            "article_id": article["article_id"],
            "cluster_id": article["cluster_id"],
            "contextual_article_id": contextual_id,
            "kind": "article",
            "local_path": f"/{article['local_slug']}/",
            "production_path": f"/{article['production_slug']}/",
            "related_article_ids": related_ids,
            "surface_id": f"article-{article['article_code']}",
        }
    assert inventory["clusters"] == [
        {
            "anchor": row["anchor"],
            "article_ids": row["article_ids"],
            "cluster_id": row["cluster_id"],
        }
        for row in navigation["clusters"]
    ]
    assert [
        row["surface_id"] for row in inventory["surfaces"] if row["kind"] == "policy"
    ] == [
        "policy-about-ad-policy",
        "policy-comparison-policy",
        "policy-privacy-policy",
    ]
    serialized = INVENTORY.read_text(encoding="utf-8").casefold()
    for prohibited in (
        "credential",
        "secret",
        "snapshot_id",
        "product_id",
        "query_text",
    ):
        assert prohibited not in serialized


def test_public_audit_covers_home_ten_articles_and_three_pages_at_four_widths() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert len(inventory["surfaces"]) == 14
    assert len(inventory["viewports"]) == 4
    assert len(inventory["surfaces"]) * len(inventory["viewports"]) == 56
    for surface in inventory["surfaces"]:
        if surface["production_path"] != "/":
            assert surface["production_path"] not in source
    assert "const rawSurfaces = inventory?.surfaces;" in source
    assert "const rawClusters = inventory?.clusters;" in source
    assert "const widths = inventory?.viewports;" in source
    assert "path: surface.production_path" in source
    assert "response.status() !== 200" in source
    assert "response.url() !== expectedUrl" in source
    for marker in (
        "audit.homeClusters.length !== expectedClusters.length",
        "cluster.anchor !== expected.anchor",
        "cluster.links.length !== expected.paths.length",
        "link.pathname !== expected.paths[linkIndex]",
        "audit.internalLinks.length !== expectedInternalLinks.length",
        "surface.contextual_article_id",
        "surface.related_article_ids.map",
        "link.origin !== origin",
        "link.search !== ''",
        "link.hash !== ''",
        "page.request.get(link.href, { maxRedirects: 0 })",
        "linkResponse.status() !== 200",
        "linkResponse.url() !== link.href",
        "results.length !== surfaces.length * widths.length",
    ):
        assert marker in source
    assert "process.cwd()" not in source


def test_public_audit_shell_requires_all_56_artifacts_and_is_portable() -> None:
    source = SHELL.read_text(encoding="utf-8")
    assert 'readonly repository_root="$(CDPATH= cd -- "$script_directory/.."' in source
    assert "wordpress-audit-inventory.v3.json" in source
    assert "inventory.surfaces" in source
    assert "inventory.viewports" in source
    assert "artifact_name in $artifact_names" in source
    assert "for name in" not in source
    assert '[ "$#" -eq "$expected_count" ]' in source
    assert "/home/minami/rakuten" not in source
    subprocess.run(
        ["/usr/bin/bash", "-n", str(SHELL)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_local_preview_audit_fail_closes_every_surface_seo_head() -> None:
    source = LOCAL_AUDIT.read_text(encoding="utf-8")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert len(inventory["surfaces"]) == 14
    assert len({row["local_path"] for row in inventory["surfaces"]}) == 14
    assert len({row["production_path"] for row in inventory["surfaces"]}) == 14
    assert len(inventory["surfaces"]) * len(inventory["viewports"]) == 56
    for marker in (
        "new Set(rawSurfaces.map((surface) => surface.local_path)).size !== 14",
        "new Set(rawSurfaces.map((surface) => surface.production_path)).size !== 14",
        "const requiredWidths = [360, 390, 768, 1440]",
        "width !== requiredWidths[index]",
        "response.status() !== 200",
        "response.url() !== expectedUrl",
        "home: ['Organization', 'WebSite']",
        "article: ['Article', 'BreadcrumbList', 'Organization', 'WebSite']",
        "policy: ['BreadcrumbList', 'Organization', 'WebSite']",
        "['Product', 'Offer', 'Review', 'FAQPage']",
        "const normalized = value.trim();",
        "audit.canonicalLinks.length !== 1",
        "audit.canonicalLinks[0]?.rawHref !== audit.currentUrl",
        "audit.canonicalLinks[0]?.resolvedHref !== audit.currentUrl",
        "audit.titleCount !== 1",
        "audit.metaDescriptions.length !== 1",
        "audit.metaDescriptions[0] === ''",
        "values.length === 1 && values[0] !== ''",
        "audit.openGraph.title[0] !== audit.title",
        "audit.openGraph.description[0] !== audit.metaDescriptions[0]",
        "audit.openGraph.url[0] !== audit.currentUrl",
        "audit.openGraph.image[0] === expectedOpenGraphImageUrl",
        "openGraphImageResponse.status()",
        "openGraphImageResponse.url()",
        "openGraphImageResponseContentType === 'image/webp'",
        "openGraphImageResponseBodyBytes <= 2 * 1024 * 1024",
        "await openGraphImageResponse.dispose()",
        "openGraphImageValid",
        "audit.jsonLdScriptCount !== 1",
        "audit.jsonLdParseFailed",
        "invalidJsonLdTypes.length !== 0",
        "missingJsonLdTypes.length !== 0",
        "presentForbiddenJsonLdTypes.length !== 0",
        "localNoindexHeaderValid",
        "audit.metaRobots.length === 1",
        "metaRobotsDirectives.includes('noindex')",
        "metaRobotsDirectives.includes('nofollow')",
        "localNoindexMetaValid",
        "seoHeadAuditFailed",
        "results.length !== surfaces.length * widths.length",
        "await page.screenshot({ path: screenshot, fullPage: true })",
    ):
        assert marker in source
    assert ".split(/[/#:]/)" not in source
    assert "robots_index_follow" not in source
    subprocess.run(
        [_node_executable(), "--check", str(LOCAL_AUDIT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_local_preview_seo_head_predicate_rejects_malformed_inputs() -> None:
    script = r"""
const fs = require('fs');
const factory = eval(fs.readFileSync(process.argv[1], 'utf8'));
if (typeof factory.validateSeoHead !== 'function') {
  throw new Error('SEO_VALIDATOR_NOT_EXPOSED');
}

const expectedUrl = 'http://127.0.0.1:24261/';
const expectedOpenGraphImageUrl =
  'http://127.0.0.1:24261/wp-content/themes/'
  + 'kurashinoshirube-child/assets/images/home-hero.webp';
const baseline = {
  audit: {
    canonicalLinks: [{ rawHref: expectedUrl, resolvedHref: expectedUrl }],
    currentUrl: expectedUrl,
    jsonLdParseFailed: false,
    jsonLdScriptCount: 1,
    jsonLdTypes: ['Organization', 'WebSite'],
    metaDescriptions: ['検証済みの説明です。'],
    metaRobots: ['noindex, nofollow'],
    openGraph: {
      description: ['検証済みの説明です。'],
      image: [expectedOpenGraphImageUrl],
      title: ['検証済みタイトル'],
      url: [expectedUrl],
    },
    title: '検証済みタイトル',
    titleCount: 1,
  },
  expectedOpenGraphImageUrl,
  expectedUrl,
  forbiddenJsonLdTypes: ['Product', 'Offer', 'Review', 'FAQPage'],
  localNoindexHeaderValid: true,
  openGraphImageResponseValid: true,
  requiredJsonLdTypes: ['Organization', 'WebSite'],
};

const accepted = factory.validateSeoHead(structuredClone(baseline));
if (accepted.failed) throw new Error('VALID_SEO_HEAD_REJECTED');

function requireRejection(name, mutate) {
  const candidate = structuredClone(baseline);
  mutate(candidate);
  if (!factory.validateSeoHead(candidate).failed) {
    throw new Error(`${name}_ACCEPTED`);
  }
}

const cases = [
  ['wrong_current_url', (value) => { value.audit.currentUrl += 'wrong/'; }],
  ['missing_canonical', (value) => { value.audit.canonicalLinks = []; }],
  ['duplicate_canonical', (value) => {
    value.audit.canonicalLinks.push(structuredClone(value.audit.canonicalLinks[0]));
  }],
  ['relative_canonical', (value) => { value.audit.canonicalLinks[0].rawHref = '/'; }],
  ['wrong_resolved_canonical', (value) => {
    value.audit.canonicalLinks[0].resolvedHref += 'wrong/';
  }],
  ['duplicate_title', (value) => { value.audit.titleCount = 2; }],
  ['empty_title', (value) => { value.audit.title = ''; }],
  ['missing_description', (value) => { value.audit.metaDescriptions = []; }],
  ['empty_description', (value) => { value.audit.metaDescriptions = ['']; }],
  ['wrong_og_title', (value) => { value.audit.openGraph.title = ['wrong']; }],
  ['wrong_og_description', (value) => {
    value.audit.openGraph.description = ['wrong'];
  }],
  ['wrong_og_url', (value) => { value.audit.openGraph.url = [expectedUrl + 'wrong/']; }],
  ['offpath_og_image', (value) => {
    value.audit.openGraph.image = [expectedUrl + 'not-an-image'];
  }],
  ['unreachable_og_image', (value) => {
    value.openGraphImageResponseValid = false;
  }],
  ['duplicate_json_ld', (value) => { value.audit.jsonLdScriptCount = 2; }],
  ['malformed_json_ld', (value) => { value.audit.jsonLdParseFailed = true; }],
  ['evil_json_ld_type', (value) => {
    value.audit.jsonLdTypes.push('https://evil.invalid/Article');
  }],
  ['missing_json_ld_type', (value) => { value.audit.jsonLdTypes = ['Organization']; }],
  ['forbidden_json_ld_type', (value) => { value.audit.jsonLdTypes.push('Product'); }],
  ['missing_noindex_header', (value) => { value.localNoindexHeaderValid = false; }],
  ['missing_noindex_meta', (value) => { value.audit.metaRobots = []; }],
  ['conflicting_index_meta', (value) => {
    value.audit.metaRobots = ['noindex, nofollow, index'];
  }],
  ['conflicting_follow_meta', (value) => {
    value.audit.metaRobots = ['noindex, nofollow, follow'];
  }],
];
for (const [name, mutate] of cases) requireRejection(name, mutate);
"""
    subprocess.run(
        [_node_executable(), "-e", script, str(LOCAL_AUDIT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_local_preview_audit_rejects_duplicate_inventory_paths() -> None:
    script = r"""
const fs = require('fs');
const [auditPath, inventoryPath] = process.argv.slice(1);
const factory = eval(fs.readFileSync(auditPath, 'utf8'));
const baseline = JSON.parse(fs.readFileSync(inventoryPath, 'utf8'));

async function requireRejection(name, mutate) {
  const inventory = structuredClone(baseline);
  mutate(inventory);
  try {
    await factory({
      artifactDirectory: '/tmp/raos-local-preview-audit-test',
      inventory,
      origin: 'http://127.0.0.1:24261',
    })({});
  } catch (error) {
    if (error instanceof Error && error.message === 'RAOS_WORDPRESS_AUDIT_INVENTORY_INVALID') {
      return;
    }
    throw error;
  }
  throw new Error(`${name}_ACCEPTED`);
}

(async () => {
  await requireRejection('DUPLICATE_LOCAL_PATH', (inventory) => {
    inventory.surfaces[1].local_path = inventory.surfaces[0].local_path;
  });
  await requireRejection('DUPLICATE_PRODUCTION_PATH', (inventory) => {
    inventory.surfaces[1].production_path = inventory.surfaces[0].production_path;
  });
  await requireRejection('WRONG_VIEWPORT_ORDER', (inventory) => {
    inventory.viewports = [390, 360, 768, 1440];
  });
  await requireRejection('WRONG_VIEWPORT_VALUE', (inventory) => {
    inventory.viewports = [360, 390, 768, 1280];
  });
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
    subprocess.run(
        [_node_executable(), "-e", script, str(LOCAL_AUDIT), str(INVENTORY)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
