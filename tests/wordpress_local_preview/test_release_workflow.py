"""Local selection/reuse behavior; no live credentials, browser or publication."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess

import pytest

from scripts.raos_wordpress_browser_plan import browser_plan
from scripts import raos_wordpress_verification as verification
from tests.wordpress_local_preview.test_mixed_audit_report import (
    inputs_and_results,
    owner,
)


def test_article_selection_covers_related_routes_without_fixed_screenshot_total():
    _inputs, _results, inventory = inputs_and_results()
    articles = [row for row in inventory["surfaces"] if row["kind"] == "article"]
    manifest = {
        "articles": [{"article_id": articles[0]["article_id"]}],
        "shared_artifacts": {},
    }
    markup = {row["article_id"]: "<p>Independent fixture</p>" for row in articles}
    planned = browser_plan(inventory, manifest, article_markup=markup)
    assert articles[0]["surface_id"] in planned["surface_ids"]
    assert all(
        row["surface_id"] in planned["surface_ids"]
        for row in inventory["surfaces"]
        if row["kind"] == "home"
    )
    assert len(planned["screenshots"]) < len(browser_plan(inventory)["screenshots"])
    full = browser_plan(
        inventory,
        {**manifest, "shared_artifacts": {"theme": {}}},
        article_markup=markup,
    )
    assert full["surface_ids"] == browser_plan(inventory)["surface_ids"]


def test_selected_browser_report_rejects_missing_and_wrong_surface_even_at_same_count():
    inputs, results, inventory = inputs_and_results()
    articles = [row for row in inventory["surfaces"] if row["kind"] == "article"]
    inputs["browser_plan"] = browser_plan(
        inventory,
        {
            "articles": [{"article_id": articles[0]["article_id"]}],
            "shared_artifacts": {},
        },
        article_markup={row["article_id"]: "<p>Fixture</p>" for row in articles},
    )
    chosen = [
        row
        for row in results
        if row["surface"] in inputs["browser_plan"]["surface_ids"]
    ]
    assert len(owner.validate_results(chosen, inventory, inputs)) == len(
        inputs["browser_plan"]["screenshots"]
    )
    with pytest.raises(owner.ReportFailure):
        owner.validate_results(chosen[:-1], inventory, inputs)
    changed = deepcopy(chosen)
    changed[0] = deepcopy(changed[1])
    with pytest.raises(owner.ReportFailure):
        owner.validate_results(changed, inventory, inputs)


def successful_check(tmp_path: Path):
    output = tmp_path / "output/fast.log"
    output.parent.mkdir()
    output.write_bytes(b"Synthetic checks passed\n")
    now = datetime(2026, 9, 6, tzinfo=UTC)
    result = {
        "schema": verification.SCHEMA,
        "check_id": "fast",
        "inputs": {"source_tree_sha256": "a" * 64},
        "exit_code": 0,
        "started_at": (now - timedelta(minutes=2)).isoformat(),
        "captured_at": (now - timedelta(minutes=1)).isoformat(),
        "output": "output/fast.log",
        "output_sha256": verification.digest(output.read_bytes()),
    }
    return output, now, result


def test_unchanged_result_reuses_original_without_retimestamping(tmp_path):
    _output, now, result = successful_check(tmp_path)
    before = deepcopy(result)
    assert verification.reusable(
        result, check_id="fast", inputs=result["inputs"], root=tmp_path, now=now
    )
    assert result == before


@pytest.mark.parametrize(
    "mutation",
    ["failed", "cancelled", "missing", "changed", "expired", "tampered", "symlink"],
)
def test_invalid_result_never_reused(tmp_path, mutation):
    output, now, result = successful_check(tmp_path)
    inputs = deepcopy(result["inputs"])
    if mutation == "failed":
        result["exit_code"] = 1
    elif mutation == "cancelled":
        result["exit_code"] = None
    elif mutation == "missing":
        output.unlink()
    elif mutation == "changed":
        inputs["source_tree_sha256"] = "b" * 64
    elif mutation == "expired":
        now += timedelta(days=1)
    elif mutation == "tampered":
        output.write_bytes(b"changed")
    else:
        actual = output.with_suffix(".actual")
        output.rename(actual)
        output.symlink_to(actual)
    assert not verification.reusable(
        result, check_id="fast", inputs=inputs, root=tmp_path, now=now
    )


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", None])
def test_required_ci_rejects_non_success(monkeypatch, tmp_path, conclusion):
    def run(command, **kwargs):
        if command[0] == "git":
            return subprocess.CompletedProcess(
                command, 0, stdout="a" * 40 if command[1] == "rev-parse" else b""
            )
        payload = {
            "workflow_runs": [
                {
                    "head_sha": "a" * 40,
                    "path": verification.WORKFLOW,
                    "event": "pull_request",
                    "run_number": 1,
                    "run_attempt": 1,
                    "status": "completed",
                    "conclusion": conclusion,
                }
            ]
        }
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload).encode()
        )

    monkeypatch.setattr(verification.subprocess, "run", run)
    with pytest.raises(ValueError, match="not successful"):
        verification.required_ci(tmp_path)


def test_required_ci_rejects_untracked_files_before_querying_github(
    monkeypatch, tmp_path
):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[0] == "git"
        return subprocess.CompletedProcess(
            command, 0, stdout=b"new_runtime.py\0" if command[1] == "ls-files" else b""
        )

    monkeypatch.setattr(verification.subprocess, "run", run)
    with pytest.raises(ValueError, match="untracked"):
        verification.required_ci(tmp_path)
    assert len(calls) == 2


@pytest.mark.parametrize("aggregate", ["success", "failure", "cancelled", "missing"])
def test_required_ci_requires_successful_aggregate_across_paginated_jobs(
    monkeypatch, tmp_path, aggregate
):
    def run(command, **kwargs):
        if command[0] == "git":
            return subprocess.CompletedProcess(
                command, 0, stdout="a" * 40 if command[1] == "rev-parse" else b""
            )
        if "--paginate" in command:
            payload = [
                {"jobs": [{"name": "Tests", "conclusion": "success"}]},
                {
                    "jobs": []
                    if aggregate == "missing"
                    else [{"name": "Final Integration", "conclusion": aggregate}]
                },
            ]
        else:
            payload = {
                "workflow_runs": [
                    {
                        "id": 77,
                        "html_url": "https://github.com/jamozi/rakuten/actions/runs/77",
                        "head_sha": "a" * 40,
                        "path": verification.WORKFLOW,
                        "event": "pull_request",
                        "run_number": 1,
                        "run_attempt": 2,
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            }
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload).encode()
        )

    monkeypatch.setattr(verification.subprocess, "run", run)
    if aggregate == "success":
        assert verification.required_ci(tmp_path)["run_attempt"] == 2
    else:
        with pytest.raises(ValueError, match="Final Integration"):
            verification.required_ci(tmp_path)


def test_changed_selection_invalidates_fast_result_even_for_same_tree(monkeypatch):
    from types import SimpleNamespace
    from scripts import raos_wordpress_release_workflow as workflow

    monkeypatch.setattr(verification, "source_fingerprint", lambda root: "a" * 64)

    def selected(tests):
        return SimpleNamespace(
            as_json=lambda: {
                "changed_files": [],
                "reasons": {},
                "full_reasons": [],
                "python_tests": tests,
            }
        )

    assert workflow.check_inputs(selected(["one.py"])) != workflow.check_inputs(
        selected(["one.py", "shared.py"])
    )


@pytest.mark.parametrize("changed", [False, True])
def test_implicit_resume_reuses_valid_subject_but_preserves_changed_subject(
    monkeypatch, tmp_path, changed
):
    from types import SimpleNamespace
    from scripts import raos_wordpress_release_workflow as workflow

    args = workflow.parser().parse_args(
        ["prepare", "--articles", "article-one", "--snapshot-name", "snapshot"]
    )
    old = tmp_path / "old-candidate"
    old.mkdir()
    original = old / "manifest.v1.json"
    original.write_bytes(b"original frozen candidate")

    def validate(path, **kwargs):
        assert path == old
        if changed:
            raise ValueError("CANDIDATE_CHANGED")

    monkeypatch.setattr(
        workflow.importlib,
        "import_module",
        lambda name: SimpleNamespace(prepare_candidate=validate),
    )
    state = {
        "request_scope": workflow.request_scope(args),
        "candidate": str(old),
        "preview_fixture": str(tmp_path / "preview"),
    }
    workflow.restore_selection(args, state)
    assert args.candidate == (None if changed else old)
    assert original.read_bytes() == b"original frozen candidate"


def test_unchanged_prepare_runs_no_tests_generation_sync_or_capture(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace
    from scripts import raos_wordpress_release_workflow as workflow

    args = workflow.parser().parse_args(
        [
            "prepare",
            "--candidate",
            str(tmp_path / "candidate"),
            "--preview-fixture",
            str(tmp_path / "preview"),
        ]
    )
    state = {
        "generation_source_sha256": "a" * 64,
        "checks": {"fast": {"original": True}},
    }
    selected = SimpleNamespace(
        as_json=lambda: {"changed_files": [], "reasons": {}, "full_reasons": []}
    )
    monkeypatch.setattr(
        workflow, "plan", lambda args: ({"missing_inputs": []}, selected, {})
    )
    monkeypatch.setattr(workflow, "previous_report", lambda: state)
    monkeypatch.setattr(verification, "source_fingerprint", lambda root: "a" * 64)
    monkeypatch.setattr(verification, "reusable", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        verification, "required_ci", lambda root: {"conclusion": "success"}
    )
    monkeypatch.setattr(workflow, "save_report", lambda result: None)

    def unexpected(*args, **kwargs):
        pytest.fail("unchanged preparation must not generate, test, sync or capture")

    monkeypatch.setattr(workflow, "_run", unexpected)
    monkeypatch.setattr(workflow, "generate_once", unexpected)
    monkeypatch.setattr(verification, "run_check", unexpected)

    def run(command, **kwargs):
        assert command[-1] == "status"
        return subprocess.CompletedProcess(
            command, 0, stdout=b"RAOS_WORDPRESS_PREVIEW_READY"
        )

    monkeypatch.setattr(workflow.subprocess, "run", run)
    monkeypatch.setattr(
        workflow.environment_owner,
        "capture_local",
        lambda *args: {
            "captured_at": "actual read time",
            "local": {"script_debug": False},
        },
    )
    report = {"captured_at": "original time", "screenshots": ["original.png"]}
    modules = {
        "raos_wordpress_incremental_publication": SimpleNamespace(
            prepare_candidate=lambda *args, **kwargs: SimpleNamespace(
                snapshot={}, manifest={}
            )
        ),
        "mixed_audit_report": SimpleNamespace(
            REPORT=tmp_path / "browser.json",
            current_inputs=lambda *args, **kwargs: {},
            validate_report=lambda *args, **kwargs: report,
        ),
    }
    monkeypatch.setattr(workflow.importlib, "import_module", lambda name: modules[name])
    result = workflow.prepare(args)
    assert result["browser"]["captured_at"] == "original time"
    assert result["checks"]["fast"] == {"original": True}


@pytest.mark.parametrize(
    "path,full",
    [
        ("scripts/raos_wordpress_incremental_publication.py", False),
        ("changes/wordpress-local-preview-v1/mu-plugins/preview.php", True),
        ("changes/wordpress-local-preview-v1/gateway/nginx.conf", True),
        ("changes/wordpress-local-preview-v1/compose.yaml", True),
        ("changes/editorial-measurement-v1/wordpress-plugin/plugin.php", True),
        ("unknown-runtime.py", True),
        ("changes/unknown-component/runtime.php", True),
        ("scripts/new_presentation_adapter.py", True),
        ("changes/wordpress-local-preview-v1/seed.php", True),
        ("tests/wordpress_local_preview/test_release_workflow.py", False),
    ],
)
def test_shared_and_unknown_presentation_select_full_but_release_only_does_not(
    path, full
):
    from scripts.raos_wordpress_browser_plan import presentation_requires_full

    assert presentation_requires_full([path]) is full


@pytest.mark.parametrize(
    "mutation", ["none", "article", "policy", "theme", "snapshot", "baseline"]
)
def test_candidate_fixture_mismatch_is_checked_before_browser_work(mutation):
    from scripts import raos_wordpress_incremental_publication as port

    snapshot = {
        "documents": [
            {"slug": "guide", "post_type": "post", "content_sha256": "b" * 64}
        ],
        "deployment_status": {"theme": {"tree_sha256": "c" * 64}},
    }
    manifest = {
        "articles": [
            {"article_id": "a01", "slug": "guide", "local_artifact": {"key": "local"}}
        ],
        "shared_artifacts": {"comparison-policy": {"sha256": "d" * 64}},
    }
    artifacts = {"local": b"new body"}
    inputs = {
        "source_snapshot_sha256": port.digest(
            port.publication.canonical_json_bytes(snapshot)
        ),
        "scope": {"selected_article_ids": ["a01"]},
        "article_body_sha256": {"guide": port.digest(artifacts["local"])},
        "page_body_sha256": {"comparison-policy": "d" * 64},
        "theme_tree_sha256": "c" * 64,
        "baseline_document_sha256": {"guide": "b" * 64},
    }
    if mutation == "article":
        inputs["article_body_sha256"]["guide"] = "e" * 64
    if mutation == "policy":
        inputs["page_body_sha256"]["comparison-policy"] = "e" * 64
    if mutation == "theme":
        inputs["theme_tree_sha256"] = "e" * 64
    if mutation == "snapshot":
        inputs["source_snapshot_sha256"] = "e" * 64
    if mutation == "baseline":
        inputs["baseline_document_sha256"]["guide"] = "e" * 64
    if mutation == "none":
        port.validate_browser_inputs(
            inputs, manifest=manifest, artifact_bytes=artifacts, snapshot=snapshot
        )
    else:
        with pytest.raises(port.publication.PublicationFailure, match="BROWSER_"):
            port.validate_browser_inputs(
                inputs, manifest=manifest, artifact_bytes=artifacts, snapshot=snapshot
            )


def test_browser_tool_upgrade_changes_reuse_inputs(monkeypatch):
    versions = {"chrome": "Google Chrome 150.0.0.1"}

    def run(command, **kwargs):
        assert command[-1] == "--version"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=versions["chrome"] if "chrome" in command[0] else "v24.18.1",
        )

    monkeypatch.setattr(owner.subprocess, "run", run)
    monkeypatch.setattr(owner.shutil, "which", lambda command: "/usr/bin/node")
    original = owner.tool_versions()
    versions["chrome"] = "Google Chrome 150.0.0.2"
    assert owner.tool_versions() != original


def test_owner_execution_receives_the_common_python_import_roots(monkeypatch):
    from scripts import raos_wordpress_release_workflow as workflow

    called = []
    monkeypatch.setattr(
        workflow.subprocess, "run", lambda command, **kwargs: called.append(kwargs)
    )
    workflow._run(["synthetic-owner"], {"PYTHONPATH": "/existing-extra"})
    assert called[0]["env"]["PYTHONPATH"].split(":") == [
        str(workflow.ROOT),
        str(workflow.ROOT / "python"),
        "/existing-extra",
    ]
