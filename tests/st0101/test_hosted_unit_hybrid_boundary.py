"""Closed hosted/owner-private Unit boundary for approved ST-0101."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any, Mapping

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = REPOSITORY_ROOT / "tests/st0101"
CONTRACT_PATH = REPOSITORY_ROOT / "changes/st-0101/hosted-unit-hybrid-boundary.v1.yaml"
HANDOFF_PATH = REPOSITORY_ROOT / (
    "changes/st-0101/DESIGN_HANDOFF_V1_ST0101_HOSTED_UNIT_HYBRID_BOUNDARY_V1.yaml"
)
PYPROJECT_PATH = REPOSITORY_ROOT / "pyproject.toml"
MAKEFILE_PATH = REPOSITORY_ROOT / "Makefile"
HANDOFF_BYTES = 22392
HANDOFF_SHA256 = "d3a644d67e5e96723c10da4cbf9f60323aa4394a89e4edbcd6fc41ed1972a88d"
MARKER_NAME = "raos_owner_private"
MARKER_REGISTRATION = (
    "raos_owner_private: requires the physical owner repository and untracked "
    "owner-private policy inputs"
)
OWNER_MARKER_DECORATOR = "pytest.mark.raos_owner_private"
NODE_ID_PATTERN = re.compile(
    r"tests/st0101/test_[a-z0-9_]+\.py::test_[a-z0-9_]+(?:\[[^\r\n]+\])?"
)

OWNER_PRIVATE_NODE_IDS = (
    "tests/st0101/test_chatgpt_pro_browser_selection.py::test_owner_private_skill_records_edge_first_scope_and_profile_prohibition",
    "tests/st0101/test_chatgpt_pro_initial_ui_settle.py::test_owner_private_skill_preserves_initial_settle_boundary",
    "tests/st0101/test_chatgpt_pro_interactive_auth_wait.py::test_owner_private_skill_keeps_wait_scoped_to_pro_ask",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_owner_private_skill_and_metadata_retain_approved_policy",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_make_pro_launcher_ignores_wrong_ambient_uv_and_setup_uses_it",
    "tests/st0101/test_chatgpt_pro_response_wait.py::test_owner_private_skill_keeps_answer_now_observation_only",
    "tests/st0101/test_chatgpt_pro_wslg_display.py::test_owner_private_skill_requires_chatgpt_only_login_without_edge_sync",
)

PORTABLE_NODE_IDS = (
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_live_doctor_reports_compound_cloudflare_challenge_as_captcha",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_successful_ask_emits_sanitized_result_and_hash_bound_private_artifacts",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_cli_ask_without_request_file_reads_stdin_into_private_artifact",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_live_no_model_picker_records_pre_submission_unavailability[ordinary-0-PRO_UNAVAILABLE_FALLBACK-CONTINUE_CANONICAL_LOCAL_ONLY]",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_live_no_model_picker_records_pre_submission_unavailability[gated-4-BLOCKED_PRO_REQUIRED-STOP]",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_live_security_invariants_remain_hard_refusals[MCP_TOOL_NOT_ALLOWED-browser_evaluate-arguments0]",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_live_security_invariants_remain_hard_refusals[RAW_PROMPT_TOOL_ARGUMENT-browser_type-arguments1]",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_live_contract_drift_remains_a_hard_refusal",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_legacy_waiting_ambiguity_cli_remains_generic_without_diagnostic",
    "tests/st0101/test_chatgpt_pro_orchestrator.py::test_live_resume_nonallowlisted_refusal_remains_hard_and_state_unchanged",
    "tests/st0101/test_chatgpt_pro_private_runtime.py::test_stdio_transport_verifies_runtime_before_process_start",
    "tests/st0101/test_chatgpt_pro_private_runtime.py::test_stdio_transport_uses_fixed_path_despite_hostile_ambient_path",
    "tests/st0101/test_chatgpt_pro_private_runtime.py::test_stdio_transport_cleans_process_when_initialize_fails",
    "tests/st0101/test_chatgpt_pro_private_runtime.py::test_wrapper_and_runtime_resources_never_reference_shared_npx",
    "tests/st0101/test_chatgpt_pro_wslg_display.py::test_orchestrator_refuses_absent_x11_endpoint_before_popen",
    "tests/st0101/test_chatgpt_pro_wslg_display.py::test_orchestrator_refuses_regular_x11_endpoint_before_popen",
)


class BoundaryContractError(ValueError):
    """One closed boundary invariant was violated."""


class _StrictYamlLoader(yaml.SafeLoader):
    """Safe loader which also rejects duplicate and merged mappings."""


def _construct_strict_mapping(
    loader: _StrictYamlLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge" or key_node.value == "<<":
            raise BoundaryContractError("YAML merge keys are prohibited")
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str:
            raise BoundaryContractError("mapping keys must be strings")
        if key in mapping:
            raise BoundaryContractError(f"duplicate mapping key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictYamlLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_strict_mapping,
)


def _load_yaml_text(text: str) -> dict[str, Any]:
    for event in yaml.parse(text):
        if (
            isinstance(event, yaml.events.AliasEvent)
            or getattr(event, "anchor", None) is not None
        ):
            raise BoundaryContractError("YAML anchors and aliases are prohibited")
    loaded = yaml.load(text, Loader=_StrictYamlLoader)
    if type(loaded) is not dict:
        raise BoundaryContractError("document root must be a mapping")
    return loaded


def _load_yaml(path: Path) -> dict[str, Any]:
    return _load_yaml_text(path.read_text(encoding="utf-8"))


def _require_exact_keys(
    mapping: object, expected: set[str], *, label: str
) -> dict[str, Any]:
    if type(mapping) is not dict:
        raise BoundaryContractError(f"{label} must be a mapping")
    typed = mapping
    if set(typed) != expected:
        raise BoundaryContractError(f"{label} keys are not exact")
    return typed


def _validate_inventory(
    value: object, expected: tuple[str, ...], *, label: str
) -> tuple[str, ...]:
    if type(value) is not list or not all(type(item) is str for item in value):
        raise BoundaryContractError(f"{label} must be a string list")
    inventory = tuple(value)
    if len(set(inventory)) != len(inventory):
        raise BoundaryContractError(f"{label} contains a duplicate")
    for node_id in inventory:
        if "*" in node_id or "?" in node_id or not NODE_ID_PATTERN.fullmatch(node_id):
            raise BoundaryContractError(f"{label} contains a non-exact node ID")
    if inventory != expected:
        raise BoundaryContractError(f"{label} differs from the approved inventory")
    return inventory


def _validate_boundary_contract(document: object) -> dict[str, Any]:
    root = _require_exact_keys(
        document,
        {
            "schema",
            "story_id",
            "slice_id",
            "marker",
            "requirements",
            "owner_private_node_ids",
            "portable_node_ids",
        },
        label="boundary",
    )
    if root["schema"] != "RAOS_HOSTED_UNIT_HYBRID_BOUNDARY_V1":
        raise BoundaryContractError("schema is not exact")
    if root["story_id"] != "ST-0101":
        raise BoundaryContractError("story is not exact")
    if root["slice_id"] != "ST0101_HOSTED_UNIT_HYBRID_BOUNDARY_V1":
        raise BoundaryContractError("slice is not exact")

    marker = _require_exact_keys(
        root["marker"],
        {"name", "hosted_selector", "local_selector", "local_target"},
        label="marker",
    )
    if marker != {
        "name": MARKER_NAME,
        "hosted_selector": "not raos_owner_private",
        "local_selector": MARKER_NAME,
        "local_target": "pro-owner-private-test",
    }:
        raise BoundaryContractError("marker metadata is not exact")

    requirements = _require_exact_keys(
        root["requirements"],
        {"owner_private_inventory", "portable_inventory", "network_sandbox"},
        label="requirements",
    )
    owner = _require_exact_keys(
        requirements["owner_private_inventory"],
        {"count", "match", "declaration", "disallowed_outcomes"},
        label="owner-private requirements",
    )
    if owner != {
        "count": 7,
        "match": "exact_full_node_id_equality",
        "declaration": "direct_function_marker_only",
        "disallowed_outcomes": [
            "skip",
            "xfail",
            "xpass",
            "dynamic_marker",
            "module_or_file_marker",
            "wildcard_or_prefix_inventory",
        ],
    }:
        raise BoundaryContractError("owner-private requirements are not exact")
    if type(owner["count"]) is not int:
        raise BoundaryContractError("owner-private count must be an integer")
    portable = _require_exact_keys(
        requirements["portable_inventory"],
        {"count", "execution", "production_guards"},
        label="portable requirements",
    )
    if portable != {
        "count": 16,
        "execution": "hosted_in_process_test_substitution",
        "production_guards": "unchanged",
    }:
        raise BoundaryContractError("portable requirements are not exact")
    if type(portable["count"]) is not int:
        raise BoundaryContractError("portable count must be an integer")
    network = _require_exact_keys(
        requirements["network_sandbox"],
        {"skip_count", "owner", "relationship"},
        label="network requirements",
    )
    if network != {
        "skip_count": 9,
        "owner": "ci-network-assert",
        "relationship": "separate_and_unchanged",
    }:
        raise BoundaryContractError("network requirements are not exact")
    if type(network["skip_count"]) is not int:
        raise BoundaryContractError("network skip count must be an integer")

    _validate_inventory(
        root["owner_private_node_ids"],
        OWNER_PRIVATE_NODE_IDS,
        label="owner-private inventory",
    )
    _validate_inventory(
        root["portable_node_ids"],
        PORTABLE_NODE_IDS,
        label="portable inventory",
    )
    return root


def _owner_marker_attributes(tree: ast.AST) -> list[ast.Attribute]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and ast.unparse(node) == OWNER_MARKER_DECORATOR
    ]


def _direct_marker_node_ids_from_sources(sources: Mapping[Path, str]) -> set[str]:
    node_ids: set[str] = set()
    for path, source in sources.items():
        tree = ast.parse(source, filename=str(path))
        permitted_marker_nodes: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                if any(
                    isinstance(target, ast.Name) and target.id == "pytestmark"
                    for target in targets
                ):
                    raise BoundaryContractError("module or file marker is prohibited")
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name in {
                "pytest_collection_modifyitems",
                "pytest_collection_finish",
                "pytest_generate_tests",
            }:
                raise BoundaryContractError("dynamic marker hooks are prohibited")
            if isinstance(node, ast.Call):
                call_name = ast.unparse(node.func)
                if call_name == "getattr" and any(
                    isinstance(argument, ast.Constant) and argument.value == MARKER_NAME
                    for argument in node.args
                ):
                    raise BoundaryContractError("dynamic marker lookup is prohibited")
                if call_name.endswith((".add_marker", ".applymarker")):
                    marker_constants = {
                        argument.value
                        for argument in node.args
                        if isinstance(argument, ast.Constant)
                        and type(argument.value) is str
                    }
                    if MARKER_NAME in marker_constants or any(
                        ast.unparse(attribute) == OWNER_MARKER_DECORATOR
                        for attribute in _owner_marker_attributes(node)
                    ):
                        raise BoundaryContractError(
                            "dynamic marker application is prohibited"
                        )

        for statement in tree.body:
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            direct = [
                decorator
                for decorator in statement.decorator_list
                if ast.unparse(decorator) == OWNER_MARKER_DECORATOR
            ]
            if not direct:
                continue
            if len(direct) != 1:
                raise BoundaryContractError("owner marker must appear exactly once")
            permitted_marker_nodes.add(id(direct[0]))
            decorator_names = [ast.unparse(item) for item in statement.decorator_list]
            if any(".skip" in name or ".xfail" in name for name in decorator_names):
                raise BoundaryContractError("hidden skip or xfail is prohibited")
            for child in ast.walk(statement):
                if isinstance(child, ast.Call) and ast.unparse(child.func) in {
                    "pytest.skip",
                    "pytest.xfail",
                    "pytest.importorskip",
                }:
                    raise BoundaryContractError("runtime skip or xfail is prohibited")
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            node_ids.add(f"{relative}::{statement.name}")

        observed_marker_nodes = {id(node) for node in _owner_marker_attributes(tree)}
        if observed_marker_nodes != permitted_marker_nodes:
            raise BoundaryContractError(
                "owner marker must be a direct top-level function decorator"
            )
    return node_ids


def _direct_marker_node_ids() -> set[str]:
    paths = list(sorted(TEST_ROOT.glob("test_*.py")))
    paths.append(REPOSITORY_ROOT / "tests/conftest.py")
    sources = {path: path.read_text(encoding="utf-8") for path in paths}
    return _direct_marker_node_ids_from_sources(sources)


def _collect_node_ids(selector: str | None) -> set[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "--collect-only",
        "-q",
        "--color=no",
    ]
    if selector is not None:
        command.extend(("-m", selector))
    command.append("tests/st0101")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTEST_") and key not in {"PYTHONHOME", "PYTHONPATH"}
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if process.returncode != 0:
        raise AssertionError(process.stderr or process.stdout)
    node_ids = {
        line.strip()
        for line in process.stdout.splitlines()
        if line.startswith("tests/st0101/") and "::" in line
    }
    if not node_ids:
        raise AssertionError("pytest collection returned no ST-0101 node IDs")
    return node_ids


def test_contract_is_closed_and_binds_the_exact_approved_handoff() -> None:
    handoff_bytes = HANDOFF_PATH.read_bytes()
    assert len(handoff_bytes) == HANDOFF_BYTES
    assert hashlib.sha256(handoff_bytes).hexdigest() == HANDOFF_SHA256
    contract = _validate_boundary_contract(_load_yaml(CONTRACT_PATH))
    handoff = _load_yaml_text(handoff_bytes.decode("utf-8"))["DESIGN_HANDOFF_V1"]
    reconciliation = handoff["hosted_failure_reconciliation"]
    assert tuple(contract["owner_private_node_ids"]) == tuple(
        reconciliation["owner_private_node_ids"]
    )
    assert tuple(contract["portable_node_ids"]) == tuple(
        reconciliation["portable_node_ids"]
    )


def test_marker_registration_and_make_selectors_are_exact_and_narrow() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    assert pyproject["tool"]["pytest"]["ini_options"]["markers"] == [
        MARKER_REGISTRATION
    ]

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert makefile.count("-m 'not raos_owner_private'") == 1
    assert makefile.count("-m raos_owner_private tests/st0101") == 1
    phony_declaration = makefile[
        makefile.index(".PHONY:") : makefile.index("\nbootstrap:")
    ]
    phony_targets = phony_declaration.replace("\\\n", " ").split()
    assert phony_targets.count("pro-owner-private-test") == 1
    owner_target = makefile[
        makefile.index("pro-owner-private-test:") : makefile.index("python-install:")
    ]
    assert 'test "$(RAOS_REPOSITORY_ROOT)" = /home/minami/rakuten' in owner_target
    assert "test_hosted_unit_hybrid_boundary.py" in owner_target
    assert "PRO_RUNTIME_READY" in owner_target
    assert "len(cases) == 7" in owner_target
    assert 'root.findall(".//skipped")' in owner_target
    assert owner_target.index("test_hosted_unit_hybrid_boundary.py") < (
        owner_target.index("-m raos_owner_private")
    )
    assert owner_target.count('cd "$(RAOS_REPOSITORY_ROOT)"') == 3
    for digest in (
        "ba54950ce5b13803dfc14f9c0e1e05c2dc7384b78e6aac675f31a265d3ae1172",
        "fbb6ed9a22a2204045da6f9b6aa96db2fad21ebd4fcce5284bc2bf5793c394aa",
        "b77308a94b3254f467391e37ba21741481acc6d4737905e4119b67b4407ccafd",
        "06fbf7646f830182a5a424172bb76056bdda433a1a94d5f0784f19cb9681d77f",
        "acaefe2d566d84e504803b7df4d745d2eab5dd64fc8d548d4934dca1929cae07",
    ):
        assert digest in owner_target
    ci_unit = makefile[makefile.index("ci-unit:") : makefile.index("ci-contracts:")]
    assert ci_unit.count("not raos_owner_private") == 1
    assert ci_unit.count("tests/st0101") == 1
    assert "tests/st0102" in ci_unit
    assert "tests/st0801" in ci_unit


def test_direct_function_markers_equal_the_contract_without_hidden_outcomes() -> None:
    _validate_boundary_contract(_load_yaml(CONTRACT_PATH))
    assert not (TEST_ROOT / "conftest.py").exists()
    assert not (REPOSITORY_ROOT / "conftest.py").exists()
    assert _direct_marker_node_ids() == set(OWNER_PRIVATE_NODE_IDS)


def test_full_marked_and_hosted_collections_form_an_exact_partition() -> None:
    full = _collect_node_ids(None)
    marked = _collect_node_ids(MARKER_NAME)
    hosted = _collect_node_ids(f"not {MARKER_NAME}")
    assert marked == set(OWNER_PRIVATE_NODE_IDS)
    assert full == marked | hosted
    assert marked.isdisjoint(hosted)
    assert set(PORTABLE_NODE_IDS).issubset(hosted)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "renamed",
        "wildcard",
        "prefix",
        "duplicate",
        "type-confusion",
    ],
)
def test_inventory_validator_rejects_nonexact_mutations(mutation: str) -> None:
    document = deepcopy(_load_yaml(CONTRACT_PATH))
    inventory = document["owner_private_node_ids"]
    if mutation == "type-confusion":
        document["requirements"]["owner_private_inventory"]["count"] = True
    elif mutation == "missing":
        inventory.pop()
    elif mutation == "extra":
        inventory.append(
            "tests/st0101/test_chatgpt_pro_orchestrator.py::test_unapproved_extra"
        )
    elif mutation == "renamed":
        inventory[0] = inventory[0] + "_renamed"
    elif mutation == "wildcard":
        inventory[0] = "tests/st0101/test_chatgpt_pro_*.py::test_owner_private_*"
    elif mutation == "prefix":
        inventory[0] = "tests/st0101/test_chatgpt_pro_browser_selection.py"
    else:
        inventory.append(inventory[0])
    with pytest.raises(BoundaryContractError):
        _validate_boundary_contract(document)


@pytest.mark.parametrize(
    "source",
    [
        "import pytest\npytestmark = pytest.mark.raos_owner_private\n",
        (
            "import pytest\n@pytest.mark.raos_owner_private\n"
            "class TestPrivate:\n    def test_case(self):\n        pass\n"
        ),
        (
            "import pytest\ndef pytest_collection_modifyitems(items):\n"
            "    for item in items:\n"
            "        item.add_marker(getattr(pytest.mark, 'raos_owner_private'))\n"
        ),
        (
            "import pytest\n@pytest.mark.raos_owner_private\n@pytest.mark.skip\n"
            "def test_case():\n    pass\n"
        ),
        (
            "import pytest\n@pytest.mark.raos_owner_private\n@pytest.mark.xfail\n"
            "def test_case():\n    pass\n"
        ),
        (
            "import pytest\n@pytest.mark.raos_owner_private\n"
            "def test_case():\n    pytest.skip('hidden')\n"
        ),
    ],
)
def test_declaration_validator_rejects_file_dynamic_and_hidden_outcomes(
    source: str,
) -> None:
    synthetic_path = TEST_ROOT / "test_synthetic_owner_private.py"
    with pytest.raises(BoundaryContractError):
        _direct_marker_node_ids_from_sources({synthetic_path: source})


@pytest.mark.parametrize(
    "yaml_text",
    [
        "schema: one\nschema: two\n",
        "defaults: &defaults\n  value: one\nmerged:\n  <<: *defaults\n",
    ],
)
def test_yaml_loader_rejects_duplicate_merge_anchor_and_alias_forms(
    yaml_text: str,
) -> None:
    with pytest.raises(BoundaryContractError):
        _load_yaml_text(yaml_text)
