"""CI behavior: fail closed on missing required checks, defer Draft checks."""

import json
import os
from pathlib import Path
import subprocess
import sys

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
    assert jobs["final"]["if"] == "always()"
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


def test_draft_then_ready_cannot_turn_deferred_checks_into_gate_success() -> None:
    # Event-time selections remain skipped even if the PR is ready by aggregation.
    assert WORKFLOW["jobs"]["final"]["if"] == "always()"
    with pytest.raises(ValueError, match="lock validation must succeed"):
        aggregate(
            {job: True for job in JOBS},
            {job: "skipped" for job in JOBS},
            plan_result="success",
            lock_result="skipped",
        )


def merge_metadata() -> dict:
    sha = "a" * 40
    return {
        "run": {
            "id": 42, "run_attempt": 1, "status": "completed",
            "conclusion": "success", "event": "pull_request", "head_sha": sha,
            "repository": {"full_name": "example/repo"},
            "path": ".github/workflows/ci.yml",
            "pull_requests": [{"number": 7}],
        },
        "pr": {
            "number": 7, "state": "open", "draft": False, "merged": False,
            "head": {"sha": sha}, "base": {"repo": {"full_name": "example/repo"}},
        },
        "pages": [{"total_count": 1, "jobs": [{
            "id": 100, "run_id": 42, "run_attempt": 1, "head_sha": sha,
            "name": "Final Integration", "status": "completed", "conclusion": "success",
        }]}],
    }


def run_auto_merge(tmp_path: Path, metadata: dict):
    workflow = yaml.load(
        (ROOT / ".github/workflows/auto-merge.yml").read_text(), Loader=yaml.BaseLoader
    )
    job = workflow["jobs"]["merge"]
    assert all("uses" not in step for step in job["steps"])
    assert workflow["permissions"] == {"contents": "write", "pull-requests": "write"}
    script = "\n".join(step["run"] for step in job["steps"])
    fixture = tmp_path / "metadata.json"
    fixture.write_text(json.dumps(metadata))
    calls = tmp_path / "calls.jsonl"
    gh = tmp_path / "gh"
    gh.write_text("#!" + sys.executable + "\n" + r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ["TEST_CALLS"]).open("a") as stream:
    stream.write(json.dumps(args) + "\n")
data = json.loads(Path(os.environ["TEST_METADATA"]).read_text())
if args[:2] == ["pr", "merge"]:
    if "merge_head" in data and "--match-head-commit" in args:
        if args[args.index("--match-head-commit") + 1] != data["merge_head"]:
            sys.exit(23)
    sys.exit(0)
if args[0] != "api":
    sys.exit(90)
route = args[1]
if data.get("api_failure"):
    sys.exit(22)
if route == "repos/example/repo/actions/runs/42":
    value = data["run"]
    if "--jq" in args:
        print(value["pull_requests"][0]["number"])
        sys.exit(0)
elif route == "repos/example/repo/pulls/7":
    value = data["pr"]
    if "--jq" in args:
        print("draft" if value["draft"] else value["state"])
        sys.exit(0)
elif route == "repos/example/repo/actions/runs/42/attempts/1/jobs?per_page=100":
    assert "--paginate" in args and "--slurp" in args
    value = data["pages"]
else:
    sys.exit(91)
print(json.dumps(value))
''')
    gh.chmod(0o755)
    environment = {
        **os.environ, "PATH": str(tmp_path) + os.pathsep + os.defpath,
        "REPOSITORY": "example/repo", "RUN_ID": "42", "RUN_ATTEMPT": "1",
        "GH_TOKEN": "synthetic-test-token", "TEST_METADATA": str(fixture),
        "TEST_CALLS": str(calls),
    }
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail"], input=script, text=True,
        env=environment, cwd=tmp_path, capture_output=True, timeout=10,
    )
    observed = [json.loads(line) for line in calls.read_text().splitlines()]
    return result, observed


def test_auto_merge_requires_gate_and_pins_the_exact_current_head(tmp_path) -> None:
    metadata = merge_metadata()
    result, calls = run_auto_merge(tmp_path, metadata)
    assert result.returncode == 0, result.stderr
    assert calls[-1] == [
        "pr", "merge", "7", "--repo", "example/repo", "--squash", "--auto",
        "--match-head-commit", "a" * 40,
    ]
    assert any("--paginate" in call and "--slurp" in call for call in calls)


@pytest.mark.parametrize(("path", "value"), [
    (("run",), None),
    (("pr",), []),
    (("pages",), {}),
    (("pages", 0), None),
    (("pages", 0, "jobs", 0), None),
    (("run", "run_attempt"), True),
    (("pages", 0, "jobs", 0, "run_attempt"), True),
    (("run", "status"), "in_progress"),
    (("run", "conclusion"), "failure"),
    (("run", "event"), "workflow_dispatch"),
    (("run", "id"), 43),
    (("run", "run_attempt"), 2),
    (("run", "head_sha"), "b" * 40),
    (("run", "head_sha"), ""),
    (("run", "repository", "full_name"), "other/repo"),
    (("run", "path"), ".github/workflows/other.yml"),
    (("run", "pull_requests"), []),
    (("run", "pull_requests"), [{"number": 7}, {"number": 8}]),
    (("run", "pull_requests", 0, "number"), True),
    (("pr", "number"), 8),
    (("pr", "state"), "closed"),
    (("pr", "draft"), True),
    (("pr", "draft"), None),
    (("pr", "merged"), True),
    (("pr", "head", "sha"), "b" * 40),
    (("pr", "base", "repo", "full_name"), "other/repo"),
    (("pages",), []),
    (("pages", 0, "jobs"), []),
    (("pages", 0, "jobs"), None),
    (("pages", 0, "total_count"), 2),
    (("pages", 0, "total_count"), True),
    (("pages", 0, "jobs", 0, "name"), "Other job"),
    (("pages", 0, "jobs", 0, "status"), "in_progress"),
    # A draft-time run can be green while its gate was skipped and the PR is ready.
    (("pages", 0, "jobs", 0, "conclusion"), "skipped"),
    (("pages", 0, "jobs", 0, "conclusion"), "failure"),
    (("pages", 0, "jobs", 0, "conclusion"), "cancelled"),
    (("pages", 0, "jobs", 0, "conclusion"), None),
    (("pages", 0, "jobs", 0, "run_id"), 43),
    (("pages", 0, "jobs", 0, "run_attempt"), 2),
    (("pages", 0, "jobs", 0, "head_sha"), "b" * 40),
    (("pages", 0, "jobs", 0, "id"), None),
    (("api_failure",), True),
])
def test_auto_merge_rejects_unproven_metadata(tmp_path, path, value) -> None:
    metadata = merge_metadata()
    target = metadata
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    result, calls = run_auto_merge(tmp_path, metadata)
    assert result.returncode != 0
    assert not any(call[:2] == ["pr", "merge"] for call in calls)


def test_auto_merge_finds_gate_after_first_page_without_truncation(tmp_path) -> None:
    metadata = merge_metadata()
    gate = metadata["pages"][0]["jobs"][0]
    filler = [{**gate, "id": i + 1000, "name": f"Tests {i}"} for i in range(100)]
    metadata["pages"] = [
        {"total_count": 101, "jobs": filler}, {"total_count": 101, "jobs": [gate]},
    ]
    result, _ = run_auto_merge(tmp_path, metadata)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("problem", ["duplicate_id", "duplicate_gate", "inconsistent_total"])
def test_auto_merge_rejects_ambiguous_or_incomplete_pages(tmp_path, problem) -> None:
    metadata = merge_metadata()
    gate = metadata["pages"][0]["jobs"][0]
    other = {**gate, "id": 101, "name": "Tests"}
    if problem == "duplicate_id":
        other["id"] = gate["id"]
    if problem == "duplicate_gate":
        other["name"] = gate["name"]
    metadata["pages"] = [
        {"total_count": 2, "jobs": [gate]},
        {"total_count": 3 if problem == "inconsistent_total" else 2, "jobs": [other]},
    ]
    result, calls = run_auto_merge(tmp_path, metadata)
    assert result.returncode != 0
    assert not any(call[:2] == ["pr", "merge"] for call in calls)


def test_auto_merge_head_change_during_merge_is_rejected_by_pin(tmp_path) -> None:
    metadata = merge_metadata()
    metadata["merge_head"] = "b" * 40
    result, calls = run_auto_merge(tmp_path, metadata)
    assert result.returncode != 0
    assert calls[-1][-2:] == ["--match-head-commit", "a" * 40]
