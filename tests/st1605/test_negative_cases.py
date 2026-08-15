from __future__ import annotations

import ast
import builtins
import copy
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from scripts import build_st1605_failure_injection_drill as builder

base = builder.base


@pytest.mark.parametrize("action", builder.ACTION_NAMES)
@pytest.mark.parametrize("invalid", [True, 1, 0.0, "0"])
def test_non_exact_zero_external_action_fails_closed(
    action: str, invalid: object, contract: dict[str, object]
) -> None:
    execution = contract["execution_boundary"]
    assert isinstance(execution, dict)
    counts = execution["external_action_counts"]
    assert isinstance(counts, dict)
    counts[action] = invalid
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        builder.validate_contract(contract)
    assert error.value.code == "SAFE_BOUNDARY_DRIFT"


@pytest.mark.parametrize(
    ("section", "key", "invalid"),
    [
        ("document", "classification", "FORMAL_TST_028_EVIDENCE"),
        ("document", "operational_execution", True),
        ("document", "acceptance_criteria_satisfied", True),
        ("execution_boundary", "network_access", "ALLOWED"),
        ("execution_boundary", "provider_calls", "ALLOWED"),
        ("execution_boundary", "credential_access", "ALLOWED"),
        ("execution_boundary", "database_connection", "ALLOWED"),
        ("execution_boundary", "queue_connection", "ALLOWED"),
        ("execution_boundary", "staging_access", "ALLOWED"),
        ("execution_boundary", "randomness", "ALLOWED"),
        ("execution_boundary", "cli_python_isolated_mode", "OPTIONAL"),
        ("execution_boundary", "cli_python_no_bytecode_mode", "OPTIONAL"),
        ("execution_boundary", "runtime_module_loading", "PATH_BASED_IMPORT"),
        (
            "execution_boundary",
            "runtime_module_inventory_scope",
            "FULL_RAOS_PACKAGE_GRAPH",
        ),
        (
            "execution_boundary",
            "runtime_adapter_package_boundary",
            "EXECUTE_PACKAGE_INIT",
        ),
        ("execution_boundary", "preloaded_raos_modules", "ALLOWED"),
        ("execution_boundary", "unlisted_raos_dependencies", "ALLOWED"),
        ("execution_boundary", "unrelated_provider_sdk_imports", "ALLOWED"),
        ("execution_boundary", "runtime_module_cleanup", "ALL_RAOS_NAMES"),
        (
            "execution_boundary",
            "foreign_raos_modules_during_scope",
            "DELETE_AND_FAIL",
        ),
        ("execution_boundary", "preloaded_helper_module", "ALLOWED"),
        ("execution_boundary", "credential_environment_reads", "ALLOWED"),
        ("execution_boundary", "process_context", "ENV-CI"),
        ("execution_boundary", "target_adapter_environment", "ENV-DEV"),
        ("execution_boundary", "step_up_fixture_environment", "ENV-CI"),
        ("evidence_boundary", "formal_tst_028", "PASS"),
        ("evidence_boundary", "owner_response", "PASS"),
        ("evidence_boundary", "runbook_validation", "PASS"),
        ("evidence_boundary", "staging_drill", "PASS"),
        ("evidence_boundary", "behavioral_observation_scope", "ALL_SCENARIOS"),
        ("evidence_boundary", "behavioral_observation_scenarios", 6),
        ("evidence_boundary", "static_tabletop_reference_scenarios", 0),
        ("evidence_boundary", "story_acceptance", True),
        ("evidence_boundary", "st_1607_eligible", True),
    ],
)
def test_authority_or_attestation_escalation_is_rejected(
    section: str, key: str, invalid: object, contract: dict[str, object]
) -> None:
    mapping = contract[section]
    assert isinstance(mapping, dict)
    mapping[key] = invalid
    with pytest.raises(builder.FailureInjectionDrillError):
        builder.validate_contract(contract)


def test_unknown_missing_or_reordered_contract_key_is_rejected(
    contract: dict[str, object],
) -> None:
    unknown = copy.deepcopy(contract)
    unknown["unknown"] = None
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        builder.validate_contract(unknown)
    assert error.value.code == "CONTRACT_SCHEMA_DRIFT"

    missing = copy.deepcopy(contract)
    del missing["scenarios"]
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        builder.validate_contract(missing)
    assert error.value.code == "CONTRACT_SCHEMA_DRIFT"

    reordered = {key: contract[key] for key in reversed(tuple(contract))}
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        builder.validate_contract(reordered)
    assert error.value.code == "CONTRACT_SCHEMA_DRIFT"


def test_scenario_nondeterminism_inventory_or_overclaim_is_rejected(
    contract: dict[str, object],
) -> None:
    scenarios = contract["scenarios"]
    assert isinstance(scenarios, list)
    mutated = copy.deepcopy(contract)
    mutated_scenarios = mutated["scenarios"]
    assert isinstance(mutated_scenarios, list)
    mutated_scenarios.reverse()
    with pytest.raises(builder.FailureInjectionDrillError):
        builder.validate_contract(mutated)

    outcome = scenarios[0]["expected_observation"]
    assert isinstance(outcome, dict)
    outcome["operation_executed"] = True
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        builder.validate_contract(contract)
    assert error.value.code == "SAFE_BOUNDARY_DRIFT"


def test_fixed_time_uuid_and_generation_cannot_drift(
    contract: dict[str, object],
) -> None:
    fixture = contract["deterministic_fixture"]
    assert isinstance(fixture, dict)
    for field, invalid in (
        ("observation_time", "2026-08-16T00:00:01Z"),
        ("site_id", "00000000-0000-0000-0000-000000009999"),
        ("kill_switch_generation", 8),
    ):
        mutated = copy.deepcopy(contract)
        mutated_fixture = mutated["deterministic_fixture"]
        assert isinstance(mutated_fixture, dict)
        mutated_fixture[field] = invalid
        with pytest.raises(builder.FailureInjectionDrillError):
            builder.validate_contract(mutated)


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("target_adapter_environment", "ENV-DEV"),
        ("step_up_fixture_environment", "ENV-CI"),
    ),
)
def test_kill_switch_observation_environment_boundary_cannot_drift(
    contract: dict[str, object], field: str, invalid: str
) -> None:
    scenarios = contract["scenarios"]
    assert isinstance(scenarios, list)
    observation = scenarios[4]["expected_observation"]
    assert isinstance(observation, dict)
    observation[field] = invalid
    with pytest.raises(builder.FailureInjectionDrillError):
        builder.validate_contract(contract)


def test_unsafe_or_absolute_repository_uri_is_rejected(
    contract: dict[str, object],
) -> None:
    sources = contract["authority_sources"]
    assert isinstance(sources, list)
    for invalid in ("repo://../outside", "repo:///absolute", "https://example.test"):
        mutated = copy.deepcopy(contract)
        mutated_sources = mutated["authority_sources"]
        assert isinstance(mutated_sources, list)
        mutated_sources[0]["uri"] = invalid
        with pytest.raises(builder.FailureInjectionDrillError):
            builder.validate_contract(mutated)


def test_duplicate_yaml_key_and_alias_are_rejected(repository_copy: Path) -> None:
    contract_path = repository_copy / builder.CONTRACT_PATH
    original = contract_path.read_text()
    contract_path.write_text(original + "document: {}\n")
    with pytest.raises(base.ProductionDeploymentContractError):
        builder.load_contract(repository_copy)
    contract_path.write_text("a: &x {}\nb: *x\n")
    with pytest.raises(base.ProductionDeploymentContractError):
        builder.load_contract(repository_copy)


def test_semantically_tampered_st1602_plan_is_rejected_after_digest_rebind(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = Path("changes/st-1602/generated/slo-alert-reference-plan.v1.json")
    path = repository_copy / relative
    plan = json.loads(path.read_text())
    plan["open_decision"]["notifications_enabled"] = True
    path.write_text(json.dumps(plan, indent=2) + "\n")
    digest = builder._sha256_bytes(path.read_bytes())  # noqa: SLF001
    hashes = dict(builder.EXPECTED_ST1602_HASHES)
    hashes[relative.as_posix()] = digest
    monkeypatch.setattr(builder, "EXPECTED_ST1602_HASHES", hashes)
    raw = builder._load_yaml(  # noqa: SLF001
        repository_copy, builder.CONTRACT_PATH, "contract"
    )
    assert isinstance(raw, dict)
    inputs = raw["dependency_bindings"]["slo_alert_reference"]["inputs"]
    next(row for row in inputs if row["uri"] == f"repo://{relative}")["sha256"] = digest
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        builder.validate_contract(raw, repository_copy)
    assert error.value.code == "DEPENDENCY_SEMANTIC_DRIFT"


def test_check_mode_never_calls_atomic_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_write(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("check mode attempted a write")

    monkeypatch.setattr(base, "_atomic_write", forbidden_write)
    builder.build(check=True)


def test_builder_has_no_external_nondeterministic_or_mutating_surface() -> None:
    source = (builder.REPO_ROOT / builder.GENERATOR_PATH).read_text()
    tree = ast.parse(source)
    assert source.index('if __name__ == "__main__"') < source.index("import yaml")
    first_non_builtin_import = source.index("import argparse")
    assert source.index("sys.flags.isolated") < first_non_builtin_import
    assert source.index("sys.flags.dont_write_bytecode") < first_non_builtin_import
    forbidden_imports = {
        "boto3",
        "botocore",
        "requests",
        "httpx",
        "socket",
        "subprocess",
        "sqlalchemy",
        "psycopg",
        "random",
        "secrets",
        "time",
    }
    observed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            observed.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            observed.add(node.module.split(".")[0])
    assert observed.isdisjoint(forbidden_imports)
    for token in (
        "os.environ",
        "getenv(",
        "datetime.now",
        "uuid4(",
        "Popen(",
        "subprocess.run",
        "requests.",
        "socket.",
        "publish(",
        "rollback(",
        "delete(",
    ):
        assert token not in source
    assert "build_st1505_staging_deployment" not in source
    assert "read_bytes(" not in source
    assert "_output_file(" not in source
    for secure_helper in (
        "_read_repository_file(",
        "_parse_yaml_bytes(",
        "_parse_json_bytes(",
        "_atomic_write(",
    ):
        assert secure_helper in source
    assert "LOCAL_SYNTHETIC_PASS" not in source

    helper_path = Path(next(iter(builder.EXPECTED_IMPLEMENTATION_HASHES)))
    helper_source = (builder.REPO_ROOT / helper_path).read_text()
    helper_tree = ast.parse(helper_source)
    helper_imports: set[str] = set()
    for node in ast.walk(helper_tree):
        if isinstance(node, ast.Import):
            helper_imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            helper_imports.add(node.module.split(".")[0])
    assert helper_imports.isdisjoint({"random", "secrets"})
    assert "os.urandom" not in helper_source
    assert "uuid4(" not in helper_source


def test_repository_imports_are_lazy_and_match_the_closed_inventory() -> None:
    source = (builder.REPO_ROOT / builder.GENERATOR_PATH).read_text()
    tree = ast.parse(source)
    assert all(
        not (
            (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith(("raos", "scripts"))
            )
            or (
                isinstance(node, ast.Import)
                and any(
                    alias.name.startswith(("raos", "scripts")) for alias in node.names
                )
            )
        )
        for node in tree.body
    )
    assert builder.EXPECTED_IMPLEMENTATION_HASHES == {
        builder.SECURE_IO_PATH.as_posix(): builder.SECURE_IO_SHA256,
    }
    assert "base: Any = _load_secure_io_bootstrap(REPO_ROOT)" in source
    assert 'exec(compile(content, module.__file__, "exec")' in source
    assert "class _CapturedRuntimeLoader" in source
    assert "class _ClosedRuntimeFinder" in source
    assert "SECURE_IO_MODULE_NAME in sys.modules" in source
    assert "_remove_owned_runtime_modules(finder)" in source
    assert "loaded_names = [name for name in sys.modules" not in source
    assert (
        "compile(\n                captured.content,\n                captured.origin"
        in source
    )
    loader = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_import_runtime_bindings"
    )
    observed = {
        node.module
        for node in ast.walk(loader)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.startswith("raos")
    }
    assert observed == set(builder.DIRECT_RUNTIME_IMPORTS)
    assert observed.issubset(builder.EXPECTED_RUNTIME_MODULES)
    assert builder.RUNTIME_NAMESPACE_PACKAGES == (
        "raos.adapters",
        "raos.application",
        "raos.domain",
    )
    assert "raos.adapters" not in builder.EXPECTED_RUNTIME_MODULES
    assert len(builder.EXPECTED_RUNTIME_MODULES) == 34
    assert {
        "raos.adapters.ai_contract_registry",
        "raos.adapters.openai_responses",
        "raos.adapters.queue_fake",
        "raos.adapters.recorded_ai",
        "raos.domain.ai.provider",
        "raos.ports.ai_provider",
        "raos.shared",
        "raos.shared.contract_repository",
    }.isdisjoint(builder.EXPECTED_RUNTIME_MODULES)


def test_runtime_preflight_happens_before_any_raos_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    original_import = builtins.__import__

    def rejected_preflight(_root: Path) -> object:
        events.append("preflight")
        raise builder.FailureInjectionDrillError("TEST_PREFLIGHT_STOP", "runtime")

    def observed_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name.startswith("raos"):
            events.append(f"import:{name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builder, "_capture_runtime_module_inputs", rejected_preflight)
    monkeypatch.setattr(builtins, "__import__", observed_import)
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        with builder._runtime_binding_scope(builder.REPO_ROOT):  # noqa: SLF001
            raise AssertionError("rejected preflight entered runtime scope")
    assert error.value.code == "TEST_PREFLIGHT_STOP"
    assert events == ["preflight"]


@pytest.mark.parametrize("module_name", ("raos", "raos.preloaded"))
def test_preloaded_raos_module_is_rejected_before_capture(
    module_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def forbidden_capture(_root: Path) -> object:
        events.append("capture")
        raise AssertionError("preloaded module reached source capture")

    monkeypatch.setitem(sys.modules, module_name, ModuleType(module_name))
    monkeypatch.setattr(builder, "_capture_runtime_module_inputs", forbidden_capture)
    with pytest.raises(builder.FailureInjectionDrillError) as error:
        with builder._runtime_binding_scope(builder.REPO_ROOT):  # noqa: SLF001
            raise AssertionError("preloaded module entered runtime scope")
    assert error.value.code == "RUNTIME_MODULE_PRELOADED"
    assert events == []


def test_runtime_scope_preserves_foreign_sentinel_after_inventory_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign_name = "raos.foreign_sentinel"
    foreign_module = ModuleType(foreign_name)
    owned_modules: dict[str, ModuleType] = {}
    meta_path_before = tuple(sys.meta_path)

    with pytest.raises(builder.FailureInjectionDrillError) as error:
        with builder._runtime_binding_scope(builder.REPO_ROOT):  # noqa: SLF001
            owned_modules.update(
                {
                    name: module
                    for name in (
                        *builder.EXPECTED_RUNTIME_MODULES,
                        *builder.RUNTIME_NAMESPACE_PACKAGES,
                    )
                    if isinstance((module := sys.modules.get(name)), ModuleType)
                }
            )
            monkeypatch.setitem(sys.modules, foreign_name, foreign_module)

    assert error.value.code == "RUNTIME_MODULE_INVENTORY_DRIFT"
    assert sys.modules.get(foreign_name) is foreign_module
    assert tuple(sys.meta_path) == meta_path_before
    assert len(owned_modules) == (
        len(builder.EXPECTED_RUNTIME_MODULES) + len(builder.RUNTIME_NAMESPACE_PACKAGES)
    )
    assert all(
        sys.modules.get(name) is not module for name, module in owned_modules.items()
    )


def test_runtime_scope_preserves_foreign_expected_name_replacement() -> None:
    replacement_name = "raos.adapters.recorded_kill_switch"
    foreign_module = ModuleType(replacement_name)
    owned_modules: dict[str, ModuleType] = {}

    try:
        with pytest.raises(builder.FailureInjectionDrillError) as error:
            with builder._runtime_binding_scope(builder.REPO_ROOT):  # noqa: SLF001
                owned_modules.update(
                    {
                        name: module
                        for name in (
                            *builder.EXPECTED_RUNTIME_MODULES,
                            *builder.RUNTIME_NAMESPACE_PACKAGES,
                        )
                        if isinstance((module := sys.modules.get(name)), ModuleType)
                    }
                )
                assert owned_modules[replacement_name] is not foreign_module
                sys.modules[replacement_name] = foreign_module

        assert error.value.code == "RUNTIME_MODULE_INVENTORY_DRIFT"
        assert sys.modules.get(replacement_name) is foreign_module
        assert all(
            sys.modules.get(name) is not module
            for name, module in owned_modules.items()
        )
    finally:
        if sys.modules.get(replacement_name) is foreign_module:
            del sys.modules[replacement_name]


def test_runtime_scope_exception_removes_only_its_owned_module_identities() -> None:
    owned_modules: dict[str, ModuleType] = {}
    meta_path_before = tuple(sys.meta_path)

    with pytest.raises(RuntimeError, match="scope-body-stop"):
        with builder._runtime_binding_scope(builder.REPO_ROOT):  # noqa: SLF001
            owned_modules.update(
                {
                    name: module
                    for name in (
                        *builder.EXPECTED_RUNTIME_MODULES,
                        *builder.RUNTIME_NAMESPACE_PACKAGES,
                    )
                    if isinstance((module := sys.modules.get(name)), ModuleType)
                }
            )
            raise RuntimeError("scope-body-stop")

    assert tuple(sys.meta_path) == meta_path_before
    assert owned_modules
    assert all(
        sys.modules.get(name) is not module for name, module in owned_modules.items()
    )


def test_runtime_scope_cleans_partial_owned_import_after_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partial_owned: dict[str, ModuleType] = {}
    expected_count = len(builder.EXPECTED_RUNTIME_MODULES) + len(
        builder.RUNTIME_NAMESPACE_PACKAGES
    )

    def partial_import_then_fail() -> object:
        builtins.__import__(
            "raos.adapters.development_oidc",
            fromlist=("DevelopmentOidcAdapter",),
        )
        partial_owned.update(
            {
                name: module
                for name in (
                    *builder.EXPECTED_RUNTIME_MODULES,
                    *builder.RUNTIME_NAMESPACE_PACKAGES,
                )
                if isinstance((module := sys.modules.get(name)), ModuleType)
            }
        )
        if not 0 < len(partial_owned) < expected_count:
            raise AssertionError("fixture did not stop after a partial import")
        raise RuntimeError("partial-runtime-import-stop")

    monkeypatch.setattr(builder, "_import_runtime_bindings", partial_import_then_fail)
    with pytest.raises(RuntimeError, match="partial-runtime-import-stop"):
        with builder._runtime_binding_scope(builder.REPO_ROOT):  # noqa: SLF001
            raise AssertionError("partial import unexpectedly yielded")

    assert all(
        sys.modules.get(name) is not module for name, module in partial_owned.items()
    )


def test_unlisted_raos_dependency_is_rejected_without_side_effect(
    repository_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = repository_copy / "unlisted-runtime-executed"
    unlisted = repository_copy / "python/raos/unlisted_runtime_dependency.py"
    unlisted.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('EXECUTED', encoding='utf-8')\n",
        encoding="utf-8",
    )
    root_path, _digest = builder.EXPECTED_RUNTIME_MODULES["raos"]
    root_source = repository_copy / root_path
    root_content = b"import raos.unlisted_runtime_dependency\n"
    root_source.write_bytes(root_content)
    expected_modules = dict(builder.EXPECTED_RUNTIME_MODULES)
    expected_modules["raos"] = (
        root_path,
        builder._sha256_bytes(root_content),  # noqa: SLF001
    )
    monkeypatch.setattr(builder, "EXPECTED_RUNTIME_MODULES", expected_modules)

    with pytest.raises(builder.FailureInjectionDrillError) as error:
        with builder._runtime_binding_scope(repository_copy):  # noqa: SLF001
            raise AssertionError("unlisted dependency entered runtime scope")
    assert error.value.code == "RUNTIME_MODULE_DEPENDENCY_UNLISTED"
    assert not marker.exists()
    assert not any(name == "raos" or name.startswith("raos.") for name in sys.modules)


def test_secure_io_hash_preflight_happens_before_helper_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def rejected_preflight(_root: Path) -> bytes:
        events.append("preflight")
        raise builder.SecureIoBootstrapError("TEST_PREFLIGHT_STOP")

    def forbidden_exec(*_args: object, **_kwargs: object) -> None:
        events.append("exec")
        raise AssertionError("helper code executed before exact-byte preflight")

    monkeypatch.delitem(sys.modules, builder.SECURE_IO_MODULE_NAME)
    monkeypatch.setattr(builder, "_bootstrap_read_secure_io", rejected_preflight)
    monkeypatch.setattr(builtins, "exec", forbidden_exec)
    with pytest.raises(builder.SecureIoBootstrapError) as error:
        builder._load_secure_io_bootstrap(builder.REPO_ROOT)  # noqa: SLF001
    assert error.value.code == "TEST_PREFLIGHT_STOP"
    assert events == ["preflight"]


def test_secure_io_bootstrap_rejects_preloaded_helper_without_replacing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preloaded = ModuleType(builder.SECURE_IO_MODULE_NAME)
    events: list[str] = []

    def forbidden_read(_root: Path) -> bytes:
        events.append("read")
        raise AssertionError("preloaded helper reached descriptor read")

    def forbidden_exec(*_args: object, **_kwargs: object) -> None:
        events.append("exec")
        raise AssertionError("preloaded helper reached execution")

    monkeypatch.setitem(sys.modules, builder.SECURE_IO_MODULE_NAME, preloaded)
    monkeypatch.setattr(builder, "_bootstrap_read_secure_io", forbidden_read)
    monkeypatch.setattr(builtins, "exec", forbidden_exec)
    with pytest.raises(builder.SecureIoBootstrapError) as error:
        builder._load_secure_io_bootstrap(builder.REPO_ROOT)  # noqa: SLF001

    assert error.value.code == "HELPER_MODULE_PRELOADED"
    assert sys.modules.get(builder.SECURE_IO_MODULE_NAME) is preloaded
    assert events == []


def test_cli_accepts_only_generate_or_check() -> None:
    assert builder.parse_args([]).check is False
    assert builder.parse_args(["--check"]).check is True
    with pytest.raises(SystemExit) as error:
        builder.parse_args(["--apply"])
    assert error.value.code == 2


def test_nonisolated_cli_stops_before_build(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden_build(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("nonisolated CLI reached build")

    monkeypatch.setattr(builder, "build", forbidden_build)
    assert builder.main(["--check"]) == 1
    assert capsys.readouterr().err == (
        "ST1605_ERROR code=ISOLATED_MODE_REQUIRED field=cli.python\n"
    )
