"""Mixed publication expectations follow the bound body, including legacy pages."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.verified_incremental_v1.test_reader_page_preview import browser_owners
from tests.wordpress_local_preview.test_reader_page_scope import reader_preview

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "changes/wordpress-local-preview-v1/browser/wordpress_local_preview_audit.function.js"


def modern(article):
    return f"<span class='raos-reader-view' data-raos-article-id='{article}' data-raos-reader-components='true' hidden></span>"


def test_bound_markup_distinguishes_selected_legacy_and_already_migrated_bodies():
    _, report = browser_owners()
    assert report.derive_reader_component_article_ids(
        {"selected": modern("selected"), "preserved": "<p>Original disclosure</p>",
         "already-modern": modern("already-modern")},
        required_article_ids={"selected"},
    ) == ["already-modern", "selected"]


@pytest.mark.parametrize("markup", ["<p>Missing required components</p>",
    modern("wrong-article"), modern("selected") * 2])
def test_missing_or_mismatched_required_reader_components_are_rejected(markup):
    _, report = browser_owners()
    with pytest.raises(ValueError):
        report.derive_reader_component_article_ids(
            {"selected": markup}, required_article_ids={"selected"})


def test_bound_component_ids_do_not_remove_registered_breadcrumb_categories(tmp_path):
    inventory, result, _, _, report = reader_preview(tmp_path)
    original = deepcopy(inventory)
    selected = inventory["reader_display"]["article_ids"][:1]
    binding = {**dict(result.binding), "reader_components_article_ids": selected}
    actual = report.bind_reader_inventory(inventory, binding)
    assert actual["reader_display"]["component_article_ids"] == selected
    assert actual["reader_display"]["article_ids"] == original["reader_display"]["article_ids"]
    assert actual["reader_display"]["primary_categories"] == original["reader_display"]["primary_categories"]
    assert inventory == original


@pytest.mark.parametrize("ids", [["unknown"], ["a", "a"], "all"])
def test_unknown_or_malformed_component_expectations_cannot_relax_checks(tmp_path, ids):
    inventory, result, _, _, report = reader_preview(tmp_path)
    with pytest.raises(ValueError):
        report.bind_reader_inventory(
            inventory, {**dict(result.binding), "reader_components_article_ids": ids})


@pytest.mark.parametrize(("text", "expected"), [
    ("公式情報確認：2026年9月5日 ／ 実機確認：未実施", True),
    ("出典の取得日：2026-08-23〜2026-08-31（出典別） ／ 記事確認：2026年9月5日 ／ 実機確認：未実施", True),
    ("出典の取得日：2026-08-31 ／ 実機確認：未実施", False),
    ("記事確認：2026年9月5日 ／ 実機確認：未実施", False),
    ("公式情報確認：2026年9月5日", False),
])
def test_status_labels_preserve_source_dates_distinct_from_article_review(text, expected):
    node = shutil.which("node")
    assert node
    result = subprocess.run([node, "-e",
        "const fs=require('fs');const f=eval(fs.readFileSync(process.argv[1],'utf8'));"
        "process.stdout.write(JSON.stringify(f.hasResearchStatusLabels(JSON.parse(process.argv[2]))));",
        str(AUDIT), json.dumps(text)], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) is expected
