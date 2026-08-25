"""Deterministic owner generation tests for ST-1702."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat

import pytest
import yaml

from scripts import (
    build_st1702_category_fixtures_rules_reference_plan as generator,
)


def test_render_is_deterministic_and_matches_installed_outputs() -> None:
    first = generator.render_outputs()
    second = generator.render_outputs()
    assert first == second
    for relative, expected in first.items():
        assert (generator.REPO_ROOT / relative).read_bytes() == expected


def test_check_mode_accepts_exact_outputs() -> None:
    assert generator.main(["--check"]) == 0


def _snapshot(path: Path) -> tuple[bytes, int, int, int]:
    metadata = path.lstat()
    content = (
        os.readlink(path).encode("utf-8")
        if stat.S_ISLNK(metadata.st_mode)
        else path.read_bytes()
    )
    return (
        content,
        metadata.st_ino,
        metadata.st_mtime_ns,
        stat.S_IMODE(metadata.st_mode),
    )


def _optional_snapshot(path: Path) -> tuple[bytes, int, int, int] | None:
    return _snapshot(path) if os.path.lexists(path) else None


def _transaction_companions(root: Path) -> tuple[Path, ...]:
    companions: list[Path] = []
    for relative in generator.GENERATED_PATHS:
        target = root / relative
        companions.extend(
            (
                target.with_name(f".{target.name}{generator.NEXT_SUFFIX}"),
                target.with_name(f".{target.name}{generator.PREVIOUS_SUFFIX}"),
                target.with_name(f".{target.name}{generator.ABSENT_SUFFIX}"),
            )
        )
    state_parent = root / generator.MANIFEST_PATH.parent
    companions.extend(
        (
            state_parent / generator.TRANSACTION_STATE_NAME,
            state_parent / generator.TRANSACTION_STATE_NEXT_NAME,
        )
    )
    return tuple(companions)


def _assert_no_transaction_companions(root: Path) -> None:
    assert not [path for path in _transaction_companions(root) if os.path.lexists(path)]


class _SimulatedCrash(BaseException):
    pass


def test_check_mode_is_a_no_write_snapshot() -> None:
    paths = [generator.REPO_ROOT / relative for relative in generator.GENERATED_PATHS]
    before = {path: _snapshot(path) for path in paths}
    generator.build(check=True)
    after = {path: _snapshot(path) for path in paths}
    assert after == before


def test_isolated_publication_is_atomic_0644_and_adjacent(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
    _assert_no_transaction_companions(isolated_repository)
    generator.build(isolated_repository, check=True)


@pytest.mark.parametrize("failure_after_link", [False, True])
def test_injected_second_publish_failure_restores_exact_output_tuples(
    failure_after_link: bool,
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    reference = isolated_repository / generator.REFERENCE_PLAN_PATH
    reference.write_bytes(b"drifted-reference-plan\n")
    reference.chmod(0o600)
    os.utime(
        reference,
        ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000),
    )
    before = {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    }
    real_publish = generator._publish_output
    calls = 0

    def fail_second(root: Path, slot: generator._OutputSlot) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            if failure_after_link:
                real_publish(root, slot)
            raise OSError("injected second publish failure")
        real_publish(root, slot)

    monkeypatch.setattr(generator, "_publish_output", fail_second)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
        generator.build(isolated_repository)
    assert caught.value.code == "OUTPUT_TRANSACTION_FAILED"
    assert {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(isolated_repository)


@pytest.mark.parametrize(
    ("boundary", "corrupted_relative"),
    [
        (
            f"BACKED_UP_{generator.REFERENCE_PLAN_PATH.as_posix()}",
            generator.REFERENCE_PLAN_PATH,
        ),
        (
            f"BACKED_UP_{generator.MANIFEST_PATH.as_posix()}",
            generator.MANIFEST_PATH,
        ),
    ],
)
def test_staged_next_drift_after_each_backup_is_rolled_back_exactly(
    boundary: str,
    corrupted_relative: Path,
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    before = {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    }
    corrupted = False

    def corrupt_after_backup(name: str) -> None:
        nonlocal corrupted
        if name == boundary and not corrupted:
            corrupted = True
            target = isolated_repository / corrupted_relative
            target.with_name(f".{target.name}{generator.NEXT_SUFFIX}").write_bytes(
                b"corrupted-staged-output\n"
            )

    monkeypatch.setattr(generator, "_transaction_checkpoint", corrupt_after_backup)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
        generator.build(isolated_repository)
    assert caught.value.code == "OUTPUT_COMPANION_DRIFT"
    assert {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(isolated_repository)


@pytest.mark.parametrize(
    "boundary",
    [
        f"PUBLISHED_{generator.REFERENCE_PLAN_PATH.as_posix()}",
        f"PUBLISHED_{generator.MANIFEST_PATH.as_posix()}",
    ],
)
def test_published_target_drift_before_commit_is_rolled_back_exactly(
    boundary: str,
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    before = {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    }
    corrupted = False

    def corrupt_after_publish(name: str) -> None:
        nonlocal corrupted
        if name == boundary and not corrupted:
            corrupted = True
            relative = (
                generator.REFERENCE_PLAN_PATH
                if name.endswith(generator.REFERENCE_PLAN_PATH.as_posix())
                else generator.MANIFEST_PATH
            )
            (isolated_repository / relative).write_bytes(
                b"corrupted-published-output\n"
            )

    monkeypatch.setattr(generator, "_transaction_checkpoint", corrupt_after_publish)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
        generator.build(isolated_repository)
    assert caught.value.code == "OUTPUT_PUBLISH_DRIFT"
    assert {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(isolated_repository)


@pytest.mark.parametrize(
    ("boundary", "replacement_parent"),
    [
        (f"PUBLISHED_{generator.REFERENCE_PLAN_PATH.as_posix()}", False),
        (f"PUBLISHED_{generator.REFERENCE_PLAN_PATH.as_posix()}", True),
        ("COMMIT_MARKED", False),
        ("COMMIT_MARKED", True),
    ],
)
def test_pending_recovery_requires_complete_transaction_bound_parent_inventory(
    boundary: str,
    replacement_parent: bool,
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    original = {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    }

    def crash_at(name: str) -> None:
        if name == boundary:
            raise _SimulatedCrash

    monkeypatch.setattr(generator, "_transaction_checkpoint", crash_at)
    with pytest.raises(_SimulatedCrash):
        generator.build(isolated_repository)
    pending = {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
        if (isolated_repository / relative).exists()
    }
    state = (
        isolated_repository
        / generator.MANIFEST_PATH.parent
        / generator.TRANSACTION_STATE_NAME
    )
    state_before = _snapshot(state)
    generated_parent = isolated_repository / generator.REFERENCE_PLAN_PATH.parent
    parked = generated_parent.with_name("generated.parked-pending-transaction")
    generated_parent.rename(parked)
    if replacement_parent:
        generated_parent.mkdir(mode=0o755)

    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.build(isolated_repository, check=True)
    assert _snapshot(state) == state_before
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator._recover_pending_transaction(isolated_repository, mutate=True)
    assert _snapshot(state) == state_before

    if replacement_parent:
        generated_parent.rmdir()
    parked.rename(generated_parent)
    monkeypatch.setattr(generator, "_transaction_checkpoint", lambda _name: None)
    generator._recover_pending_transaction(isolated_repository, mutate=True)
    expected = pending if boundary == "COMMIT_MARKED" else original
    assert {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    } == expected
    _assert_no_transaction_companions(isolated_repository)


@pytest.mark.parametrize(
    "boundary",
    [
        f"STAGED_{generator.REFERENCE_PLAN_PATH.as_posix()}",
        f"STAGED_{generator.MANIFEST_PATH.as_posix()}",
        f"BACKED_UP_{generator.REFERENCE_PLAN_PATH.as_posix()}",
        f"BACKED_UP_{generator.MANIFEST_PATH.as_posix()}",
        f"PUBLISHED_{generator.REFERENCE_PLAN_PATH.as_posix()}",
        f"PUBLISHED_{generator.MANIFEST_PATH.as_posix()}",
        "COMMIT_MARKED",
    ],
)
@pytest.mark.parametrize(
    "original_presence",
    [(True, True), (False, False), (True, False), (False, True)],
)
def test_transaction_crash_matrix_recovers_existing_absent_and_mixed_outputs(
    boundary: str,
    original_presence: tuple[bool, bool],
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    for relative, present in zip(
        generator.GENERATED_PATHS,
        original_presence,
        strict=True,
    ):
        if not present:
            (isolated_repository / relative).unlink()
    before = {
        relative: _optional_snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    }

    def crash_at(name: str) -> None:
        if name == boundary:
            raise _SimulatedCrash

    monkeypatch.setattr(generator, "_transaction_checkpoint", crash_at)
    with pytest.raises(_SimulatedCrash):
        generator.build(isolated_repository)
    monkeypatch.setattr(generator, "_transaction_checkpoint", lambda _name: None)
    generator._recover_pending_transaction(isolated_repository, mutate=True)

    if boundary == "COMMIT_MARKED":
        expected = generator.render_outputs(isolated_repository)
        for relative in generator.GENERATED_PATHS:
            target = isolated_repository / relative
            assert target.read_bytes() == expected[relative]
            assert stat.S_IMODE(target.stat().st_mode) == generator.OUTPUT_MODE
    else:
        assert {
            relative: _optional_snapshot(isolated_repository / relative)
            for relative in generator.GENERATED_PATHS
        } == before
    _assert_no_transaction_companions(isolated_repository)


def test_post_preflight_target_swap_is_not_overwritten_and_recovers(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    before = {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    }
    target = isolated_repository / generator.MANIFEST_PATH
    parked = target.with_name("manifest.parked-for-test")

    def swap_target(_slots: object) -> None:
        target.rename(parked)
        target.symlink_to(isolated_repository / generator.CONTRACT_PATH)

    monkeypatch.setattr(generator, "_before_transaction_commit", swap_target)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
        generator.build(isolated_repository)
    assert caught.value.code == "OUTPUT_ROLLBACK_REQUIRED"
    assert target.is_symlink()
    assert (
        _snapshot(isolated_repository / generator.REFERENCE_PLAN_PATH)
        == before[generator.REFERENCE_PLAN_PATH]
    )

    target.unlink()
    parked.rename(target)
    monkeypatch.setattr(generator, "_before_transaction_commit", lambda _slots: None)
    generator._recover_pending_transaction(isolated_repository, mutate=True)
    assert {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(isolated_repository)


def test_post_preflight_ancestor_swap_is_not_followed_and_recovers(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    before = {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    }
    generated = isolated_repository / generator.REFERENCE_PLAN_PATH.parent
    parked = generated.with_name("generated.parked-for-test")

    def swap_ancestor(_slots: object) -> None:
        generated.rename(parked)
        generated.symlink_to(parked, target_is_directory=True)

    monkeypatch.setattr(generator, "_before_transaction_commit", swap_ancestor)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
        generator.build(isolated_repository)
    assert caught.value.code == "OUTPUT_ROLLBACK_REQUIRED"
    assert generated.is_symlink()
    assert (
        _snapshot(isolated_repository / generator.MANIFEST_PATH)
        == before[generator.MANIFEST_PATH]
    )

    generated.unlink()
    parked.rename(generated)
    monkeypatch.setattr(generator, "_before_transaction_commit", lambda _slots: None)
    generator._recover_pending_transaction(isolated_repository, mutate=True)
    assert {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(isolated_repository)


def test_locked_coordinator_parent_swap_retains_recoverable_state(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    before = {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    }
    coordinator_parent = isolated_repository / generator.MANIFEST_PATH.parent
    parked = coordinator_parent.with_name("st-1702.parked-lock-parent")

    def swap_locked_parent(_slots: object) -> None:
        coordinator_parent.rename(parked)
        coordinator_parent.symlink_to(parked, target_is_directory=True)

    monkeypatch.setattr(generator, "_before_transaction_commit", swap_locked_parent)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
        generator.build(isolated_repository)
    assert caught.value.code == "OUTPUT_LOCK_RECOVERY_REQUIRED"
    assert coordinator_parent.is_symlink()

    coordinator_parent.unlink()
    parked.rename(coordinator_parent)
    monkeypatch.setattr(generator, "_before_transaction_commit", lambda _slots: None)
    generator._recover_pending_transaction(isolated_repository, mutate=True)
    assert {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    } == before
    _assert_no_transaction_companions(isolated_repository)


def test_check_refuses_pending_recovery_without_writing(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator.build(isolated_repository)
    original = {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    }
    crash_point = f"PUBLISHED_{generator.REFERENCE_PLAN_PATH.as_posix()}"

    def crash_after_first_publish(name: str) -> None:
        if name == crash_point:
            raise _SimulatedCrash

    monkeypatch.setattr(generator, "_transaction_checkpoint", crash_after_first_publish)
    with pytest.raises(_SimulatedCrash):
        generator.build(isolated_repository)
    pending_paths = [
        path
        for path in (
            *(isolated_repository / relative for relative in generator.GENERATED_PATHS),
            *_transaction_companions(isolated_repository),
        )
        if os.path.lexists(path)
    ]
    before_check = {path: _snapshot(path) for path in pending_paths}
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as caught:
        generator.build(isolated_repository, check=True)
    assert caught.value.code == "OUTPUT_RECOVERY_REQUIRED"
    assert {path: _snapshot(path) for path in pending_paths} == before_check

    monkeypatch.setattr(generator, "_transaction_checkpoint", lambda _name: None)
    generator._recover_pending_transaction(isolated_repository, mutate=True)
    assert {
        relative: _snapshot(isolated_repository / relative)
        for relative in generator.GENERATED_PATHS
    } == original
    _assert_no_transaction_companions(isolated_repository)


def test_malformed_transaction_state_is_preserved_and_rejected_read_only(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    state = (
        isolated_repository
        / generator.MANIFEST_PATH.parent
        / generator.TRANSACTION_STATE_NAME
    )
    state.write_bytes(b"MALFORMED_ST1702_TRANSACTION_STATE\n")
    state.chmod(generator.PRIVATE_COMPANION_MODE)
    before = _snapshot(state)
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as check_error:
        generator.build(isolated_repository, check=True)
    assert check_error.value.code == "OUTPUT_RECOVERY_REQUIRED"
    assert _snapshot(state) == before
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as write_error:
        generator.build(isolated_repository)
    assert write_error.value.code == "OUTPUT_RECOVERY_REQUIRED"
    assert _snapshot(state) == before


@pytest.mark.parametrize(
    "shape",
    ["state-symlink", "state-next-only", "orphan-previous", "state-wrong-mode"],
)
def test_malformed_recovery_shapes_are_never_repaired_by_check(
    shape: str,
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    state_parent = isolated_repository / generator.MANIFEST_PATH.parent
    state = state_parent / generator.TRANSACTION_STATE_NAME
    state_next = state_parent / generator.TRANSACTION_STATE_NEXT_NAME
    reference = isolated_repository / generator.REFERENCE_PLAN_PATH
    previous = reference.with_name(f".{reference.name}{generator.PREVIOUS_SUFFIX}")
    if shape == "state-symlink":
        state.symlink_to(isolated_repository / generator.CONTRACT_PATH)
    elif shape == "state-next-only":
        state_next.write_bytes(b'{"phase":"COMMIT"}\n')
        state_next.chmod(generator.PRIVATE_COMPANION_MODE)
    elif shape == "orphan-previous":
        previous.write_bytes(b"uncoordinated-previous\n")
        previous.chmod(generator.OUTPUT_MODE)
    else:
        state.write_bytes(b'{"phase":"ROLLBACK"}\n')
        state.chmod(0o644)
    relevant = [
        path
        for path in (
            *(isolated_repository / relative for relative in generator.GENERATED_PATHS),
            *_transaction_companions(isolated_repository),
        )
        if os.path.lexists(path)
    ]
    before = {path: _snapshot(path) for path in relevant}
    with pytest.raises(generator.CategoryFixturesRulesReferenceError):
        generator.build(isolated_repository, check=True)
    assert {path: _snapshot(path) for path in relevant} == before


def test_manifest_binds_sources_authority_dependencies_and_local_io() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    reference = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert [row["uri"] for row in manifest["source_artifacts"]] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_PATHS
    ]
    assert manifest["provenance"]["integration_base_commit"] == (
        generator.INTEGRATION_BASE_COMMIT
    )
    assert manifest["provenance"]["authority_inputs"] == generator._source_rows()
    assert manifest["provenance"]["dependency_inputs"] == [
        {
            "story_id": story_id,
            "artifacts": generator._artifact_rows(artifacts),
        }
        for story_id, artifacts in generator.DEPENDENCY_ARTIFACTS
    ]
    assert manifest["provenance"]["implementation_io"] == (
        "SELF_CONTAINED_DESCRIPTOR_CAPTURED_BOUNDED_INPUTS_AND_"
        "RECOVERABLE_PAIRED_OUTPUT_TRANSACTION"
    )
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": len(reference),
            "sha256": generator._sha256(reference),
        }
    ]


def test_manifest_keeps_the_exact_non_execution_boundary() -> None:
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )
    boundary = manifest["boundary"]
    assert boundary["input_capture"] == ("DESCRIPTOR_CAPTURED_SINGLE_PASS_SAME_BYTES")
    assert boundary["repository_root_capture"] == (
        "COMPONENT_DESCRIPTOR_WALK_O_NOFOLLOW"
    )
    assert boundary["input_size_limit_bytes"] == generator.MAX_SOURCE_BYTES
    assert boundary["output_pair_transaction"] == "RECOVERABLE_ALL_OR_NOTHING"
    assert boundary["transaction_inventory_binding"] == (
        "ORDERED_PATH_PARENT_IDENTITY_ORIGINAL_AND_STAGED"
    )
    assert boundary["commit_revalidation"] == ("TARGET_NEXT_PARENT_AND_LOCK_IDENTITY")
    assert boundary["recovery_parent_drift"] == "FAIL_CLOSED_STATE_RETAINED"
    assert boundary["pending_check_behavior"] == "READ_ONLY_REFUSAL"
    assert boundary["executable"] is False
    assert boundary["canonical_mutation_authority"] == "NONE"
    assert boundary["od_001"] == "HUMAN_DECISION_REQUIRED"
    assert boundary["od_006"] == "EXTERNAL_EVIDENCE_REQUIRED"
    assert boundary["od_007"] == "HUMAN_DECISION_REQUIRED"
    assert boundary["category_candidate_authority"] == (
        "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE"
    )
    assert boundary["runtime_category_config"] == "NOT_CREATED"
    assert boundary["golden_products"] == "NOT_CREATED"
    assert boundary["automatic_merge_enabled"] is False
    assert boundary["automatic_split_enabled"] is False
    assert boundary["human_review_required"] is True
    assert boundary["domain_reviewer_approval"] == "NOT_OBTAINED"
    assert boundary["freshness_policy_activation"] == ("DISABLED_UNRESOLVED_OD_007")
    assert boundary["category_override_applied"] is False
    assert boundary["provider_override_applied"] is False
    assert boundary["formal_tst_020"] == "NOT_EXECUTED"
    assert boundary["story_acceptance"] is False
    assert boundary["st1702_ready"] is False


def test_generated_or_manifest_drift_is_rejected(
    isolated_repository: Path,
) -> None:
    generator.build(isolated_repository)
    for relative in generator.GENERATED_PATHS:
        path = isolated_repository / relative
        original = path.read_bytes()
        path.write_bytes(original + b"drift")
        with pytest.raises(generator.CategoryFixturesRulesReferenceError):
            generator.build(isolated_repository, check=True)
        path.write_bytes(original)


def test_reference_plan_bytes_are_canonical_utf8_json() -> None:
    content = (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    assert content.endswith(b"\n")
    assert b"\r" not in content
    parsed = json.loads(content)
    assert content == generator._json_bytes(parsed)


def test_cli_rejects_every_argument_except_exact_check() -> None:
    for arguments in (["--check=yes"], ["--unknown"], ["--check", "extra"]):
        with pytest.raises(SystemExit) as caught:
            generator.parse_args(arguments)
        assert caught.value.code == 2
