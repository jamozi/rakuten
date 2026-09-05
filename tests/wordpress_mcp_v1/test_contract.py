from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

import pytest
from jsonschema.validators import Draft202012Validator
from scripts import build_wordpress_mcp_v1, raos_wordpress_publication_request


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/wordpress-mcp-v1"
PLUGIN = SLICE / "wordpress-plugin/raos-codex-mcp-abilities"


def test_owner_generator_defaults_to_manifest_mode(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        build_wordpress_mcp_v1,
        "write_manifest",
        lambda: calls.append("manifest"),
    )
    monkeypatch.setattr(sys, "argv", ["build_wordpress_mcp_v1.py"])

    assert build_wordpress_mcp_v1.main() == 0
    assert calls == ["manifest"]


def test_repo_plugin_registry_has_one_deterministic_owner_for_both_packages() -> None:
    registry = json.loads(build_wordpress_mcp_v1.REGISTRY.read_text())
    expected = build_wordpress_mcp_v1.repo_artifact_registry()
    assert registry == expected
    rows = {row["artifact_id"]: row for row in registry["artifacts"]}
    abilities = build_wordpress_mcp_v1.package_bytes(
        build_wordpress_mcp_v1.plugin_payloads()
    )
    assert rows["raos-codex-mcp-abilities-v1"]["package_sha256"] == (
        hashlib.sha256(abilities).hexdigest()
    )
    measurement = json.loads(
        (ROOT / build_wordpress_mcp_v1.MEASUREMENT_MANIFEST_PATH).read_text()
    )
    assert rows["raos-editorial-measurement-v1"]["package_sha256"] == (
        measurement["package_sha256"]
    )
    review = rows["raos-editorial-measurement-v1"]["migration_review"]
    assert review == {
        "schema": "RAOS_WORDPRESS_PLUGIN_MIGRATION_REVIEW_V1",
        "assessment": "REVIEWED_PLUGIN_OWNED_ACTIVATION_MIGRATION",
        "package_sha256": measurement["package_sha256"],
        "file_manifest_sha256": (
            build_wordpress_mcp_v1.REVIEWED_MEASUREMENT_FILE_MANIFEST_SHA256
        ),
    }


def test_owner_plugin_version_is_bound_across_package_and_runtime() -> None:
    assert build_wordpress_mcp_v1.PLUGIN_VERSION == "1.3.1"
    entrypoint = (PLUGIN / "raos-codex-mcp-abilities.php").read_text(
        encoding="utf-8"
    )
    assert " * Version: 1.3.1" in entrypoint
    assert "define('RAOS_CODEX_MCP_VERSION', '1.3.1');" in entrypoint
    assert (PLUGIN / "README.md").read_text(encoding="utf-8").startswith(
        "# RAOS Codex MCP Abilities 1.3.1\n"
    )


def test_owner_plugin_runtime_revision_is_bound_across_every_critical_class() -> None:
    revision = build_wordpress_mcp_v1.PLUGIN_RUNTIME_REVISION
    assert (
        raos_wordpress_publication_request.EXPECTED_PLUGIN_RUNTIME_REVISION
        == revision
    )
    assert re.fullmatch(r"[0-9a-f]{64}", revision)
    entrypoint = (PLUGIN / "raos-codex-mcp-abilities.php").read_text(
        encoding="utf-8"
    )
    assert (
        "'RAOS_CODEX_MCP_RUNTIME_REVISION',\n"
        f"    '{revision}'" in entrypoint
    )
    for relative in (
        "raos-codex-mcp-abilities.php",
        "includes/class-raos-codex-mcp-store.php",
        "includes/class-raos-codex-mcp-content.php",
        "includes/class-raos-codex-mcp-deployment.php",
    ):
        source = (PLUGIN / relative).read_text(encoding="utf-8")
        assert source.count(f"const RUNTIME_REVISION = '{revision}';") == 1
    assert build_wordpress_mcp_v1.runtime_manifest()["plugin"][
        "runtime_revision"
    ] == revision


def test_review_and_apply_ttls_are_distinct_and_exposed_without_ambiguity() -> None:
    store = (
        PLUGIN / "includes/class-raos-codex-mcp-store.php"
    ).read_text(encoding="utf-8")
    content = (
        PLUGIN / "includes/class-raos-codex-mcp-content.php"
    ).read_text(encoding="utf-8")
    deployment = (
        PLUGIN / "includes/class-raos-codex-mcp-deployment.php"
    ).read_text(encoding="utf-8")

    assert "const PROPOSAL_REVIEW_TTL_SECONDS = 3600;" in store
    assert "const APPLY_LEASE_TTL_SECONDS = 900;" in store
    assert "const TTL_SECONDS" not in store
    assert "$created_unix + self::PROPOSAL_REVIEW_TTL_SECONDS" in store
    # Content/theme/plugin approvals plus the exact wp-admin bootstrap
    # attestation each receive a fresh, internally consistent apply TTL.
    assert store.count("$approved_unix + self::APPLY_LEASE_TTL_SECONDS") == 4
    assert (
        "'proposal_review_ttl_seconds' => "
        "RAOS_Codex_MCP_Store::PROPOSAL_REVIEW_TTL_SECONDS"
    ) in content
    assert (
        "'lease_ttl_seconds' => "
        "RAOS_Codex_MCP_Store::APPLY_LEASE_TTL_SECONDS"
    ) in content
    assert (
        "'lease_ttl_seconds' => "
        "RAOS_Codex_MCP_Store::APPLY_LEASE_TTL_SECONDS"
    ) in deployment
    assert "'proposal_ttl_seconds'" not in content
    assert "'ttl_seconds'" not in content
    assert "'ttl_seconds'" not in deployment


def test_publication_runtime_binds_portfolio_materializer_and_browser_audit() -> None:
    required = {
        "changes/editorial-portfolio-v2/editorial-portfolio.v2.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/rakuten-capture-runtime-manifest.v1.json",
        "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json",
        "changes/wordpress-local-preview-v1/browser/check.sh",
        "changes/wordpress-local-preview-v1/browser/lighthouse_check.sh",
        "changes/wordpress-local-preview-v1/browser/wordpress_local_preview_audit.function.js",
        "changes/wordpress-local-preview-v1/bin/materialize_yoast.py",
        "changes/wordpress-local-preview-v1/fixtures/production-pages.json",
        "changes/wordpress-local-preview-v1/fixtures/production-pages/about-ad-policy.html",
        "changes/wordpress-local-preview-v1/fixtures/production-pages/comparison-policy.html",
        "changes/wordpress-local-preview-v1/fixtures/production-pages/privacy-policy.html",
        "changes/wordpress-local-preview-v1/policy-profiles.v1.json",
        "changes/wordpress-quality-audit-v1/quality-audit-contract.v1.json",
        "changes/wordpress-quality-audit-v1/quality-audit-ledger.v1.json",
        "scripts/raos_editorial_portfolio_v2.py",
        "scripts/wordpress_quality_audit_v1.py",
    }
    entrypoint = ROOT / "scripts/raos_editorial_portfolio_v2.py"
    for node in ast.walk(ast.parse(entrypoint.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith("raos."):
            continue
        module_path = Path("python", *node.module.split(".")).with_suffix(".py")
        if (ROOT / module_path).is_file():
            required.add(module_path.as_posix())
            continue
        package_path = ROOT / "python" / Path(*node.module.split("."))
        for alias in node.names:
            imported = package_path / f"{alias.name}.py"
            if imported.is_file():
                required.add(imported.relative_to(ROOT).as_posix())
    assert required <= set(build_wordpress_mcp_v1.RUNTIME_PATHS)
    runtime_paths = {
        row["path"] for row in build_wordpress_mcp_v1.runtime_manifest()["runtime_files"]
    }
    assert required <= runtime_paths
    assert not any(
        path.startswith(("output/", "tmp/")) for path in runtime_paths
    )


def test_quality_audit_ledger_is_runtime_input_without_a_fingerprint_cycle() -> None:
    contract = json.loads(
        (
            ROOT
            / "changes/wordpress-quality-audit-v1/quality-audit-contract.v1.json"
        ).read_text(encoding="utf-8")
    )
    fingerprint_inputs = {
        value
        for group in contract["fingerprint_groups"]
        for value in group["inputs"]
    }
    runtime_paths = set(build_wordpress_mcp_v1.RUNTIME_PATHS)

    assert {
        "changes/wordpress-quality-audit-v1/quality-audit-contract.v1.json",
        "changes/wordpress-quality-audit-v1/quality-audit-ledger.v1.json",
        "scripts/wordpress_quality_audit_v1.py",
    } <= runtime_paths
    assert "changes/wordpress-mcp-v1/runtime-manifest.v1.json" not in (
        fingerprint_inputs
    )
    assert "changes/wordpress-quality-audit-v1/quality-audit-ledger.v1.json" not in (
        fingerprint_inputs
    )


@pytest.mark.parametrize(
    "relative",
    [
        "includes/class-raos-codex-mcp-store.php",
        "includes/class-raos-codex-mcp-content.php",
        "includes/class-raos-codex-mcp-deployment.php",
    ],
)
@pytest.mark.parametrize("replacement", [b"", b"0" * 64])
def test_owner_build_rejects_stale_critical_class_runtime_revision(
    relative: str,
    replacement: bytes,
) -> None:
    payloads = {
        name: (PLUGIN / name).read_bytes()
        for name in build_wordpress_mcp_v1.PLUGIN_FILES
    }
    expected = build_wordpress_mcp_v1.PLUGIN_RUNTIME_REVISION.encode("ascii")
    payloads[relative] = payloads[relative].replace(expected, replacement, 1)
    with pytest.raises(
        build_wordpress_mcp_v1.BuildFailure,
        match="WORDPRESS_MCP_V1_PLUGIN_RUNTIME_REVISION_INVALID",
    ):
        build_wordpress_mcp_v1._validate_plugin_runtime_revision(payloads)


@pytest.mark.parametrize("remove_global", [False, True])
def test_owner_build_rejects_stale_main_runtime_identity(remove_global: bool) -> None:
    payloads = {
        name: (PLUGIN / name).read_bytes()
        for name in build_wordpress_mcp_v1.PLUGIN_FILES
    }
    main = payloads["raos-codex-mcp-abilities.php"]
    revision = build_wordpress_mcp_v1.PLUGIN_RUNTIME_REVISION.encode("ascii")
    if remove_global:
        marker = b"'RAOS_CODEX_MCP_RUNTIME_REVISION',\n    '" + revision + b"'"
    else:
        marker = b"const RUNTIME_REVISION = '" + revision + b"';"
    payloads["raos-codex-mcp-abilities.php"] = main.replace(marker, b"", 1)
    with pytest.raises(
        build_wordpress_mcp_v1.BuildFailure,
        match="WORDPRESS_MCP_V1_PLUGIN_RUNTIME_REVISION_INVALID",
    ):
        build_wordpress_mcp_v1._validate_plugin_runtime_revision(payloads)


def test_public_contract_and_schema_are_valid() -> None:
    contract = json.loads((SLICE / "contracts/wordpress-mcp.v1.json").read_text())
    schema = json.loads((SLICE / "contracts/wordpress-mcp.v1.schema.json").read_text())
    readme = (SLICE / "README.md").read_text(encoding="utf-8")
    Draft202012Validator.check_schema(schema)
    assert contract["version"] == "1.3.1"
    assert contract["wordpress_version"] == "7.1.x"
    assert contract["mcp_adapter"]["version"] == "0.6.1"
    assert contract["remote_proxy"]["version"] == "0.4.0"
    assert contract["local_bridge"]["sdk"].endswith("@1.30.0")
    assert contract["approval"] == {
        "channel": "wp-admin",
        "batch": True,
        "batch_all_or_nothing": True,
        "batch_manifest_bound": True,
        "batch_registered_exact_ids": True,
        "batch_plugin_excluded": True,
        "hash_suffix_length": 8,
        "minimum_reason_length": 10,
        "reauthentication": True,
        "self_approval": False,
        "review_ttl_seconds": 3600,
    }
    assert contract["publication_request"] == {
        "command": "make wordpress-production-request ARTICLES=all",
        "mapping": "changes/wordpress-local-preview-v1/production-mapping.v1.json",
        "local_preview_required": True,
        "proposal_idempotency": True,
        "deployment_transport": "wordpressDeployment stdio MCP",
        "approval_wait_seconds": 3600,
        "apply_recovery_seconds": 900,
        "operator_budget_seconds": 4500,
        "bridge_timeout_seconds": 4620,
        "foreground_timeout_seconds": 4680,
        "release_batch_identity_bound": True,
        "release_preflight_all_members": True,
        "atomic_batch_claim_before_mutation": True,
        "theme_before_content": True,
        "theme_tree_sha256_bound": True,
        "php_opcache_manifest_invalidation": True,
        "loaded_theme_runtime_readback": True,
        "plugin_in_release_batch": False,
        "production_readback": True,
        "anonymous_public_readback": True,
        "receipt_storage": ".secrets/wordpress-mcp/publication-requests",
    }
    assert "`--articles all`" in readme
    assert "partial or comma-separated selections fail closed" in readme
    assert "may be an exact comma-separated subset" not in readme
    assert contract["host_gates"] == {
        "global_kill_switch": "RAOS_OPERATOR_WRITES_ENABLED",
        "draft": "RAOS_CODEX_DRAFT_WRITES_ENABLED",
        "default": False,
    }
    assert contract["approval_scoped_apply_gate"] == {
        "storage": "RAOS_CODEX_PRIVATE_DIR",
        "created_by": "separate_wp_admin_approval",
        "kinds": ["CONTENT_RELEASE", "THEME_RELEASE", "PLUGIN_CHANGE"],
        "proposal_bound": True,
        "hash_bound": True,
        "single_use": True,
        "lease_ttl_seconds": 900,
        "removed_after_terminal_state": True,
    }


def test_public_batch_and_aggregate_receipt_schema_fail_closed() -> None:
    schema = json.loads((SLICE / "contracts/wordpress-mcp.v1.schema.json").read_text())
    validator = Draft202012Validator(schema)
    batch = {
        "schema": "RAOSWordPressPublicationBatchV1",
        "batch_token": "a" * 64,
        "batch_manifest_sha256": "b" * 64,
        "proposal_count": 2,
        "proposal_ids": ["c" * 64],
        "expires_at_gmt": "2026-08-29T12:00:00Z",
        "review_url": "https://kurashinoshirube.com/wp-admin/tools.php?page=raos-codex-proposals",
    }
    assert not validator.is_valid(batch)
    approved_batch = batch | {
        "expected_theme_tree_sha256": "e" * 64,
        "proposal_count": 1,
        "state": "APPROVED",
    }
    assert validator.is_valid(approved_batch)

    operation = {
        "schema": "OperationReceiptV1",
        "proposal_id": "d" * 64,
        "operation_id": "d" * 64,
        "state": "PENDING",
        "result_code": "PROPOSAL_PENDING_APPROVAL",
        "before_sha256": "e" * 64,
        "after_sha256": "f" * 64,
        "audit_id": "0" * 64,
    }
    aggregate = {
        "schema": "ReleaseWaitApplyReceiptV1",
        "batch_token": "a" * 64,
        "batch_manifest_sha256": "b" * 64,
        "proposal_count": 1,
        "proposal_ids": ["d" * 64],
        "state": "APPLIED",
        "receipts": [operation],
    }
    assert not validator.is_valid(aggregate)

    claim = {
        "schema": "RAOSWordPressPublicationBatchClaimV1",
        "batch_token": "a" * 64,
        "batch_manifest_sha256": "b" * 64,
        "proposal_count": 2,
        "proposal_ids": ["d" * 64],
        "batch_claimed_at_gmt": "2026-08-29T12:00:00Z",
        "proposals": [operation],
    }
    assert not validator.is_valid(claim)


def test_codex_project_enables_only_two_mcp_servers_without_secrets() -> None:
    config_bytes = (ROOT / ".codex/config.toml").read_bytes()
    config = tomllib.loads(config_bytes.decode("utf-8"))
    enabled = {
        name
        for name, server in config["mcp_servers"].items()
        if server.get("enabled") is True
    }
    assert enabled == {"wordpressEditor", "wordpressDeployment"}
    editor = config["mcp_servers"]["wordpressEditor"]
    deployment = config["mcp_servers"]["wordpressDeployment"]
    assert editor["enabled_tools"] == [
        "raos-codex-site-status",
        "raos-codex-content-list",
        "raos-codex-content-get",
        "raos-codex-content-create-draft",
        "raos-codex-content-update-draft",
        "raos-codex-content-propose-release",
        "raos-codex-publication-batch-register",
        "raos-codex-operation-get",
        "raos-measurement-aggregate-report",
    ]
    assert deployment["enabled_tools"] == [
        "deployment-status",
        "publication-batch-status",
        "release-wait-and-apply",
        "theme-propose-release",
        "plugin-propose-change",
        "plugin-apply-change",
        "operation-recover",
    ]
    lowered = config_bytes.lower()
    assert b"application_password" not in lowered
    assert b"bearer_token =" not in lowered
    assert b"wp_api_password" not in lowered


def test_root_final_static_checks_wordpress_owner_manifest() -> None:
    makefile = (ROOT / "Makefile").read_text()
    final_static = makefile.split("final-static:", 1)[1].split("\n\n", 1)[0]
    assert "$(MAKE) -C changes/wordpress-mcp-v1 manifest-check" in final_static


def test_editor_status_exposes_loaded_theme_runtime_version_and_revision() -> None:
    content = (
        PLUGIN / "includes/class-raos-codex-mcp-content.php"
    ).read_text(encoding="utf-8")
    status = content.split("public function site_status", 1)[1].split(
        "public function content_list", 1
    )[0]
    assert "get_stylesheet() === 'kurashinoshirube-child'" in status
    assert "defined('KURASHINOSHIRUBE_THEME_VERSION')" in status
    assert "constant('KURASHINOSHIRUBE_THEME_VERSION')" in status
    assert "'runtime_version' => $theme_runtime_version" in status
    assert "defined('KURASHINOSHIRUBE_THEME_RUNTIME_REVISION')" in status
    assert "constant('KURASHINOSHIRUBE_THEME_RUNTIME_REVISION')" in status
    assert "'runtime_revision' => $theme_runtime_revision" in status
    assert "'plugin_runtime_revision' => $plugin_runtime_revision" in status


def test_editor_status_and_publication_mutations_require_exact_yoast_28_3() -> None:
    content = (
        PLUGIN / "includes/class-raos-codex-mcp-content.php"
    ).read_text(encoding="utf-8")
    deployment = (
        PLUGIN / "includes/class-raos-codex-mcp-deployment.php"
    ).read_text(encoding="utf-8")
    status = content.split("public function site_status", 1)[1].split(
        "public function content_list", 1
    )[0]
    yoast = content.split("public static function yoast_status", 1)[1].split(
        "public static function exact_yoast_gate", 1
    )[0]
    gate = content.split("public static function exact_yoast_gate", 1)[1].split(
        "public function site_status", 1
    )[0]
    claim = deployment.split("public function claim_publication_batch", 1)[1].split(
        "private static function publication_batch_status", 1
    )[0]
    apply_gate = deployment.split("private static function apply_gate", 1)[1].split(
        "private static function gate", 1
    )[0]

    assert "'yoast' => $yoast" in status
    assert "'wordpress-seo/wp-seo.php'" in yoast
    assert "get_file_data($plugin_path" in yoast
    assert "get_option('active_plugins'" in yoast
    assert "get_site_option('active_sitewide_plugins'" in yoast
    assert "defined('WPSEO_VERSION')" in yoast
    assert "'version_exact' => $version_exact" in yoast
    assert "'options' => $selected" in yoast
    assert "RAOS_Codex_MCP_Store::hash($settings)" in yoast
    assert "'settings_fingerprint'" in yoast
    assert "'settings_exact' => $settings_exact" in yoast
    for option_name in ("wpseo", "wpseo_social"):
        assert f"'{option_name}'" in yoast
    assert "'28.3' !== $status['version']" in gate
    assert "raos_codex_yoast_configuration_drift" in gate
    assert claim.index("RAOS_Codex_MCP_Content::exact_yoast_gate()") < claim.index(
        "RAOS_Codex_MCP_Store::claim_publication_batch_apply("
    )
    assert "array('CONTENT_RELEASE', 'THEME_RELEASE')" in apply_gate
    assert "RAOS_Codex_MCP_Content::exact_yoast_gate()" in apply_gate
    assert "PLUGIN_CHANGE" not in apply_gate.split("exact_yoast_gate", 1)[0].split(
        "array('CONTENT_RELEASE', 'THEME_RELEASE')", 1
    )[1]


def test_deployment_status_exposes_loaded_theme_runtime_version_and_revision() -> None:
    deployment = (
        PLUGIN / "includes/class-raos-codex-mcp-deployment.php"
    ).read_text(encoding="utf-8")
    status = deployment.split("public function status", 1)[1].split(
        "public function create_proposal", 1
    )[0]
    assert "defined('KURASHINOSHIRUBE_THEME_VERSION')" in status
    assert "constant('KURASHINOSHIRUBE_THEME_VERSION')" in status
    assert "'runtime_version' => $theme_runtime_version" in status
    assert "defined('KURASHINOSHIRUBE_THEME_RUNTIME_REVISION')" in status
    assert "constant('KURASHINOSHIRUBE_THEME_RUNTIME_REVISION')" in status
    assert "'runtime_revision' => $theme_runtime_revision" in status
    assert "'plugin_runtime_revision' => $plugin_runtime_revision" in status


def test_plugin_runtime_aggregate_and_mutation_gates_fail_closed() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text(encoding="utf-8")
    store = (
        PLUGIN / "includes/class-raos-codex-mcp-store.php"
    ).read_text(encoding="utf-8")
    content = (
        PLUGIN / "includes/class-raos-codex-mcp-content.php"
    ).read_text(encoding="utf-8")
    deployment = (
        PLUGIN / "includes/class-raos-codex-mcp-deployment.php"
    ).read_text(encoding="utf-8")

    aggregate = main.split("public static function plugin_runtime_revision", 1)[1]
    aggregate = aggregate.split("public static function runtime_identity_is_exact", 1)[
        0
    ]
    for class_name in (
        "__CLASS__",
        "'RAOS_Codex_MCP_Store'",
        "'RAOS_Codex_MCP_Content'",
        "'RAOS_Codex_MCP_Deployment'",
    ):
        assert class_name in aggregate
    for marker in (
        "defined('RAOS_CODEX_MCP_RUNTIME_REVISION')",
        "class_exists($class_name, false)",
        "defined($constant_name)",
        "constant($constant_name)",
        "hash_equals($expected, $actual)",
        "return null;",
    ):
        assert marker in aggregate

    assert "add_action('init', array($this, 'maybe_upgrade'), 0);" in main
    assert "array('RAOS_Codex_MCP_Store', 'maybe_upgrade')" not in main
    for method in (
        "activate",
        "maybe_upgrade",
        "transport_permission",
        "ability_permission",
        "operator_rest_permission",
        "render_admin_page",
        "handle_approval",
        "handle_batch_approval",
    ):
        section = main.split(f"function {method}", 1)[1]
        section = section.split("\n    }", 1)[0]
        assert "runtime_identity" in section

    store_gate = store.split("private static function runtime_identity_gate", 1)[1]
    assert "defined('RAOS_CODEX_MCP_RUNTIME_REVISION')" in store_gate
    assert "method_exists('RAOS_Codex_MCP_Abilities', 'plugin_runtime_revision')" in store_gate
    assert "hash_equals(self::RUNTIME_REVISION, $revision)" in store_gate
    for method in (
        "install",
        "maybe_upgrade",
        "create",
        "get",
        "register_publication_batch",
        "get_publication_batch",
        "approve",
        "approve_publication_batch",
        "claim_publication_batch_apply",
        "claim_apply",
        "complete",
        "mark_failed",
    ):
        section = store.split(f"public static function {method}", 1)[1]
        before_database = section.split("global $wpdb;", 1)[0]
        assert "self::runtime_identity_gate()" in before_database

    for source in (content, deployment):
        helper = source.split("private static function loaded_plugin_runtime_revision", 1)[
            1
        ]
        assert "method_exists('RAOS_Codex_MCP_Abilities', 'plugin_runtime_revision')" in helper
        assert "hash_equals(self::RUNTIME_REVISION, $revision)" in helper
        assert "raos_codex_plugin_runtime_mixed" in helper


def test_lockfile_has_exact_mcp_versions() -> None:
    lock = json.loads((ROOT / "package-lock.json").read_text())
    packages = lock["packages"]
    workspace = packages["packages/wordpress-mcp-bridge"]
    assert workspace["dependencies"] == {
        "@automattic/mcp-wordpress-remote": "0.4.0",
        "@modelcontextprotocol/sdk": "1.30.0",
        "zod": "4.4.3",
    }
    assert (
        packages["node_modules/@automattic/mcp-wordpress-remote"]["version"] == "0.4.0"
    )
    assert packages["node_modules/@modelcontextprotocol/sdk"]["version"] == "1.30.0"
    assert packages["node_modules/@playwright/cli"]["version"] == "0.1.18"
    assert packages["node_modules/zod"]["version"] == "4.4.3"


def test_local_bridge_initialization_tool_schemas_and_annotations() -> None:
    node = shutil.which("node")
    assert node is not None
    messages = "\n".join(
        (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "pytest", "version": "1.0.0"},
                    },
                }
            ),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            ),
            "",
        )
    )
    result = subprocess.run(
        [
            node,
            "--experimental-strip-types",
            "packages/wordpress-mcp-bridge/src/index.ts",
        ],
        cwd=ROOT,
        input=messages,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=20,
    )
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    initialized = next(response for response in responses if response.get("id") == 1)
    listed = next(response for response in responses if response.get("id") == 2)
    assert initialized["result"]["protocolVersion"] == "2025-11-25"
    instructions = initialized["result"]["instructions"]
    for boundary in (
        "cannot approve",
        "PHP",
        "SQL",
        "If-Match",
        "approval lease",
    ):
        assert boundary in instructions
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert set(tools) == {
        "deployment-status",
        "publication-batch-status",
        "release-wait-and-apply",
        "theme-propose-release",
        "plugin-propose-change",
        "plugin-apply-change",
        "operation-recover",
    }
    for tool in tools.values():
        assert tool["inputSchema"]["additionalProperties"] is False
    assert tools["publication-batch-status"]["inputSchema"]["properties"] == {
        "batch_token": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "batch_manifest_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "proposal_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
    }
    assert tools["release-wait-and-apply"]["inputSchema"]["properties"] == {
        "evidence_expires_at_gmt": {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        },
        "batch_token": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "batch_manifest_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "proposal_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
    }
    assert tools["publication-batch-status"]["annotations"] == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    plugin_schema = tools["plugin-propose-change"]["inputSchema"]
    serialized = json.dumps(plugin_schema, sort_keys=True)
    for forbidden in ("url", "path", "zip", "uninstall", "delete", "command"):
        assert f'"{forbidden}"' not in serialized.lower()


def test_wordpress_plugin_hard_safety_boundaries_are_present() -> None:
    sources = "\n".join(path.read_text() for path in sorted(PLUGIN.rglob("*.php")))
    expected = (
        "mcp_adapter_create_default_server",
        "WP_MCP_VERSION",
        "'0.6.1'",
        "RAOS_CODEX_APPROVAL_LEASE_V1",
        "approval_scoped_lease",
        "approval-lease-",
        "wp_authenticate_application_password_errors",
        "rest_request_before_callbacks",
        "XMLRPC_REQUEST",
        "If-Match",
        "Idempotency-Key",
        "raos_codex_self_approval_forbidden",
        "wp_check_password",
        "MANUAL_REVIEW_REQUIRED",
        "REVIEWED_PLUGIN_OWNED_ACTIVATION_MIGRATION",
        "PLUGIN_BOOTSTRAP_ATTESTED_AFTER_MANUAL_INSTALL",
        "raos_codex_mcp_attest_bootstrap",
        "raos_codex_zip_symlink_refused",
        "raos_codex_zip_case_collision",
        "raos_codex_code_hash_drift",
        "raos_codex_atomic_filesystem_required",
        "downloads.wordpress.org",
        "RAOS_CODEX_REPO_ARTIFACT_HASHES",
        "raos_codex_wordpress_org_digest_mismatch",
        "raos_codex_plugin_activation_failed",
        "X-RAOS-Batch-Token",
        "X-RAOS-Batch-Manifest-SHA256",
        "Content and theme proposals cannot be approved individually.",
    )
    for marker in expected:
        assert marker in sources
    assert "$handler['callback']" in sources
    assert "'0000-00-00 00:00:00' === $modified_gmt" in sources
    assert "get_gmt_from_date($post->post_modified, 'Y-m-d H:i:s')" in sources
    assert "publish_posts" not in sources
    assert "manage_plugins" not in sources
    assert "uninstall_plugin(" not in sources
    assert "eval(" not in sources
    for retired_gate in (
        "RAOS_CODEX_CONTENT_APPLY_ENABLED",
        "RAOS_CODEX_THEME_APPLY_ENABLED",
        "RAOS_CODEX_PLUGIN_APPLY_ENABLED",
    ):
        assert retired_gate not in sources
    assert not re.search(r"register_rest_route\([^)]*(?:wp/v2|xmlrpc)", sources)


def test_manual_bootstrap_attestation_is_wp_admin_only_and_exactly_bound() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text()
    deployment = (
        PLUGIN / "includes/class-raos-codex-mcp-deployment.php"
    ).read_text()
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()
    operator = (ROOT / "scripts/raos_wordpress_deployment_operator.py").read_text()

    assert "admin_post_raos_codex_mcp_attest_bootstrap" in main
    assert "check_admin_referer('raos_codex_mcp_attest_bootstrap_'" in main
    assert "wp_check_password($current_password" in main
    assert "proposal_suffix" in main
    assert "package_suffix" in main
    assert "validate_manual_bootstrap_attestation($row)" in main
    assert "RAOS_Codex_MCP_Deployment::attest_manual_bootstrap(" in main
    assert "/attest" not in deployment
    assert "attest-manual-bootstrap" not in operator
    assert "bootstrap-attest" not in operator

    for marker in (
        "BOOTSTRAP_ARTIFACT_ID = 'raos-codex-mcp-abilities-v1'",
        "BOOTSTRAP_SLUG = 'raos-codex-mcp-abilities'",
        "BOOTSTRAP_VERSION = '1.3.1'",
        "secure_staged_file($row['package_path'])",
        "validate_proposal_integrity($row)",
        "hash_equals($row['after_sha256'], $target['tree_sha256'])",
        "hash_equals($descriptor_json, $validated_json)",
        "verify_package_provenance($validated, $package)",
        "raos_codex_bootstrap_attestation_channel_refused",
        "wp_doing_ajax()",
        "wp_doing_cron()",
    ):
        assert marker in deployment
    assert "WHERE proposal_id = %s AND kind = 'PLUGIN_CHANGE'" in store
    assert "AND state = 'MANUAL_REQUIRED'" in store
    assert "AND result_code = 'MANUAL_REVIEW_REQUIRED'" in store
    assert "AND created_by <> %d" in store
    assert "AND after_sha256 = %s AND payload_json = %s" in store
    assert "PLUGIN_BOOTSTRAP_ATTESTED_AFTER_MANUAL_INSTALL" in store
    assert "RAOS_Codex_MCP_Deployment::remove_approval_lease" in store
    assert "RAOS_Codex_MCP_Deployment::BOOTSTRAP_ARTIFACT_ID" in store
    assert "RAOS_Codex_MCP_Deployment::validate_manual_bootstrap_attestation(" in store
    assert "true !== constant('RAOS_OPERATOR_WRITES_ENABLED')" in store
    assert "raos_codex_self_approval_forbidden" in store


def test_reviewed_measurement_migration_identity_agrees_in_both_validators() -> None:
    registry = json.loads(build_wordpress_mcp_v1.REGISTRY.read_text())
    measurement = next(
        row
        for row in registry["artifacts"]
        if row["artifact_id"] == "raos-editorial-measurement-v1"
    )
    review = measurement["migration_review"]
    deployment = (
        PLUGIN / "includes/class-raos-codex-mcp-deployment.php"
    ).read_text()
    operator = (ROOT / "scripts/raos_wordpress_deployment_operator.py").read_text()
    for value in (
        measurement["artifact_id"],
        measurement["slug"],
        measurement["version"],
        measurement["package_sha256"],
        review["file_manifest_sha256"],
        review["assessment"],
    ):
        assert value in deployment
        assert value in operator
    assert "reviewed_migration_eligible(" in deployment
    assert "_reviewed_migration_eligible(" in operator
    assert "verify_package_provenance($validated, $package)" in deployment
    assert "raos_codex_code_validation_drift" in deployment


def test_editor_and_operator_credentials_are_separate_and_route_bound() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text()
    assert "raos_codex_mcp_editor" in main
    assert "raos_codex_deployment_operator" in main
    assert "RAOS Codex Editor MCP" in main
    assert "RAOS Codex Deployment Bridge" in main
    assert "'/raos-codex-mcp/v1/editor'" in main
    assert "'/raos-codex-deploy/v1/status'" in main
    assert "administrator" in main
    assert "array($role => true) === $user->caps" in main


def test_private_credential_launchers_enforce_purpose_and_non_reuse() -> None:
    editor_launcher = (
        ROOT / "scripts/raos_wordpress_editor_mcp_launcher.mjs"
    ).read_text()
    operator = (ROOT / "scripts/raos_wordpress_deployment_operator.py").read_text()
    credential_store = (ROOT / "scripts/store_wordpress_mcp_credential.py").read_text()
    assert "editor-application-password.v1.json" in editor_launcher
    assert "operator-application-password.v1.json" in editor_launcher
    assert (
        "operator.application_password === editor.application_password"
        in editor_launcher
    )
    assert "proxyMetadata?.version !== '0.4.0'" in editor_launcher
    assert '"deployment_operator"' in operator
    assert "stat.S_IMODE(metadata.st_mode) != 0o600" in operator
    assert "WORDPRESS_MCP_CREDENTIAL_REUSE_FORBIDDEN" in credential_store
    assert "getpass.getpass" in credential_store
    assert '"--replace-username"' in credential_store
    assert "os.replace(temporary, target)" in credential_store
    assert "APPLICATION_PASSWORD_NAMES" in credential_store


def test_disposable_wordpress_71_e2e_is_pinned_and_separate_from_live() -> None:
    e2e = ROOT / "tests/wordpress_mcp_v1/e2e"
    compose = (e2e / "compose.yaml").read_text()
    gateway = (e2e / "gateway/nginx.conf").read_text()
    runner = (e2e / "run.sh").read_text()
    client = (e2e / "client.py").read_text()
    approval = (e2e / "approve_harness.php").read_text()
    assert "wordpress:7.1.0-php8.3-apache@sha256:" in compose
    assert "wordpress:cli-2.12.0-php8.3@sha256:" in compose
    assert "mariadb:11.8.3@sha256:" in compose
    assert "nginx:1.29.1-alpine@sha256:" in compose
    assert "internal: true" in compose
    assert compose.count("ports:") == 1
    assert compose.count("target: /var/www/html") == 2
    assert compose.count("target: /var/www/raos-code") == 2
    assert "target: /var/www/raos-codex-private" not in compose
    assert "RAOS_CODEX_PRIVATE_DIR', '/var/www/raos-code/private'" in compose
    assert (
        "'127.0.0.1:${RAOS_WORDPRESS_E2E_PORT:?RAOS_WORDPRESS_E2E_PORT is required}:8080'"
        in compose
    )
    assert "compose up --detach database wordpress gateway" in runner
    assert 'install -d -m 0755 "$RAOS_WORDPRESS_E2E_DATA_DIR"' in runner
    assert "rewrite structure '/%postname%/' --hard" in runner
    assert "config set WP_CONTENT_DIR /var/www/raos-code/wp-content" in runner
    assert '"$(wordpress_cli core version)" == 7.1' in runner
    assert "RAOS_WORDPRESS_E2E_EDITOR_ROUTE_MISSING" in runner
    assert '--prompt=admin_password >"$install_log" 2>&1' in runner
    assert "umask 0077" in runner
    assert "[[:alnum:]_-]{32,}" in runner
    assert runner.count("--porcelain >/dev/null 2>&1") == 2
    assert "approve_proposal()" in runner
    assert "RAOS_WORDPRESS_E2E_APPROVAL_FAILED" in runner
    assert "proxy_pass http://wordpress:80;" in gateway
    assert "proxy_set_header X-Forwarded-Proto https;" in gateway
    assert "client_max_body_size 48m;" in gateway
    assert "location ^~ /.raos-codex-private/" in gateway
    assert "return 404;" in gateway
    assert "RAOS_CODEX_CONTENT_APPLY_ENABLED" not in compose
    assert "RAOS_CODEX_THEME_APPLY_ENABLED" not in compose
    assert "RAOS_CODEX_PLUGIN_APPLY_ENABLED" not in compose
    assert "RAOS_OPERATOR_WRITES_ENABLED', true" in compose
    assert "RAOS_CODEX_REPO_ARTIFACT_HASHES" in compose
    assert "1c3cd47c32e99b4e7d8690a44a7890256e92a8b96f61776cbe1894e5483cf676" in runner
    assert "docker compose" in runner
    assert "down --volumes --remove-orphans" in runner
    assert "http://127.0.0.1:" in client
    assert "tools/list" in client
    assert "raos_codex_rest_scope_forbidden" in client
    assert "raos_codex_publication_batch_headers_invalid" in client
    assert "PLUGIN_CHANGE_APPLIED" in client
    assert "THEME_RELEASE_APPLIED" in client
    assert "raos_codex_code_readback_failed" in client
    assert "handle_approval()" in approval
    assert "$_REQUEST = $_POST;" in approval
    assert "RAOS_Codex_MCP_Store::approve" not in approval


def test_disposable_code_artifacts_are_reproducible(tmp_path: Path) -> None:
    # The deployment operator intentionally refuses to package a dirty theme.
    # This integration worktree contains the candidate theme edits, so the
    # clean-checkout reproducibility assertion is exercised in CI/release
    # checkouts while local development remains fail-closed.
    relative_theme = (
        "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
        "kurashinoshirube-child"
    )
    if subprocess.run(
        ("git", "status", "--porcelain=v1", "--", relative_theme),
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout:
        pytest.skip("candidate theme is intentionally dirty in the integration worktree")
    script = ROOT / "tests/wordpress_mcp_v1/e2e/prepare_packages.py"
    first = tmp_path / "first"
    second = tmp_path / "second"
    for destination in (first, second):
        subprocess.run(
            [str(ROOT / ".venv/bin/python"), str(script), str(destination)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    assert (first / "artifacts.json").read_bytes() == (
        second / "artifacts.json"
    ).read_bytes()
    assert (first / "kurashinoshirube-child-baseline.zip").read_bytes() == (
        second / "kurashinoshirube-child-baseline.zip"
    ).read_bytes()
    bundle = json.loads((first / "artifacts.json").read_text(encoding="ascii"))
    assert set(bundle) == {
        "schema",
        "theme",
        "plugin_success",
        "plugin_rollback",
    }
    assert bundle["theme"]["code_package"]["slug"] == "kurashinoshirube-child"
    assert bundle["plugin_success"]["code_package"]["automatic_apply_eligible"]
    assert bundle["plugin_rollback"]["code_package"]["automatic_apply_eligible"]
