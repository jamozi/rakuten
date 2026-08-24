"""Owner-generation and provenance checks for ST-1302 recorded V2."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat

import pytest
import yaml

from scripts import build_st1302_provider_fact_commit_recorded as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _isolated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    required = {
        *generator.SOURCE_PATHS,
        generator.HELPER_PATH,
        *(path for _name, path, _digest in generator.SOURCE_BINDINGS),
    }
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return root


def test_contract_and_projection_are_exact_and_preserve_unresolved_boundaries() -> None:
    contract = generator.load_contract()
    assert tuple(contract) == generator.CONTRACT_KEYS
    projection = generator.projection()
    assert projection["open_decision_boundary"] == generator.EXPECTED_OPEN_DECISION
    assert projection["preview_binding"] == generator.EXPECTED_PREVIEW_BINDING
    assert projection["vocabulary_boundary"] == generator.EXPECTED_VOCABULARY
    assert projection["authority_boundary"] == generator.EXPECTED_AUTHORITY
    recorded = projection["recorded_result"]
    assert recorded["result_sha256"] == (
        "882a330bdc6485d424d55033c0cddbe1748b8b4b3b0751ddf3e4682ef574f7d0"
    )
    assert recorded["canonical_commission_event_types"] == [None, None]
    assert recorded["generated_commission_jpy"] == "200"
    assert recorded["confirmed_commission_jpy"] == "80"
    assert recorded["confirmed_missing_count"] == 1


def test_render_is_deterministic_and_matches_installed_outputs() -> None:
    first = generator.render_outputs()
    assert first == generator.render_outputs()
    for relative, content in first.items():
        assert (REPOSITORY_ROOT / relative).read_bytes() == content


def test_check_mode_is_no_write_and_accepts_exact_outputs() -> None:
    paths = [REPOSITORY_ROOT / relative for relative in generator.GENERATED_PATHS]
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }
    generator.build(check=True)
    after = {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }
    assert before == after
    assert generator.main(["--check"]) == 0


def test_manifest_binds_every_owned_source_and_generated_projection() -> None:
    manifest = yaml.safe_load((REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes())
    plan = (REPOSITORY_ROOT / generator.PLAN_PATH).read_bytes()
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.PLAN_PATH.as_posix()}",
            "bytes": len(plan),
            "sha256": generator._sha256(plan),
        }
    ]
    assert manifest["external_authority"] is False
    assert set(manifest["boundary"].values()) >= {
        "EXTERNAL_EVIDENCE_REQUIRED",
        "NOT_ASSERTED",
        False,
        "NOT_EXECUTED",
    }


def test_isolated_generation_is_atomic_mode_0644_and_checkable(
    tmp_path: Path,
) -> None:
    root = _isolated_repository(tmp_path)
    generator.build(root)
    for relative in generator.GENERATED_PATHS:
        target = root / relative
        assert target.is_file()
        assert not target.is_symlink()
        assert stat.S_IMODE(target.stat().st_mode) == 0o644
        assert not tuple(target.parent.glob(f".{target.name}.*.tmp"))
    generator.build(root, check=True)


def test_bound_input_drift_and_generated_output_drift_are_rejected(
    tmp_path: Path,
) -> None:
    root = _isolated_repository(tmp_path)
    generator.build(root)
    source = root / generator.SOURCE_BINDINGS[0][1]
    source.write_bytes(source.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.ProviderFactRecordedBuildError):
        generator.render_outputs(root)
    root = _isolated_repository(tmp_path / "second")
    generator.build(root)
    output = root / generator.PLAN_PATH
    output.write_bytes(output.read_bytes() + b"drift")
    with pytest.raises(generator.ProviderFactRecordedBuildError):
        generator.build(root, check=True)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "production_eligible", True),
        ("open_decision_boundary", "resolved", True),
        ("preview_binding", "canonical_preview_hash_equivalence", "ASSERTED"),
        ("vocabulary_boundary", "mapping_defined", True),
        ("authority_boundary", "provider_call_authorized", True),
        ("verification_boundary", "TST-030", "PASS"),
    ],
)
def test_contract_cannot_claim_resolution_mapping_authority_or_formal_pass(
    tmp_path: Path,
    section: str,
    field: str,
    value: object,
) -> None:
    root = _isolated_repository(tmp_path)
    path = root / generator.CONTRACT_PATH
    contract = yaml.safe_load(path.read_bytes())
    contract[section][field] = value
    path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    with pytest.raises(generator.ProviderFactRecordedBuildError):
        generator.load_contract(root)


def test_contract_symlink_and_generated_symlink_are_rejected(tmp_path: Path) -> None:
    root = _isolated_repository(tmp_path)
    contract = root / generator.CONTRACT_PATH
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(Exception):
        generator.load_contract(root)

    root = _isolated_repository(tmp_path / "second")
    target = root / generator.PLAN_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    outside_json = tmp_path / "outside.json"
    outside_json.write_bytes(b"outside")
    target.symlink_to(outside_json)
    with pytest.raises(Exception):
        generator.build(root)
    assert outside_json.read_bytes() == b"outside"


def test_projection_json_is_utf8_deterministic_and_contains_no_raw_event_keys() -> None:
    content = (REPOSITORY_ROOT / generator.PLAN_PATH).read_bytes()
    assert content.endswith(b"\n") and b"\r" not in content
    assert content == generator._json_bytes(json.loads(content))
    assert b"synthetic-event-0001" not in content
    assert b"st1302-recorded-synthetic-0001" not in content


def test_cli_rejects_all_nonexact_arguments() -> None:
    for arguments in (["--check=yes"], ["--unknown"], ["--check", "extra"]):
        with pytest.raises(SystemExit) as caught:
            generator.parse_args(arguments)
        assert caught.value.code == 2
