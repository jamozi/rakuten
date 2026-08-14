"""Initial fail-closed checks for the ST-0703 recorded-fixture inventory."""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tomllib

import pytest
import yaml

from conftest import REPOSITORY_ROOT
from scripts import build_st0703_recorded_adapter as generator


CONTRACT_PATH = REPOSITORY_ROOT / generator.CONTRACT_PATH
FIXTURE_ROOT = REPOSITORY_ROOT / generator.FIXTURE_ROOT
GENERATOR_PATH = REPOSITORY_ROOT / "scripts/build_st0703_recorded_adapter.py"
EXPECTED_CONTRACT_SHA256 = (
    "2366b2f1041d14b4b87053f122b8df36cbf726acdf38c8722a3495667eb84b9b"
)
EXPECTED_REGISTRY_SHA256 = (
    "d1fa295307bdad7ec7fdb2f68167468c2209640d2c9fba8da881229f73bcc8d7"
)
EXPECTED_WHEEL_SHA256 = (
    "f97e231d9a8fa69ab55897df1080f02d99913fb0a30e3ee56ea16a1eb6c2d434"
)
EXPECTED_SDIST_SHA256 = (
    "7c736d592f81471ce1f734838390983c4d8c8aecff23dcd36e600a58e5032d9c"
)
EXPECTED_PREDECESSOR_MANIFEST_PROJECTION_SHA256 = {
    Path("changes/st-0204/manifest.yaml"): (
        "eef287ef5fc35fbcd979dd6c85bbe89d0949fa1186967c167b33dc4a76defdb4"
    ),
    Path("changes/st-0701/manifest.yaml"): (
        "a0d5aad3b2c95ba7a365d0fc0be5a7825834f7a9639260823e2729c27391ad0b"
    ),
    Path("changes/st-0801/manifest.yaml"): (
        "7704359cb758e3bf35bbe88e91e41c7f484e8133f1ab7d4a139b2bafde7b2540"
    ),
}
EXPECTED_PREDECESSOR_SEMANTIC_OUTPUT_SHA256 = {
    Path("changes/st-0204/manifest.yaml"): (
        "repo://changes/st-0204/generated/runtime-config.v1.schema.json",
        "5633b01e4f660a048e57ca4501a6a7e66f4aeca8412ff36f8644e68d4e04006e",
    ),
    Path("changes/st-0701/manifest.yaml"): (
        "repo://changes/st-0701/generated/ai-task-registry.v1.json",
        "33bbb3601aae2e02d37bf995a2522e67684befcd9a43ba4375b4a7685aedef07",
    ),
}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _copy_inputs(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    contract_target = root / generator.CONTRACT_PATH
    contract_target.parent.mkdir(parents=True)
    shutil.copy2(CONTRACT_PATH, contract_target)
    shutil.copy2(
        REPOSITORY_ROOT / generator.PYPROJECT_PATH,
        root / generator.PYPROJECT_PATH,
    )
    shutil.copy2(
        REPOSITORY_ROOT / generator.UV_LOCK_PATH,
        root / generator.UV_LOCK_PATH,
    )
    shutil.copy2(
        REPOSITORY_ROOT / generator.UV_CONFIG_PATH,
        root / generator.UV_CONFIG_PATH,
    )
    contract = yaml.safe_load(CONTRACT_PATH.read_bytes())
    for entries in contract["provenance"].values():
        for entry in entries:
            relative = Path(entry["uri"].removeprefix("repo://"))
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPOSITORY_ROOT / relative, target)
    for relative in generator.PREDECESSOR_MANIFEST_PROJECTION_SHA256:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(REPOSITORY_ROOT / relative, target)
    shutil.copytree(FIXTURE_ROOT, root / generator.FIXTURE_ROOT)
    script_target = root / GENERATOR_PATH.relative_to(REPOSITORY_ROOT)
    script_target.parent.mkdir(parents=True)
    shutil.copy2(GENERATOR_PATH, script_target)
    return root


def _replace_nested_request_member(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    replacement: bytes,
) -> bytes:
    filename = "success-structured.json"
    path = root / generator.FIXTURE_ROOT / filename
    content = path.read_bytes()
    member = b'"content": "SYNTHETIC_TEST_ONLY input record."'
    assert content.count(member) == 1
    mutated = content.replace(member, replacement)
    path.write_bytes(mutated)
    _repin_fixture(monkeypatch, filename, mutated)
    return mutated


def _repin_fixture(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content: bytes,
) -> None:
    monkeypatch.setattr(
        generator,
        "FIXTURE_SPECS",
        tuple(
            replace(spec, byte_count=len(content), sha256=_sha256(content))
            if spec.path == filename
            else spec
            for spec in generator.FIXTURE_SPECS
        ),
    )


def _write_fixture_document(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    document: dict[str, object],
) -> None:
    content = (
        json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode("utf-8")
    (root / generator.FIXTURE_ROOT / filename).write_bytes(content)
    _repin_fixture(monkeypatch, filename, content)


def _write_yaml_document(path: Path, document: object) -> None:
    path.write_bytes(
        yaml.safe_dump(
            document,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=1000,
        ).encode("utf-8")
    )


def _manifest_projection_sha256(document: dict[str, object]) -> str:
    projection = copy.deepcopy(document)
    source_artifacts = projection["source_artifacts"]
    assert isinstance(source_artifacts, list)
    for artifact in source_artifacts:
        assert isinstance(artifact, dict)
        artifact["bytes"] = 0
        artifact["sha256"] = "0" * 64
    content = json.dumps(
        projection,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(content)


def _replace_and_repin_input(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: Path,
    expected_hash_attribute: str,
    old: bytes,
    new: bytes,
) -> None:
    path = root / relative
    content = path.read_bytes()
    assert content.count(old) == 1
    mutated = content.replace(old, new)
    path.write_bytes(mutated)
    monkeypatch.setattr(generator, expected_hash_attribute, _sha256(mutated))


def _snapshot_tree(root: Path) -> dict[str, tuple[int, int, int, int, int, str]]:
    result: dict[str, tuple[int, int, int, int, int, str]] = {}
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        digest = _sha256(path.read_bytes()) if stat.S_ISREG(metadata.st_mode) else ""
        result[path.relative_to(root).as_posix()] = (
            metadata.st_mode,
            metadata.st_nlink,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
            digest,
        )
    return result


def _run_check(root: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "scripts/build_st0703_recorded_adapter.py", "--check"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_real_repository_check_succeeds() -> None:
    result = _run_check(REPOSITORY_ROOT)

    assert result.returncode == 0, result.stderr
    assert (
        "ST-0703 recorded fixtures are current "
        f"(count=5, registry_sha256={EXPECTED_REGISTRY_SHA256})" in result.stdout
    )
    assert result.stderr == ""
    assert generator.check(REPOSITORY_ROOT) == EXPECTED_REGISTRY_SHA256
    assert generator.EXPECTED_CONTRACT_SHA256 == EXPECTED_CONTRACT_SHA256
    assert _sha256(CONTRACT_PATH.read_bytes()) == EXPECTED_CONTRACT_SHA256


def test_subprocess_check_does_not_write_to_inputs(tmp_path: Path) -> None:
    root = _copy_inputs(tmp_path)
    before = _snapshot_tree(root)

    result = _run_check(root)

    assert result.returncode == 0, result.stderr
    assert EXPECTED_REGISTRY_SHA256 in result.stdout
    assert result.stderr == ""
    assert _snapshot_tree(root) == before


def test_registry_binds_all_dependency_source_inputs() -> None:
    registry = json.loads(generator.render_fixture_registry(REPOSITORY_ROOT))
    contract = yaml.safe_load(CONTRACT_PATH.read_bytes())
    provenance_inputs = [
        {
            "path": entry["uri"].removeprefix("repo://"),
            "sha256": entry["sha256"],
        }
        for entries in contract["provenance"].values()
        for entry in entries
    ]
    assert registry["source_inputs"] == [
        {
            "path": generator.CONTRACT_PATH.as_posix(),
            "sha256": generator.EXPECTED_CONTRACT_SHA256,
        },
        {
            "path": generator.PYPROJECT_PATH.as_posix(),
            "sha256": generator.EXPECTED_PYPROJECT_SHA256,
        },
        {
            "path": generator.UV_LOCK_PATH.as_posix(),
            "sha256": generator.EXPECTED_UV_LOCK_SHA256,
        },
        {
            "path": generator.UV_CONFIG_PATH.as_posix(),
            "sha256": generator.EXPECTED_UV_CONFIG_SHA256,
        },
        *provenance_inputs,
    ]


def test_v5_authority_is_exact_approved_and_preserves_v4_d1_through_d4() -> None:
    authority_sources = {
        generator.V4_HANDOFF_PATH: generator.V4_HANDOFF_SHA256,
        generator.V4_RECONCILIATION_PATH: generator.V4_RECONCILIATION_SHA256,
        generator.V4_APPROVAL_PATH: generator.V4_APPROVAL_SHA256,
        generator.V5_DECISION_REQUEST_PATH: generator.V5_DECISION_REQUEST_SHA256,
        generator.V5_HANDOFF_PATH: generator.V5_HANDOFF_SHA256,
        generator.V5_RECONCILIATION_PATH: generator.V5_RECONCILIATION_SHA256,
        generator.V5_APPROVAL_PATH: generator.V5_APPROVAL_SHA256,
    }
    for relative, expected_digest in authority_sources.items():
        assert _sha256((REPOSITORY_ROOT / relative).read_bytes()) == expected_digest

    contract = yaml.load(CONTRACT_PATH.read_bytes(), Loader=generator.UniqueKeyLoader)
    assert isinstance(contract, dict)
    assert contract["implementation_authority"] == (
        generator.EXPECTED_IMPLEMENTATION_AUTHORITY
    )
    generator._validate_v5_authority(REPOSITORY_ROOT, contract)

    v4 = yaml.load(
        (REPOSITORY_ROOT / generator.V4_HANDOFF_PATH).read_bytes(),
        Loader=generator.UniqueKeyLoader,
    )["DESIGN_HANDOFF_V1"]
    v5 = yaml.load(
        (REPOSITORY_ROOT / generator.V5_HANDOFF_PATH).read_bytes(),
        Loader=generator.UniqueKeyLoader,
    )["DESIGN_HANDOFF_V1"]
    for key in generator.V5_INHERITED_DECISION_KEYS:
        assert v5["decision"][key] == v4["decision"][key]
    assert v5["decision"]["authority_revision"]["replaced_decision"] == ("ST0703-V3-D5")
    assert v5["decision"]["gate_wiring"]["decision_id"] == ("ST0703-V5-D5-CORRECTION")

    approval = yaml.load(
        (REPOSITORY_ROOT / generator.V5_APPROVAL_PATH).read_bytes(),
        Loader=generator.UniqueKeyLoader,
    )["DESIGN_HANDOFF_APPROVAL_V1"]
    assert approval["status"] == "APPROVED_FOR_IMPLEMENTATION"
    assert approval["implementation_authority"] == "ST0703_RECORDED_SCOPE_ONLY"
    assert approval["approved_decisions"] == list(generator.V5_APPROVED_DECISIONS)
    assert approval["open_decisions"] == []


def test_predecessor_manifest_semantic_projection_baselines_are_current() -> None:
    expected = {
        path.as_posix(): digest
        for path, digest in EXPECTED_PREDECESSOR_MANIFEST_PROJECTION_SHA256.items()
    }

    assert generator.PREDECESSOR_MANIFEST_PROJECTION_SHA256 == (
        EXPECTED_PREDECESSOR_MANIFEST_PROJECTION_SHA256
    )
    assert generator._validate_predecessor_manifest_semantics(REPOSITORY_ROOT) == (
        expected
    )
    for (
        relative,
        expected_digest,
    ) in EXPECTED_PREDECESSOR_MANIFEST_PROJECTION_SHA256.items():
        document = yaml.load(
            (REPOSITORY_ROOT / relative).read_bytes(),
            Loader=generator.UniqueKeyLoader,
        )
        assert isinstance(document, dict)
        assert _manifest_projection_sha256(document) == expected_digest


def test_predecessor_manifest_semantic_outputs_retain_exact_hashes() -> None:
    for relative, (
        artifact_uri,
        expected_digest,
    ) in EXPECTED_PREDECESSOR_SEMANTIC_OUTPUT_SHA256.items():
        document = yaml.load(
            (REPOSITORY_ROOT / relative).read_bytes(),
            Loader=generator.UniqueKeyLoader,
        )
        assert isinstance(document, dict)
        generated_artifacts = document["generated_artifacts"]
        assert isinstance(generated_artifacts, list)
        matches = [
            artifact
            for artifact in generated_artifacts
            if isinstance(artifact, dict) and artifact.get("uri") == artifact_uri
        ]
        assert len(matches) == 1
        assert matches[0]["sha256"] == expected_digest
        artifact_path = Path(artifact_uri.removeprefix("repo://"))
        assert _sha256((REPOSITORY_ROOT / artifact_path).read_bytes()) == (
            expected_digest
        )


@pytest.mark.parametrize(
    ("relative", "expected_digest"),
    tuple(EXPECTED_PREDECESSOR_MANIFEST_PROJECTION_SHA256.items()),
    ids=("st-0204", "st-0701", "st-0801"),
)
def test_predecessor_manifest_guard_allows_only_source_byte_metadata_changes(
    tmp_path: Path,
    relative: Path,
    expected_digest: str,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / relative
    document = yaml.safe_load(path.read_bytes())
    for artifact in document["source_artifacts"]:
        artifact["bytes"] += 1
        artifact["sha256"] = "1" * 64
    _write_yaml_document(path, document)

    observed = generator._validate_predecessor_manifest_semantics(root)

    assert observed[relative.as_posix()] == expected_digest


@pytest.mark.parametrize(
    "relative",
    tuple(EXPECTED_PREDECESSOR_MANIFEST_PROJECTION_SHA256),
    ids=("st-0204", "st-0701", "st-0801"),
)
def test_predecessor_manifest_semantic_tamper_fails_closed(
    tmp_path: Path,
    relative: Path,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / relative
    document = yaml.safe_load(path.read_bytes())
    document["document"]["id"] += "-TAMPERED"
    _write_yaml_document(path, document)

    with pytest.raises(RuntimeError, match="semantic projection drift"):
        generator.check(root)


def test_generation_checks_predecessor_semantics_before_writing(
    tmp_path: Path,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / Path("changes/st-0801/manifest.yaml")
    document = yaml.safe_load(path.read_bytes())
    document["document"]["story_id"] = "ST-0801-TAMPERED"
    _write_yaml_document(path, document)

    with pytest.raises(RuntimeError, match="semantic projection drift"):
        generator.generate(root)

    assert not (root / generator.GENERATED_REGISTRY_PATH).exists()
    assert not (root / generator.MANIFEST_PATH).exists()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("added-key", "must contain exact keys"),
        ("missing-key", "must contain exact keys"),
        ("unnormalized-uri", "normalized POSIX relative path"),
        ("duplicate-uri", "source artifact URI duplicated"),
        ("zero-bytes", "byte count must be a positive integer"),
        ("boolean-bytes", "byte count must be a positive integer"),
        ("uppercase-digest", "digest must be lowercase SHA-256"),
        ("short-digest", "digest must be lowercase SHA-256"),
    ),
)
def test_predecessor_manifest_source_artifact_shape_fails_closed(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / Path("changes/st-0801/manifest.yaml")
    document = yaml.safe_load(path.read_bytes())
    source_artifacts = document["source_artifacts"]
    artifact = source_artifacts[0]

    if mutation == "added-key":
        artifact["unexpected"] = "value"
    elif mutation == "missing-key":
        artifact.pop("sha256")
    elif mutation == "unnormalized-uri":
        artifact["uri"] = "repo://changes/st-0801/../st-0801/README.md"
    elif mutation == "duplicate-uri":
        source_artifacts[1]["uri"] = artifact["uri"]
    elif mutation == "zero-bytes":
        artifact["bytes"] = 0
    elif mutation == "boolean-bytes":
        artifact["bytes"] = True
    elif mutation == "uppercase-digest":
        artifact["sha256"] = artifact["sha256"].upper()
    else:
        artifact["sha256"] = "0" * 63
    _write_yaml_document(path, document)

    with pytest.raises(RuntimeError, match=message):
        generator.check(root)


def test_predecessor_manifest_duplicate_yaml_key_fails_strict_load(
    tmp_path: Path,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / Path("changes/st-0801/manifest.yaml")
    content = path.read_bytes()
    member = b"  bytes: 18563\n  sha256:"
    assert content.count(member) == 1
    path.write_bytes(content.replace(member, b"  bytes: 18563\n  bytes: 1\n  sha256:"))

    with pytest.raises(RuntimeError, match="must be strict YAML"):
        generator.check(root)


def _make_target_block(makefile: str, target: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(target)}:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        makefile,
    )
    assert match is not None
    return match.group(0)


def test_openai_recorded_make_targets_are_exact_and_read_only_after_hydration() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    logical_makefile = makefile.replace("\\\n", " ")
    phony_line = next(
        line for line in logical_makefile.splitlines() if line.startswith(".PHONY:")
    )
    targets = (
        "openai-recorded-generate",
        "openai-recorded-check",
        "openai-recorded-static",
        "openai-recorded-test",
        "openai-recorded-gate",
    )
    for target in targets:
        assert phony_line.split().count(target) == 1
        assert logical_makefile.count(f"\n{target}:") == 1

    generate = _make_target_block(makefile, "openai-recorded-generate")
    assert generate.splitlines()[0] == "openai-recorded-generate: | python-sync"
    assert generate.count("$(UV_RUN) run --locked --no-sync --no-env-file") == 1
    assert "scripts/build_st0703_recorded_adapter.py" in generate
    assert "UV_READONLY_RUN" not in generate

    check = _make_target_block(makefile, "openai-recorded-check")
    assert check.splitlines()[0] == "openai-recorded-check:"
    assert "python-sync" not in check
    assert check.count("$(UV_READONLY_RUN)") == 2
    assert check.count("scripts/build_st0703_recorded_adapter.py --check") == 2
    assert check.count("--check-installed") == 1

    test = _make_target_block(makefile, "openai-recorded-test")
    assert test.splitlines()[0] == "openai-recorded-test:"
    assert "python-sync" not in test
    assert test.count("$(UV_READONLY_RUN)") == 1
    assert "pytest \\\n\t\t-p no:cacheprovider -q tests/st0703" in test

    gate = _make_target_block(makefile, "openai-recorded-gate").rstrip()
    gate_header = gate.splitlines()[0:2]
    logical_gate_header = " ".join(
        line.removesuffix("\\").strip() for line in gate_header
    )
    gate_tokens = logical_gate_header.split()[1:]
    assert gate_tokens == [
        "ai-registry-check",
        "openai-recorded-check",
        "openai-recorded-static",
        "openai-recorded-test",
    ]
    assert gate == (
        "openai-recorded-gate: ai-registry-check openai-recorded-check \\\n"
        "\topenai-recorded-static openai-recorded-test\n"
        "\tPYTHONDONTWRITEBYTECODE=1 $(UV_READONLY_RUN) python \\\n"
        "\t\tscripts/build_st0204_config_loader.py --check"
    )
    assert "config-check" not in logical_gate_header
    assert gate.count("$(UV_READONLY_RUN)") == 1
    assert gate.count("scripts/build_st0204_config_loader.py --check") == 1
    assert "$(UV_RUN)" not in gate
    assert "python-sync" not in gate
    assert "$(MAKE)" not in gate

    config_check = _make_target_block(makefile, "config-check")
    assert config_check.splitlines()[0] == "config-check: | python-sync"
    assert config_check.count("python-sync") == 1
    assert config_check.count("$(UV_READONLY_RUN)") == 1
    assert config_check.count("scripts/build_st0204_config_loader.py --check") == 1


def test_openai_recorded_static_target_has_the_exact_bounded_surface() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    static = _make_target_block(makefile, "openai-recorded-static")
    sources = (
        "python/raos/adapters/__init__.py",
        "python/raos/adapters/openai_responses.py",
        "python/raos/adapters/recorded_ai.py",
        "python/raos/domain/ai/provider.py",
        "python/raos/ports/ai_provider.py",
        "scripts/build_st0703_recorded_adapter.py",
        "tests/st0703",
    )

    assert static.splitlines()[0] == "openai-recorded-static:"
    assert "python-sync" not in static
    assert static.count("$(UV_READONLY_RUN)") == 3
    assert "ruff check --no-cache" in static
    assert "ruff format --check --no-cache" in static
    assert "mypy --strict --explicit-package-bases --cache-dir=/dev/null" in static
    assert (
        'MYPYPATH="$(RAOS_REPOSITORY_ROOT)/python:'
        '$(RAOS_REPOSITORY_ROOT)/tests/st0703"' in static
    )
    for source in sources:
        expected_count = 4 if source == "tests/st0703" else 3
        assert static.count(source) == expected_count


def test_openai_recorded_base_ci_wiring_stays_in_existing_denied_jobs() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    logical_makefile = makefile.replace("\\\n", " ")
    joined_policy_header = next(
        line
        for line in logical_makefile.splitlines()
        if line.startswith("ci-repository-policy:")
    )
    assert joined_policy_header.count("openai-recorded-check") == 1
    assert "openai-recorded-static" not in joined_policy_header
    assert "openai-recorded-test" not in joined_policy_header
    assert "openai-recorded-gate" not in joined_policy_header

    unit = _make_target_block(makefile, "ci-unit")
    assert unit.count("tests/st0703") == 1
    assert unit.index("tests/st0701") < unit.index("tests/st0703")
    assert unit.index("tests/st0703") < unit.index("tests/st0801")

    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_bytes()
    assert b"openai-recorded" not in workflow
    assert b"OPENAI_API_KEY" not in workflow
    assert _sha256(workflow) == (
        "80c98463465df12a4fc8106eba2bd29c43267b8839346a225166c24387945c45"
    )


@pytest.mark.parametrize(
    ("relative", "message"),
    (
        (generator.PYPROJECT_PATH, "pyproject"),
        (generator.UV_LOCK_PATH, "uv.lock"),
        (generator.UV_CONFIG_PATH, "uv configuration"),
    ),
)
def test_dependency_inputs_reject_symlinks(
    tmp_path: Path,
    relative: Path,
    message: str,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / relative
    path.unlink()
    path.symlink_to(root / generator.CONTRACT_PATH)

    with pytest.raises(RuntimeError, match=message):
        generator.check(root)


@pytest.mark.parametrize(
    ("relative", "message"),
    (
        (generator.PYPROJECT_PATH, "pyproject hash drift"),
        (generator.UV_LOCK_PATH, r"uv\.lock hash drift"),
        (generator.UV_CONFIG_PATH, "uv configuration hash drift"),
    ),
)
def test_dependency_input_raw_hash_drift_fails_closed(
    tmp_path: Path,
    relative: Path,
    message: str,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / relative
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(RuntimeError, match=message):
        generator.check(root)


def test_missing_fixture_fails_closed_in_a_disposable_copy(tmp_path: Path) -> None:
    root = _copy_inputs(tmp_path)
    missing = root / generator.FIXTURE_ROOT / "success-structured.json"
    missing.unlink()

    with pytest.raises(RuntimeError, match=r"inventory mismatch: missing=\["):
        generator.check(root)


def test_extra_fixture_fails_closed_in_a_disposable_copy(tmp_path: Path) -> None:
    root = _copy_inputs(tmp_path)
    extra = root / generator.FIXTURE_ROOT / "unexpected.json"
    extra.write_text("{}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match=r"inventory mismatch: .*extra=\["):
        generator.check(root)


def test_one_byte_fixture_tamper_fails_closed(tmp_path: Path) -> None:
    root = _copy_inputs(tmp_path)
    target = root / generator.FIXTURE_ROOT / "success-structured.json"
    original = target.read_bytes()
    tampered = bytearray(original)
    offset = tampered.index(b"SYNTHETIC_TEST_ONLY")
    tampered[offset] = ord("X")
    target.write_bytes(tampered)

    assert len(tampered) == len(original)
    assert (
        sum(left != right for left, right in zip(original, tampered, strict=True)) == 1
    )
    with pytest.raises(RuntimeError, match="fixture raw-byte drift"):
        generator.check(root)


def test_fixture_symlink_is_rejected(tmp_path: Path) -> None:
    root = _copy_inputs(tmp_path)
    target = root / generator.FIXTURE_ROOT / "success-structured.json"
    target.unlink()
    target.symlink_to("refusal-completed.json")

    with pytest.raises(RuntimeError, match="only regular files"):
        generator.check(root)


def test_contract_hash_drift_fails_before_parsing(tmp_path: Path) -> None:
    root = _copy_inputs(tmp_path)
    path = root / generator.CONTRACT_PATH
    path.write_bytes(path.read_bytes() + b"\n# drift\n")

    with pytest.raises(RuntimeError, match="contract hash drift"):
        generator.check(root)


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (b'"openai==2.52.0",', b'"openai==2.51.0",'),
        (b'  "openai==2.52.0",\n', b""),
        (
            b'  "openai==2.52.0",\n',
            b'  "openai==2.52.0",\n  "openai==2.52.0",\n',
        ),
    ),
)
def test_pyproject_requires_one_exact_openai_direct_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    old: bytes,
    new: bytes,
) -> None:
    root = _copy_inputs(tmp_path)
    _replace_and_repin_input(
        root,
        monkeypatch,
        generator.PYPROJECT_PATH,
        "EXPECTED_PYPROJECT_SHA256",
        old,
        new,
    )

    with pytest.raises(RuntimeError, match="pyproject OpenAI dependency drift"):
        generator.check(root)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    (
        (b'version = "2.52.0"', b'version = "2.51.0"', "OpenAI package"),
        (
            b'name = "openai"\nversion = "2.52.0"\n'
            b'source = { registry = "https://pypi.org/simple" }',
            b'name = "openai"\nversion = "2.52.0"\n'
            b'source = { registry = "https://example.invalid/simple" }',
            "OpenAI package",
        ),
        (
            b"sha256:7c736d592f81471ce1f734838390983c4d8c8aecff23dcd36e600a58e5032d9c",
            b"sha256:0000000000000000000000000000000000000000000000000000000000000000",
            "OpenAI package",
        ),
        (
            b"sha256:f97e231d9a8fa69ab55897df1080f02d99913fb0a30e3ee56ea16a1eb6c2d434",
            b"sha256:1111111111111111111111111111111111111111111111111111111111111111",
            "OpenAI package",
        ),
        (
            b"openai-2.52.0.tar.gz",
            b"openai-2.51.0.tar.gz",
            "OpenAI package",
        ),
        (
            b"openai-2.52.0-py3-none-any.whl",
            b"openai-2.51.0-py3-none-any.whl",
            "OpenAI package",
        ),
        (b"size = 1098876", b"size = 1098877", "OpenAI package"),
        (b"size = 1659569", b"size = 1659570", "OpenAI package"),
        (
            b'upload-time = "2026-07-31T15:13:03.228Z"',
            b'upload-time = "2026-07-31T15:13:04.228Z"',
            "OpenAI package",
        ),
        (
            b'upload-time = "2026-07-31T15:13:01.145Z"',
            b'upload-time = "2026-07-31T15:13:02.145Z"',
            "OpenAI package",
        ),
        (
            b'exclude-newer = "2026-08-01T16:50:16Z"',
            b'exclude-newer = "2026-08-02T16:50:16Z"',
            "root metadata",
        ),
        (
            b'{ name = "openai", specifier = "==2.52.0" }',
            b'{ name = "openai", specifier = "==2.51.0" }',
            "root metadata",
        ),
        (
            b'    { name = "openai" },\n    { name = "psycopg",',
            b'    { name = "psycopg",',
            "root metadata",
        ),
    ),
)
def test_uv_lock_openai_artifact_and_root_metadata_drift_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    old: bytes,
    new: bytes,
    message: str,
) -> None:
    root = _copy_inputs(tmp_path)
    _replace_and_repin_input(
        root,
        monkeypatch,
        generator.UV_LOCK_PATH,
        "EXPECTED_UV_LOCK_SHA256",
        old,
        new,
    )

    with pytest.raises(RuntimeError, match=message):
        generator.check(root)


def test_uv_lock_rejects_a_duplicate_openai_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / generator.UV_LOCK_PATH
    content = path.read_bytes() + (
        b'\n[[package]]\nname = "openai"\nversion = "2.52.0"\n'
        b'source = { registry = "https://pypi.org/simple" }\n'
    )
    path.write_bytes(content)
    monkeypatch.setattr(generator, "EXPECTED_UV_LOCK_SHA256", _sha256(content))

    with pytest.raises(RuntimeError, match="OpenAI package drift"):
        generator.check(root)


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (b'required-version = "==0.12.1"', b'required-version = "==0.12.0"'),
        (
            b'exclude-newer = "2026-08-01T16:50:16Z"',
            b'exclude-newer = "2026-08-02T16:50:16Z"',
        ),
        (b"no-sources = true", b"no-sources = false"),
        (b'index-strategy = "first-index"', b'index-strategy = "unsafe-best-match"'),
        (b'keyring-provider = "disabled"', b'keyring-provider = "subprocess"'),
        (b'url = "https://pypi.org/simple"', b'url = "https://example.invalid/simple"'),
    ),
)
def test_uv_configuration_cutoff_index_and_safety_drift_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    old: bytes,
    new: bytes,
) -> None:
    root = _copy_inputs(tmp_path)
    _replace_and_repin_input(
        root,
        monkeypatch,
        generator.UV_CONFIG_PATH,
        "EXPECTED_UV_CONFIG_SHA256",
        old,
        new,
    )

    with pytest.raises(RuntimeError, match="uv configuration drift"):
        generator.check(root)


def test_contract_sdk_release_metadata_is_bound_to_locked_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_inputs(tmp_path)
    _replace_and_repin_input(
        root,
        monkeypatch,
        generator.CONTRACT_PATH,
        "EXPECTED_CONTRACT_SHA256",
        b"wheel_sha256: f97e231d9a8fa69ab55897df1080f02d99913fb0a30e3ee56ea16a1eb6c2d434",
        b"wheel_sha256: 0000000000000000000000000000000000000000000000000000000000000000",
    )

    with pytest.raises(RuntimeError, match="SDK dependency binding drift"):
        generator.check(root)


def test_contract_repository_cutoff_is_bound_to_uv_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_inputs(tmp_path)
    _replace_and_repin_input(
        root,
        monkeypatch,
        generator.CONTRACT_PATH,
        "EXPECTED_CONTRACT_SHA256",
        b'repository_cutoff: "2026-08-01T16:50:16Z"',
        b'repository_cutoff: "2026-08-02T16:50:16Z"',
    )

    with pytest.raises(RuntimeError, match="SDK dependency binding drift"):
        generator.check(root)


def test_contract_provenance_source_hash_drift_fails_closed(tmp_path: Path) -> None:
    root = _copy_inputs(tmp_path)
    relative = Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md")
    path = root / relative
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(RuntimeError, match="provenance source hash drift"):
        generator.check(root)


def test_contract_provenance_source_symlink_is_rejected(tmp_path: Path) -> None:
    root = _copy_inputs(tmp_path)
    relative = Path("docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md")
    path = root / relative
    path.unlink()
    path.symlink_to(root / generator.PYPROJECT_PATH)

    with pytest.raises(RuntimeError, match="provenance source.*regular file"):
        generator.check(root)


def test_contract_provenance_source_ancestor_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    root = _copy_inputs(tmp_path)
    ancestor = root / "docs/canonical/01_integration"
    real_ancestor = ancestor.with_name("01_integration-real")
    ancestor.rename(real_ancestor)
    ancestor.symlink_to(real_ancestor.name, target_is_directory=True)

    with pytest.raises(RuntimeError, match="provenance source ancestor"):
        generator.check(root)


def test_contract_provenance_rejects_escaping_repo_uri(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_inputs(tmp_path)
    _replace_and_repin_input(
        root,
        monkeypatch,
        generator.CONTRACT_PATH,
        "EXPECTED_CONTRACT_SHA256",
        b"repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        b"repo://../RAOS_07_integration_design_v1.0.md",
    )

    with pytest.raises(RuntimeError, match="normalized POSIX relative path"):
        generator.check(root)


def test_contract_provenance_rejects_duplicate_repo_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_inputs(tmp_path)
    _replace_and_repin_input(
        root,
        monkeypatch,
        generator.CONTRACT_PATH,
        "EXPECTED_CONTRACT_SHA256",
        b"repo://docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
        b"repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
    )

    with pytest.raises(RuntimeError, match="provenance path duplicated"):
        generator.check(root)


@pytest.mark.parametrize(
    "replacement",
    (
        b'"\\u0061uthorization": "SYNTHETIC_TEST_ONLY input record."',
        b'"content": "s\\u006b-synthetic-placeholder"',
        b'"HeAdEr": "SYNTHETIC_TEST_ONLY input record."',
        b'"ClIeNt_SeCrEt": "placeholder"',
        b'"content": "BeArEr synthetic-placeholder"',
        b'"content": "CrEdEnTiAl synthetic-placeholder"',
        b'"content": "-----BEGIN PrIvAtE KeY-----"',
        b'"Api_Key": "placeholder"',
        b'"content": "AcCeSs_ToKeN synthetic-placeholder"',
        b'"content": "PaSsWoRd synthetic-placeholder"',
        b'"SeT-CoOkIe": "synthetic-placeholder"',
    ),
)
def test_decoded_audit_rejects_escaped_or_mixed_case_keys_and_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: bytes,
) -> None:
    root = _copy_inputs(tmp_path)
    mutated = _replace_nested_request_member(monkeypatch, root, replacement)

    assert not any(
        marker in mutated.lower() for marker in generator.FORBIDDEN_FIXTURE_MARKERS
    )
    with pytest.raises(RuntimeError, match="forbidden decoded material"):
        generator.check(root)


@pytest.mark.parametrize(
    "replacement",
    (
        b'"content": "https:\\/\\/example.invalid/live"',
        b'"content": "note https:\\/\\/example.invalid/live"',
        b'"content": "http:\\/\\/example.invalid/live"',
        b'"content": "synthetic://user@example.invalid/path"',
        b'"content": "urn:raos:synthetic:test?query=forbidden"',
        b'"content": "urn:raos:synthetic:test#fragment"',
    ),
)
def test_decoded_uri_audit_rejects_network_and_sensitive_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: bytes,
) -> None:
    root = _copy_inputs(tmp_path)
    mutated = _replace_nested_request_member(monkeypatch, root, replacement)

    assert not any(
        marker in mutated.lower() for marker in generator.FORBIDDEN_FIXTURE_MARKERS
    )
    with pytest.raises(RuntimeError, match="forbidden URI material"):
        generator.check(root)


def test_current_schema_urn_remains_allowed() -> None:
    generator._validate_decoded_fixture_material(
        {"schema": {"$id": "urn:raos:synthetic:st0703:output:v1"}},
        label="synthetic fixture",
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "added-key",
        "missing-key",
        "model",
        "content",
        "role",
        "schema",
        "schema-added-key",
        "schema-missing-key",
        "name",
        "effort",
        "tokens",
        "token-type",
        "store",
        "tool",
    ),
)
def test_expected_request_requires_the_exact_canonical_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    root = _copy_inputs(tmp_path)
    filename = "success-structured.json"
    path = root / generator.FIXTURE_ROOT / filename
    document = json.loads(path.read_bytes())
    request = document["expected_request"]
    output_format = request["text"]["format"]
    schema = output_format["schema"]

    if mutation == "added-key":
        request["unexpected"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "missing-key":
        request.pop("tools")
    elif mutation == "model":
        request["model"] = "raos-other-synthetic-model"
    elif mutation == "content":
        request["input"][1]["content"] = "SYNTHETIC_TEST_ONLY changed input."
    elif mutation == "role":
        request["input"][1]["role"] = "assistant"
    elif mutation == "schema":
        schema["properties"]["score"]["type"] = "number"
    elif mutation == "schema-added-key":
        schema["description"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "schema-missing-key":
        schema.pop("required")
    elif mutation == "name":
        output_format["name"] = "raos_other_output_v1"
    elif mutation == "effort":
        request["reasoning"]["effort"] = "low"
    elif mutation == "tokens":
        request["max_output_tokens"] = 127
    elif mutation == "token-type":
        request["max_output_tokens"] = 128.0
    elif mutation == "store":
        request["store"] = True
    else:
        request["tools"] = [{"name": "synthetic_tool", "type": "function"}]

    mutated = (
        json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode("utf-8")
    path.write_bytes(mutated)
    _repin_fixture(monkeypatch, filename, mutated)

    with pytest.raises(RuntimeError, match="expected request drift"):
        generator.check(root)


@pytest.mark.parametrize(
    ("filename", "mutation"),
    (
        ("success-structured.json", "added-key"),
        ("refusal-completed.json", "missing-key"),
        ("success-structured.json", "usage-token"),
        ("refusal-completed.json", "usage-token"),
        ("incomplete-max-output-tokens.json", "usage-token"),
        ("incomplete-content-filter.json", "usage-token"),
        ("success-structured.json", "cached-over-input"),
        ("success-structured.json", "output"),
        ("refusal-completed.json", "refusal-code"),
        ("incomplete-max-output-tokens.json", "incomplete-reason"),
        ("incomplete-content-filter.json", "incomplete-reason"),
        ("error-rate-limit-429.json", "error-code"),
        ("error-rate-limit-429.json", "retryable"),
        ("success-structured.json", "recorder-calls"),
        ("error-rate-limit-429.json", "recorder-calls"),
        ("success-structured.json", "recorder-bool"),
        ("error-rate-limit-429.json", "retryable-int"),
        ("error-rate-limit-429.json", "null-output"),
        ("error-rate-limit-429.json", "null-usage"),
    ),
)
def test_expected_result_requires_the_exact_scenario_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    mutation: str,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / generator.FIXTURE_ROOT / filename
    document = json.loads(path.read_bytes())
    expected = document["expected"]

    if mutation == "added-key":
        expected["unexpected"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "missing-key":
        expected.pop("usage")
    elif mutation == "usage-token":
        expected["usage"]["output_tokens"] += 1
    elif mutation == "cached-over-input":
        expected["usage"]["cached_input_tokens"] = expected["usage"]["input_tokens"] + 1
    elif mutation == "output":
        expected["output"] = {"label": "synthetic-fail", "score": 7}
    elif mutation == "refusal-code":
        expected["refusal_code"] = "AI-PRV-999"
    elif mutation == "incomplete-reason":
        expected["incomplete_reason"] = "other"
    elif mutation == "error-code":
        expected["provider_error_code"] = "OTHER"
    elif mutation == "retryable":
        expected["retryable"] = False
    elif mutation == "recorder-calls":
        expected["recorder_calls"] = 2
    elif mutation == "recorder-bool":
        expected["recorder_calls"] = True
    elif mutation == "retryable-int":
        expected["retryable"] = 1
    elif mutation == "null-output":
        expected["output"] = {}
    else:
        expected["usage"] = {
            "cached_input_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    mutated = (
        json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode("utf-8")
    path.write_bytes(mutated)
    _repin_fixture(monkeypatch, filename, mutated)

    with pytest.raises(RuntimeError, match="expected result drift"):
        generator.check(root)


@pytest.mark.parametrize(
    "mutation",
    (
        "transport-added-key",
        "transport-missing-key",
        "kind",
        "status-code",
        "body-shape",
        "body-added-key",
        "body-missing-key",
        "model",
        "store",
        "tools",
        "max-output-tokens",
        "reasoning",
        "reasoning-added-key",
        "response-object",
        "response-id",
        "created-at",
        "completed-at",
        "response-status",
        "text-format",
    ),
)
def test_completed_response_transport_requires_exact_request_bound_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    root = _copy_inputs(tmp_path)
    filename = "success-structured.json"
    path = root / generator.FIXTURE_ROOT / filename
    document = json.loads(path.read_bytes())
    transport = document["transport"]
    body = transport["body"]

    if mutation == "transport-added-key":
        transport["unexpected"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "transport-missing-key":
        transport.pop("kind")
    elif mutation == "kind":
        transport["kind"] = "recorded_response"
    elif mutation == "status-code":
        transport["status_code"] = 201
    elif mutation == "body-shape":
        transport["body"] = []
    elif mutation == "body-added-key":
        body["unexpected"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "body-missing-key":
        body.pop("background")
    elif mutation == "model":
        body["model"] = "raos-other-synthetic-model"
    elif mutation == "store":
        body["store"] = True
    elif mutation == "tools":
        body["tools"] = [{"type": "function"}]
    elif mutation == "max-output-tokens":
        body["max_output_tokens"] = 127
    elif mutation == "reasoning":
        body["reasoning"]["effort"] = "low"
    elif mutation == "reasoning-added-key":
        body["reasoning"]["unexpected"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "response-object":
        body["object"] = "other"
    elif mutation == "response-id":
        body["id"] = "resp_synthetic_other_001"
    elif mutation == "created-at":
        body["created_at"] += 1
    elif mutation == "completed-at":
        body["completed_at"] += 1
    elif mutation == "response-status":
        body["status"] = "incomplete"
    else:
        body["text"]["format"]["name"] = "raos_other_output_v1"

    _write_fixture_document(root, monkeypatch, filename, document)
    with pytest.raises(RuntimeError, match="transport"):
        generator.check(root)


@pytest.mark.parametrize(
    "mutation",
    (
        "usage-added-key",
        "usage-missing-key",
        "input-details-added-key",
        "input-details-missing-key",
        "output-details-added-key",
        "input-bool",
        "output-bool",
        "cached-bool",
        "cache-write-bool",
        "reasoning-bool",
        "total-bool",
        "negative-token",
        "cache-write-token",
        "cached-over-input",
        "total-mismatch",
        "input-binding",
        "output-binding",
        "reasoning-binding",
    ),
)
def test_response_usage_requires_integer_invariants_and_expected_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    root = _copy_inputs(tmp_path)
    filename = "success-structured.json"
    path = root / generator.FIXTURE_ROOT / filename
    document = json.loads(path.read_bytes())
    usage = document["transport"]["body"]["usage"]
    input_details = usage["input_tokens_details"]
    output_details = usage["output_tokens_details"]

    if mutation == "usage-added-key":
        usage["unexpected"] = 0
    elif mutation == "usage-missing-key":
        usage.pop("total_tokens")
    elif mutation == "input-details-added-key":
        input_details["unexpected"] = 0
    elif mutation == "input-details-missing-key":
        input_details.pop("cache_write_tokens")
    elif mutation == "output-details-added-key":
        output_details["unexpected"] = 0
    elif mutation == "input-bool":
        usage["input_tokens"] = True
    elif mutation == "output-bool":
        usage["output_tokens"] = True
    elif mutation == "cached-bool":
        input_details["cached_tokens"] = False
    elif mutation == "cache-write-bool":
        input_details["cache_write_tokens"] = False
    elif mutation == "reasoning-bool":
        output_details["reasoning_tokens"] = False
    elif mutation == "total-bool":
        usage["total_tokens"] = True
    elif mutation == "negative-token":
        usage["input_tokens"] = -1
    elif mutation == "cache-write-token":
        input_details["cache_write_tokens"] = 1
    elif mutation == "cached-over-input":
        input_details["cached_tokens"] = usage["input_tokens"] + 1
    elif mutation == "total-mismatch":
        usage["total_tokens"] += 1
    elif mutation == "input-binding":
        usage["input_tokens"] += 1
        usage["total_tokens"] += 1
    elif mutation == "output-binding":
        usage["output_tokens"] += 1
        usage["total_tokens"] += 1
    else:
        output_details["reasoning_tokens"] = 1

    _write_fixture_document(root, monkeypatch, filename, document)
    with pytest.raises(RuntimeError, match="usage"):
        generator.check(root)


@pytest.mark.parametrize(
    ("filename", "mutation"),
    (
        ("success-structured.json", "invalid-json"),
        ("success-structured.json", "duplicate-json-key"),
        ("success-structured.json", "nonobject-json"),
        ("success-structured.json", "nonfinite-json"),
        ("success-structured.json", "wrong-json-output"),
        ("success-structured.json", "extra-json-output"),
        ("success-structured.json", "message-id"),
        ("success-structured.json", "message-role"),
        ("success-structured.json", "message-status"),
        ("success-structured.json", "message-added-key"),
        ("success-structured.json", "empty-output"),
        ("success-structured.json", "duplicate-message"),
        ("success-structured.json", "tool-item"),
        ("success-structured.json", "reasoning-item"),
        ("success-structured.json", "mixed-output-items"),
        ("success-structured.json", "unknown-content"),
        ("success-structured.json", "mixed-content"),
        ("success-structured.json", "content-added-key"),
        ("success-structured.json", "duplicate-content"),
        ("refusal-completed.json", "wrong-refusal"),
        ("refusal-completed.json", "refusal-output-text"),
        ("refusal-completed.json", "mixed-content"),
        ("refusal-completed.json", "empty-content"),
        ("refusal-completed.json", "duplicate-content"),
        ("incomplete-max-output-tokens.json", "response-status"),
        ("incomplete-max-output-tokens.json", "message-status"),
        ("incomplete-max-output-tokens.json", "incomplete-reason"),
        ("incomplete-content-filter.json", "incomplete-reason"),
        ("incomplete-max-output-tokens.json", "partial-full-json"),
        ("incomplete-content-filter.json", "partial-full-json"),
    ),
)
def test_response_output_rejects_unknown_mixed_empty_or_duplicate_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    mutation: str,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / generator.FIXTURE_ROOT / filename
    document = json.loads(path.read_bytes())
    body = document["transport"]["body"]
    output = body["output"]
    message = output[0]
    content = message["content"]

    if mutation == "invalid-json":
        content[0]["text"] = "{invalid"
    elif mutation == "duplicate-json-key":
        content[0]["text"] = '{"label":"synthetic-pass","score":7,"score":7}'
    elif mutation == "nonobject-json":
        content[0]["text"] = '["synthetic-pass",7]'
    elif mutation == "nonfinite-json":
        content[0]["text"] = '{"label":"synthetic-pass","score":NaN}'
    elif mutation == "wrong-json-output":
        content[0]["text"] = '{"label":"synthetic-fail","score":7}'
    elif mutation == "extra-json-output":
        content[0]["text"] = '{"extra":0,"label":"synthetic-pass","score":7}'
    elif mutation == "message-id":
        message["id"] = "msg_synthetic_other_001"
    elif mutation == "message-role":
        message["role"] = "developer"
    elif mutation == "message-status":
        message["status"] = (
            "completed" if message["status"] == "incomplete" else "incomplete"
        )
    elif mutation == "message-added-key":
        message["unexpected"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "empty-output":
        body["output"] = []
    elif mutation == "duplicate-message":
        output.append(copy.deepcopy(message))
    elif mutation == "tool-item":
        body["output"] = [{"id": "call_synthetic_001", "type": "function_call"}]
    elif mutation == "reasoning-item":
        body["output"] = [{"id": "rs_synthetic_001", "type": "reasoning"}]
    elif mutation == "mixed-output-items":
        output.append({"id": "call_synthetic_001", "type": "function_call"})
    elif mutation == "unknown-content":
        content[0]["type"] = "unknown"
    elif mutation == "mixed-content":
        content.append(
            {"refusal": "SYNTHETIC_TEST_ONLY refusal marker.", "type": "refusal"}
        )
    elif mutation == "content-added-key":
        content[0]["unexpected"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "duplicate-content":
        content.append(copy.deepcopy(content[0]))
    elif mutation == "wrong-refusal":
        content[0]["refusal"] = "SYNTHETIC_TEST_ONLY changed refusal."
    elif mutation == "refusal-output-text":
        content[0] = {
            "annotations": [],
            "logprobs": [],
            "text": '{"label":"synthetic-pass","score":7}',
            "type": "output_text",
        }
    elif mutation == "empty-content":
        message["content"] = []
    elif mutation == "response-status":
        body["status"] = "completed"
    elif mutation == "incomplete-reason":
        body["incomplete_details"]["reason"] = "other"
    else:
        content[0]["text"] = '{"label":"synthetic-pass","score":7}'

    _write_fixture_document(root, monkeypatch, filename, document)
    with pytest.raises(RuntimeError, match="(?:output|transport)"):
        generator.check(root)


@pytest.mark.parametrize(
    "mutation",
    (
        "transport-status",
        "body-added-key",
        "body-missing-key",
        "error-added-key",
        "error-missing-key",
        "code",
        "type",
        "message",
        "param",
    ),
)
def test_rate_limit_transport_requires_the_exact_error_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    root = _copy_inputs(tmp_path)
    filename = "error-rate-limit-429.json"
    path = root / generator.FIXTURE_ROOT / filename
    document = json.loads(path.read_bytes())
    transport = document["transport"]
    body = transport["body"]
    error = body["error"]

    if mutation == "transport-status":
        transport["status_code"] = 500
    elif mutation == "body-added-key":
        body["unexpected"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "body-missing-key":
        body.pop("error")
    elif mutation == "error-added-key":
        error["unexpected"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "error-missing-key":
        error.pop("param")
    elif mutation == "code":
        error["code"] = "other"
    elif mutation == "type":
        error["type"] = "other_error"
    elif mutation == "message":
        error["message"] = "SYNTHETIC_TEST_ONLY changed diagnostic."
    else:
        error["param"] = "synthetic"

    _write_fixture_document(root, monkeypatch, filename, document)
    with pytest.raises(RuntimeError, match="(?:error|transport)"):
        generator.check(root)


@pytest.mark.parametrize(
    ("filename", "mutation"),
    (
        ("success-structured.json", "added-key"),
        ("success-structured.json", "missing-key"),
        ("success-structured.json", "production-mode"),
        ("success-structured.json", "model"),
        ("success-structured.json", "quote"),
        ("success-structured.json", "negative-cost"),
        ("success-structured.json", "bool-cost"),
        ("success-structured.json", "float-cost"),
        ("success-structured.json", "wrong-cost"),
        ("success-structured.json", "null-cost"),
        ("success-structured.json", "refusal-cost-swap"),
        ("refusal-completed.json", "success-cost-swap"),
        ("incomplete-max-output-tokens.json", "filter-cost-swap"),
        ("incomplete-content-filter.json", "max-cost-swap"),
        ("error-rate-limit-429.json", "error-mode"),
        ("error-rate-limit-429.json", "model"),
        ("error-rate-limit-429.json", "quote"),
        ("error-rate-limit-429.json", "error-cost"),
    ),
)
def test_synthetic_pricing_requires_exact_scenario_and_request_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    mutation: str,
) -> None:
    root = _copy_inputs(tmp_path)
    path = root / generator.FIXTURE_ROOT / filename
    document = json.loads(path.read_bytes())
    pricing = document["pricing"]

    if mutation == "added-key":
        pricing["unexpected"] = "SYNTHETIC_TEST_ONLY"
    elif mutation == "missing-key":
        pricing.pop("quote_id")
    elif mutation == "production-mode":
        pricing["mode"] = "PRODUCTION"
    elif mutation == "model":
        pricing["model_id"] = "raos-other-synthetic-model"
    elif mutation == "quote":
        pricing["quote_id"] = "st0703-other-synthetic-quote"
    elif mutation == "negative-cost":
        pricing["expected_cost_jpy"] = -1
    elif mutation == "bool-cost":
        pricing["expected_cost_jpy"] = True
    elif mutation == "float-cost":
        pricing["expected_cost_jpy"] = 7.0
    elif mutation == "wrong-cost":
        pricing["expected_cost_jpy"] = 8
    elif mutation == "null-cost":
        pricing["expected_cost_jpy"] = None
    elif mutation == "refusal-cost-swap":
        pricing["expected_cost_jpy"] = 3
    elif mutation == "success-cost-swap":
        pricing["expected_cost_jpy"] = 7
    elif mutation == "filter-cost-swap":
        pricing["expected_cost_jpy"] = 5
    elif mutation == "max-cost-swap":
        pricing["expected_cost_jpy"] = 11
    elif mutation == "error-mode":
        pricing["mode"] = "SYNTHETIC_TEST_ONLY"
    else:
        pricing["expected_cost_jpy"] = 0

    _write_fixture_document(root, monkeypatch, filename, document)
    with pytest.raises(RuntimeError, match="pricing"):
        generator.check(root)


def test_openai_252_pin_and_distribution_hashes_are_consistent() -> None:
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    lock = tomllib.loads((REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8"))
    contract = yaml.safe_load(CONTRACT_PATH.read_bytes())

    dependencies = pyproject["project"]["dependencies"]
    assert [item for item in dependencies if item.startswith("openai")] == [
        "openai==2.52.0"
    ]

    openai_packages = [item for item in lock["package"] if item["name"] == "openai"]
    assert len(openai_packages) == 1
    openai_package = openai_packages[0]
    assert openai_package["version"] == "2.52.0"
    assert openai_package["source"] == {"registry": "https://pypi.org/simple"}
    assert openai_package["sdist"] == {
        "url": "https://files.pythonhosted.org/packages/bb/5a/"
        "c45fa035cd72c70ebe67c6e079e3adf871492382634f69e3dff62c43597d/"
        "openai-2.52.0.tar.gz",
        "hash": f"sha256:{EXPECTED_SDIST_SHA256}",
        "size": 1098876,
        "upload-time": "2026-07-31T15:13:03.228Z",
    }
    assert openai_package["wheels"] == [
        {
            "url": "https://files.pythonhosted.org/packages/a1/ac/"
            "ceb40c995df49533ad4dcff6c37f0d85cf14446a212363fc9d2f927e60b4/"
            "openai-2.52.0-py3-none-any.whl",
            "hash": f"sha256:{EXPECTED_WHEEL_SHA256}",
            "size": 1659569,
            "upload-time": "2026-07-31T15:13:01.145Z",
        }
    ]

    root_package = next(item for item in lock["package"] if item["name"] == "raos")
    locked_requirement = next(
        item
        for item in root_package["metadata"]["requires-dist"]
        if item["name"] == "openai"
    )
    assert locked_requirement == {"name": "openai", "specifier": "==2.52.0"}

    sdk = contract["official_sdk"]
    assert sdk["version"] == "2.52.0"
    assert sdk["exact_requirement"] == "openai==2.52.0"
    assert sdk["release_metadata"]["wheel_sha256"] == EXPECTED_WHEEL_SHA256
    assert sdk["release_metadata"]["sdist_sha256"] == EXPECTED_SDIST_SHA256
