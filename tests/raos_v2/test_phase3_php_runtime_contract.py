from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests/raos_v2/phase3-wordpress-runtime.php"
WORKFLOW = ROOT / ".github/workflows/ci.yml"
SOURCE_PLUGIN = ROOT / (
    "packages/web-ui/src/decision-support-v2/wordpress/plugin/"
    "raos-v2-decision-support/raos-v2-decision-support.php"
)
GENERATED_PLUGIN = ROOT / (
    "changes/raos-v2/phase-3/wordpress/artifact/"
    "raos-v2-decision-support/raos-v2-decision-support.php"
)
SOURCE_BINDING = SOURCE_PLUGIN.with_name("cutover-binding.v1.json")
GENERATED_BINDING = GENERATED_PLUGIN.with_name("cutover-binding.v1.json")
EXPECTED_PLUGIN_SHA256 = (
    "b7ebed3ffabd6a5067707ec898e15901382e1782459f5087a3798b27fdc970b1"
)


def test_phase3_php_harness_executes_all_fail_closed_runtime_cases() -> None:
    source = HARNESS.read_text(encoding="utf-8")

    for contract in (
        "RAOS_V2_PHASE3_WORDPRESS_RUNTIME_RECEIPT_V1",
        "LOCAL_CI_NOT_WORDPRESS_PRODUCTION",
        "PASSED_LOCAL_CI_STUB",
        "FAILED_LOCAL_CI_STUB",
        "INACTIVE_PLUGIN_RUNTIME_EFFECT",
        "TRACKED_BINDING_NOT_DEPLOYMENT_DISABLED",
        "NON_TARGET_CONTENT_CHANGED",
        "NON_TARGET_STYLE_ENQUEUED",
        "DISABLED_BINDING_TARGET_NOT_BLOCKED",
        "DISABLED_BINDING_TARGET_CONTENT_LEAKED",
        "DISABLED_BINDING_TARGET_STYLE_ENQUEUED",
        "MISSING_BINDING_TARGET_NOT_BLOCKED",
        "INVALID_BINDING_TARGET_NOT_BLOCKED",
        "WRONG_POST_ID_NOT_BLOCKED",
        "LEGACY_FILTER_TRANSFORM_NOT_PRESERVED",
        "LEGACY_TARGET_ENVELOPED",
        "LEGACY_TARGET_STYLE_ALLOWED",
        "INTERMEDIATE_CONTENT_NOT_BLOCKED",
        "INTERMEDIATE_CONTENT_LEAKED",
        "SEALED_TARGET_NOT_ACTIVATED",
        "SEALED_TARGET_STYLE_INVALID",
        "SEALED_TARGET_RAW_ENVELOPE_INVALID",
        "SEALED_TARGET_NOT_IDEMPOTENT",
        "SECONDARY_QUERY_CONTENT_CHANGED",
        "SECONDARY_QUERY_V2_PROJECTION_LEAKED",
        "MISMATCHED_CURRENT_POST_CONTENT_CHANGED",
        "OUTSIDE_MAIN_LOOP_TARGET_NOT_BLOCKED",
        "OUTSIDE_MAIN_LOOP_TARGET_CONTENT_LEAKED",
        "NON_MAIN_QUERY_TARGET_NOT_BLOCKED",
        "NON_MAIN_QUERY_TARGET_CONTENT_LEAKED",
        "MAIN_CONTENT_PROJECTION_COUNT_INVALID",
        "SEALED_EARLIER_FILTER_OUTPUT_NOT_DISCARDED",
        "SEALED_EARLIER_FILTER_OUTPUT_LEAKED",
        "BOUNDARY_BYTE_DRIFT_NOT_BLOCKED",
        "BOUNDARY_BYTE_DRIFT_LEAKED",
        "LATER_MAX_PRIORITY_FILTER_DID_NOT_TERMINATE",
        "LATER_MAX_PRIORITY_FILTER_EXECUTED",
        "FORBIDDEN_CAPABILITY_CALLED",
        "SOURCE_CAPABILITY_MUTATION_NOT_REJECTED",
        "PLUGIN_SOURCE_CAPABILITY_SURFACE_INVALID",
        "PLUGIN_SOURCE_BYTE_PIN_INVALID",
        "PLUGIN_SOURCE_BYTE_PIN_MUTATION_NOT_REJECTED",
        "SEALED_CONTENT_HASH_MISMATCH",
        "ACTION_HOOK_SURFACE_INVALID",
        "FILTER_HOOK_SURFACE_INVALID",
        "php_version",
        "plugin_version",
        "plugin_sha256",
        "STRICT_CALL_ALLOWLIST_PASSED",
        "EXPECTED_SHA256_MATCHED",
    ):
        assert contract in source

    assert "require $runtime_plugin_file;" in source
    assert "hash('sha256', $sealed_content)" in source
    assert "apply_filters('the_content', $wrapped) === $wrapped" in source
    assert "raos_v2_runtime_default_content_filter" in source
    assert "function is_main_query(): bool" in source
    assert "function in_the_loop(): bool" in source
    assert "function get_the_ID()" in source
    assert "$GLOBALS['post'] = $current_post ?? $queried_post;" in source
    assert "ARMED_EXACT_LEGACY_OR_SEALED" in source
    assert "catch (RaosV2RuntimeTermination $caught)" in source
    assert source.index("FORBIDDEN_CAPABILITY_CALLED") < source.index(
        "'status' => 'PASSED_LOCAL_CI_STUB'"
    )


def test_phase3_php_harness_has_no_skip_or_success_fallback() -> None:
    source = HARNESS.read_text(encoding="utf-8").lower()

    for prohibited in (
        "command -v php",
        "php --version ||",
        "continue-on-error",
        "status' => 'skipped",
        'status" => "skipped',
        "php_runtime_unavailable",
    ):
        assert prohibited not in source

    assert "catch (throwable $error)" in source
    assert "exit(1);" in source


def test_phase3_php_harness_runtime_surface_denies_write_network_admin_rest() -> None:
    source = HARNESS.read_text(encoding="utf-8")

    for forbidden_stub in (
        "wp_remote_get",
        "wp_remote_post",
        "wp_remote_request",
        "wp_insert_post",
        "wp_update_post",
        "update_option",
        "add_option",
        "delete_option",
        "update_post_meta",
        "register_rest_route",
        "wp_schedule_event",
        "set_transient",
    ):
        assert f"function {forbidden_stub}(" in source

    assert "'hook' => 'wp_enqueue_scripts'" in source
    assert "'hook' => 'the_content'" in source
    assert "'admin_hook' => false" in source
    assert "'rest_hook' => false" in source
    assert "'wordpress_write' => false" in source
    assert "'network' => false" in source
    assert "function raos_v2_runtime_plugin_source_violations(" in source
    assert "token_get_all($source)" in source
    assert "strpos($name, 'raos_v2_decision_support_') !== 0" in source
    assert "substr_count($source, '@file_get_contents($path)') !== 1" in source
    assert (
        "raos_v2_runtime_plugin_source_violations($plugin_source) === array()" in source
    )
    assert (
        f"const RAOS_V2_RUNTIME_EXPECTED_PLUGIN_SHA256 = '{EXPECTED_PLUGIN_SHA256}';"
    ) in source
    for plugin_path in (SOURCE_PLUGIN, GENERATED_PLUGIN):
        assert sha256(plugin_path.read_bytes()).hexdigest() == EXPECTED_PLUGIN_SHA256
    for direct_primitive in (
        "file_put_contents('/tmp/forbidden', 'x')",
        "fsockopen('example.invalid', 443)",
        "mysqli_connect('example.invalid')",
        "exec('false')",
        "unlink('/tmp/forbidden')",
        "new PDO('sqlite::memory:')",
        "$callable()",
        "$wpdb->query('DELETE')",
        "UnsafeRuntime::write()",
        "require '/tmp/forbidden.php'",
        "`false`",
    ):
        assert direct_primitive in source
    for byte_pin_mutation in (
        "https://example.invalid/write-probe",
        "add_action('wp_enqueue_scripts', 'session_start');",
        "$GLOBALS['raos_callable']();",
    ):
        assert byte_pin_mutation in source


def test_phase3_ci_executes_lint_and_both_artifacts_without_ignoring_failure(
    monkeypatch,
) -> None:
    from types import SimpleNamespace
    import pytest
    import yaml
    from scripts import raos_checks
    from scripts.build_raos_v2_successor import phase3_php_ci_wired

    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    assert phase3_php_ci_wired(WORKFLOW.read_text())
    without_php = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    del without_php["jobs"]["php"]
    assert not phase3_php_ci_wired(yaml.safe_dump(without_php))
    ignoring_failure = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    ignoring_failure["jobs"]["php"]["continue-on-error"] = "true"
    assert not phase3_php_ci_wired(yaml.safe_dump(ignoring_failure))
    job = workflow["jobs"]["php"]
    assert any(
        step.get("with", {}).get("php-version") == "7.4" for step in job["steps"]
    )
    assert any(
        step.get("run") == ".venv/bin/python scripts/raos_ci.py php"
        for step in job["steps"]
    )
    plan = SimpleNamespace(python_tests=(), node_tests=(), vitest_tests=(), php=True)
    commands = []
    failing = None

    def run(_root, command, label):
        commands.append(tuple(command))
        return int(label == failing)

    monkeypatch.setattr(raos_checks, "run", run)
    assert raos_checks.execute(ROOT, {}, plan, stage="php") == 0
    assert ("php", "-l", str(HARNESS.relative_to(ROOT))) in commands
    for kind, plugin in (("source", SOURCE_PLUGIN), ("generated", GENERATED_PLUGIN)):
        assert ("php", "-l", str(plugin.relative_to(ROOT))) in commands
        assert any(
            command[:4]
            == (
                "php",
                str(HARNESS.relative_to(ROOT)),
                kind,
                str(plugin.relative_to(ROOT)),
            )
            for command in commands
        )
    for failing in ("php-lint-harness", "php-runtime-source", "php-runtime-generated"):
        with pytest.raises(RuntimeError, match="check failed"):
            raos_checks.execute(ROOT, {}, plan, stage="php")


def test_phase3_source_and_generated_plugins_expose_only_public_render_hooks() -> None:
    for plugin_path in (SOURCE_PLUGIN, GENERATED_PLUGIN):
        source = plugin_path.read_text(encoding="utf-8").lower()
        assert source.count("add_action(") == 2
        assert source.count("add_filter(") == 1
        assert "'wp_enqueue_scripts'" in source
        assert "'template_redirect'" in source
        assert "'the_content'" in source
        assert "raos_v2_decision_support_version = '0.6.0'" in source
        assert "raos_v2_decision_support_main_content_post" in source
        assert "raos_v2_decision_support_current_content_post" in source
        assert "is_main_query()" in source
        assert "in_the_loop()" in source
        assert "get_the_id()" in source
        for prohibited in (
            "admin_init",
            "admin_menu",
            "rest_api_init",
            "wp_ajax_",
            "wp_remote_",
            "wp_insert_post",
            "wp_update_post",
            "update_option",
            "register_rest_route",
            "file_put_contents",
            "fopen(",
            "unlink(",
            "rename(",
            "fsockopen",
            "stream_socket_client",
            "mysqli_",
            "new pdo",
            "mail(",
            "exec(",
            "system(",
            "shell_exec(",
            "proc_open(",
        ):
            assert prohibited not in source


def test_phase3_source_and_generated_cutover_bindings_default_disabled() -> None:
    bindings = []
    for binding_path in (SOURCE_BINDING, GENERATED_BINDING):
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        assert binding["schema"] == "RAOS_V2_WORDPRESS_CUTOVER_BINDING_V1"
        assert binding["version"] == "1.0.0"
        assert binding["state"] == "DEPLOYMENT_DISABLED"
        assert binding["target"]["post_id"] == 0
        assert binding["hashes"]["legacy_post_content_sha256"] == "UNAVAILABLE"
        assert binding["hashes"]["preaction_binding_sha256"] == "UNAVAILABLE"
        assert binding["hashes"]["sealed_package_sha256"] == "UNAVAILABLE"
        assert binding["hashes"]["source_owner_export_sha256"] == "UNAVAILABLE"
        bindings.append(binding)
    assert bindings[0] == bindings[1]
