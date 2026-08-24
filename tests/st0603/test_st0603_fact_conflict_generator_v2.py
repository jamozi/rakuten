"""Deterministic owner-generator checks for ST-0603 V2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from scripts import build_st0603_fact_conflict_runtime as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def _all_sources() -> tuple[Path, ...]:
    return (
        *generator.CANONICAL,
        *generator.PREDECESSOR_RUNTIME,
        *generator.RUNTIME_SOURCE,
        *generator.OWNED_TEST_SOURCE,
        *generator.DOCUMENTATION,
        generator.CONTRACT,
        generator.FIXTURE,
        generator.GENERATOR,
    )


@pytest.fixture()
def st0603_generator_repository_v2(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for relative in (
        *_all_sources(),
        generator.OUTPUT,
        generator.MANIFEST,
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return root


def test_v2_render_is_deterministic_and_installed_bytes_match() -> None:
    first = generator._render()  # noqa: SLF001
    second = generator._render()  # noqa: SLF001
    assert first == second
    assert (REPOSITORY_ROOT / generator.OUTPUT).read_bytes() == first[0]
    assert (REPOSITORY_ROOT / generator.MANIFEST).read_bytes() == first[1]


def test_v2_check_mode_is_no_write() -> None:
    paths = (generator.OUTPUT, generator.MANIFEST)
    before = {
        path: (
            (REPOSITORY_ROOT / path).read_bytes(),
            (REPOSITORY_ROOT / path).stat().st_mtime_ns,
        )
        for path in paths
    }
    assert generator.main(["--check"]) == 0
    after = {
        path: (
            (REPOSITORY_ROOT / path).read_bytes(),
            (REPOSITORY_ROOT / path).stat().st_mtime_ns,
        )
        for path in paths
    }
    assert after == before


def test_generated_report_keeps_conflict_and_authority_closed() -> None:
    report = _json(REPOSITORY_ROOT / generator.OUTPUT)
    conflict = report["conflict_boundary"]
    authority = report["authority_boundary"]
    formal = report["formal_evidence"]
    assert isinstance(conflict, dict)
    assert isinstance(authority, dict)
    assert isinstance(formal, dict)
    assert conflict["status"] == "UNRESOLVED"
    assert conflict["queue_status"] == "HUMAN_REVIEW"
    assert conflict["readiness"] == "NOT_READY"
    assert conflict["content_policy"] == "source_conflict"
    assert conflict["silent_resolution_forbidden"] is True
    assert conflict["winner_fact_id"] is None
    assert conflict["tolerance"] is None
    assert conflict["resolution"] is None
    assert authority["production_authority"] == "NONE"
    assert all(
        type(authority[key]) is int and authority[key] == 0
        for key in (
            "external_action_count",
            "provider_action_count",
            "publication_action_count",
            "ai_action_count",
        )
    )
    assert formal["TST-007"] == "LOCAL_ANALOG_ONLY_FORMAL_NOT_EXECUTED"
    assert formal["TST-020"] == "LOCAL_ANALOG_ONLY_FORMAL_NOT_EXECUTED"


def test_manifest_binds_every_owner_and_predecessor_source() -> None:
    manifest = _json(REPOSITORY_ROOT / generator.MANIFEST)
    sources = manifest["source_sha256"]
    generated = manifest["generated_sha256"]
    assert isinstance(sources, dict) and isinstance(generated, dict)
    assert set(sources) == {str(path) for path in _all_sources()}
    assert all(
        sources[str(path)]
        == hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest()
        for path in _all_sources()
    )
    assert generated == {
        str(generator.OUTPUT): hashlib.sha256(
            (REPOSITORY_ROOT / generator.OUTPUT).read_bytes()
        ).hexdigest()
    }
    assert manifest["formal_TST_007"] == "NOT_EXECUTED"
    assert manifest["formal_TST_020"] == "NOT_EXECUTED"
    assert manifest["production"] == "NOT_EXECUTED"
    assert manifest["production_authority"] == "NONE"


@pytest.mark.parametrize(
    ("relative", "mutate"),
    [
        (
            generator.CONTRACT,
            lambda value: value.update({"unexpected": True}),
        ),
        (
            generator.CONTRACT,
            lambda value: value["comparison_boundary"].update(  # type: ignore[union-attr]
                {"tolerance": "0.01"}
            ),
        ),
        (
            generator.CONTRACT,
            lambda value: value["conflict_boundary"].update(  # type: ignore[union-attr]
                {"silent_resolution_forbidden": False}
            ),
        ),
        (
            generator.CONTRACT,
            lambda value: value["excluded_inputs_and_capabilities"].append(  # type: ignore[union-attr]
                "opaque_extra_input"
            ),
        ),
        (
            generator.FIXTURE,
            lambda value: value["expected_report"].update(  # type: ignore[union-attr]
                {"winner_fact_id": "FCT-INVENTED"}
            ),
        ),
        (
            generator.FIXTURE,
            lambda value: value["metamorphic_cases"].__setitem__(  # type: ignore[union-attr]
                0, "OPAQUE_REPLACEMENT"
            ),
        ),
    ],
)
def test_closed_contract_and_fixture_mutations_are_rejected(
    st0603_generator_repository_v2: Path,
    monkeypatch,
    relative: Path,
    mutate,
) -> None:
    target = st0603_generator_repository_v2 / relative
    value = _json(target)
    mutate(value)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(generator, "REPO_ROOT", st0603_generator_repository_v2)
    with pytest.raises(generator.BuildError):
        generator._render()  # noqa: SLF001


def test_predecessor_byte_drift_is_rejected(
    st0603_generator_repository_v2: Path,
    monkeypatch,
) -> None:
    target = st0603_generator_repository_v2 / generator.PREDECESSOR_RUNTIME[0]
    target.write_bytes(target.read_bytes() + b"\n")
    monkeypatch.setattr(generator, "REPO_ROOT", st0603_generator_repository_v2)
    with pytest.raises(generator.BuildError, match="PREDECESSOR_HASH_DRIFT"):
        generator._render()  # noqa: SLF001


def test_isolated_generation_is_atomic_mode_0644_and_checkable(
    st0603_generator_repository_v2: Path,
    monkeypatch,
) -> None:
    (st0603_generator_repository_v2 / generator.OUTPUT).unlink()
    (st0603_generator_repository_v2 / generator.MANIFEST).unlink()
    monkeypatch.setattr(generator, "REPO_ROOT", st0603_generator_repository_v2)
    assert generator.main([]) == 0
    assert generator.main(["--check"]) == 0
    assert (
        st0603_generator_repository_v2 / generator.OUTPUT
    ).stat().st_mode & 0o777 == (0o644)
    assert (
        st0603_generator_repository_v2 / generator.MANIFEST
    ).stat().st_mode & 0o777 == 0o644
    assert not tuple(
        (st0603_generator_repository_v2 / generator.OUTPUT.parent).glob("*.tmp")
    )


def test_output_symlink_and_unknown_cli_argument_fail_closed(
    st0603_generator_repository_v2: Path,
    monkeypatch,
) -> None:
    output = st0603_generator_repository_v2 / generator.OUTPUT
    target = output.with_suffix(".target")
    target.write_bytes(b"sentinel")
    output.unlink()
    output.symlink_to(target)
    monkeypatch.setattr(generator, "REPO_ROOT", st0603_generator_repository_v2)
    with pytest.raises(generator.BuildError, match="OUTPUT_PATH_INVALID"):
        generator.main([])
    assert target.read_bytes() == b"sentinel"
    with pytest.raises(SystemExit):
        generator.main(["--unknown"])


def test_output_symlink_ancestor_is_rejected(
    st0603_generator_repository_v2: Path,
    monkeypatch,
) -> None:
    output = st0603_generator_repository_v2 / generator.OUTPUT
    output.unlink()
    output.parent.rmdir()
    outside = st0603_generator_repository_v2 / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"unchanged")
    output.parent.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(generator, "REPO_ROOT", st0603_generator_repository_v2)
    with pytest.raises(generator.BuildError, match="OUTPUT_PATH_INVALID"):
        generator.main([])
    assert sentinel.read_bytes() == b"unchanged"
    assert not (outside / output.name).exists()
