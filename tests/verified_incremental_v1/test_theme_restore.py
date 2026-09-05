"""Synthetic theme rollback evidence; no Git or Docker operation in unit tests."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from raos.application.editorial import local_scratch_theme_restore_v1 as theme
from raos.application.editorial.local_scratch_restore_v1 import (
    build_scratch_restoration,
    verify_scratch_restoration,
)
from raos.application.editorial.verified_incremental_preview_v1 import (
    build_local_restoration,
)
from raos.application.editorial.verified_incremental_v1 import (
    canonical,
    digest,
    IncrementalPublicationFailure,
)
from tests.verified_incremental_v1.test_restore import snapshot, scratch_readback

ROOT = Path(__file__).resolve().parents[2]


def sample():
    value, slugs = snapshot()
    baseline = theme.build_theme_package(
        {
            "style.css": b"Version: 1.4.0\n",
            "functions.php": b"<?php // synthetic baseline\n",
        }
    )
    candidate = theme.build_theme_package(
        {
            "style.css": b"Version: 1.5.1\n",
            "functions.php": b"<?php // synthetic candidate\n",
            "assets/new.css": b"body{}",
        }
    )
    value["deployment_status"] = {
        "schema": "RAOS_WORDPRESS_DEPLOYMENT_BASELINE_SNAPSHOT_V1",
        "source": "BOUNDED_WORDPRESS_DEPLOYMENT_MCP",
        "status": "CAPTURED_READ_ONLY",
        "theme": {
            "slug": theme.THEME_SLUG,
            "active": True,
            "tree_sha256": json.loads(baseline)["tree_sha256"],
        },
    }
    initial = build_local_restoration(value, article_slugs=slugs)
    preparation_hash = digest(canonical(initial.preparation))
    content = build_scratch_restoration(
        value,
        article_slugs=slugs,
        preparation_sha256=preparation_hash,
        environment_id=preparation_hash[:8] + "-abcdef123456",
    )
    content_readback = scratch_readback(content)
    content_receipt = {
        **verify_scratch_restoration(content, content_readback),
        "verified_at": "2026-09-05T09:00:00+00:00",
    }
    arguments = {
        "article_slugs": slugs,
        "content_receipt_raw": canonical(content_receipt),
        "content_readback_raw": canonical(content_readback),
        "baseline_package_raw": baseline,
        "candidate_package_raw": candidate,
    }
    return value, arguments, theme.build_scratch_theme_restoration(value, **arguments)


def readback(expected):
    preparation = json.loads(expected.preparation)
    return {
        "schema": "RAOS_WORDPRESS_SCRATCH_THEME_RESTORE_READBACK_V1",
        "publication_profile": theme.PROFILE,
        "publication_authority": False,
        "production_authority": False,
        "scratch_only": True,
        "temporary_environment": True,
        "environment_id": preparation["environment_id"],
        "preparation_sha256": digest(expected.preparation),
        "theme_slug": theme.THEME_SLUG,
        "site_url": "http://scratch.wordpress.invalid",
        "operation": "SAME_BASENAME_FILES_ONLY_NO_ACTIVATION",
        "stages": [
            {
                "stage": stage,
                "theme_tree_sha256": preparation[kind + "_tree_sha256"],
                "file_manifest": preparation[kind + "_file_manifest"],
                "content_readback": scratch_readback(expected.content),
                "wordpress_options_sha256": "a" * 64,
            }
            for stage, kind in (
                ("baseline_before", "baseline"),
                ("candidate_installed", "candidate"),
                ("baseline_restored", "baseline"),
            )
        ],
    }


def test_theme_package_uses_exact_deployment_tree_not_zip_or_json_file_hash():
    files = {"style.css": b"test", "assets/a.css": b""}
    raw = theme.build_theme_package(files)
    assert theme.parse_theme_package(raw) == files
    assert json.loads(raw)["tree_sha256"] == digest(
        canonical(theme.theme_manifest(files)).rstrip(b"\n")
    )
    assert json.loads(raw)["tree_sha256"] != digest(raw)


@pytest.mark.parametrize(
    "path", ["../outside", "/absolute", "x//y", "x/./y", "x/../y", "x\\y", ""]
)
def test_theme_package_rejects_unbounded_paths(path):
    with pytest.raises(IncrementalPublicationFailure):
        theme.build_theme_package({"style.css": b"", path: b"bad"})


def test_theme_package_rejects_case_collisions_and_rehashed_contents_mismatch():
    with pytest.raises(IncrementalPublicationFailure):
        theme.build_theme_package({"style.css": b"", "Style.css": b""})
    raw = json.loads(theme.build_theme_package({"style.css": b"one"}))
    raw["files"][0]["contents_b64"] = "dHdv"
    with pytest.raises(IncrementalPublicationFailure):
        theme.parse_theme_package(canonical(raw))


def test_theme_rollback_requires_three_actual_states_and_preserves_content_and_options():
    snapshot_value, arguments, expected = sample()
    original = deepcopy(snapshot_value)
    proof = readback(expected)
    result = theme.verify_scratch_theme_restoration(expected, proof)
    assert result["verified_noncontent_rollback_targets"] == ["theme"]
    assert result["baseline_tree_sha256"] == result["restored_tree_sha256"]
    assert result["baseline_tree_sha256"] != result["candidate_tree_sha256"]
    assert result["content_restore_receipt_sha256"] == digest(
        arguments["content_receipt_raw"]
    )
    assert result["source_snapshot_sha256"] == digest(
        canonical(snapshot_value).rstrip(b"\n")
    )
    assert result["verified_document_count"] == 14
    assert result["wordpress_options_unchanged"] is True
    for flag in (
        "publication_authority",
        "production_authority",
        "production_writes",
        "current_preview_modified",
        "activation_changed",
        "ports_published",
    ):
        assert result[flag] is False
    assert snapshot_value == original


@pytest.mark.parametrize("stage", [0, 1, 2])
@pytest.mark.parametrize(
    "field",
    [
        "theme_tree_sha256",
        "file_manifest",
        "wordpress_options_sha256",
        "content_readback",
    ],
)
def test_any_stage_tree_document_or_option_change_refuses_rollback(stage, field):
    _snapshot, _arguments, expected = sample()
    proof = readback(expected)
    proof["stages"][stage][field] = "b" * 64
    with pytest.raises(IncrementalPublicationFailure):
        theme.verify_scratch_theme_restoration(expected, proof)


@pytest.mark.parametrize(
    "field,value",
    [
        ("publication_authority", True),
        ("publication_authority", 0),
        ("scratch_only", False),
        ("operation", "ACTIVATE"),
        ("environment_id", "other"),
        ("stages", []),
    ],
)
def test_theme_rehearsal_cannot_masquerade_as_production_or_skip_candidate(
    field, value
):
    _snapshot, _arguments, expected = sample()
    proof = readback(expected)
    proof[field] = value
    with pytest.raises(IncrementalPublicationFailure):
        theme.verify_scratch_theme_restoration(expected, proof)


def test_uncaptured_or_different_live_theme_baseline_is_rejected():
    value, arguments, _expected = sample()
    value["deployment_status"]["theme"]["tree_sha256"] = "f" * 64
    with pytest.raises(IncrementalPublicationFailure):
        theme.build_scratch_theme_restoration(value, **arguments)


def test_theme_php_is_local_files_only_with_same_filesystem_recoverable_swaps():
    php = (
        ROOT / "changes/wordpress-local-preview-v1/scratch-theme-restore.php"
    ).read_text()
    for guard in (
        "RAOS_LOCAL_RESTORE_SCRATCH",
        "DB_NAME !== 'scratch_wordpress'",
        "DB_HOST !== 'database'",
        "wp_get_environment_type() !== 'local'",
        "WP_HTTP_BLOCK_EXTERNAL",
        "defined('RAOS_LOCAL_PREVIEW')",
    ):
        assert guard in php.split("function theme_restore_read", 1)[0]
    for prohibited in (
        "switch_theme(",
        "activate_plugin(",
        "update_option(",
        "wp_update_post(",
        "wp_insert_post(",
        "wp_remote_",
        "unlink(",
        "rmdir(",
    ):
        assert prohibited not in php
    assert "'/var/www/html/wp-content/themes/.raos-scratch-'" in php
    assert "rename($theme_root, $before_saved)" in php
    assert "finally" in php and "rename($before_saved, $theme_root)" in php
    assert "SELECT option_name, option_value, autoload" in php
    assert all(
        stage in php
        for stage in ("baseline_before", "candidate_installed", "baseline_restored")
    )


def test_theme_script_never_restarts_regular_preview_or_runs_candidate_code():
    script = (ROOT / "scripts/raos_wordpress_scratch_theme_restore.py").read_text()
    assert '"--skip-themes",' in script and '"--skip-plugins",' in script
    assert 'project = "raos-wp-scratch-" + environment_id' in script
    assert '"--pull",' in script and '"never",' in script
    assert "wordpress_preview.sh" not in script and "shell=True" not in script
    assert "5bd4a8d06be87494961012d38336879ad1e123cb" in script
