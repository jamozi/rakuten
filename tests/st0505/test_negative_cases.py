"""Hostile closed-boundary tests for the ST-0505 builder."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any, Callable, cast

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import build_st0505_rakuten_live_smoke_reference_plan as generator


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "interface_only", False),
        ("document", "decision", "READY"),
        ("document", "approval", "approved"),
        ("document", "story_acceptance", True),
        ("document", "production_eligible", True),
        ("predecessor", "commit", "0" * 40),
        ("predecessor", "connection_status", "CONNECTED"),
        ("open_decision", "resolved", True),
        ("open_decision", "blocking", False),
        ("open_decision", "safe_default", "LIVE"),
        ("open_decision", "live_credentials_available", True),
        ("open_decision", "live_execution_authorized", True),
        ("live_smoke_definition", "status", "CONFIGURED"),
        ("live_smoke_definition", "runnable", True),
        ("live_smoke_definition", "runner", "runner"),
        ("live_smoke_definition", "command", "smoke --live"),
        ("live_smoke_definition", "selected_environment", "staging"),
        ("live_smoke_definition", "selected_account", "account"),
        ("live_smoke_definition", "selected_endpoint", "https://example.invalid"),
        ("live_smoke_definition", "credential_selection", "secret-ref"),
        ("live_smoke_definition", "request", "request"),
        ("live_smoke_definition", "response", "response"),
        ("live_smoke_definition", "report", "report"),
        ("live_smoke_definition", "retry_policy", "retry"),
        ("live_smoke_definition", "pagination_policy", "paginate"),
        ("live_smoke_definition", "artifacts", ["artifact"]),
        ("observation_defaults", "status", "PASS"),
        ("observation_defaults", "started_at", "2026-08-10T00:00:00Z"),
        ("observation_defaults", "finished_at", "2026-08-10T00:00:01Z"),
        ("observation_defaults", "auth_observation", "SUCCESS"),
        ("observation_defaults", "schema_observation", "VALID"),
        ("observation_defaults", "rate_observation", "OK"),
        ("observation_defaults", "provider_request_id", "request-1"),
        ("observation_defaults", "http_status", 200),
        ("observation_defaults", "latency", "100ms"),
        ("observation_defaults", "observations", ["auth"]),
        ("observation_defaults", "errors", ["none"]),
        ("observation_defaults", "evidence", ["report"]),
        ("rate_quota_cost_defaults", "rate_limit", 100),
        ("rate_quota_cost_defaults", "rate_remaining", 99),
        ("rate_quota_cost_defaults", "rate_reset", "later"),
        ("rate_quota_cost_defaults", "quota_limit", 1000),
        ("rate_quota_cost_defaults", "quota_remaining", 999),
        ("rate_quota_cost_defaults", "cost", 1),
        ("rate_quota_cost_defaults", "currency", "JPY"),
        ("rate_quota_cost_defaults", "capacity", "1rps"),
        ("rate_quota_cost_defaults", "values", [0]),
        ("execution_boundary", "enabled", True),
        ("execution_boundary", "live_smoke", "EXECUTED"),
        ("execution_boundary", "network", "ALLOWED"),
        ("execution_boundary", "credential", "ALLOWED"),
        ("execution_boundary", "provider", "ALLOWED"),
        ("execution_boundary", "sdk", "AVAILABLE"),
        ("execution_boundary", "filesystem", "AVAILABLE"),
        ("execution_boundary", "repository", "AVAILABLE"),
        ("execution_boundary", "storage", "EXECUTED"),
        ("execution_boundary", "persistence", "EXECUTED"),
        ("execution_boundary", "staging", "EXECUTED"),
        ("execution_boundary", "external_actions", ["provider-call"]),
        ("verification_boundary", "formal_tst_016", "PASS"),
        ("verification_boundary", "live_auth", "PASS"),
        ("verification_boundary", "live_schema", "PASS"),
        ("verification_boundary", "live_rate", "PASS"),
        ("verification_boundary", "provider_runtime", "PASS"),
        ("verification_boundary", "network", "PASS"),
        ("verification_boundary", "credentials", "PASS"),
        ("verification_boundary", "production", "READY"),
    ],
)
def test_forbidden_live_selection_observation_or_claim_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.RakutenLiveSmokeReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [False, True, 0.0, "0"])
@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
def test_bool_float_string_and_nonzero_do_not_bypass_exact_zero_actions(
    action: str,
    replacement: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["execution_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.RakutenLiveSmokeReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("runtime_boundary", "credential_reader", "AVAILABLE"),
        ("runtime_boundary", "provider_adapter", "AVAILABLE"),
        ("runtime_boundary", "endpoint", "https://example.invalid"),
        ("runtime_boundary", "provider_call", "ALLOWED"),
        ("execution_evidence", "credential_values_received", True),
        ("execution_evidence", "real_store_setup", "EXECUTED"),
        ("check_boundary", "secret_file_open", "ALLOWED"),
        ("check_boundary", "secret_content_read", "ALLOWED"),
        ("launcher_boundary", "python_flags", ["-I"]),
        ("launcher_boundary", "site_import", "ENABLED"),
        ("launcher_boundary", "executable_pth_hooks", "ENABLED"),
        ("launcher_boundary", "trusted_ancestor_owner", "CURRENT_ONLY"),
        ("launcher_boundary", "owner_controlled_nodes", "ROOT_ALLOWED"),
        ("launcher_boundary", "group_world_writable", "ALLOWED"),
        ("launcher_boundary", "venv_python_symlink", "FOLLOW_ONLY"),
        ("launcher_boundary", "python_path", "AMBIENT"),
        ("launcher_boundary", "stdlib_metadata", "DIRECT_IMPORTS_ONLY"),
        ("launcher_boundary", "python314_zip", "ALLOWED"),
        ("launcher_boundary", "pre_python_path_configuration", "ALLOWED"),
        ("launcher_boundary", "base_executable_override_environment", "INHERITED"),
        ("launcher_boundary", "runtime_rpath_shadow_libraries", "ALLOWED"),
        ("launcher_boundary", "credential_script_open", "PATH_ONLY"),
        ("launcher_boundary", "credential_script_execution", "PATH_REOPEN"),
        ("launcher_boundary", "interpreter_execution", "UNVALIDATED_PATH"),
        ("launcher_boundary", "same_euid_runtime_mutator", "SUPPORTED"),
        ("launcher_boundary", "os_platform_tcb", "UNBOUNDED"),
        ("input_boundary", "terminal_mode", "NONCANONICAL_ALLOWED"),
        ("input_boundary", "maximum_value_bytes", 4095),
        ("input_boundary", "rejected_line_handling", "RETURN_IMMEDIATELY"),
        ("input_boundary", "rejected_line_descriptor", "BLOCKING"),
        ("input_boundary", "rejected_line_discard_limit_bytes", 0),
        ("input_boundary", "rejected_line_timeout_seconds", 0.0),
        ("input_boundary", "incomplete_drain_restore", "TCSANOW"),
        ("input_boundary", "successful_drain_boundary", "DRAIN_ALL_AVAILABLE"),
        ("input_boundary", "hidden_mode_restore", "TCSANOW_ON_SUCCESS"),
        ("input_boundary", "prompt_input_cardinality", "QUEUED_LINE_ALLOWED"),
        ("input_boundary", "queued_typeahead", "PRESERVED"),
        ("provider_contract_context", "future_access_key_transport", "QUERY"),
    ),
)
def test_credential_intake_runtime_or_secret_read_inflation_is_rejected(
    section: str, field: str, value: object
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["local_credential_intake"][section][field] = value
    with pytest.raises(generator.RakutenLiveSmokeReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("observation_defaults")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["live_smoke_definition"]["unknown"] = None


def _reverse_sources(value: dict[str, Any]) -> None:
    value["authority"]["sources"].reverse()


def _reverse_actions(value: dict[str, Any]) -> None:
    counts = value["execution_boundary"]["action_counts"]
    value["execution_boundary"]["action_counts"] = dict(reversed(tuple(counts.items())))


@pytest.mark.parametrize(
    "mutation",
    [_remove_top, _add_top, _add_nested, _reverse_sources, _reverse_actions],
)
def test_missing_unknown_and_reordered_keys_are_rejected(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    mutation(contract)
    with pytest.raises(generator.RakutenLiveSmokeReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("mutation", ("omit", "reorder", "duplicate", "hash"))
def test_predecessor_inventory_omission_reorder_duplicate_or_hash_drift_is_rejected(
    mutation: str,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    artifacts = contract["predecessor"]["artifacts"]
    if mutation == "omit":
        artifacts.pop()
    elif mutation == "reorder":
        artifacts[-2:] = reversed(artifacts[-2:])
    elif mutation == "duplicate":
        artifacts.append(deepcopy(artifacts[-1]))
    else:
        artifacts[-1]["sha256"] = "0" * 64

    with pytest.raises(generator.RakutenLiveSmokeReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    ("field", "inflated"),
    (
        ("non_executable", False),
        ("requested_page", 2),
        ("hits_minimum", 0),
        ("hits_maximum", 31),
        ("retry_limit", 1),
        ("pagination_followup_limit", 1),
        ("review_derived_request_inputs", "AVAILABLE"),
        ("affiliate_rate_request_inputs", "AVAILABLE"),
        ("provider_text_trust", "TRUSTED"),
    ),
)
def test_live_request_policy_semantic_inflation_is_rejected(
    field: str,
    inflated: object,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    policy = contract["predecessor"]["semantics"]["live_request_policy"]
    policy[field] = inflated

    with pytest.raises(generator.RakutenLiveSmokeReferenceError):
        generator.validate_contract(contract)


def test_live_request_policy_unknown_semantic_is_rejected() -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    policy = contract["predecessor"]["semantics"]["live_request_policy"]
    policy["unexpected"] = "AVAILABLE"

    with pytest.raises(generator.RakutenLiveSmokeReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    [
        b"document: {}\ndocument: {}\n",
        b"document: &shared {}\nauthority: *shared\n",
        b"document: !!python/object/apply:os.system [id]\n",
        b"base: &base {enabled: false}\nmerged: {<<: *base}\n",
    ],
)
def test_yaml_duplicate_alias_tag_and_merge_are_rejected(
    isolated_repository: Path,
    payload: bytes,
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)
    with pytest.raises(
        (generator.RakutenLiveSmokeReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        (generator.RakutenLiveSmokeReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_symlink_contract_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


def test_symlink_contract_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    changes = isolated_repository / "changes"
    moved = tmp_path / "changes"
    changes.rename(moved)
    changes.symlink_to(moved, target_is_directory=True)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


def test_output_symlink_target_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    target = isolated_repository / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


def test_output_symlink_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    generated = isolated_repository / generator.REFERENCE_PLAN_PATH.parent
    outside = tmp_path / "generated"
    outside.mkdir()
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.symlink_to(outside, target_is_directory=True)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert not tuple(outside.iterdir())


def test_path_traversal_is_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize(
    "relative",
    [
        generator.OPEN_DECISIONS_PATH,
        generator.TEST_CATALOG_PATH,
        generator.STORY_PATH,
        generator.DESIGN_HANDOFF_PATH,
        *(path for path, _digest in generator.EXPECTED_PREDECESSOR_ARTIFACTS),
    ],
)
def test_authority_or_predecessor_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.RakutenLiveSmokeReferenceError):
        generator.render_outputs(isolated_repository)


def _rebind_expected_predecessor(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = cast(dict[str, Any], deepcopy(generator.EXPECTED_PREDECESSOR))
    expected["artifacts"] = generator._expected_predecessor_artifacts()
    monkeypatch.setattr(generator, "EXPECTED_PREDECESSOR", expected)


def test_predecessor_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.EXPECTED_PREDECESSOR_ARTIFACTS[1][0]
    path = isolated_repository / relative
    text = path.read_text(encoding="utf-8").replace(
        'RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"',
        'RECORDED_TEST_ONLY = "LIVE"',
        1,
    )
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (candidate, digest if candidate == relative else expected)
        for candidate, expected in generator.EXPECTED_PREDECESSOR_ARTIFACTS
    )
    monkeypatch.setattr(generator, "EXPECTED_PREDECESSOR_ARTIFACTS", rebound)
    _rebind_expected_predecessor(monkeypatch)
    contract = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    contract["predecessor"]["artifacts"][1]["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(
        generator.RakutenLiveSmokeReferenceError,
        match=r"PREDECESSOR_SEMANTIC_DRIFT field=predecessor\.domain",
    ):
        generator.render_outputs(isolated_repository)


@pytest.mark.parametrize(
    ("needle", "replacement"),
    (
        (
            "_exact_int(self.hits, minimum=1, maximum=30)",
            "_exact_int(self.hits, minimum=1, maximum=31)",
        ),
        (
            "    def __post_init__(self) -> None:\n"
            '        if type(self.api_version) is not str or self.api_version != "2026-07-01":',
            "    def __post_init__(self) -> None:\n"
            "        return None\n"
            '        if type(self.api_version) is not str or self.api_version != "2026-07-01":',
        ),
        (
            "        _exact_int(self.hits, minimum=1, maximum=30)",
            "        if False:\n"
            "            _exact_int(self.hits, minimum=1, maximum=30)",
        ),
        (
            "        _exact_int(self.hits, minimum=1, maximum=30)",
            "        try:\n"
            "            _exact_int(self.hits, minimum=1, maximum=30)\n"
            "        except Exception:\n"
            "            pass",
        ),
        (
            "        if self.has_review_only:\n            fail_item_search()",
            "        if self.has_review_only:\n"
            "            return None\n"
            "        if self.has_review_only:\n"
            "            fail_item_search()",
        ),
        (
            "    def provider_derived_recommendation_inputs(self) -> tuple[()]:\n"
            "        return ()",
            "    def provider_derived_recommendation_inputs(self) -> tuple[()]:\n"
            "        return (None,)",
        ),
        (
            '    """Validated policy projection only; it has no provider action '
            'surface."""',
            '    """Validated policy projection only; it has no provider action '
            'surface."""\n\n'
            "    def __bool__(self) -> bool:\n"
            "        return True",
        ),
        (
            "__all__ = [",
            "RakutenItemSearchLiveRequestV1.__post_init__ = lambda self: None\n\n"
            "__all__ = [",
        ),
        (
            "    genre_information_flag: bool",
            "    genre_information_flag: bool\n    diagnostic_marker: bool",
        ),
        (
            "        if self.attribute_flag and "
            "(self.genre_id is None or self.genre_id == 0):\n"
            "            fail_item_search()",
            "        pass",
        ),
        (
            "def _exact_int(value: object, *, minimum: int, maximum: int) -> int:\n"
            "    if type(value) is not int or not minimum <= value <= maximum:",
            "def _exact_int(value: object, *, minimum: int, maximum: int) -> int:\n"
            "    return value\n"
            "    if type(value) is not int or not minimum <= value <= maximum:",
        ),
        (
            '            "hits": self.hits,',
            '            "hits": self.hits,\n'
            '            "has_review_only": self.has_review_only,',
        ),
        (
            '            "hits": self.hits,',
            '            "hits": self.hits,\n            "min_affiliate_rates": 0,',
        ),
        ("import json", "import json\nimport socket"),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def execute(self) -> None:\n"
            "        return None",
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def dynamic_socket(self) -> object:\n"
            '        return __import__("socket").socket()',
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def dynamic_socket(self) -> object:\n"
            "        from builtins import __import__ as loader\n\n"
            '        return loader("socket").socket()',
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def dynamic_socket(self) -> object:\n"
            "        from importlib import import_module as loader\n\n"
            '        return loader("socket").socket()',
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def reflected_socket(self) -> object:\n"
            "        from sys import modules as registry\n\n"
            '        return registry["socket"].socket()',
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def reflected_socket(self) -> object:\n"
            "        from json import __builtins__ as loader\n\n"
            '        return loader["__import__"]("socket").socket()',
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def reflected_socket(self) -> object:\n"
            '        return object.__getattribute__((lambda: None), "__globals__")'
            '["__builtins__"]["__import__"]("socket").socket()',
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def dynamic_marker(self) -> str:\n"
            '        return "__getattribute__"',
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def import_marker(self) -> str:\n"
            '        return "socket"',
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def indirect_call(self) -> object:\n"
            "        return (lambda: None)()",
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def capability(self) -> object:\n"
            "        return breakpoint()",
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def capability(self) -> object:\n"
            "        loader = breakpoint\n"
            "        return loader()",
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def capability(self) -> object:\n"
            "        return self.unknown_call()",
        ),
        (
            '    """Validated policy projection only; it has no provider action surface."""',
            '    """Validated policy projection only; it has no provider action surface."""\n\n'
            "    def capability(self) -> object:\n"
            "        from raos.adapters.subprocess_runner import "
            "SubprocessCommandRunner as dict\n"
            "        return dict()",
        ),
        ("import hashlib", "import hashlib as safe_hashlib"),
        (
            "from dataclasses import dataclass",
            "from dataclasses import dataclass as safe_dataclass",
        ),
        (
            "from typing import NoReturn, SupportsIndex",
            "from .typing import NoReturn, SupportsIndex",
        ),
        (
            "from typing import NoReturn, SupportsIndex",
            "from typing import *",
        ),
        ("import json", "import json\nimport collections"),
        (
            "    genre_information_flag: bool",
            "    genre_information_flag: bool\n    credential_reference: str | None",
        ),
    ),
)
def test_live_policy_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    needle: str,
    replacement: str,
) -> None:
    relative = generator.EXPECTED_PREDECESSOR_ARTIFACTS[9][0]
    path = isolated_repository / relative
    text = path.read_text(encoding="utf-8")
    assert text.count(needle) == 1
    text = text.replace(needle, replacement, 1)
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (candidate, digest if candidate == relative else expected)
        for candidate, expected in generator.EXPECTED_PREDECESSOR_ARTIFACTS
    )
    monkeypatch.setattr(generator, "EXPECTED_PREDECESSOR_ARTIFACTS", rebound)
    _rebind_expected_predecessor(monkeypatch)
    contract = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    contract["predecessor"]["artifacts"][9]["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(
        generator.RakutenLiveSmokeReferenceError,
        match=r"PREDECESSOR_SEMANTIC_DRIFT field=predecessor\.live_policy",
    ):
        generator.render_outputs(isolated_repository)


def test_canonical_story_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.STORY_PATH
    catalog = yaml.safe_load(path.read_bytes())
    story = next(item for item in catalog["stories"] if item["id"] == "ST-0505")
    story["verification_status"] = "PASS"
    path.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rebound = tuple(
        (
            role,
            source,
            digest if source == generator.STORY_PATH.as_posix() else expected,
        )
        for role, source, expected in generator.EXPECTED_SOURCES
    )
    monkeypatch.setattr(generator, "EXPECTED_SOURCES", rebound)
    contract = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    for source in contract["authority"]["sources"]:
        if source["role"] == "story":
            source["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(generator.RakutenLiveSmokeReferenceError):
        generator.render_outputs(isolated_repository)


def test_failure_is_stable_sanitized_and_does_not_echo_rejected_value() -> None:
    canary = "secret-canary-live-endpoint-value"
    contract = deepcopy(generator.load_contract())
    contract["live_smoke_definition"]["selected_endpoint"] = canary
    with pytest.raises(generator.RakutenLiveSmokeReferenceError) as caught:
        generator.validate_contract(contract)
    assert canary not in str(caught.value)
    assert caught.value.__cause__ is None


def test_builder_ast_has_no_external_runtime_or_action_surface() -> None:
    source = (generator.REPO_ROOT / generator.GENERATOR_PATH).read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert imported.isdisjoint(
        {
            "boto3",
            "httpx",
            "requests",
            "socket",
            "subprocess",
            "urllib",
            "sqlalchemy",
            "psycopg",
            "os",
            "random",
            "time",
            "uuid",
        }
    )
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called.isdisjoint(
        {"eval", "exec", "getenv", "Popen", "system", "sleep", "urlopen"}
    )
    assert attributes.isdisjoint(
        {
            "connect",
            "execute",
            "publish",
            "send",
            "request",
            "getenv",
            "resolve_credentials",
        }
    )
