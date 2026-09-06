"""Behavioral regression checks for context routing and capability isolation."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

import pytest

from scripts import codex_harness as harness
from scripts.raos_test_plan import create_plan


def test_navigation_and_scoped_capabilities():
    assert harness.check(harness.ROOT) == {"status": "PASS", "errors": []}


def test_explicit_inherited_app_enable_beats_default_but_not_project_override():
    inherited = {"apps": {key: {"enabled": True} for key in harness.OUT_OF_SCOPE_APPS}}
    default_only = harness.merge(inherited, {"apps": {"_default": {"enabled": False}}})
    assert all(
        harness.app_enabled(default_only, key) for key in harness.OUT_OF_SCOPE_APPS
    )
    project = harness.read_config(harness.ROOT / ".codex/config.toml")
    effective = harness.merge(inherited, project)
    assert all(
        not harness.app_enabled(effective, key) for key in harness.OUT_OF_SCOPE_APPS
    )
    assert harness.app_enabled(effective, harness.GITHUB)


@pytest.mark.parametrize(
    "path",
    [
        "AGENTS.md",
        "AGENTS.override.md",
        "python/raos/AGENTS.md",
        ".codex/config.toml",
        ".agents/skills/raos-editorial-review/SKILL.md",
    ],
)
def test_instruction_changes_select_behavior_and_boundary_tests(path):
    plan = create_plan(harness.ROOT, {}, [Path(path)])
    assert "tests/evals/codex_harness/test_harness.py" in plan.python_tests
    assert "tests/st0403/test_authorization.py" in plan.python_tests
    assert "tests/editorial_portfolio_v3/test_contract.py" in plan.python_tests
    assert "tests/st1001/public-shell-boundaries.test.ts" in plan.node_tests


def test_shared_planner_changes_still_require_full_selection():
    plan = create_plan(harness.ROOT, {}, [Path("scripts/raos_test_plan.py")])
    assert plan.full


def test_links_validate_anchors_and_reject_escape(tmp_path):
    (tmp_path / "map.md").write_text("[source](target.md#contract)\n")
    target = tmp_path / "target.md"
    target.write_text("# Contract\n")
    assert harness.check_links(tmp_path, ["map.md"]) == []
    target.write_text("# Renamed\n")
    assert "broken anchor" in harness.check_links(tmp_path, ["map.md"])[0]
    (tmp_path / "map.md").write_text("[bad](../outside.md)\n")
    assert "escaping link" in harness.check_links(tmp_path, ["map.md"])[0]


def test_skills_have_unique_metadata_and_real_reference_routes():
    paths = list((harness.ROOT / ".agents/skills").glob("*/SKILL.md"))
    rows = [harness.skill_metadata(path) for path in paths]
    assert len({row["name"] for row in rows}) == len(rows)
    assert all(row["name"] == path.parent.name for row, path in zip(rows, paths))
    assert not harness.check_links(
        harness.ROOT, [str(p.relative_to(harness.ROOT)) for p in paths]
    )


def complete_evaluation():
    return {
        "protocol_sha256": "synthetic-protocol",
        "model": "same-model",
        "reasoning": "same-effort",
        "runs": [
            {
                "case": case,
                "run": run,
                "status": "COMPLETED",
                "acceptance": True,
                "boundary_violations": [],
                "behavior": {"acceptance_probe": True},
                "scores": {
                    name: 2
                    for name in json.loads(harness.CASES.read_text())["dimensions"]
                },
            }
            for case in "ABCDE"
            for run in range(1, 4)
        ],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "timeout",
        "missing",
        "duplicate",
        "boundary",
        "model",
        "grader",
        "before_timeout",
        "false_acceptance",
    ],
)
def test_compare_cannot_promote_incomplete_or_unsafe_runs_to_pass(mutation):
    before = complete_evaluation()
    after = deepcopy(before)
    assert harness.compare(before, after)["status"] == "PASS"
    if mutation == "timeout":
        after["runs"][0].update(status="TIMEOUT", acceptance=False)
    elif mutation == "missing":
        after["runs"].pop()
    elif mutation == "duplicate":
        after["runs"][1]["run"] = 1
    elif mutation == "boundary":
        after["runs"][0]["boundary_violations"] = ["unapproved-write"]
    elif mutation == "model":
        after["model"] = "different-model"
    elif mutation == "grader":
        before["runs"][0]["behavior"] = {"grader_execution": False}
    elif mutation == "false_acceptance":
        after["runs"][0]["status"] = "TIMEOUT"
    else:
        before["runs"][0]["status"] = "TIMEOUT"
    assert harness.compare(before, after)["status"] == "FAIL"


def test_buffered_final_events_arrive_before_the_process_exits():
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time; print('one\\ntwo\\ncompleted', flush=True); time.sleep(5)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        lines = harness.line_queue(process.stdout)
        assert [lines.get(timeout=1).strip() for _ in range(3)] == [
            "one",
            "two",
            "completed",
        ]
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=2)


def test_regrading_passing_behavior_does_not_complete_a_timed_out_turn():
    case = json.loads(harness.CASES.read_text())["cases"][0]
    record = {
        "status": "TIMEOUT",
        "read_paths": case["sources"],
        "tool_calls": [],
        "test_commands_passed": 1,
        "boundary_violations": [],
        "unexpected_changes": [],
    }
    harness.score_record(record, case, {"valid_behavior": True})
    assert record["acceptance"] is False


def test_hidden_normalizer_grader_detects_the_injected_bug(tmp_path):
    package = tmp_path / "tools/affiliate_ingestion"
    package.mkdir(parents=True)
    shutil.copyfile(
        harness.ROOT / "tools/affiliate_ingestion/normalize.py",
        package / "normalize.py",
    )

    def grade():
        result = subprocess.run(
            [sys.executable, str(harness.FIXTURES), "A"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    assert all(grade().values())
    harness.fixture_module().prepare(tmp_path, "A")
    assert not all(grade().values())


def test_paging_grader_accepts_a_complete_synthetic_implementation(tmp_path):
    package = tmp_path / "tools/affiliate_ingestion"
    shutil.copytree(
        harness.ROOT / "tools/affiliate_ingestion",
        package,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    config = package / "config.py"
    config.write_text(
        config.read_text().replace('"next_url",', '"next_url", "next_link",')
    )
    client = package / "client.py"
    client.write_text(
        client.read_text()
        .replace(
            'elif pagination_type == "next_url":',
            'elif pagination_type in {"next_url", "next_link"}:',
        )
        .replace(
            'pagination.get("next_url_path", "next")',
            'pagination.get("next_url_path", "links.next.href" if pagination_type == "next_link" else "next")',
        )
    )
    normalizer = package / "normalize.py"
    normalizer.write_text(
        normalizer.read_text().replace(
            '"commission_amount",', '"commission_amount", "reward_jpy",'
        )
    )
    result = subprocess.run(
        [sys.executable, str(harness.FIXTURES), "B"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert all(json.loads(result.stdout).values()), result.stdout


def test_app_allowlist_checks_exact_runtime_resource_names():
    config = {
        "apps": {
            "_default": {"enabled": False},
            "synthetic": {
                "enabled": True,
                "default_tools_enabled": False,
                "tools": {"github.fetch_pr": {"enabled": True}},
            },
        }
    }
    assert harness.app_tool_enabled(config, "synthetic", "github.fetch_pr")
    assert not harness.app_tool_enabled(config, "synthetic", "github.delete_file")
    config["apps"]["synthetic"]["enabled"] = False
    assert not harness.app_tool_enabled(config, "synthetic", "github.fetch_pr")


def test_skill_launcher_preserves_global_controls_without_writing(
    tmp_path, monkeypatch
):
    home = tmp_path / "user"
    home.mkdir()
    global_file = home / "config.toml"
    global_file.write_text('[[skills.config]]\nname="shared"\nenabled=false\n')
    project = tmp_path / "repo"
    (project / ".codex").mkdir(parents=True)
    (project / ".codex/config.toml").write_text(
        '[[skills.config]]\npath="/synthetic/gsd/SKILL.md"\nenabled=false\n'
    )
    before = global_file.read_bytes()
    monkeypatch.setenv("CODEX_HOME", str(home))
    controls = harness.project_skill_overrides(project)
    assert controls == {
        "skills.config": [
            {"name": "shared", "enabled": False},
            {"path": "/synthetic/gsd/SKILL.md", "enabled": False},
        ]
    }
    assert global_file.read_bytes() == before
    assert (
        tomllib.loads("value=" + harness.toml(controls["skills.config"]))["value"]
        == controls["skills.config"]
    )


def test_snapshot_does_not_expose_grader_or_user_state(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    for name in (
        "AGENTS.md",
        "tests/evals/codex_harness/cases.json",
        "scripts/codex_harness.py",
    ):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic\n")
    for args in (
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        harness.run(["git", *args], repo)
    (repo / "untracked-private").write_text("synthetic sentinel")
    destination = tmp_path / "isolated"
    destination.mkdir()
    harness.snapshot(repo, destination, "HEAD")
    assert (destination / "AGENTS.md").is_file()
    assert not (destination / "untracked-private").exists()
    assert not (destination / "tests/evals/codex_harness").exists()
    assert not (destination / "scripts/codex_harness.py").exists()
