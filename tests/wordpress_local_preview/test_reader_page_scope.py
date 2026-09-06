"""Pure Python/Node fixtures for the mixed reader browser bridge; never starts a browser."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import shutil
import sys
import subprocess

import pytest

from tests.verified_incremental_v1.test_reader_page_preview import (
    browser_owners,
    page_inputs,
    rehash,
    results_for,
    write_preview,
)
from tests.verified_incremental_v1.test_preview import metadata_for
from raos.application.editorial.verified_incremental_preview_v1 import (
    build_mixed_preview,
)

ROOT = Path(__file__).resolve().parents[2]
BROWSER = ROOT / "changes/wordpress-local-preview-v1/browser"
AUDIT = BROWSER / "wordpress_local_preview_audit.function.js"
CHECK = BROWSER / "check.sh"
INVENTORY = (
    ROOT / "changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json"
)


def reader_preview(tmp_path, *, hubs=True, page_selection=None, published_hubs=()):
    inventory = json.loads(INVENTORY.read_bytes())
    known_hubs = tuple(row["local_path"].strip("/") for row in inventory["reader_hubs"])
    data = page_inputs(hubs=known_hubs if hubs else ())
    if page_selection is not None:
        data["page_overrides"] = {
            slug: page
            for slug, page in data["page_overrides"].items()
            if slug in page_selection
        }
    for document in data["snapshot"]["documents"]:
        if document["slug"] in published_hubs:
            document["status"] = "publish"
            rehash(document)
    old_posts = [
        row for row in data["snapshot"]["documents"] if row["post_type"] == "post"
    ]
    article_rows = [row for row in inventory["surfaces"] if row["kind"] == "article"]
    source_posts, source_articles, article_ids = [], {}, {}
    for index, (document, surface) in enumerate(
        zip(old_posts, article_rows, strict=True)
    ):
        slug = surface["production_path"].strip("/")
        document.update(
            slug=slug,
            block_markup=f'<article class="product-profile" data-raos-product-id="PRD-{index}"><p>Preserved evidence</p></article>',
        )
        rehash(document)
        source_posts.append(
            {
                "article_id": surface["article_id"],
                "slug": surface["local_path"].strip("/"),
                "title": "Unused new title",
                "excerpt": "Unused new excerpt",
                "category": "移動",
                "date": "2026-08-29 00:00:00",
                "content_file": f"articles/{slug}.html",
            }
        )
        source_articles[slug] = b"<p>Unselected new draft</p>"
        article_ids[slug] = surface["article_id"]
    data.update(
        source_posts={**data["source_posts"], "posts": source_posts},
        source_articles=source_articles,
        article_ids_by_slug=article_ids,
    )
    data["snapshot"]["public_metadata"] = metadata_for(
        [row for row in data["snapshot"]["documents"] if row["status"] == "publish"]
    )
    result = build_mixed_preview(**data)
    root = write_preview(tmp_path, result)
    scope_owner, report = browser_owners()
    scope = scope_owner.load_scope(root, inventory)
    return inventory, result, scope, root, report


NODE = """
const fs = require('fs');
const factory = eval(fs.readFileSync(process.argv[1], 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  try {
    if (input.action === 'scope') {
      const result = factory.validateIncrementalScope({
        publicationProfile: 'verified-incremental', linkMode: 'standard-api',
        incrementalScope: input.scope,
        articleIds: input.inventory.surfaces.filter(row => row.kind === 'article').map(row => row.article_id),
        coreSurfaces: input.inventory.surfaces,
        categorySurfaces: input.inventory.local_surfaces.filter(row => row.kind === 'archive' && row.archive_type === 'category'),
      });
      process.stdout.write(JSON.stringify({valid: true, scope: result}));
    } else if (input.action === 'article') {
      process.stdout.write(JSON.stringify(factory.validateIncrementalArticle(input.article)));
    } else {
      const page = {
        on() { throw new Error('FIXTURE_AFTER_VALIDATION'); },
        context() { return { browser() { return {
          async newContext() { return { async newPage() { return page; }, async close() {} }; },
        }; } }; },
      };
      await factory({
        artifactDirectory: '/tmp/synthetic-reader-browser', axeSource: 'x'.repeat(100001),
        inventory: input.inventory, origin: 'http://127.0.0.1:18080',
        publicationProfile: 'verified-incremental', linkMode: 'standard-api',
        incrementalScope: input.scope, workers: input.workers || 1,
        selectedSurfaceIds: input.selection || null,
      })(page);
      throw new Error('UNEXPECTED_BROWSER_COMPLETION');
    }
  } catch (error) {
    process.stdout.write(JSON.stringify({valid: error.message === 'FIXTURE_AFTER_VALIDATION', error: error.message}));
  }
})();
"""


def node(payload):
    binary = shutil.which("node")
    assert binary
    result = subprocess.run(
        [binary, "-e", NODE, str(AUDIT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert result.stderr == ""
    return json.loads(result.stdout)


def promoted(tmp_path, *, hubs=True):
    inventory, result, scope, root, report = reader_preview(tmp_path, hubs=hubs)
    return (
        report.bind_reader_inventory(inventory, dict(result.binding)),
        result,
        scope,
        root,
    )


@pytest.mark.parametrize("hubs", [False, True])
def test_true_page_only_scope_and_registered_core_inventory_reach_browser_boundary(
    tmp_path, hubs
):
    inventory, _, scope, _ = promoted(tmp_path, hubs=hubs)
    assert scope["selected_article_ids"] == []
    assert (
        len(inventory["surfaces"]) == 29 if hubs else len(inventory["surfaces"]) == 14
    )
    assert len(inventory["local_surfaces"]) == 12
    assert node({"action": "scope", "inventory": inventory, "scope": scope})["valid"]
    assert node({"inventory": inventory, "scope": scope})["valid"]


@pytest.mark.parametrize("workers", [1, 3])
def test_page_only_scope_preserves_complete_inventory_through_parallel_workers(
    tmp_path, workers
):
    inventory, _, scope, _ = promoted(tmp_path)
    assert node({"inventory": inventory, "scope": scope, "workers": workers})["valid"]
    selected = [
        row["surface_id"] for row in inventory["surfaces"] + inventory["local_surfaces"]
    ]
    selected.remove("hub-categories")
    result = node(
        {
            "inventory": inventory,
            "scope": scope,
            "workers": workers,
            "selection": selected,
        }
    )
    assert result["valid"] is False
    assert result["error"] == "RAOS_WORDPRESS_BROWSER_SELECTION_INVALID"


@pytest.mark.parametrize(
    "mutation",
    [
        "empty_selection",
        "missing_core",
        "missing_pages",
        "duplicate_pages",
        "unsorted_pages",
        "arbitrary_page",
        "local_guide",
        "missing_hub",
        "extra_hub",
        "missing_article_evidence",
        "wrong_article_identity",
        "extra_scope_field",
    ],
)
def test_reader_scope_rejects_widening_and_missing_identity_evidence(
    tmp_path, mutation
):
    inventory, _, scope, _ = promoted(tmp_path)
    if mutation == "empty_selection":
        scope["reader_page_slugs"] = []
    elif mutation == "missing_core":
        del scope["core_document_slugs"]
    elif mutation == "missing_pages":
        del scope["reader_page_slugs"]
    elif mutation == "duplicate_pages":
        scope["reader_page_slugs"].append(scope["reader_page_slugs"][0])
    elif mutation == "unsorted_pages":
        scope["reader_page_slugs"].reverse()
    elif mutation == "arbitrary_page":
        scope["reader_page_slugs"].append("arbitrary")
    elif mutation == "local_guide":
        scope["core_document_slugs"].append("local-preview-extra-guide")
    elif mutation == "missing_hub":
        scope["core_document_slugs"].remove("categories")
    elif mutation == "extra_hub":
        inventory["surfaces"] = [
            row
            for row in inventory["surfaces"]
            if row["surface_id"] != "hub-categories"
        ]
    elif mutation == "missing_article_evidence":
        scope["articles"].pop()
    elif mutation == "wrong_article_identity":
        scope["articles"][0]["article_id"] = "unregistered"
    else:
        scope["unbound_pages"] = ["arbitrary"]
    result = node({"action": "scope", "inventory": inventory, "scope": scope})
    assert not result["valid"], result
    assert result["error"] == "RAOS_WORDPRESS_INCREMENTAL_SCOPE_INVALID"


@pytest.mark.parametrize(
    "mutation",
    [
        "arbitrary_core",
        "arbitrary_local",
        "hub_path",
        "hub_kind",
        "hub_identifier",
        "duplicate_hub",
        "catalog_missing",
        "catalog_extra",
        "article_identity",
        "width_missing",
        "width_duplicate",
    ],
)
def test_browser_inventory_accepts_only_exact_hubs_and_existing_ui_routes(
    tmp_path, mutation
):
    inventory, _, scope, _ = promoted(tmp_path)
    hub = next(row for row in inventory["surfaces"] if row["kind"] == "reader_hub")
    if mutation == "arbitrary_core":
        inventory["surfaces"].append(
            {
                "kind": "policy",
                "surface_id": "extra",
                "production_path": "/extra/",
                "local_path": "/extra/",
            }
        )
    elif mutation == "arbitrary_local":
        inventory["local_surfaces"].append(
            {"kind": "reader_hub", "surface_id": "hub-extra", "local_path": "/extra/"}
        )
    elif mutation == "hub_path":
        hub["local_path"] = "/guides/?scope=arbitrary"
    elif mutation == "hub_kind":
        hub["kind"] = "local_guide"
    elif mutation == "hub_identifier":
        hub["surface_id"] = "local-guide"
    elif mutation == "duplicate_hub":
        inventory["surfaces"].append(deepcopy(hub))
    elif mutation == "catalog_missing":
        inventory["reader_hubs"].pop()
    elif mutation == "catalog_extra":
        inventory["reader_hubs"].append(
            {"kind": "reader_hub", "surface_id": "hub-extra", "local_path": "/extra/"}
        )
    elif mutation == "article_identity":
        next(row for row in inventory["surfaces"] if row["kind"] == "article")[
            "article_id"
        ] = "unregistered"
    elif mutation == "width_missing":
        inventory["viewports"].remove(1024)
    else:
        inventory["viewports"][-1] = 390
    assert node({"inventory": inventory, "scope": scope})["valid"] is False


def wrapper_blocks():
    source = CHECK.read_text()
    python = source.split("<<'PYREADERINVENTORY' || refuse\n", 1)[1].split(
        "\nPYREADERINVENTORY", 1
    )[0]
    javascript = re.findall(r""""\$node_bin" -e '\n(.*?)\n' """, source, re.S)
    assert len(javascript) == 2
    return python, javascript


def bound_files(tmp_path, *, hubs=True):
    from scripts.raos_wordpress_browser_plan import browser_plan

    inventory, result, scope, _root, report = reader_preview(tmp_path, hubs=hubs)
    bound = report.bind_reader_inventory(inventory, dict(result.binding))
    inputs = {
        **result.binding,
        "scope": scope,
        "preparation_binding_sha256": scope["preparation_binding_sha256"],
        "audit_inventory_sha256": report.sha(INVENTORY.read_bytes()),
        "browser_plan": browser_plan(bound),
    }
    binding_path, scope_path = tmp_path / "run-binding.json", tmp_path / "scope.json"
    binding_path.write_bytes(report.canonical({"inputs": inputs}))
    scope_path.write_bytes(report.canonical(scope))
    return bound, report, inputs, binding_path, scope_path


@pytest.mark.parametrize("hubs", [False, True])
def test_wrapper_passes_bound_inventory_and_exact_scope_to_capture(tmp_path, hubs):
    bound, report, inputs, binding_path, scope_path = bound_files(tmp_path, hubs=hubs)
    python, javascript = wrapper_blocks()
    bridge = subprocess.run(
        [
            sys.executable,
            "-c",
            python,
            str(BROWSER),
            str(INVENTORY),
            str(binding_path),
            str(scope_path),
        ],
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert json.loads(bridge.stdout) == bound
    assert report.bind_reader_inventory(bound, inputs) == bound
    assert inputs["audit_inventory_sha256"] == report.sha(INVENTORY.read_bytes())
    runtime_inventory = tmp_path / "runtime-inventory.json"
    runtime_inventory.write_bytes(bridge.stdout)
    axe = tmp_path / "axe.js"
    axe.write_text("x" * 100001)
    factory = tmp_path / "inspect-options.js"
    factory.write_text("(options) => options")
    output = tmp_path / "runtime.js"
    binary = shutil.which("node")
    assert binary
    subprocess.run(
        [
            binary,
            "-e",
            javascript[0],
            str(factory),
            str(runtime_inventory),
            str(axe),
            str(output),
            str(tmp_path / "screenshots"),
            "http://127.0.0.1:18080",
            "verified-incremental",
            "standard-api",
            str(scope_path),
            str(binding_path),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    options = json.loads(
        subprocess.run(
            [
                binary,
                "-e",
                "process.stdout.write(JSON.stringify(eval(require('fs').readFileSync(process.argv[1], 'utf8'))))",
                str(output),
            ],
            check=True,
            capture_output=True,
            timeout=10,
        ).stdout
    )
    assert options["inventory"] == bound
    assert options["incrementalScope"] == inputs["scope"]
    assert options["selectedSurfaceIds"] == inputs["browser_plan"]["surface_ids"]
    assert options["publicationProfile"] == "verified-incremental"
    assert options["linkMode"] == "standard-api"
    assert CHECK.read_text().count('"${runtime_inventory_file:-$audit_inventory}"') == 2


@pytest.mark.parametrize("mutation", ["inventory_hash", "scope", "binding_core"])
def test_wrapper_refuses_inventory_or_scope_drift_before_capture(tmp_path, mutation):
    _bound, report, inputs, binding_path, scope_path = bound_files(tmp_path)
    if mutation == "inventory_hash":
        inputs["audit_inventory_sha256"] = "b" * 64
    elif mutation == "scope":
        scope_path.write_text("{}")
    else:
        inputs["core_document_slugs"].append("local-extra-guide")
        inputs["core_document_slugs"].sort()
    binding_path.write_bytes(report.canonical({"inputs": inputs}))
    python, _ = wrapper_blocks()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            python,
            str(BROWSER),
            str(INVENTORY),
            str(binding_path),
            str(scope_path),
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert result.stdout == b""
    assert b"RAOS_WORDPRESS_MIXED_BROWSER_REPORT_INVALID" in result.stderr


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "missing_hub",
        "missing_1024",
        "missing_zoom",
        "unexpected_guide",
        "symlink",
    ],
)
def test_wrapper_checks_actual_surface_width_and_zoom_screenshots(tmp_path, mutation):
    inventory, report, inputs, binding_path, _ = bound_files(tmp_path)
    runtime_inventory = tmp_path / "runtime-inventory.json"
    runtime_inventory.write_bytes(report.canonical(inventory))
    shots = tmp_path / "screenshots"
    shots.mkdir()
    expected = inputs["browser_plan"]["screenshots"]
    for name in expected:
        (shots / name).write_bytes(b"Synthetic screenshot fixture")
    if mutation == "missing_hub":
        for name in expected:
            if name.startswith("local-preview-hub-categories-"):
                (shots / name).unlink()
    elif mutation == "missing_1024":
        (shots / "local-preview-hub-categories-1024.png").unlink()
    elif mutation == "missing_zoom":
        (shots / "local-preview-hub-categories-zoom200.png").unlink()
    elif mutation == "unexpected_guide":
        (shots / "local-preview-extra-guide-360.png").write_bytes(b"Extra fixture")
    elif mutation == "symlink":
        shot = shots / expected[0]
        shot.unlink()
        shot.symlink_to(shots / expected[1])
    _, javascript = wrapper_blocks()
    binary = shutil.which("node")
    assert binary
    result = subprocess.run(
        [
            binary,
            "-e",
            javascript[1],
            str(runtime_inventory),
            str(shots),
            str(binding_path),
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == (0 if mutation is None else 69)
    assert result.stdout == result.stderr == b""
    assert len(expected) == len(inputs["browser_plan"]["surface_ids"]) * (
        len(inventory["viewports"]) + 1
    )


def test_only_bound_hubs_promote_and_v1_inventory_is_unchanged(tmp_path):
    inventory, result, _scope, _root, report = reader_preview(tmp_path)
    original = deepcopy(inventory)
    binding = dict(result.binding)
    assert report.bind_reader_inventory(inventory, {}) is inventory
    assert inventory == original
    binding["core_document_slugs"] = sorted(
        set(binding["core_document_slugs"]) - (report.READER_HUB_SLUGS - {"categories"})
    )
    binding["reader_page_slugs"] = ["categories", "home", "privacy-policy"]
    bound = report.bind_reader_inventory(inventory, binding)
    assert [row for row in bound["surfaces"] if row["kind"] == "reader_hub"] == [
        next(
            row
            for row in inventory["reader_hubs"]
            if row["surface_id"] == "hub-categories"
        )
    ]
    assert bound["local_surfaces"] == original["local_surfaces"]
    assert inventory == original
    assert report.bind_reader_inventory(bound, binding) == bound


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "extra",
        "extra_field",
        "identity",
        "kind",
        "path",
        "collision",
    ],
)
def test_report_binds_only_exact_registered_catalog_rows(tmp_path, mutation):
    inventory, result, _scope, _root, report = reader_preview(tmp_path)
    row = inventory["reader_hubs"][0]
    if mutation == "missing":
        inventory["reader_hubs"].pop()
    elif mutation == "duplicate":
        inventory["reader_hubs"][-1] = deepcopy(row)
    elif mutation == "extra":
        inventory["reader_hubs"].append(
            {"surface_id": "extra", "kind": "reader_hub", "local_path": "/extra/"}
        )
    elif mutation == "extra_field":
        row["production_path"] = row["local_path"]
    elif mutation == "identity":
        row["surface_id"] = "local-guide"
    elif mutation == "kind":
        row["kind"] = "local_guide"
    elif mutation == "path":
        row["local_path"] = "/local-guide/"
    else:
        inventory["local_surfaces"].append({**row, "kind": "local_guide"})
    with pytest.raises(report.ReportFailure):
        report.bind_reader_inventory(inventory, dict(result.binding))


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "product_identity",
        "image_identity",
        "cta_identity",
        "role",
        "intent",
        "policy",
    ],
)
def test_page_only_keeps_old_article_identity_and_evidence_checks(tmp_path, mutation):
    from tests.wordpress_local_preview.test_incremental_browser_scope import (
        _audit,
        _scope,
    )

    inventory, _result, scope, _root = promoted(tmp_path)
    legacy = _scope()["articles"][1]
    article_id = scope["articles"][0]["article_id"]
    scope["articles"][0] = {**legacy, "article_id": article_id}
    assert node({"action": "scope", "inventory": inventory, "scope": scope})["valid"]
    audit = deepcopy(_audit(scope, article_id))
    for image in audit["commerceImages"]:
        image["state"] = "unknown"
    if mutation == "product_identity":
        audit["productIds"][0] = "PRD-OTHER"
    elif mutation == "image_identity":
        audit["commerceImages"][0]["product_id"] = "PRD-OTHER"
    elif mutation == "cta_identity":
        audit["commerceCtas"][0]["product_id"] = "PRD-OTHER"
    elif mutation == "role":
        audit["articleFacts"]["contentRoleLabels"] = ["Invented role"]
    elif mutation == "intent":
        audit["articleFacts"]["primaryQueryIntents"] = ["Invented intent"]
    elif mutation == "policy":
        audit["disclosure"]["policyLinkCount"] += 1
    result = node(
        {
            "action": "article",
            "article": {
                "scope": scope,
                "articleId": article_id,
                "audit": audit,
            },
        }
    )
    assert result["failed"] is (mutation is not None)
    assert result["selected"] is False
    assert result["commerceStatus"] == "UNCHANGED_NOT_REVERIFIED"


def test_report_replays_raw_catalog_with_real_plan_and_full_page_coverage(tmp_path):
    inventory, result, scope, _root, report = reader_preview(tmp_path)
    bound = report.bind_reader_inventory(inventory, dict(result.binding))
    from scripts.raos_wordpress_browser_plan import browser_plan

    inputs = {
        **result.binding,
        "scope": scope,
        "preparation_binding_sha256": "a" * 64,
        "browser_plan": browser_plan(bound),
    }
    rows = results_for(bound, result.binding)
    statuses = {
        row["surface_id"]: row.get("expected_http_status", 200)
        for row in bound["surfaces"] + bound["local_surfaces"]
    }
    for row in rows:
        row["httpStatus"] = statuses[row["surface"]]
    names = report.validate_results(rows, inventory, inputs)
    assert names == sorted(inputs["browser_plan"]["screenshots"])
    for missing in [("hub-categories", 1024), ("home", 390)]:
        with pytest.raises(report.ReportFailure):
            report.validate_results(
                [row for row in rows if (row["surface"], row["width"]) != missing],
                inventory,
                inputs,
            )
    with pytest.raises(report.ReportFailure):
        report.validate_results(
            [row for row in rows if not row["surface"].startswith("hub-")],
            inventory,
            inputs,
        )


@pytest.mark.parametrize(
    "selection,published",
    [
        ({"home"}, set()),
        ({"privacy-policy"}, set()),
        ({"categories"}, {"purposes"}),
    ],
)
def test_selected_and_already_published_hubs_define_exact_core_set(
    tmp_path, selection, published
):
    inventory, result, scope, _root, report = reader_preview(
        tmp_path,
        page_selection=selection,
        published_hubs=published,
    )
    bound = report.bind_reader_inventory(inventory, dict(result.binding))
    assert scope["reader_page_slugs"] == sorted(selection)
    core_hubs = {
        row["local_path"].strip("/")
        for row in bound["surfaces"]
        if row["kind"] == "reader_hub"
    }
    assert core_hubs == (selection & report.READER_HUB_SLUGS) | published
    assert core_hubs == set(scope["core_document_slugs"]) & report.READER_HUB_SLUGS
    assert all(row["kind"] != "reader_hub" for row in bound["local_surfaces"])
    assert node({"inventory": bound, "scope": scope, "workers": 3})["valid"]


@pytest.mark.parametrize("age_minutes", [0, 120, 121])
def test_catalog_report_replay_keeps_original_two_hour_expiry(
    tmp_path, monkeypatch, age_minutes
):
    from tests.wordpress_local_preview import test_mixed_audit_report as fixtures
    from scripts.raos_wordpress_browser_plan import browser_plan

    # Evidence and fixtures are synthetic; runtime and WordPress are never consulted.
    inputs, raw, shots, _summary = fixtures.evidence(tmp_path, monkeypatch)
    _scope_owner, report = browser_owners()
    inventory = json.loads(INVENTORY.read_bytes())
    inputs.update(
        reader_page_slugs=sorted(report.READER_HUB_SLUGS),
        core_document_slugs=sorted(
            {
                "home" if row["kind"] == "home" else row["production_path"].strip("/")
                for row in inventory["surfaces"]
            }
            | report.READER_HUB_SLUGS
        ),
    )
    inputs["scope"].update(
        reader_page_slugs=inputs["reader_page_slugs"],
        core_document_slugs=inputs["core_document_slugs"],
    )
    bound = report.bind_reader_inventory(inventory, inputs)
    inputs["browser_plan"] = browser_plan(bound)
    results = report.parse_results(raw)
    template = next(
        row for row in results if row["surface"] == "home" and row["width"] == 360
    )
    for surface in bound["surfaces"]:
        if surface["kind"] != "reader_hub":
            continue
        identifier = surface["surface_id"]
        for width in inventory["viewports"]:
            results.append(
                {
                    **deepcopy(template),
                    "surface": identifier,
                    "width": width,
                    "localPath": surface["local_path"],
                    "productionPath": None,
                    "screenshot": f"/synthetic/local-preview-{identifier}-{width}.png",
                    "zoomScreenshot": f"/synthetic/local-preview-{identifier}-zoom200.png"
                    if width == 390
                    else None,
                }
            )
    for name in report.validate_results(results, inventory, inputs):
        (shots / name).write_bytes(b"\x89PNG\r\n\x1a\nSynthetic PNG fixture")
    raw = b"### Result\n" + report.canonical(results)
    captured = datetime(2026, 9, 5, 2, 5, tzinfo=UTC)
    monkeypatch.setattr(report, "LIGHTHOUSE", fixtures.owner.LIGHTHOUSE)
    recorded = report.assemble_report(
        inputs=inputs,
        raw_result=raw,
        artifact_directory=shots,
        started_at="2026-09-05T02:00:00+00:00",
        captured_at=captured.isoformat(),
    )
    report_path, original_path = tmp_path / "report.json", tmp_path / "original.txt"
    report_path.write_bytes(report.canonical(recorded))
    original_path.write_bytes(raw)
    monkeypatch.setattr(report, "REPORT", report_path)
    monkeypatch.setattr(report, "ORIGINAL", original_path)
    monkeypatch.setattr(report, "ARTIFACTS", shots)
    monkeypatch.setattr(
        report, "current_inputs", lambda *args, **kwargs: deepcopy(inputs)
    )
    arguments = {
        "fixture_root": tmp_path,
        "origin": inputs["origin"],
        "now": captured + timedelta(minutes=age_minutes),
    }
    if age_minutes > 120:
        with pytest.raises(report.ReportFailure):
            report.validate_report(report_path, **arguments)
    else:
        assert report.validate_report(report_path, **arguments) == recorded
        assert recorded["captured_at"] == captured.isoformat()
        assert recorded["core_document_slugs"] == inputs["core_document_slugs"]
        assert recorded["browser_result_count"] == len(
            bound["surfaces"] + bound["local_surfaces"]
        ) * len(inventory["viewports"])


def test_scope_cli_replays_page_only_fixture_with_declared_hubs(tmp_path):
    _inventory, _result, scope, root, _report = reader_preview(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(BROWSER / "incremental_scope.py"),
            "--fixture-root",
            str(root),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    assert result.stderr == b""
    assert json.loads(result.stdout) == scope
    assert scope["selected_article_ids"] == []
