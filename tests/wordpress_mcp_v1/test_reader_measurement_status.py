"""Reader status is a bounded, read-only projection alongside legacy measurement."""

from __future__ import annotations

from copy import deepcopy
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTENT = "changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/includes/class-raos-codex-mcp-content.php"
HARNESS = r"""
define('ABSPATH', '/synthetic/');
define('WP_PLUGIN_DIR', '/synthetic/missing-plugins');
define('RAOS_CODEX_MCP_VERSION', 'synthetic');
$wp_version = '7.1.0';
$input = json_decode(base64_decode($argv[1]), true, 512, JSON_THROW_ON_ERROR);
$abilities = array();
$reader_calls = 0;
function home_url($path = '') { return 'https://kurashinoshirube.com' . $path; }
function get_stylesheet() { return 'kurashinoshirube-child'; }
function wp_get_theme($slug) {
    return new class {
        public function exists() { return true; }
        public function get($field) { return '1.5.1'; }
    };
}
function get_option($name, $default = null) { return $default; }
function is_multisite() { return false; }
function wp_register_ability($name, $config) {
    $GLOBALS['abilities'][$name] = $config['meta']['annotations'];
}
function update_option(...$args) { throw new RuntimeException('status may not write'); }
function wp_remote_request(...$args) { throw new RuntimeException('status may not use network'); }
final class RAOS_Codex_MCP_Store {
    const APPLY_LEASE_TTL_SECONDS = 900;
    const PROPOSAL_REVIEW_TTL_SECONDS = 3600;
    public static function hash($value) { return hash('sha256', json_encode($value)); }
}
if ($input['available']) {
    function raos_reader_measurement_status() {
        $GLOBALS['reader_calls']++;
        if ($GLOBALS['reader_sample'] === 'throw') {
            throw new RuntimeException('private approval actor and raw row');
        }
        return $GLOBALS['reader_sample'];
    }
}
if ($input['legacy']) {
    define('RAOS_EDITORIAL_MEASUREMENT_VERSION', 'legacy-fixture');
    function raos_editorial_measurement_enabled() { return true; }
    function wp_get_ability($name) { return $name === 'raos-measurement/aggregate-report'; }
}
require $argv[2];
$content = new RAOS_Codex_MCP_Content(new stdClass());
$content->register_abilities();
$statuses = array();
foreach ($input['samples'] as $reader_sample) {
    $statuses[] = $content->site_status(array('collection_enabled' => true));
}
echo json_encode(array('statuses' => $statuses, 'abilities' => $abilities, 'reader_calls' => $reader_calls), JSON_THROW_ON_ERROR);
"""


def run_status(samples, *, available=True, legacy=False):
    php = os.environ.get("RAOS_PHP_BIN") or shutil.which("php")
    if not php:
        pytest.skip("PHP CLI unavailable; reader site-status harness not executed")
    payload = base64.b64encode(
        json.dumps(
            {
                "samples": samples,
                "available": available,
                "legacy": legacy,
            }
        ).encode()
    ).decode()
    result = subprocess.run(
        [php, "-d", "display_errors=1", "-r", HARNESS, payload, str(ROOT / CONTENT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    return json.loads(result.stdout)


def status(*, enabled=False):
    return {
        "schema": "RAOSReaderMeasurementStatusV1",
        "plugin_active": True,
        "plugin_version": "1.0.0",
        "collection_enabled": enabled,
        "contract_sha256": "a" * 64,
        "policy_sha256": "b" * 64,
        "approved_revision": "c" * 64 if enabled else None,
        "cleanup": {
            "healthy": True,
            "last_success_date": "2026-09-06",
            "last_error_code": None,
        },
    }


def test_missing_plugin_has_unknown_collection_and_keeps_legacy_off():
    result = run_status([None], available=False)
    actual = result["statuses"][0]
    assert "reader_measurement" in actual
    assert actual["reader_measurement"] == {
        "schema": "RAOSReaderMeasurementStatusV1",
        "plugin_active": False,
        "plugin_version": None,
        "collection_enabled": None,
        "contract_sha256": None,
        "policy_sha256": None,
        "approved_revision": None,
        "cleanup": {
            "healthy": None,
            "last_success_date": None,
            "last_error_code": None,
        },
    }
    assert actual["measurement"] == {
        "plugin_active": False,
        "plugin_version": None,
        "collection_enabled": False,
        "aggregate_ability_registered": False,
        "raw_event_tool_exposed": False,
    }
    assert result["reader_calls"] == 0


def test_reader_known_off_and_on_do_not_replace_legacy_status_or_add_abilities():
    samples = [status(), status(enabled=True)]
    result = run_status(samples, legacy=True)
    for actual, expected in zip(result["statuses"], samples, strict=True):
        assert "reader_measurement" in actual
        assert actual["reader_measurement"] == expected
        assert actual["measurement"] == {
            "plugin_active": True,
            "plugin_version": "legacy-fixture",
            "collection_enabled": True,
            "aggregate_ability_registered": True,
            "raw_event_tool_exposed": False,
        }
        assert not any(actual["writes_enabled"].values())
    assert result["reader_calls"] == 2
    assert set(result["abilities"]) == {
        "raos-codex/site-status",
        "raos-codex/content-list",
        "raos-codex/content-get",
        "raos-codex/content-create-draft",
        "raos-codex/content-update-draft",
        "raos-codex/content-propose-release",
        "raos-codex/publication-batch-register",
        "raos-codex/operation-get",
    }
    assert result["abilities"]["raos-codex/site-status"] == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def test_projection_never_forwards_extra_private_fields_or_error_details():
    sample = status(enabled=True)
    sample.update({"approval_actor_id": 42, "raw_rows": [{"private": "secret"}]})
    sample["cleanup"]["error_message"] = "secret host/database/actor"
    result = run_status([sample, "throw"])
    assert "reader_measurement" in result["statuses"][0]
    assert result["statuses"][0]["reader_measurement"] == status(enabled=True)
    failed = result["statuses"][1]["reader_measurement"]
    assert failed["collection_enabled"] is None
    assert failed["cleanup"]["healthy"] is None
    assert "secret" not in json.dumps(result)
    assert "private approval actor" not in json.dumps(result)


def test_invalid_status_schema_types_and_contradictions_never_claim_enabled():
    samples = [None, [], "invalid", {}, {"schema": "Other"}]
    for field, value in (
        ("schema", "Other"),
        ("plugin_active", "true"),
        ("plugin_active", False),
        ("collection_enabled", 1),
        ("collection_enabled", "false"),
        ("plugin_version", {"private": "secret"}),
        ("contract_sha256", "bad"),
        ("policy_sha256", "b" * 64 + "\n"),
        ("approved_revision", 42),
        ("cleanup", {"healthy": "yes"}),
    ):
        sample = status(enabled=True)
        sample[field] = value
        samples.append(sample)
    samples.append(
        {
            key: value
            for key, value in status(enabled=True).items()
            if key != "collection_enabled"
        }
    )
    result = run_status(samples)
    for actual in result["statuses"]:
        assert "reader_measurement" in actual
        assert actual["reader_measurement"]["collection_enabled"] is None


def test_cleanup_dates_and_codes_are_bounded_without_exposing_arbitrary_text():
    samples = []
    for field, value in (
        ("healthy", "true"),
        ("last_success_date", "2026-02-30"),
        ("last_success_date", "2026-09-06\n"),
        ("last_error_code", {"private": "secret"}),
        ("last_error_code", "database password is secret"),
        ("last_error_code", "x" * 500),
    ):
        sample = deepcopy(status())
        sample["cleanup"][field] = value
        samples.append(sample)
    result = run_status(samples)
    for actual in result["statuses"]:
        assert "reader_measurement" in actual
        assert actual["reader_measurement"]["cleanup"] == {
            "healthy": None,
            "last_success_date": None,
            "last_error_code": None,
        }
    assert "secret" not in json.dumps(result)


def test_cleanup_only_forwards_registered_error_codes():
    codes = [
        "MAINTENANCE_UNAVAILABLE",
        "CLEANUP_STALE",
        "STORAGE_UNAVAILABLE",
        "CLEANUP_FAILED",
        "CLEANUP_STATUS_UNAVAILABLE",
    ]
    samples = []
    for code in codes + ["private_actor", "UNREGISTERED_ERROR"]:
        sample = status()
        sample["cleanup"].update(healthy=False, last_error_code=code)
        samples.append(sample)
    results = run_status(samples)["statuses"]
    assert [
        item["reader_measurement"]["cleanup"]["last_error_code"] for item in results
    ] == codes + [None, None]


def test_loaded_but_unavailable_reader_provider_cannot_masquerade_as_absent():
    results = run_status([None, "throw", {"schema": "Other"}])["statuses"]
    for item in results:
        assert item["reader_measurement"]["plugin_active"] is True
        assert item["reader_measurement"]["collection_enabled"] is None


def site_status_fixture():
    from scripts import raos_wordpress_publication_request as publication

    return {
        "schema": "RAOSWordPressSiteStatusV1",
        "origin": publication.ORIGIN,
        "wordpress_version_compatible": True,
        "mcp_adapter_version": "0.6.1",
        "mcp_adapter_version_compatible": True,
        "plugin_version": publication.EXPECTED_PLUGIN_VERSION,
        "plugin_runtime_revision": publication.EXPECTED_PLUGIN_RUNTIME_REVISION,
        "writes_enabled": dict.fromkeys(
            ("global", "draft", "content_apply", "theme_apply", "plugin_apply"), True
        ),
        "theme": {
            "slug": "kurashinoshirube-child",
            "exists": True,
            "active": True,
            "version": "1.5.1",
            "runtime_version": "1.5.1",
            "runtime_revision": "d" * 64,
        },
        "yoast": {
            "plugin_slug": "wordpress-seo",
            "installed": True,
            "active": True,
            "version": publication.EXPECTED_YOAST_VERSION,
            "version_exact": True,
            "options": deepcopy(publication.EXPECTED_YOAST_OPTIONS),
            "settings_fingerprint": publication.EXPECTED_YOAST_SETTINGS_FINGERPRINT,
            "settings_exact": True,
        },
        "apply_authorization": {
            "mode": "approval_scoped_lease",
            "default": False,
            "single_use": True,
            "lease_ttl_seconds": publication.EXPECTED_APPLY_LEASE_TTL_SECONDS,
        },
        "measurement": {
            "plugin_active": False,
            "plugin_version": None,
            "collection_enabled": False,
            "aggregate_ability_registered": False,
            "raw_event_tool_exposed": False,
        },
        "server": {
            "endpoint": publication.EDITOR_ENDPOINT,
            "publish_tool_exposed": False,
            "delete_tool_exposed": False,
            "media_write_tool_exposed": False,
            "proposal_review_ttl_seconds": publication.EXPECTED_PROPOSAL_REVIEW_TTL_SECONDS,
        },
    }


@pytest.mark.parametrize("enabled", [True, None])
def test_default_off_client_rejects_active_reader_on_or_unknown(enabled):
    from scripts import raos_wordpress_publication_request as publication

    value = site_status_fixture()
    value["reader_measurement"] = status(enabled=True)
    value["reader_measurement"]["collection_enabled"] = enabled
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(value, require_measurement_off=True)


def test_default_off_client_accepts_old_missing_block_absent_plugin_and_known_reader_off():
    from scripts import raos_wordpress_publication_request as publication

    value = site_status_fixture()
    publication.validate_site_status(value, require_measurement_off=True)
    value["reader_measurement"] = run_status([None], available=False)["statuses"][0][
        "reader_measurement"
    ]
    publication.validate_site_status(value, require_measurement_off=True)
    value["reader_measurement"] = status()
    publication.validate_site_status(value, require_measurement_off=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "Other"),
        ("plugin_active", 1),
        ("collection_enabled", "false"),
        ("contract_sha256", "bad"),
        ("approved_revision", 42),
        ("plugin_version", "private text"),
        ("approval_actor_id", 42),
        ("cleanup", {"healthy": True}),
    ],
)
def test_optional_reader_client_block_has_exact_fields_and_types_even_without_off_gate(
    field, value
):
    from scripts import raos_wordpress_publication_request as publication

    document = site_status_fixture()
    document["reader_measurement"] = status()
    document["reader_measurement"][field] = value
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(document)


@pytest.mark.parametrize(
    "field,value",
    [
        ("healthy", 1),
        ("last_success_date", "2026-02-30"),
        ("last_success_date", "2026-09-06\n"),
        ("last_error_code", "private error"),
        ("last_error_code", []),
        ("private_rows", []),
    ],
)
def test_client_never_accepts_unbounded_cleanup_fields(field, value):
    from scripts import raos_wordpress_publication_request as publication

    document = site_status_fixture()
    document["reader_measurement"] = status()
    document["reader_measurement"]["cleanup"][field] = value
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(document)


def test_optional_reader_validation_does_not_exempt_legacy_measurement_from_off_gate():
    from scripts import raos_wordpress_publication_request as publication

    value = site_status_fixture()
    value["reader_measurement"] = status()
    value["measurement"]["collection_enabled"] = True
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(value, require_measurement_off=True)


def test_valid_reader_on_is_only_shape_validation_when_off_gate_not_requested():
    from scripts import raos_wordpress_publication_request as publication

    value = site_status_fixture()
    value["reader_measurement"] = status(enabled=True)
    publication.validate_site_status(value)
    value["reader_measurement"]["plugin_active"] = False
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(value)


def legacy_site_status_fixture():
    value = site_status_fixture()
    value["plugin_version"] = "1.3.1"
    value["plugin_runtime_revision"] = (
        "c0dfb252e3920e87128fed6952f6a5f9ce099b57f2aed96d380ce3b02556f472"
    )
    return value


def test_legacy_runtime_requires_explicit_flag_and_exact_reviewed_pair():
    from scripts import raos_wordpress_publication_request as publication

    value = legacy_site_status_fixture()
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(value, require_measurement_off=True)
    publication.validate_site_status(
        value, require_measurement_off=True, allow_legacy_runtime=True
    )
    for field, replacement in (
        ("plugin_version", "1.3.0"),
        ("plugin_runtime_revision", "a" * 64),
        ("plugin_version", publication.EXPECTED_PLUGIN_VERSION),
        ("plugin_runtime_revision", publication.EXPECTED_PLUGIN_RUNTIME_REVISION),
    ):
        drifted = {**value, field: replacement}
        with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
            publication.validate_site_status(drifted, allow_legacy_runtime=True)


@pytest.mark.parametrize("enabled", [False, True, None])
def test_legacy_runtime_exception_never_allows_a_loaded_reader(enabled):
    from scripts import raos_wordpress_publication_request as publication

    value = legacy_site_status_fixture()
    value["reader_measurement"] = status(enabled=enabled)
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(value, allow_legacy_runtime=True)


def test_legacy_runtime_can_report_absent_reader_without_claiming_collection_off():
    from scripts import raos_wordpress_publication_request as publication

    value = legacy_site_status_fixture()
    value["reader_measurement"] = run_status([None], available=False)["statuses"][0][
        "reader_measurement"
    ]
    publication.validate_site_status(
        value, require_measurement_off=True, allow_legacy_runtime=True
    )


@pytest.mark.parametrize("reader", [None, [], {}, "unknown"])
def test_present_reader_block_must_be_complete(reader):
    from scripts import raos_wordpress_publication_request as publication

    value = site_status_fixture()
    value["reader_measurement"] = reader
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(value, require_measurement_off=True)


def test_unknown_loaded_reader_projection_is_valid_shape_but_never_default_off_ready():
    from scripts import raos_wordpress_publication_request as publication

    value = site_status_fixture()
    value["reader_measurement"] = run_status(["throw"])["statuses"][0][
        "reader_measurement"
    ]
    publication.validate_site_status(value)
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(value, require_measurement_off=True)
