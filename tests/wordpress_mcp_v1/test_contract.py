from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib

from jsonschema.validators import Draft202012Validator
from scripts import build_wordpress_mcp_v1


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/wordpress-mcp-v1"
PLUGIN = SLICE / "wordpress-plugin/raos-codex-mcp-abilities"
NODE = Path("/home/minami/.nvm/versions/node/v24.18.1/bin/node")


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


def test_public_contract_and_schema_are_valid() -> None:
    contract = json.loads((SLICE / "contracts/wordpress-mcp.v1.json").read_text())
    schema = json.loads((SLICE / "contracts/wordpress-mcp.v1.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    assert contract["wordpress_version"] == "7.1.x"
    assert contract["mcp_adapter"]["version"] == "0.6.1"
    assert contract["remote_proxy"]["version"] == "0.4.0"
    assert contract["local_bridge"]["sdk"].endswith("@1.30.0")
    assert contract["approval"] == {
        "channel": "wp-admin",
        "hash_suffix_length": 8,
        "minimum_reason_length": 10,
        "reauthentication": True,
        "self_approval": False,
        "ttl_seconds": 900,
    }


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
        "raos-codex-operation-get",
    ]
    assert deployment["enabled_tools"] == [
        "content-apply-release",
        "theme-propose-release",
        "theme-apply-release",
        "plugin-propose-change",
        "plugin-apply-change",
        "operation-recover",
    ]
    lowered = config_bytes.lower()
    assert b"application_password" not in lowered
    assert b"bearer_token =" not in lowered
    assert b"wp_api_password" not in lowered


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
            NODE,
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
    for boundary in ("cannot approve", "PHP", "SQL", "If-Match", "host gate"):
        assert boundary in instructions
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert set(tools) == {
        "content-apply-release",
        "theme-propose-release",
        "theme-apply-release",
        "plugin-propose-change",
        "plugin-apply-change",
        "operation-recover",
    }
    assert tools["content-apply-release"]["inputSchema"]["properties"] == {
        "proposal_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    }
    assert tools["content-apply-release"]["annotations"] == {
        "readOnlyHint": False,
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
        "RAOS_CODEX_CONTENT_APPLY_ENABLED",
        "RAOS_CODEX_THEME_APPLY_ENABLED",
        "RAOS_CODEX_PLUGIN_APPLY_ENABLED",
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
    assert (
        "'127.0.0.1:${RAOS_WORDPRESS_E2E_PORT:?RAOS_WORDPRESS_E2E_PORT is required}:8080'"
        in compose
    )
    assert "compose up --detach database wordpress gateway" in runner
    assert "proxy_pass http://wordpress:80;" in gateway
    assert "proxy_set_header X-Forwarded-Proto https;" in gateway
    assert "RAOS_CODEX_THEME_APPLY_ENABLED', true" in compose
    assert "RAOS_CODEX_PLUGIN_APPLY_ENABLED', true" in compose
    assert "RAOS_CODEX_REPO_ARTIFACT_HASHES" in compose
    assert "1c3cd47c32e99b4e7d8690a44a7890256e92a8b96f61776cbe1894e5483cf676" in runner
    assert "docker compose" in runner
    assert "down --volumes --remove-orphans" in runner
    assert "http://127.0.0.1:" in client
    assert "tools/list" in client
    assert "raos_codex_rest_scope_forbidden" in client
    assert "raos_codex_content_hash_drift" in client
    assert "PLUGIN_CHANGE_APPLIED" in client
    assert "THEME_RELEASE_APPLIED" in client
    assert "raos_codex_code_readback_failed" in client
    assert "handle_approval()" in approval
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
