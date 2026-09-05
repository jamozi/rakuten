"""CI behavior: fail closed on missing required checks, defer Draft checks."""

from pathlib import Path

import pytest
import yaml

from scripts.raos_ci import aggregate, test_shards as select_test_shards
from scripts.raos_test_plan import JOBS

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.load(
    (ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader
)


def test_only_successful_selected_jobs_can_complete_integration() -> None:
    required = {job: job in {"static", "tests", "secrets"} for job in JOBS}
    results = {job: "success" if required[job] else "skipped" for job in JOBS}
    aggregate(required, results, plan_result="success", lock_result="success")
    for job in JOBS:
        for failure in (
            "failure",
            "cancelled",
            "",
            "skipped" if required[job] else "success",
        ):
            with pytest.raises(ValueError):
                aggregate(
                    required,
                    {**results, job: failure},
                    plan_result="success",
                    lock_result="success",
                )


def test_missing_plan_or_results_cannot_look_like_a_noop_success() -> None:
    required = {job: True for job in JOBS}
    results = {job: "success" for job in JOBS}
    for status in ("failure", "cancelled", "skipped", ""):
        with pytest.raises(ValueError):
            aggregate(required, results, plan_result=status, lock_result="success")
        with pytest.raises(ValueError):
            aggregate(required, results, plan_result="success", lock_result=status)
    with pytest.raises(ValueError):
        aggregate({}, results, plan_result="success", lock_result="success")
    with pytest.raises(ValueError):
        aggregate(required, {}, plan_result="success", lock_result="success")


def test_pr_and_daily_events_have_distinct_full_run_policy() -> None:
    events = WORKFLOW["on"]
    assert "ready_for_review" in events["pull_request"]["types"]
    assert events["schedule"] == [{"cron": "0 18 * * *"}]
    assert "workflow_dispatch" in events
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert "pull_request_target" not in events


def test_selected_jobs_use_the_shared_runner_and_explicit_draft_gate() -> None:
    jobs = WORKFLOW["jobs"]
    for name in JOBS:
        job = jobs[name]
        assert "needs.plan.outputs." + name in job["if"]
        assert {"plan", "lock"} <= set(job["needs"])
        assert any(
            step.get("run") == f".venv/bin/python scripts/raos_ci.py {name}"
            for step in job["steps"]
        )
    assert "draft" in jobs["lock"]["if"]
    assert "draft" in jobs["final"]["if"]
    assert jobs["final"]["name"] == "Final Integration"
    assert set(JOBS) | {"plan", "lock"} <= set(jobs["final"]["needs"])


def test_shard_jobs_receive_selection_and_do_not_cancel_other_shards() -> None:
    job = WORKFLOW["jobs"]["tests"]
    assert "needs.plan.outputs.shards" in job["strategy"]["matrix"]["shard"]
    assert job["strategy"]["fail-fast"] == "false"
    assert "matrix.shard" in job["env"]["RAOS_TEST_SHARD_INDEX"]
    assert "strategy.job-total" in job["env"]["RAOS_TEST_SHARD_TOTAL"]


def test_shards_scale_to_available_capacity_and_affected_scope() -> None:
    assert select_test_shards(full=True, python_files=1500) == list(range(1, 21))
    assert len(select_test_shards(full=True, python_files=1500, limit=256)) == 256
    assert select_test_shards(full=False, python_files=0) == [1]
    assert select_test_shards(full=False, python_files=25) == [1]
    assert select_test_shards(full=False, python_files=26) == [1, 2]
    assert len(select_test_shards(full=False, python_files=5000)) == 20
    for limit in (0, 257):
        with pytest.raises(ValueError, match="RAOS_CI_TEST_SHARDS"):
            select_test_shards(full=True, python_files=1500, limit=limit)


def test_external_actions_are_pinned_and_checkout_has_no_write_credentials() -> None:
    for job in WORKFLOW["jobs"].values():
        for step in job["steps"]:
            action = step.get("uses")
            if action is None or action.startswith("./"):
                continue
            repository, separator, revision = action.partition("@")
            assert separator and len(revision) == 40
            assert all(c in "0123456789abcdef" for c in revision)
            if repository == "actions/checkout":
                assert step["with"]["persist-credentials"] == "false"


def test_auto_merge_filters_draft_and_non_pr_runs() -> None:
    text = (ROOT / ".github/workflows/auto-merge.yml").read_text()
    assert "workflow_run.event == 'pull_request'" in text
    assert "draft" in text
