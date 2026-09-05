from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / (
    "changes/wordpress-local-preview-v1/browser/"
    "wordpress_local_preview_audit.function.js"
)
SOURCE = "http://127.0.0.1:39330/wp-content/themes/example/assets/decoration.webp"


def _node(payload: dict[str, object]) -> dict[str, object]:
    node = shutil.which("node")
    assert node is not None
    result = subprocess.run(
        [
            node,
            "-e",
            """
const fs = require('fs');
const factory = eval(fs.readFileSync(process.argv[1], 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  if (input.mode === 'observe') {
    const rect = {width: input.nonzeroImage ? 1 : 0, height: 0};
    const comparison = {matches: () => !input.wrongRoot, parentElement: null};
    const cardWrapper = {
      matches: (selector) => selector === '.comparison-cards', parentElement: comparison,
    };
    const viewNode = (name) => ({
      name, display: name === input.view ? 'none' : 'block',
      matches: (selector) => selector === '.raos-comparison__cards' && name === 'cards',
      parentElement: input.detachedView ? null : name === 'cards' ? cardWrapper : comparison,
      checkVisibility: () => !input.hiddenCounterpart,
      getBoundingClientRect: () => ({width: input.zeroCounterpart ? 0 : 300, height: 100}),
    });
    const table = viewNode('table'), cards = viewNode('cards');
    const view = input.view === 'table' ? table : input.view === 'cards' ? cards : null;
    comparison.querySelector = (selector) => input.missingCounterpart ? null :
      selector.includes('table-view') ? table : cards;
    const image = {
      complete: false, naturalWidth: 0, loading: 'lazy', src: 'synthetic.webp',
      currentSrc: '', parentElement: view,
      getBoundingClientRect: () => rect, checkVisibility: () => false,
      matches: () => !input.wrongClass, hasAttribute: () => Boolean(input.productId),
      closest: (selector) => selector.startsWith('.raos-comparison__') ? view :
        input.protectedProduct ? {} : null,
    };
    global.document = {images: [image]};
    global.getComputedStyle = (node) => ({display: node.display || 'block'});
    process.stdout.write(JSON.stringify(factory.inspectImageLoading()[0]));
    return;
  }
  if (input.mode !== 'resources') {
    process.stdout.write(JSON.stringify(factory.classifyImageLoading(input)));
    return;
  }
  const calls = [];
  let disposed = 0;
  const failures = await factory.inspectHiddenLegacyImageResources({
    origin: 'http://127.0.0.1:39330', sources: input.sources,
    page: {request: {get: async (url, options) => {
      calls.push({url, options});
      if (input.throw) throw new Error('synthetic failure');
      return {
        status: () => input.status ?? 200,
        url: () => input.finalUrl ?? url,
        headers: () => ({'content-type': input.type ?? 'image/webp'}),
        body: async () => ({length: input.bytes ?? 100}),
        dispose: async () => {disposed += 1;},
      };
    }}},
  });
  process.stdout.write(JSON.stringify({failures, calls, disposed}));
})().catch(() => {process.exitCode = 1;});
""",
            str(AUDIT),
        ],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return cast(dict[str, object], json.loads(result.stdout))


def _input() -> dict[str, object]:
    return {
        "publicationProfile": "verified-incremental",
        "commerceStatus": "UNCHANGED_NOT_REVERIFIED",
        "images": [
            {
                "complete": False,
                "naturalWidth": 0,
                "loading": "lazy",
                "legacyResponsiveImage": True,
                "hasProductImageId": False,
                "verifiedProductImage": False,
                "hiddenAncestor": True,
                "zeroRect": True,
                "invisible": True,
                "source": SOURCE,
            }
        ],
    }


def test_only_pending_hidden_legacy_image_is_counted_separately() -> None:
    assert _node(_input()) == {
        "unloadedImages": 0,
        "hiddenLegacyLazySources": [SOURCE],
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publicationProfile", "legacy-full"),
        ("commerceStatus", "NOT_INCLUDED"),
        ("commerceStatus", "EXPECTED_VERIFIED_SET_PRESENT"),
        ("commerceStatus", "SCOPE_MISSING"),
        ("legacyResponsiveImage", False),
        ("hasProductImageId", True),
        ("verifiedProductImage", True),
        ("hiddenAncestor", False),
        ("zeroRect", False),
        ("invisible", False),
        ("loading", "eager"),
        ("complete", True),
        ("naturalWidth", 128),
    ],
)
def test_all_narrow_conditions_required_and_broken_hidden_images_fail(
    field: str, value: object
) -> None:
    payload = _input()
    images = cast(list[dict[str, object]], payload["images"])
    target = payload if field in payload else images[0]
    target[field] = value
    assert _node(payload) == {"unloadedImages": 1, "hiddenLegacyLazySources": []}


def test_loaded_visible_image_remains_successful() -> None:
    payload = _input()
    images = cast(list[dict[str, object]], payload["images"])
    images[0].update(
        complete=True, naturalWidth=128, hiddenAncestor=False, zeroRect=False
    )
    assert _node(payload) == {"unloadedImages": 0, "hiddenLegacyLazySources": []}


@pytest.mark.parametrize("view", ["table", "cards"])
def test_observer_recognizes_both_inactive_complementary_views(view: str) -> None:
    row = _node({"mode": "observe", "view": view})
    assert row["legacyResponsiveImage"] is True
    assert row["hiddenAncestor"] is True
    assert row["zeroRect"] is True
    assert row["invisible"] is True


@pytest.mark.parametrize(
    "change",
    [
        {"view": "unclassified"},
        {"wrongRoot": True},
        {"detachedView": True},
        {"missingCounterpart": True},
        {"hiddenCounterpart": True},
        {"zeroCounterpart": True},
        {"wrongClass": True},
    ],
)
def test_observer_rejects_unclassified_or_noncomplementary_hidden_views(
    change: dict[str, object],
) -> None:
    row = _node({"mode": "observe", "view": "table", **change})
    assert row["legacyResponsiveImage"] is False


def test_observer_protects_commerce_markers_on_image_or_ancestors() -> None:
    row = _node(
        {
            "mode": "observe",
            "view": "cards",
            "protectedProduct": True,
            "productId": True,
        }
    )
    assert row["hasProductImageId"] is True
    assert row["verifiedProductImage"] is True


def test_deferred_resource_is_read_only_checked_once_without_redirects() -> None:
    result = _node({"mode": "resources", "sources": [SOURCE, SOURCE]})
    assert result == {
        "failures": 0,
        "disposed": 1,
        "calls": [{"url": SOURCE, "options": {"maxRedirects": 0, "timeout": 5000}}],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"status": 404},
        {"status": 403},
        {"status": 302},
        {"finalUrl": SOURCE + ".other"},
        {"type": "text/html"},
        {"bytes": 0},
        {"bytes": 2 * 1024 * 1024 + 1},
        {"throw": True},
    ],
)
def test_hidden_lazy_resource_failures_are_not_ignored(
    change: dict[str, object],
) -> None:
    result = _node({"mode": "resources", "sources": [SOURCE], **change})
    assert result["failures"] == 1


@pytest.mark.parametrize(
    "source",
    [
        SOURCE.replace("127.0.0.1:39330", "example.invalid"),
        SOURCE.replace("http:", "https:"),
        SOURCE + "?redirect=1",
        SOURCE + "#fragment",
        SOURCE.replace(
            "/wp-content/themes/example/assets/decoration.webp", "/wp-admin/"
        ),
        SOURCE.replace("decoration.webp", "arbitrary.php"),
        SOURCE.replace("http://", "http://user:password@"),
        "data:image/webp;base64,AAAA",
        "not-a-url",
    ],
)
def test_deferred_dom_url_never_expands_http_authority(source: str) -> None:
    result = _node({"mode": "resources", "sources": [source]})
    assert result == {"failures": 1, "disposed": 0, "calls": []}


def test_live_wiring_preserves_image_failure_gate_without_dom_mutation() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    observer = source.split("const inspectImageLoading =", 1)[1].split(
        "const classifyImageLoading =", 1
    )[0]
    for required in (
        "image.matches('img.raos-comparison__product-image')",
        "image.closest('.raos-comparison__table-view, .raos-comparison__cards')",
        "comparison?.matches('.raos-comparison') === true",
        "':scope > .comparison-cards > .raos-comparison__cards'",
        "counterpart.checkVisibility() === true",
        "image.hasAttribute('data-raos-product-image-id')",
        "getComputedStyle(ancestor).display === 'none'",
        "rect.width === 0 && rect.height === 0",
        "image.checkVisibility() === false",
    ):
        assert required in observer
    assert "image.loading =" not in observer
    assert ".style." not in observer
    assert "audit.unloadedImages !== 0" in source
    assert "audit.hiddenLegacyImageResourceFailures !== 0" in source
    assert "images: await page.evaluate(inspectImageLoading)" in source
    assert "sources: imageLoading.hiddenLegacyLazySources" in source
    assert "hiddenLegacyLazyNotRequested: audit.hiddenLegacyLazyImageCount" in source
