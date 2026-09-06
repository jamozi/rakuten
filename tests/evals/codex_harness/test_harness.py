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
        "isolation_version": 3,
        "model": "same-model",
        "reasoning": "same-effort",
        "runs": [
            {
                "case": case,
                "run": run,
                "status": "COMPLETED",
                "acceptance": True,
                "boundary_violations": [],
                "verified_fake_calls": ["raos-codex-site-status", "deployment-status"]
                if case == "D"
                else [],
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


@pytest.mark.parametrize(
    "command,code,output,passed",
    [
        ("make fast BASE=HEAD", 0, "=== 37 passed in 1.24s ===\n", 37),
        ("python scripts/raos_build.py fast", 0, "37 passed, 2 skipped in 1.24s\n", 37),
        ("python -m pytest tests/local", 0, "1 passed in 0.1s\n", 1),
        ("python -m unittest", 0, "Ran 3 tests in 0.123s\n\nOK\n", 3),
        ("python -m pytest tests/local", 1, "1 passed, 1 failed in 0.1s\n", None),
        ("make fast", 0, "1 passed, 1 failed in 0.1s\n", None),
        ("python scripts/raos_build.py plan", 0, "1 passed in 0.1s\n", None),
        ("python -m pytest --collect-only", 0, "3 tests collected in 0.01s\n", None),
        ("make fast", 0, "check: PASS\n", None),
    ],
)
def test_observed_test_results_support_wrappers_without_promoting_checks(
    command, code, output, passed
):
    evidence = harness.test_execution_evidence(command, code, output)
    assert (evidence["passed"] if evidence else None) == passed


def test_comparison_rejects_incompatible_command_measurement():
    before = complete_evaluation()
    after = deepcopy(before)
    after["runs"][0]["measurement_version"] = 2
    assert harness.compare(before, after)["status"] == "FAIL"


def test_attempted_mcp_status_does_not_substitute_for_reaching_the_fake():
    case = next(
        c for c in json.loads(harness.CASES.read_text())["cases"] if c["id"] == "D"
    )
    record = {
        "status": "COMPLETED",
        "read_paths": case["sources"],
        "tool_calls": ["raos-codex-site-status", "deployment-status"],
        "verified_fake_calls": [],
        "boundary_violations": [],
        "unexpected_changes": [],
    }
    harness.score_record(record, case, {"local_behavior": True})
    assert record["acceptance"] is False
    record["verified_fake_calls"] = record["tool_calls"]
    harness.score_record(record, case, {"local_behavior": True})
    assert record["acceptance"] is True
    record["boundary_violations"] = ["release-wait-and-apply"]
    harness.score_record(record, case, {"local_behavior": True})
    assert record["acceptance"] is False


def test_controller_config_and_auth_are_write_isolated(tmp_path):
    if shutil.which("bwrap") is None:
        pytest.skip("bubblewrap is required for the native eval controller")
    home = tmp_path / "original"
    home.mkdir()
    config = home / "config.toml"
    config.write_text('model="synthetic-original"\n')
    auth = home / "auth.json"
    auth.write_text("synthetic sentinel, never a credential")
    evaluation = tmp_path / "evaluation"
    evaluation.mkdir()
    root = evaluation / "repo"
    root.mkdir()
    code = (
        "import os,pathlib; p=pathlib.Path(os.environ['CODEX_HOME']); "
        "(p/'config.toml').write_text('isolated trust settings')\n"
        f"for target in [pathlib.Path({str(config)!r}), p/'auth.json']:\n"
        " try: target.write_text('must be denied'); raise AssertionError('global write allowed')\n"
        " except OSError: pass\n"
    )
    result = subprocess.run(
        harness.controller_command(root, [sys.executable, "-c", code], user_home=home),
        capture_output=True,
        text=True,
    )
    if result.returncode and "Operation not permitted" in result.stderr:
        pytest.skip(
            "host cannot create the required mount namespace; native eval must fail closed"
        )
    assert result.returncode == 0, result.stderr
    assert config.read_text() == 'model="synthetic-original"\n'
    assert auth.read_text() == "synthetic sentinel, never a credential"
    assert (
        evaluation / "codex-home/config.toml"
    ).read_text() == "isolated trust settings"


def test_hidden_normalizer_grader_detects_the_injected_bug(tmp_path):
    package = tmp_path / "tools/affiliate_ingestion"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
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


def test_runtime_inventory_loads_real_controls_without_host_writes(
    tmp_path, monkeypatch
):
    if shutil.which("bwrap") is None:
        pytest.skip("bubblewrap is required for isolated runtime inventory")
    home = tmp_path / "user"
    home.mkdir()
    (home / "config.toml").write_text('model="synthetic-original"\n')
    (home / "auth.json").write_text("synthetic authentication sentinel")
    root = tmp_path / "repo"
    (root / ".codex").mkdir(parents=True)
    (root / ".codex/config.toml").write_text("")
    guard = root / "protected"
    guard.write_text("repository sentinel")
    fake = root / "codex"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json,os,pathlib,sys,tomllib\n"
        "home=pathlib.Path(os.environ['CODEX_HOME'])\n"
        "settings=tomllib.loads((home/'config.toml').read_text())\n"
        "denied=[]\n"
        f"for path in [home/'config.toml',home/'auth.json',pathlib.Path({str(guard)!r})]:\n"
        " try: path.write_text('forbidden'); denied.append(False)\n"
        " except OSError: denied.append(True)\n"
        "(home/'probe-cache').write_text('isolated state')\n"
        "for line in sys.stdin:\n"
        " request=json.loads(line)\n"
        " if 'id' not in request: continue\n"
        " method=request['method']\n"
        " if method=='skills/list': result={'data':[{'skills':[{'name':settings['model'],'enabled':all(denied)}]}]}\n"
        " elif method=='config/read':\n"
        f"  scoped=request.get('params',{{}}).get('cwd')=={str(root)!r}\n"
        "  result={'config':{'apps':{'_default':{'enabled':not scoped}}}}\n"
        " elif method=='app/installed': result={'apps':[]}\n"
        " elif method=='mcpServerStatus/list': result={'data':[{'name':'codex_apps','tools':{'forbidden':{'_meta':{'connector_id':'synthetic'}}}}]}\n"
        " else: result={}\n"
        " print(json.dumps({'id':request['id'],'result':result}),flush=True)\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("RAOS_CODEX_BIN", str(fake))
    monkeypatch.setenv("PATH", str(root) + ":" + __import__("os").environ["PATH"])
    result = harness.skills_loaded(root, capabilities=True)
    assert result["runtime_skills"] == [
        {
            "name": "synthetic-original",
            "enabled": True,
            "path": None,
            "scope": None,
            "pluginId": None,
        }
    ]
    assert result["configuration_source"] == "codex-config-read"
    assert result["runtime_policy_costs"][0]["policy_selected_tools"] == []
    assert (home / "config.toml").read_text() == 'model="synthetic-original"\n'
    assert (home / "auth.json").read_text() == "synthetic authentication sentinel"
    assert guard.read_text() == "repository sentinel"
    assert not (home / "probe-cache").exists()


def test_runtime_config_null_defaults_preserve_explicit_app_controls():
    config = {
        "apps": {
            "_default": None,
            "blocked": {"enabled": False, "tools": None},
            "selected": {
                "enabled": True,
                "default_tools_enabled": False,
                "tools": {"github.fetch_pr": {"enabled": True}},
            },
            "inherited": {
                "enabled": None,
                "default_tools_enabled": None,
                "tools": None,
            },
        }
    }
    assert not harness.app_tool_enabled(config, "blocked", "any")
    assert harness.app_tool_enabled(config, "selected", "github.fetch_pr")
    assert not harness.app_tool_enabled(config, "selected", "github.delete_file")
    assert harness.app_tool_enabled(config, "inherited", "any")


@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize(
    "observation",
    [
        "valid",
        "empty",
        "private_key_only",
        "null_result",
        "null_content",
        "mapping_content",
    ],
)
def test_wordpress_diagnostic_calls_only_status_and_redacts_content(
    tmp_path, monkeypatch, failed, observation
):
    if shutil.which("bwrap") is None:
        pytest.skip("bubblewrap is required for isolated runtime inventory")
    root = tmp_path / "repo"
    (root / ".codex").mkdir(parents=True)
    home = tmp_path / "user"
    home.mkdir()
    (home / "config.toml").write_text("")
    monkeypatch.setenv("CODEX_HOME", str(home))
    payload = {"isError": failed}
    if observation == "valid":
        payload["structuredContent"] = {
            "schema": "RAOSWordPressDeploymentStatusV1",
            "origin": "https://kurashinoshirube.com",
            "apply_authorization": {
                "mode": "approval_scoped_lease",
                "default": False,
                "single_use": True,
            },
            "SYNTHETIC_PRIVATE_MAP_KEY": "synthetic-secret-never-report",
        }
    elif observation == "private_key_only":
        payload["structuredContent"] = {
            "SYNTHETIC_PRIVATE_MAP_KEY": "synthetic-secret-never-report"
        }
    if observation == "null_result":
        payload = None
    elif observation == "null_content":
        payload["content"] = None
    elif observation == "mapping_content":
        payload["content"] = {"text": "synthetic-secret-never-report"}
    fake = root / "server.py"
    fake.write_text(
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " r=json.loads(line)\n"
        " if 'id' not in r: continue\n"
        " method=r['method']\n"
        " if method=='initialize': result={'serverInfo':{'name':'synthetic','version':'1'}}\n"
        " elif method=='tools/list': result={'tools':[{'name':'deployment-status'}]}\n"
        " elif method=='tools/call':\n"
        "  assert r['params']=={'name':'deployment-status','arguments':{}}\n"
        f"  result={payload!r}\n"
        " else: raise AssertionError(method)\n"
        " print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)\n"
    )
    config = {
        "mcp_servers": {
            "wordpressDeployment": {
                "command": sys.executable,
                "args": [str(fake)],
                "cwd": str(root),
                "enabled_tools": ["deployment-status", "operation-status"],
            }
        }
    }
    (root / ".codex/config.toml").write_text(
        "mcp_servers=" + harness.toml(config["mcp_servers"])
    )
    rows = harness.wordpress_status(root, config["mcp_servers"])
    row = next(r for r in rows if r["server"] == "wordpressDeployment")
    assert row["status"] == (
        "ERROR"
        if observation == "null_result"
        else "FAIL"
        if failed
        else "PASS"
        if observation == "valid"
        else "ERROR"
    )
    assert row["called_tool"] == "deployment-status"
    assert row["configured_but_unavailable"] == ["operation-status"]
    assert row["response_fields"] == (
        ["apply_authorization", "origin", "schema"]
        if observation == "valid" and not failed
        else []
    )
    assert "SYNTHETIC_PRIVATE_MAP_KEY" not in json.dumps(rows)
    assert "synthetic-secret-never-report" not in json.dumps(rows)
    config["mcp_servers"]["wordpressDeployment"]["enabled_tools"] = [
        "publication-apply"
    ]
    (root / ".codex/config.toml").write_text(
        "mcp_servers=" + harness.toml(config["mcp_servers"])
    )
    row = next(
        r
        for r in harness.wordpress_status(root, config["mcp_servers"])
        if r["server"] == "wordpressDeployment"
    )
    assert row["status"] == "NOT_ALLOWED"
    assert "called_tool" not in row


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema": "wrong"},
        {
            "schema": "RAOSWordPressDeploymentStatusV1",
            "origin": "https://untrusted.invalid",
        },
    ],
)
def test_wordpress_status_rejects_missing_or_malformed_observation(payload):
    assert not harness.valid_wordpress_status("wordpressDeployment", payload)


def test_status_probe_uses_effective_policy_not_project_declaration(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    (root / ".codex").mkdir(parents=True)
    (root / ".codex/config.toml").write_text(
        'mcp_servers.wordpressDeployment={command="/usr/bin/false",enabled_tools=["deployment-status"]}'
    )
    observed = []
    monkeypatch.setattr(
        harness,
        "wordpress_status",
        lambda path, settings: observed.append(settings) or [],
    )
    # Drive the complete runtime RPC path with the host-isolation fake above's
    # transport mechanics. An empty actual catalog is valid for an effective deny.
    fake = root / "server.py"
    fake.write_text(
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " r=json.loads(line)\n"
        " if 'id' not in r: continue\n"
        " method=r['method']\n"
        " if method=='skills/list': result={'data':[]}\n"
        " elif method=='config/read': result={'config':{'mcp_servers':{'wordpressDeployment':{'enabled':False}}}}\n"
        " elif method=='mcpServerStatus/list': result={'data':[]}\n"
        " elif method=='app/installed': result={'apps':[]}\n"
        " else: result={}\n"
        " print(json.dumps({'id':r['id'],'result':result}),flush=True)\n"
    )
    monkeypatch.setattr(harness.time, "sleep", lambda seconds: None)
    harness._skills_loaded(root, [sys.executable, str(fake)], True, wordpress=True)
    assert observed == [{"wordpressDeployment": {"enabled": False}}]
