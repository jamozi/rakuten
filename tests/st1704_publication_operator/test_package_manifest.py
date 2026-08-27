"""Deterministic v2 package and runtime-manifest checks."""

from __future__ import annotations

import ast
import hashlib
import io
import json
from pathlib import Path
import stat
import zipfile

from scripts import build_st1704_wordpress_publication_operator_v2 as builder


ROOT = Path(__file__).resolve().parents[2]


def test_generated_binding_is_current_and_exact() -> None:
    payload = builder.BINDINGS_PATH.read_bytes()
    assert payload == builder.build_bindings()
    text = payload.decode("utf-8")
    assert "final class RAOS_ST1704_Publication_Bindings_V2" in text
    assert "const CATEGORY_NAME = '暮らしの道具';" in text
    assert "const CATEGORY_CONTRACT = 'KURASHINO_DOGU_SINGLE_V1';" in text
    assert "count($articles) !== 4" in text
    assert builder.EXCLUDED_UPDATE_ARTICLE not in text
    for article_id, slug in builder.PUBLISH_BINDINGS:
        assert f'"{article_id}":"{slug}"' in text
    for article_id, post_id in builder.REVISION_POST_IDS:
        assert f'"{article_id}":{post_id}' in text


def test_package_is_deterministic_and_injects_after_unchanged_v1_boot() -> None:
    assert builder.PLUGIN_VERSION == "2.1.7"
    v1_before = (ROOT / builder.V1_MAIN_RELATIVE).read_bytes()
    first = builder.build_package()
    second = builder.build_package()
    assert first == second
    assert (ROOT / builder.V1_MAIN_RELATIVE).read_bytes() == v1_before
    with zipfile.ZipFile(io.BytesIO(first), "r") as archive:
        names = [builder.PACKAGE_ROOT + item for item in builder.PLUGIN_FILES]
        assert archive.namelist() == names
        for name in names:
            info = archive.getinfo(name)
            assert info.date_time == builder.ZIP_TIMESTAMP
            assert info.compress_type == zipfile.ZIP_STORED
            assert stat.S_IFMT(info.external_attr >> 16) == stat.S_IFREG
            assert stat.S_IMODE(info.external_attr >> 16) == 0o644
        main = archive.read(builder.PACKAGE_ROOT + "raos-bounded-operator.php")
    text = main.decode("utf-8")
    assert text.count(" * Version: 2.1.7\n") == 1
    assert text.count(" * Requires at least: 7.1\n") == 1
    assert text.count(" * Tested up to: 7.1\n") == 1
    assert " * Requires at least: 6.9\n" not in text
    assert "    const VERSION = '1.0.0';" in text  # v1 API compatibility
    positions = [
        text.index("RAOS_Bounded_Operator::instance();"),
        text.index("/includes/st1704-publication-bindings.v2.php"),
        text.index("/includes/st1704-publication-controller.v2.php"),
        text.index("array('RAOS_ST1704_Publication_Controller_V2', 'activate')"),
        text.index("RAOS_ST1704_Publication_Controller_V2::instance("),
    ]
    assert positions == sorted(positions)
    assert "RAOS_Bounded_Operator::instance()\n);" in text


def test_runtime_manifest_matches_sources_and_package() -> None:
    expected = builder.build_manifest()
    assert builder.MANIFEST_PATH.read_bytes() == expected
    manifest = json.loads(expected)
    assert manifest["schema"] == "RAOS_ST1704_PUBLICATION_OPERATOR_RUNTIME_MANIFEST_V2"
    assert manifest["publication_authority"] == "DISTINCT_HUMAN_APPROVAL_ONLY"
    assert manifest["codex_approval_authority"] == "NONE"
    assert manifest["writes_default"] == "DISABLED"
    assert manifest["draft_writer_role"] == {
        "activation": "EXACT_CREATE_CAPABILITY_NORMALIZE_AND_PERSISTENCE_VERIFY",
        "application_password_creation": "ABSENT",
        "capabilities": {"edit_posts": True, "read": True},
        "display_name": "RAOS Draft Writer",
        "role": "raos_draft_writer",
        "user_assignment": "ABSENT",
    }
    assert manifest["gates"][
        "RAOS_ST1704_PUBLICATION_RECONCILIATION_WRITES_ENABLED"
    ] == "DEFAULT_DISABLED_ADMIN_ONLY_INCIDENT_RECONCILIATION"
    assert manifest["incident_reconciliation"] == {
        "authority": (
            "COOKIE_SESSION_MANAGE_OPTIONS_PUBLISH_POSTS_EDIT_POST_"
            "DISTINCT_HUMAN"
        ),
        "proposal_state_mutation": "NONE",
        "rest_authority": "NONE",
        "targets": [
            {"article_id": article_id, "post_id": post_id}
            for article_id, post_id in builder.REVISION_POST_IDS[:2]
        ],
    }
    assert manifest["production_readiness"] == "NOT_READY"
    assert manifest["supported_mutations"] == [
        "PUBLISH_ST1704_ARTICLE",
        "REVISE_ST1704_DRAFT",
    ]
    assert manifest["publication_article_ids"] == [
        item[0] for item in builder.PUBLISH_BINDINGS
    ]
    canonical_paths = {
        builder.BASE_CANONICAL_DECISIONS_RELATIVE.as_posix(),
        builder.BASE_CANONICAL_BACKLOG_RELATIVE.as_posix(),
    }
    assert {row["path"] for row in manifest["integrity_inputs"]} == canonical_paths
    assert all("sha256" in row for row in manifest["integrity_inputs"])
    assert [row["path"] for row in manifest["semantic_inputs"]] == [
        path for path in builder.RUNTIME_PATHS if path not in canonical_paths
    ]
    assert all("sha256" not in row for row in manifest["semantic_inputs"])
    package = builder.build_package()
    assert manifest["package"]["sha256"] == hashlib.sha256(package).hexdigest()
    assert manifest["package"]["file_count"] == len(builder.PLUGIN_FILES)


def test_builder_is_offline_and_has_no_process_or_live_wordpress_surface() -> None:
    path = ROOT / "scripts/build_st1704_wordpress_publication_operator_v2.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert not imported & {"http", "requests", "socket", "subprocess", "urllib"}
    assert not calls & {"Popen", "run", "system", "urlopen"}
