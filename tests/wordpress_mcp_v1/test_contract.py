from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

from jsonschema.validators import Draft202012Validator
from scripts import build_wordpress_mcp_v1


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


def test_owner_plugin_version_is_bound_across_package_and_runtime() -> None:
    assert build_wordpress_mcp_v1.PLUGIN_VERSION == "1.2.1"
    entrypoint = (PLUGIN / "raos-codex-mcp-abilities.php").read_text(
        encoding="utf-8"
    )
    assert " * Version: 1.2.1" in entrypoint
    assert "define('RAOS_CODEX_MCP_VERSION', '1.2.1');" in entrypoint
    assert (PLUGIN / "README.md").read_text(encoding="utf-8").startswith(
        "# RAOS Codex MCP Abilities 1.2.1\n"
    )


def test_public_contract_and_schema_are_valid() -> None:
    contract = json.loads((SLICE / "contracts/wordpress-mcp.v1.json").read_text())
    schema = json.loads((SLICE / "contracts/wordpress-mcp.v1.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    assert contract["version"] == "1.1.0"
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
        "ttl_seconds": 900,
    }
    assert contract["publication_request"] == {
        "command": "make wordpress-production-request ARTICLES=all",
        "mapping": "changes/wordpress-local-preview-v1/production-mapping.v1.json",
        "local_preview_required": True,
        "proposal_idempotency": True,
        "deployment_transport": "wordpressDeployment stdio MCP",
        "approval_wait_seconds": 900,
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
        "ttl_seconds": 900,
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
