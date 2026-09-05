from copy import deepcopy
from datetime import UTC, datetime

import pytest

from scripts.raos_wordpress_environment import compare


def observed():
    local = {
        "wordpress_version": "7.1",
        "php_version": "8.3.32",
        "theme": {"tree_sha256": "a" * 64},
        "yoast": {"version": "28.3", "settings_exact": True},
        "measurement": {"plugin_active": False},
        "script_debug": False,
    }
    snapshot = {
        "captured_at": "2026-09-06T00:00:00Z",
        "site_status": deepcopy(local),
        "deployment_status": {
            "runtime": {"php_version": "8.3.32"},
            "theme": local["theme"],
        },
    }
    return snapshot, local


def test_only_observed_matching_components_are_reported_as_matches():
    snapshot, local = observed()
    result = compare(snapshot, {}, local)
    assert all(row["status"] == "MATCH" for row in result["components"])
    assert result["production_observed_at"] == snapshot["captured_at"]
    assert result["not_observed"] and result["intentional_local_differences"]
    assert result["publication_authority"] is False


def test_old_snapshot_and_offline_plan_do_not_invent_runtime_parity():
    snapshot, local = observed()
    del snapshot["deployment_status"]["runtime"]
    result = compare(snapshot, {}, local)
    assert (
        next(row for row in result["components"] if row["component"] == "php")["status"]
        == "NOT_OBSERVED"
    )
    assert all(row["status"] == "NOT_OBSERVED" for row in compare({}, {})["components"])


def test_unselected_theme_drift_and_runtime_differences_remain_visible():
    snapshot, local = observed()
    local["theme"] = {"tree_sha256": "b" * 64}
    local["measurement"]["plugin_active"] = True
    result = compare(snapshot, {}, local)
    states = {row["component"]: row["status"] for row in result["components"]}
    assert states["theme"] == states["measurement"] == "DIFFERENT"
    selected = compare(
        snapshot, {"shared_artifacts": {"theme": {"sha256": "b" * 64}}}, local
    )
    states = {row["component"]: row["status"] for row in selected["components"]}
    assert states["theme"] == "SELECTED_CHANGE"
    assert states["measurement"] == "DIFFERENT"
    wrong_candidate = compare(
        snapshot, {"shared_artifacts": {"theme": {"sha256": "c" * 64}}}, local
    )
    assert (
        next(
            row for row in wrong_candidate["components"] if row["component"] == "theme"
        )["status"]
        == "DIFFERENT"
    )


def test_old_serving_configuration_is_visible_even_with_new_defaults():
    snapshot, local = observed()
    local["script_debug"] = True
    result = compare(snapshot, {}, local)
    assert result["local_configuration"]["script_debug"] is True
    assert result["local_configuration"]["status"] == "DIFFERENT"
    assert result["local_defaults"]["script_debug"] is False


@pytest.mark.parametrize(
    "field,new_value", [("php_version", "8.3.34"), ("script_debug", True)]
)
def test_serving_change_invalidates_original_browser_report(
    tmp_path, monkeypatch, field, new_value
):
    from tests.wordpress_local_preview.test_mixed_audit_report import evidence, owner
    from scripts.raos_wordpress_browser_plan import browser_plan
    import json

    inputs, raw, screenshots, _summary = evidence(tmp_path, monkeypatch)
    _snapshot, local = observed()
    inputs["serving_environment_sha256"] = owner.sha(owner.canonical(local))
    inputs["browser_plan"] = browser_plan(json.loads(owner.INVENTORY.read_bytes()))
    report = owner.assemble_report(
        inputs=inputs,
        raw_result=raw,
        artifact_directory=screenshots,
        started_at="2026-09-05T02:00:00+00:00",
        captured_at="2026-09-05T02:05:00+00:00",
    )
    report_path, original = tmp_path / "report.json", tmp_path / "original.txt"
    report_path.write_bytes(owner.canonical(report))
    original.write_bytes(raw)
    monkeypatch.setattr(owner, "REPORT", report_path)
    monkeypatch.setattr(owner, "ORIGINAL", original)
    monkeypatch.setattr(owner, "ARTIFACTS", screenshots)
    monkeypatch.setattr(
        owner, "current_inputs", lambda *args, **kwargs: deepcopy(inputs)
    )
    arguments = dict(
        fixture_root=tmp_path,
        origin=inputs["origin"],
        now=datetime(2026, 9, 5, 2, 30, tzinfo=UTC),
    )
    assert (
        owner.validate_report(report_path, **arguments)["captured_at"]
        == report["captured_at"]
    )
    local[field] = new_value
    inputs["serving_environment_sha256"] = owner.sha(owner.canonical(local))
    with pytest.raises(owner.ReportFailure):
        owner.validate_report(report_path, **arguments)
