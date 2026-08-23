from __future__ import annotations

from copy import deepcopy
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator
import yaml

import raos.adapters.owner_local_pilot_json as adapter_module
from raos.adapters.owner_local_pilot_json import (
    INPUT_FILE,
    LEDGER_FILE,
    LOCK_FILE,
    OwnerLocalPilotJsonStore,
    PILOT_DIRECTORY,
    STAGE_FILE,
)
from raos.domain.editorial.owner_local_pilot import (
    ImprovementDecision,
    PILOT_POLICY,
    PilotFailure,
    PilotFailureCode,
    PilotLedger,
    PilotObservation,
    append_observation,
    build_report,
    canonical_bytes,
    empty_ledger,
)
import scripts.build_st1704_owner_local_pilot as builder
import scripts.st1704_owner_local_pilot as cli


ROOT = Path(__file__).resolve().parents[2]
PINNED_PYTHON = Path("/home/minami/rakuten/.venv/bin/python")
EXAMPLE = (
    ROOT / "changes/st-1704/owner-local-pilot-v1/examples/"
    "bootstrap-first-publication.v1.json"
)


def example() -> dict[str, object]:
    value = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def complete(slot: int) -> dict[str, object]:
    payload = example()
    payload["observation_id"] = f"PILOT-ARTICLE-{slot:02d}-COMPLETE-V1"
    payload["observed_at_utc"] = "2026-09-05T23:00:00Z"
    payload["article"] = {
        "article_ref_sha256": None,
        "public_slug": f"pilot-article-{slot}",
        "slot": slot,
    }
    payload["review"] = {
        "reviewed_at_utc": "2026-09-05T22:00:00Z",
        "reviewer_role": "OWNER",
        "status": "HUMAN_REVIEW_COMPLETE",
    }
    payload["work_minutes"] = {"state": "OBSERVED_VALUE", "value": 60}
    payload["incremental_cost_jpy"] = {
        "state": "OBSERVED_VALUE",
        "value": 100,
    }
    payload["defects"] = {
        "critical": {"state": "OBSERVED_ZERO", "value": 0},
        "major": {"state": "OBSERVED_ZERO", "value": 0},
        "minor": {"state": "OBSERVED_ZERO", "value": 0},
    }

    def metric(source_kind: str, attribution_basis: str) -> dict[str, object]:
        return {
            "attribution_basis": attribution_basis,
            "input_sha256": f"{slot}" * 64,
            "period_end": "2026-09-05",
            "period_start": "2026-08-23",
            "source_kind": source_kind,
            "state": "OBSERVED_ZERO",
            "value": 0,
        }

    payload["metrics"] = {
        "article_views": metric("WORDPRESS_ADMIN_AGGREGATE", "NOT_APPLICABLE"),
        "affiliate_clicks": metric("FIRST_PARTY_AGGREGATE", "NOT_APPLICABLE"),
        "organic_clicks": metric("SEARCH_CONSOLE_AGGREGATE", "NOT_APPLICABLE"),
        "revenue_jpy": {
            "provider_total_jpy": metric(
                "RAKUTEN_REPORT_AGGREGATE", "OWNER_REPORTED_PROVIDER_TOTAL"
            ),
            "direct_jpy": metric("RAKUTEN_REPORT_AGGREGATE", "OWNER_REPORTED_DIRECT"),
            "estimated_jpy": metric(
                "OWNER_MANUAL_AGGREGATE", "OWNER_REPORTED_ESTIMATED"
            ),
            "unattributed_jpy": metric(
                "OWNER_MANUAL_AGGREGATE", "OWNER_REPORTED_UNATTRIBUTED"
            ),
        },
    }
    return payload


def metric_at(payload: dict[str, object], *path: str) -> dict[str, object]:
    current: object = payload["metrics"]
    for component in path:
        assert type(current) is dict
        current = current[component]
    assert type(current) is dict
    return current


def ledger_for(payloads: list[dict[str, object]]) -> PilotLedger:
    ledger = empty_ledger()
    for payload in payloads:
        ledger = append_observation(ledger, PilotObservation.parse(payload))[0]
    return ledger


def store_with_input(tmp_path: Path) -> tuple[OwnerLocalPilotJsonStore, Path]:
    store = OwnerLocalPilotJsonStore(tmp_path)
    store.initialize()
    target = tmp_path / ".secrets" / PILOT_DIRECTORY / INPUT_FILE
    target.write_text(json.dumps(example()), encoding="utf-8")
    target.chmod(0o600)
    return store, target


@pytest.mark.parametrize("unsafe", ["mode", "hardlink", "symlink"])
def test_rejects_unsafe_input_file(tmp_path: Path, unsafe: str) -> None:
    store, target = store_with_input(tmp_path)
    if unsafe == "mode":
        target.chmod(0o640)
    elif unsafe == "hardlink":
        os.link(target, target.with_name("input-copy"))
    else:
        raw = target.read_bytes()
        target.unlink()
        outside = tmp_path / "outside-input"
        outside.write_bytes(raw)
        outside.chmod(0o600)
        target.symlink_to(outside)
    with pytest.raises(PilotFailure) as captured:
        store.read_observation()
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE


def test_rejects_unsafe_directory_mode(tmp_path: Path) -> None:
    store = OwnerLocalPilotJsonStore(tmp_path)
    store.initialize()
    (tmp_path / ".secrets" / PILOT_DIRECTORY).chmod(0o750)
    with pytest.raises(PilotFailure) as captured:
        store.read()
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE


def test_rejects_symlink_in_repository_root_path(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(PilotFailure) as captured:
        OwnerLocalPilotJsonStore(linked).initialize()
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE


def test_lock_contention_is_fail_closed(tmp_path: Path) -> None:
    store, _ = store_with_input(tmp_path)
    lock_path = tmp_path / ".secrets" / PILOT_DIRECTORY / LOCK_FILE
    lock_fd = os.open(lock_path, os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(PilotFailure) as captured:
            store.append(store.read_observation())
        assert captured.value.code is PilotFailureCode.STORE_BUSY
    finally:
        os.close(lock_fd)


def test_lock_unlink_and_recreate_after_flock_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, _ = store_with_input(tmp_path)
    observation = store.read_observation()
    ledger_path = tmp_path / ".secrets" / PILOT_DIRECTORY / LEDGER_FILE
    before = ledger_path.read_bytes()
    lock_path = tmp_path / ".secrets" / PILOT_DIRECTORY / LOCK_FILE
    original_flock = adapter_module.fcntl.flock
    raced = False

    def racing_flock(fd: int, operation: int) -> object:
        nonlocal raced
        result = original_flock(fd, operation)
        if not raced:
            raced = True
            lock_path.unlink()
            replacement = os.open(
                lock_path,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600,
            )
            os.close(replacement)
        return result

    monkeypatch.setattr(adapter_module.fcntl, "flock", racing_flock)
    with pytest.raises(PilotFailure) as captured:
        store.append(observation)
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE
    assert ledger_path.read_bytes() == before


def test_lock_unlink_and_recreate_before_success_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, _ = store_with_input(tmp_path)
    observation = store.read_observation()
    lock_path = tmp_path / ".secrets" / PILOT_DIRECTORY / LOCK_FILE
    original = OwnerLocalPilotJsonStore._read_ledger_with_identity
    reads = 0

    def race_after_read(
        self: OwnerLocalPilotJsonStore,
        pilot_fd: int,
        name: str = LEDGER_FILE,
    ) -> tuple[PilotLedger, os.stat_result]:
        nonlocal reads
        result = original(self, pilot_fd, name)
        if name == LEDGER_FILE:
            reads += 1
        if reads == 2 and name == LEDGER_FILE:
            lock_path.unlink()
            replacement = os.open(
                lock_path,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600,
            )
            os.close(replacement)
        return result

    monkeypatch.setattr(
        OwnerLocalPilotJsonStore, "_read_ledger_with_identity", race_after_read
    )
    with pytest.raises(PilotFailure) as captured:
        store.append(observation)
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE
    assert reads >= 2


def test_atomic_replace_failure_is_recovered_without_duplicate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, _ = store_with_input(tmp_path)
    original = OwnerLocalPilotJsonStore._replace_stage

    def crash(self: OwnerLocalPilotJsonStore, pilot_fd: int, **kwargs: object) -> None:
        del self, pilot_fd, kwargs
        raise OSError("synthetic crash")

    monkeypatch.setattr(OwnerLocalPilotJsonStore, "_replace_stage", crash)
    with pytest.raises(PilotFailure) as captured:
        store.append(store.read_observation())
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE
    directory = tmp_path / ".secrets" / PILOT_DIRECTORY
    assert (directory / STAGE_FILE).is_file()
    with pytest.raises(PilotFailure) as read_error:
        store.read()
    assert read_error.value.code is PilotFailureCode.RECOVERY_REQUIRED

    monkeypatch.setattr(OwnerLocalPilotJsonStore, "_replace_stage", original)
    recovered, created = store.initialize()
    assert not created
    assert len(recovered.events) == 1
    replay = store.append(store.read_observation())
    assert replay.disposition.value == "REPLAYED"
    assert len(replay.ledger.events) == 1


def test_post_exchange_cleanup_swap_restores_terminal_ledger_and_refuses_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, _ = store_with_input(tmp_path)
    appended = store.append(store.read_observation())
    assert len(appended.ledger.events) == 1
    directory = tmp_path / ".secrets" / PILOT_DIRECTORY
    stage = directory / STAGE_FILE
    stage.write_bytes(canonical_bytes(empty_ledger().payload()) + b"\n")
    stage.chmod(0o600)
    original_unlink = adapter_module.os.unlink
    raced = False

    def racing_unlink(path: str | bytes, *, dir_fd: int | None = None) -> None:
        nonlocal raced
        if path == STAGE_FILE and dir_fd is not None and not raced:
            raced = True
            adapter_module._rename_exchange(dir_fd, STAGE_FILE, LEDGER_FILE)
        original_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(adapter_module.os, "unlink", racing_unlink)
    with pytest.raises(PilotFailure) as captured:
        store.initialize()
    assert captured.value.code is PilotFailureCode.RECOVERY_REQUIRED
    assert raced

    recovered, created = store.initialize()
    assert not created
    assert len(recovered.events) == 1
    assert not stage.exists()


def test_terminal_ledger_swap_after_verified_write_refuses_append_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, _ = store_with_input(tmp_path)
    directory = tmp_path / ".secrets" / PILOT_DIRECTORY
    ledger_path = directory / LEDGER_FILE
    replacement = directory / "replacement-empty-ledger"
    replacement.write_bytes(canonical_bytes(empty_ledger().payload()) + b"\n")
    replacement.chmod(0o600)
    original = OwnerLocalPilotJsonStore._verify_terminal_ledger
    verifications = 0

    def swap_after_final_write_verification(
        self: OwnerLocalPilotJsonStore,
        pilot_fd: int,
        expected: PilotLedger,
        expected_identity: os.stat_result,
    ) -> None:
        nonlocal verifications
        verifications += 1
        original(self, pilot_fd, expected, expected_identity)
        if verifications == 2:
            ledger_path.rename(directory / "detached-appended-ledger")
            replacement.rename(ledger_path)

    monkeypatch.setattr(
        OwnerLocalPilotJsonStore,
        "_verify_terminal_ledger",
        swap_after_final_write_verification,
    )
    with pytest.raises(PilotFailure) as captured:
        store.append(store.read_observation())
    assert captured.value.code is PilotFailureCode.RECOVERY_REQUIRED
    assert verifications == 3


def test_stage_swap_during_exchange_rolls_back_without_ledger_loss(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, _ = store_with_input(tmp_path)
    directory = tmp_path / ".secrets" / PILOT_DIRECTORY
    ledger_path = directory / LEDGER_FILE
    before = ledger_path.read_bytes()
    original = OwnerLocalPilotJsonStore._replace_stage

    def race(self: OwnerLocalPilotJsonStore, pilot_fd: int, **kwargs: object) -> None:
        stage = directory / STAGE_FILE
        stage.rename(directory / "detached-valid-stage")
        replacement = directory / "replacement-stage"
        replacement.write_bytes(canonical_bytes(empty_ledger().payload()) + b"\n")
        replacement.chmod(0o600)
        replacement.rename(stage)
        original(self, pilot_fd, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(OwnerLocalPilotJsonStore, "_replace_stage", race)
    with pytest.raises(PilotFailure) as captured:
        store.append(store.read_observation())
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE
    assert ledger_path.read_bytes() == before


def test_invalid_preparing_ledger_never_replaces_current(tmp_path: Path) -> None:
    store, _ = store_with_input(tmp_path)
    before = store.read().payload()
    stage = tmp_path / ".secrets" / PILOT_DIRECTORY / STAGE_FILE
    stage.write_text('{"schema":"tampered"}\n', encoding="utf-8")
    stage.chmod(0o600)
    with pytest.raises(PilotFailure):
        store.initialize()
    assert (
        json.loads(
            (tmp_path / ".secrets" / PILOT_DIRECTORY / LEDGER_FILE).read_text(
                encoding="utf-8"
            )
        )
        == before
    )


def test_path_replacement_during_input_read_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, target = store_with_input(tmp_path)
    replacement = target.with_name("replacement-input")
    alternate = deepcopy(example())
    alternate["observation_id"] = "PILOT-ARTICLE-01-REPLACED-V1"
    replacement.write_text(json.dumps(alternate), encoding="utf-8")
    replacement.chmod(0o600)
    original_read = adapter_module.os.read
    swapped = False

    def racing_read(fd: int, size: int) -> bytes:
        nonlocal swapped
        result = original_read(fd, size)
        if not swapped:
            swapped = True
            target.rename(target.with_name("old-input"))
            replacement.rename(target)
        return result

    monkeypatch.setattr(adapter_module.os, "read", racing_read)
    with pytest.raises(PilotFailure) as captured:
        store.read_observation()
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE


@pytest.mark.parametrize("rebind_call", [1, 2, 3])
def test_directory_rebind_race_refuses_before_commit_or_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rebind_call: int
) -> None:
    store, _ = store_with_input(tmp_path)
    original = OwnerLocalPilotJsonStore._rebind_layout
    calls = 0

    def race(
        self: OwnerLocalPilotJsonStore,
        root_fd: int,
        secrets_fd: int,
        pilot_fd: int,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == rebind_call:
            secrets = tmp_path / ".secrets"
            secrets.rename(tmp_path / "moved-secrets")
            secrets.mkdir(mode=0o700)
            (secrets / PILOT_DIRECTORY).mkdir(mode=0o700)
        original(self, root_fd, secrets_fd, pilot_fd)

    monkeypatch.setattr(OwnerLocalPilotJsonStore, "_rebind_layout", race)
    with pytest.raises(PilotFailure) as captured:
        store.append(store.read_observation())
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE
    assert calls >= rebind_call
    assert not (tmp_path / ".secrets" / PILOT_DIRECTORY / LEDGER_FILE).exists()


@pytest.mark.parametrize("rebind_call", [1, 2, 3])
def test_repository_root_rebind_race_refuses_before_commit_or_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rebind_call: int
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    store, _ = store_with_input(repository)
    observation = store.read_observation()
    original = OwnerLocalPilotJsonStore._rebind_layout
    calls = 0

    def race(
        self: OwnerLocalPilotJsonStore,
        root_fd: int,
        secrets_fd: int,
        pilot_fd: int,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == rebind_call:
            repository.rename(tmp_path / "moved-repository")
            repository.mkdir(mode=0o700)
            secrets = repository / ".secrets"
            secrets.mkdir(mode=0o700)
            (secrets / PILOT_DIRECTORY).mkdir(mode=0o700)
        original(self, root_fd, secrets_fd, pilot_fd)

    monkeypatch.setattr(OwnerLocalPilotJsonStore, "_rebind_layout", race)
    with pytest.raises(PilotFailure) as captured:
        store.append(observation)
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE
    assert calls >= rebind_call
    assert not (repository / ".secrets" / PILOT_DIRECTORY / LEDGER_FILE).exists()


def test_repository_root_swap_after_verified_write_is_refused_before_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir(mode=0o700)
    store, _ = store_with_input(repository)
    observation = store.read_observation()
    original = OwnerLocalPilotJsonStore._read_ledger_with_identity
    reads = 0

    def race_after_read(
        self: OwnerLocalPilotJsonStore,
        pilot_fd: int,
        name: str = LEDGER_FILE,
    ) -> tuple[PilotLedger, os.stat_result]:
        nonlocal reads
        result = original(self, pilot_fd, name)
        if name == LEDGER_FILE:
            reads += 1
        if reads == 2 and name == LEDGER_FILE:
            repository.rename(tmp_path / "moved-repository")
            repository.mkdir(mode=0o700)
            secrets = repository / ".secrets"
            secrets.mkdir(mode=0o700)
            (secrets / PILOT_DIRECTORY).mkdir(mode=0o700)
        return result

    monkeypatch.setattr(
        OwnerLocalPilotJsonStore, "_read_ledger_with_identity", race_after_read
    )
    with pytest.raises(PilotFailure) as captured:
        store.append(observation)
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE
    assert reads == 2
    assert not (repository / ".secrets" / PILOT_DIRECTORY / LEDGER_FILE).exists()


def test_article_slot_identity_cannot_change() -> None:
    first_payload = example()
    first = PilotObservation.parse(first_payload)
    ledger = append_observation(empty_ledger(), first)[0]
    changed = deepcopy(first_payload)
    changed["observation_id"] = "PILOT-ARTICLE-01-SECOND-V1"
    changed["article"]["public_slug"] = "different-slug"
    with pytest.raises(PilotFailure) as captured:
        append_observation(ledger, PilotObservation.parse(changed))
    assert captured.value.code is PilotFailureCode.ARTICLE_IDENTITY_CONFLICT


@pytest.mark.parametrize(
    ("state", "value", "accepted"),
    [
        ("NOT_OBSERVED", None, True),
        ("NOT_OBSERVED", 0, False),
        ("UNAVAILABLE", None, True),
        ("UNVERIFIED", None, True),
        ("UNVERIFIED", 0, True),
        ("OBSERVED_ZERO", 0, True),
        ("OBSERVED_ZERO", None, False),
        ("OBSERVED_VALUE", 1, True),
        ("OBSERVED_VALUE", 0, False),
    ],
)
def test_value_state_mutation_matrix(
    state: str, value: int | None, accepted: bool
) -> None:
    payload = example()
    payload["work_minutes"] = {"state": state, "value": value}
    if accepted:
        PilotObservation.parse(payload)
    else:
        with pytest.raises(PilotFailure):
            PilotObservation.parse(payload)


@pytest.mark.parametrize(
    ("window", "observed_at", "accepted"),
    [
        (
            {
                "duration_days": 14,
                "end_exclusive_date": "2026-09-06",
                "start_date": "2026-08-23",
            },
            "2026-08-23T00:00:00Z",
            True,
        ),
        (
            {
                "duration_days": 13,
                "end_exclusive_date": "2026-09-05",
                "start_date": "2026-08-23",
            },
            "2026-08-23T00:00:00Z",
            False,
        ),
        (
            {
                "duration_days": 14,
                "end_exclusive_date": "2026-09-07",
                "start_date": "2026-08-23",
            },
            "2026-08-23T00:00:00Z",
            False,
        ),
        (
            {
                "duration_days": 14,
                "end_exclusive_date": "2026-09-06",
                "start_date": "2026-08-23",
            },
            "2026-08-22T23:59:59Z",
            False,
        ),
        (
            {
                "duration_days": 14,
                "end_exclusive_date": "2026-09-06",
                "start_date": "2026-08-23",
            },
            "2026-09-06T00:00:00Z",
            False,
        ),
    ],
)
def test_pilot_window_is_exactly_fourteen_days_and_starts_before_observation(
    window: dict[str, object], observed_at: str, accepted: bool
) -> None:
    payload = example()
    payload["pilot_window"] = window
    payload["observed_at_utc"] = observed_at
    if accepted:
        PilotObservation.parse(payload)
    else:
        with pytest.raises(PilotFailure):
            PilotObservation.parse(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["review"].update(
            {
                "reviewed_at_utc": "2026-09-05T23:00:01Z",
                "reviewer_role": "OWNER",
                "status": "HUMAN_REVIEW_COMPLETE",
            }
        ),
        lambda payload: payload["publication"].update(
            {"confirmed_at_utc": "2026-08-22T23:59:59Z"}
        ),
        lambda payload: metric_at(payload, "article_views").update(
            {"period_end": "2026-09-06"}
        ),
        lambda payload: metric_at(payload, "organic_clicks").update(
            {"period_start": "2026-08-22"}
        ),
        lambda payload: (
            metric_at(payload, "affiliate_clicks").update(
                {"period_end": "2026-09-05", "period_start": "2026-09-05"}
            )
            or payload.update({"observed_at_utc": "2026-09-04T23:59:59Z"})
        ),
    ],
)
def test_publication_review_and_metric_periods_are_temporally_bound(
    mutation: object,
) -> None:
    payload = complete(1)
    mutation(payload)  # type: ignore[operator]
    with pytest.raises(PilotFailure):
        PilotObservation.parse(payload)


def test_later_observation_cannot_change_pilot_window() -> None:
    first = PilotObservation.parse(example())
    ledger = append_observation(empty_ledger(), first)[0]
    later = example()
    later["observation_id"] = "PILOT-ARTICLE-02-PUBLICATION-V1"
    later["observed_at_utc"] = "2026-08-24T00:00:00Z"
    later["article"] = {
        "article_ref_sha256": None,
        "public_slug": "pilot-article-2",
        "slot": 2,
    }
    later["pilot_window"] = {
        "duration_days": 14,
        "end_exclusive_date": "2026-09-07",
        "start_date": "2026-08-24",
    }
    later["publication"] = {
        "confirmed_at_utc": "2026-08-24T00:00:00Z",
        "confirmed_by_role": "OWNER",
        "status": "HUMAN_CONFIRMED_PUBLISHED",
    }
    with pytest.raises(PilotFailure):
        append_observation(ledger, PilotObservation.parse(later))


@pytest.mark.parametrize(
    ("path", "field", "invalid"),
    [
        (("article_views",), "source_kind", "RAKUTEN_REPORT_AGGREGATE"),
        (("article_views",), "attribution_basis", "UNVERIFIED"),
        (("affiliate_clicks",), "source_kind", "WORDPRESS_ADMIN_AGGREGATE"),
        (("affiliate_clicks",), "attribution_basis", "OWNER_REPORTED_DIRECT"),
        (("organic_clicks",), "source_kind", "FIRST_PARTY_AGGREGATE"),
        (("organic_clicks",), "attribution_basis", "OWNER_REPORTED_DIRECT"),
        (
            ("revenue_jpy", "provider_total_jpy"),
            "source_kind",
            "SEARCH_CONSOLE_AGGREGATE",
        ),
        (
            ("revenue_jpy", "provider_total_jpy"),
            "attribution_basis",
            "OWNER_REPORTED_DIRECT",
        ),
        (
            ("revenue_jpy", "direct_jpy"),
            "attribution_basis",
            "OWNER_REPORTED_ESTIMATED",
        ),
        (
            ("revenue_jpy", "estimated_jpy"),
            "source_kind",
            "RAKUTEN_REPORT_AGGREGATE",
        ),
        (
            ("revenue_jpy", "unattributed_jpy"),
            "source_kind",
            "RAKUTEN_REPORT_AGGREGATE",
        ),
    ],
)
def test_metric_source_and_attribution_are_field_aware(
    path: tuple[str, ...], field: str, invalid: str
) -> None:
    payload = complete(1)
    metric_at(payload, *path)[field] = invalid
    with pytest.raises(PilotFailure):
        PilotObservation.parse(payload)


def test_unverified_metric_never_completes_pilot() -> None:
    payloads = [complete(slot) for slot in range(1, 6)]
    affiliate_clicks = metric_at(payloads[2], "affiliate_clicks")
    affiliate_clicks["state"] = "UNVERIFIED"
    affiliate_clicks["attribution_basis"] = "UNVERIFIED"
    report = build_report(ledger_for(payloads))
    assert report["decision"] == ImprovementDecision.INSUFFICIENT_EVIDENCE.value
    assert "COLLECT_AGGREGATED_METRICS" in report["proposal_candidates"]


def set_revenue(
    payload: dict[str, object],
    *,
    provider_total: int,
    direct: int,
    estimated: int,
    unattributed: int,
) -> None:
    for name, value in (
        ("provider_total_jpy", provider_total),
        ("direct_jpy", direct),
        ("estimated_jpy", estimated),
        ("unattributed_jpy", unattributed),
    ):
        metric = metric_at(payload, "revenue_jpy", name)
        metric["state"] = "OBSERVED_ZERO" if value == 0 else "OBSERVED_VALUE"
        metric["value"] = value


def test_reconciled_separate_revenue_buckets_complete_pilot() -> None:
    payloads = [complete(slot) for slot in range(1, 6)]
    for payload in payloads:
        set_revenue(
            payload,
            provider_total=100,
            direct=60,
            estimated=30,
            unattributed=10,
        )
    report = build_report(ledger_for(payloads))
    assert report["decision"] == ImprovementDecision.REVIEW_CANDIDATES_ONLY.value
    assert "RECONCILE_SEPARATE_REVENUE_BUCKETS" not in report["proposal_candidates"]
    first_article = report["articles"][0]
    revenue = first_article["metrics"]["revenue_jpy"]
    assert set(revenue) == {
        "direct_jpy",
        "estimated_jpy",
        "provider_total_jpy",
        "unattributed_jpy",
    }
    assert revenue["provider_total_jpy"]["value"] == 100
    assert revenue["direct_jpy"]["value"] == 60
    assert revenue["estimated_jpy"]["value"] == 30
    assert revenue["unattributed_jpy"]["value"] == 10


def test_unreconciled_or_unverified_revenue_is_advisory_only() -> None:
    payloads = [complete(slot) for slot in range(1, 6)]
    set_revenue(
        payloads[1],
        provider_total=100,
        direct=60,
        estimated=20,
        unattributed=10,
    )
    provider_total = metric_at(payloads[3], "revenue_jpy", "provider_total_jpy")
    provider_total["state"] = "UNVERIFIED"
    provider_total["attribution_basis"] = "UNVERIFIED"
    report = build_report(ledger_for(payloads))
    assert report["decision"] == ImprovementDecision.REVIEW_CANDIDATES_ONLY.value
    assert "RECONCILE_SEPARATE_REVENUE_BUCKETS" in report["proposal_candidates"]


@pytest.mark.parametrize("mutation", ["period", "provider_input"])
def test_revenue_reconciliation_requires_one_period_and_provider_input(
    mutation: str,
) -> None:
    payloads = [complete(slot) for slot in range(1, 6)]
    direct = metric_at(payloads[0], "revenue_jpy", "direct_jpy")
    if mutation == "period":
        direct["period_start"] = "2026-08-24"
    else:
        direct["input_sha256"] = "f" * 64
    report = build_report(ledger_for(payloads))
    assert report["decision"] == ImprovementDecision.REVIEW_CANDIDATES_ONLY.value
    assert "RECONCILE_SEPARATE_REVENUE_BUCKETS" in report["proposal_candidates"]


def test_unknown_revenue_does_not_gate_non_finance_pilot_review() -> None:
    payloads = [complete(slot) for slot in range(1, 6)]
    for payload in payloads:
        revenue = metric_at(payload, "revenue_jpy")
        for metric in revenue.values():
            assert type(metric) is dict
            metric.update(
                {
                    "attribution_basis": "NOT_APPLICABLE",
                    "input_sha256": None,
                    "period_end": None,
                    "period_start": None,
                    "source_kind": "NOT_CONNECTED",
                    "state": "NOT_OBSERVED",
                    "value": None,
                }
            )
    report = build_report(ledger_for(payloads))
    assert report["decision"] == ImprovementDecision.REVIEW_CANDIDATES_ONLY.value
    assert "RECONCILE_SEPARATE_REVENUE_BUCKETS" in report["proposal_candidates"]
    assert report["boundaries"]["finance_as_recommendation_input"] == "FORBIDDEN"


def test_provider_revenue_batch_cannot_be_reused_across_articles() -> None:
    first = PilotObservation.parse(complete(1))
    ledger = append_observation(empty_ledger(), first)[0]
    second_payload = complete(2)
    revenue = metric_at(second_payload, "revenue_jpy")
    for metric in revenue.values():
        assert type(metric) is dict
        metric["input_sha256"] = "1" * 64
    second = PilotObservation.parse(second_payload)
    with pytest.raises(PilotFailure):
        append_observation(ledger, second)


def test_generic_click_metric_is_rejected_as_ambiguous() -> None:
    payload = complete(1)
    metrics = payload["metrics"]
    assert type(metrics) is dict
    metrics["clicks"] = deepcopy(metrics["affiliate_clicks"])
    with pytest.raises(PilotFailure):
        PilotObservation.parse(payload)


def test_affiliate_destination_and_query_fields_are_rejected() -> None:
    payload = example()
    payload["affiliate_destination"] = "https://hb.afl.rakuten.co.jp/?pc=secret"
    with pytest.raises(PilotFailure):
        PilotObservation.parse(payload)


def test_runtime_manifest_matches_exact_closed_inventory() -> None:
    manifest_path = (
        ROOT / "changes/st-1704/owner-local-pilot-v1/runtime-manifest.v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "ST1704_OWNER_LOCAL_PILOT_RUNTIME_MANIFEST_V1"
    assert manifest["policy"] == PILOT_POLICY == builder.POLICY
    assert [entry["path"] for entry in manifest["paths"]] == list(builder.RUNTIME_PATHS)
    for entry in manifest["paths"]:
        raw = (ROOT / entry["path"]).read_bytes()
        assert entry["bytes"] == len(raw)
        assert entry["sha256"] == hashlib.sha256(raw).hexdigest()


def test_handoff_generated_and_domain_policy_are_semantically_equal() -> None:
    handoff = yaml.safe_load(
        (
            ROOT / "changes/st-1704/owner-local-pilot-v1/DESIGN_HANDOFF_V1.yaml"
        ).read_text(encoding="utf-8")
    )["DESIGN_HANDOFF_V1"]["decision"]
    projected = {
        "article_slots": handoff["article_slots"],
        "automatic_publication": handoff["automatic_publication"],
        "duration_days": handoff["duration_days"],
        "first_five_drafts": handoff["first_five_drafts"],
        "improvement_output": handoff["improvement_output"],
        "labor_cost_per_hour_jpy": handoff["owner_local_labor_cost_per_hour_jpy"],
        "monthly_incremental_cost_cap_jpy": handoff["monthly_incremental_cost_cap_jpy"],
        "nonessential_tracking": handoff["nonessential_tracking"],
        "site_origin": handoff["site_origin"],
    }
    assert projected == builder.POLICY == PILOT_POLICY


def test_base_ci_routes_story_test_and_generator_check() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    unit = makefile.split("\nci-unit:", 1)[1].split("\nci-contracts:", 1)[0]
    policy = makefile.split("\nci-repository-policy:", 1)[1].split("\nci-static:", 1)[0]
    assert unit.count("tests/st1704") == 1
    assert policy.count("scripts/build_st1704_owner_local_pilot.py --check") == 1
    assert "/usr/bin/env -i PATH=/usr/bin:/bin" in policy
    assert 'HOME="$(RAOS_REPOSITORY_ROOT)"' in policy
    assert "LANG=C LC_ALL=C TZ=UTC" in policy
    assert '"$(RAOS_REPOSITORY_ROOT)/.venv/bin/python" -B -I -S' in policy
    assert "$(UV_READONLY_RUN) python -B -I -S" not in policy


def test_generator_check_rejects_manifest_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    copied_root = copy_runtime_tree(tmp_path)
    copied_slice = copied_root / "changes/st-1704/owner-local-pilot-v1"
    copied_manifest = copied_slice / "runtime-manifest.v1.json"
    copied_manifest.write_bytes(copied_manifest.read_bytes() + b" ")
    monkeypatch.setattr(builder, "ROOT", copied_root)
    monkeypatch.setattr(builder, "SLICE_ROOT", copied_slice)
    monkeypatch.setattr(builder, "MANIFEST_PATH", copied_manifest)
    with pytest.raises(builder.BuildFailure):
        builder.generate(check=True)


@pytest.mark.parametrize("check", [True, False])
def test_generator_refuses_runtime_mutation_after_initial_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, check: bool
) -> None:
    copied_root = copy_runtime_tree(tmp_path)
    copied_slice = copied_root / "changes/st-1704/owner-local-pilot-v1"
    copied_manifest = copied_slice / "runtime-manifest.v1.json"
    target = copied_root / builder.RUNTIME_PATHS[0]
    original = builder._manifest_snapshot

    monkeypatch.setattr(builder, "ROOT", copied_root)
    monkeypatch.setattr(builder, "SLICE_ROOT", copied_slice)
    monkeypatch.setattr(builder, "MANIFEST_PATH", copied_manifest)

    def mutate_after_snapshot(
        root_fd: int,
    ) -> tuple[bytes, tuple[builder.RuntimeSnapshot, ...]]:
        manifest, snapshots = original(root_fd)
        target.write_bytes(target.read_bytes() + b"\n")
        return manifest, snapshots

    monkeypatch.setattr(builder, "_manifest_snapshot", mutate_after_snapshot)
    with pytest.raises(builder.BuildFailure):
        builder.generate(check=check)


def test_generator_stage_swap_rolls_back_to_previous_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    copied_root = copy_runtime_tree(tmp_path)
    copied_slice = copied_root / "changes/st-1704/owner-local-pilot-v1"
    copied_manifest = copied_slice / "runtime-manifest.v1.json"
    previous_manifest = copied_manifest.read_bytes()
    original_exchange = builder._rename_exchange
    raced = False

    monkeypatch.setattr(builder, "ROOT", copied_root)
    monkeypatch.setattr(builder, "SLICE_ROOT", copied_slice)
    monkeypatch.setattr(builder, "MANIFEST_PATH", copied_manifest)

    def replace_stage_before_exchange(parent_fd: int, left: str, right: str) -> None:
        nonlocal raced
        if not raced:
            raced = True
            os.rename(
                left,
                ".detached-generated-manifest",
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            replacement = os.open(
                left,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o644,
                dir_fd=parent_fd,
            )
            try:
                os.write(replacement, b'{"schema":"UNEXPECTED"}\n')
                os.fsync(replacement)
            finally:
                os.close(replacement)
        original_exchange(parent_fd, left, right)

    monkeypatch.setattr(builder, "_rename_exchange", replace_stage_before_exchange)
    with pytest.raises(builder.BuildFailure):
        builder.generate(check=False)
    assert raced
    assert copied_manifest.read_bytes() == previous_manifest
    assert (copied_slice / ".runtime-manifest.v1.json.preparing").is_file()


def test_generated_manifest_schema_accepts_example_and_rejects_unknown() -> None:
    manifest = json.loads(
        (
            ROOT / "changes/st-1704/owner-local-pilot-v1/runtime-manifest.v1.json"
        ).read_text(encoding="utf-8")
    )
    schema = manifest["observation_input_schema"]
    validator = Draft202012Validator(schema)
    assert not tuple(validator.iter_errors(example()))
    unknown = example()
    unknown["affiliate_url_query"] = "secret"
    assert tuple(validator.iter_errors(unknown))


def copy_runtime_tree(tmp_path: Path) -> Path:
    copied_root = tmp_path / "runtime-copy"
    copied_root.mkdir(mode=0o700)
    manifest_relative = Path(
        "changes/st-1704/owner-local-pilot-v1/runtime-manifest.v1.json"
    )
    root_fd = builder._open_absolute_directory(ROOT)
    try:
        rendered_manifest = builder._manifest_snapshot(root_fd)[0]
    finally:
        os.close(root_fd)
    manifest = json.loads(rendered_manifest)
    for entry in manifest["paths"]:
        relative = Path(entry["path"])
        target = copied_root / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    copied_manifest = copied_root / manifest_relative
    copied_manifest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    copied_manifest.write_bytes(rendered_manifest)
    return copied_root


def test_runtime_integrity_accepts_exact_copy_and_rejects_code_drift(
    tmp_path: Path,
) -> None:
    copied_root = copy_runtime_tree(tmp_path)
    _, root_identity = cli._verify_runtime_integrity(copied_root)
    root_stat = copied_root.stat()
    assert root_identity == (root_stat.st_dev, root_stat.st_ino)
    domain = copied_root / "python/raos/domain/editorial/owner_local_pilot.py"
    domain.write_bytes(domain.read_bytes() + b"\n")
    with pytest.raises(cli._RuntimeFailure) as captured:
        cli._verify_runtime_integrity(copied_root)
    assert str(captured.value) == "OWNER_LOCAL_PILOT_RUNTIME_INVALID"


def test_runtime_integrity_rejects_manifest_contract_drift(tmp_path: Path) -> None:
    copied_root = copy_runtime_tree(tmp_path)
    manifest = (
        copied_root / "changes/st-1704/owner-local-pilot-v1/runtime-manifest.v1.json"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["unexpected"] = "drift"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(cli._RuntimeFailure) as captured:
        cli._verify_runtime_integrity(copied_root)
    assert str(captured.value) == "OWNER_LOCAL_PILOT_RUNTIME_INVALID"


def test_execute_rejects_repository_root_swap_after_runtime_verification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    copied_root = copy_runtime_tree(tmp_path)
    sources, root_identity = cli._verify_runtime_integrity(copied_root)
    verified_root = tmp_path / "verified-runtime-copy"
    copied_root.rename(verified_root)
    copied_root.mkdir(mode=0o700)
    monkeypatch.setattr(cli, "OWNER_REPOSITORY_ROOT", copied_root)
    runtime_names = {
        "raos",
        "raos.domain",
        "raos.domain.editorial",
        "raos.ports",
        "raos.application",
        "raos.application.editorial",
        "raos.adapters",
        *(name for name, _ in cli._MODULE_PATHS),
    }
    saved_modules = {name: sys.modules.get(name) for name in runtime_names}
    try:
        with pytest.raises(cli._CommandFailure) as captured:
            cli._execute("init", sources, root_identity)
    finally:
        for name, module in saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    assert str(captured.value) == "STORE_UNSAFE"
    assert not (copied_root / ".secrets").exists()
    assert not (verified_root / ".secrets").exists()


def test_loaded_domain_policy_must_match_manifest_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    copied_root = copy_runtime_tree(tmp_path)
    domain = copied_root / "python/raos/domain/editorial/owner_local_pilot.py"
    source = domain.read_text(encoding="utf-8")
    mutated = source.replace('"duration_days": 14,', '"duration_days": 15,', 1)
    assert mutated != source
    domain.write_text(mutated, encoding="utf-8")
    copied_slice = copied_root / "changes/st-1704/owner-local-pilot-v1"
    monkeypatch.setattr(builder, "ROOT", copied_root)
    monkeypatch.setattr(builder, "SLICE_ROOT", copied_slice)
    monkeypatch.setattr(
        builder,
        "MANIFEST_PATH",
        copied_slice / "runtime-manifest.v1.json",
    )
    builder.generate(check=False)
    sources, root_identity = cli._verify_runtime_integrity(copied_root)
    runtime_names = {
        "raos",
        "raos.domain",
        "raos.domain.editorial",
        "raos.ports",
        "raos.application",
        "raos.application.editorial",
        "raos.adapters",
        *(name for name, _ in cli._MODULE_PATHS),
    }
    saved_modules = {name: sys.modules.get(name) for name in runtime_names}
    try:
        with pytest.raises(cli._RuntimeFailure) as captured:
            cli._execute("doctor", sources, root_identity)
    finally:
        for name, module in saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    assert str(captured.value) == "OWNER_LOCAL_PILOT_RUNTIME_INVALID"


def clean_python_command(
    script: Path, command: str, *, cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            PINNED_PYTHON.as_posix(),
            "-B",
            "-I",
            "-S",
            "-X",
            "pycache_prefix=/dev/null",
            script.as_posix(),
            command,
        ],
        cwd=cwd,
        env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin", "TZ": "UTC"},
        check=False,
        capture_output=True,
        text=True,
    )


def install_import_tripwire(root: Path, marker: Path) -> None:
    adapter = root / "python/raos/adapters/owner_local_pilot_json.py"
    adapter.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    adapter.write_text(
        "from pathlib import Path\n"
        f"Path({marker.as_posix()!r}).write_text('imported', encoding='utf-8')\n"
        "raise RuntimeError('tripwire imported')\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("linked", [False, True])
def test_cli_out_of_root_or_symlink_refuses_before_local_import(
    linked: bool, tmp_path: Path
) -> None:
    copied_root = tmp_path / ("linked-cli" if linked else "copied-cli")
    script = copied_root / "scripts/st1704_owner_local_pilot.py"
    script.parent.mkdir(mode=0o700, parents=True)
    source = ROOT / "scripts/st1704_owner_local_pilot.py"
    if linked:
        script.symlink_to(source)
    else:
        shutil.copyfile(source, script)
    marker = tmp_path / "local-import-executed"
    install_import_tripwire(copied_root, marker)
    result = clean_python_command(script, "doctor", cwd=copied_root)
    assert result.returncode == 2
    assert not marker.exists()
    refusal = json.loads(result.stdout)
    assert refusal["status"] == "REFUSED"
    assert refusal["code"] == "OWNER_LOCAL_PILOT_RUNTIME_INVALID"


def test_make_check_ignores_hostile_python_startup_and_user_site(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "ambient-python-executed"
    poison = tmp_path / "poison"
    poison.mkdir(mode=0o700)
    tripwire = (
        "from pathlib import Path\n"
        f"Path({marker.as_posix()!r}).write_text('executed', encoding='utf-8')\n"
    )
    (poison / "sitecustomize.py").write_text(tripwire, encoding="utf-8")
    startup = tmp_path / "startup.py"
    startup.write_text(tripwire, encoding="utf-8")
    user_site = tmp_path / "user-base/lib/python3.14/site-packages"
    user_site.mkdir(mode=0o700, parents=True)
    (user_site / "sitecustomize.py").write_text(tripwire, encoding="utf-8")
    makefile = ROOT / "changes/st-1704/owner-local-pilot-v1/Makefile"
    result = subprocess.run(
        ["/usr/bin/make", "-f", makefile.as_posix(), "check"],
        cwd=ROOT,
        env={
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
            "PYTHONNOUSERSITE": "0",
            "PYTHONPATH": poison.as_posix(),
            "PYTHONSTARTUP": startup.as_posix(),
            "PYTHONUSERBASE": (tmp_path / "user-base").as_posix(),
            "TZ": "UTC",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ST1704_OWNER_LOCAL_PILOT_BUILD_OK" in result.stdout
    assert not marker.exists()


def test_store_api_has_no_caller_selected_path_or_external_action() -> None:
    assert tuple(inspect.signature(OwnerLocalPilotJsonStore.read).parameters) == (
        "self",
    )
    assert tuple(
        inspect.signature(OwnerLocalPilotJsonStore.read_observation).parameters
    ) == ("self",)
    assert tuple(inspect.signature(OwnerLocalPilotJsonStore.append).parameters) == (
        "self",
        "observation",
    )
    source = inspect.getsource(OwnerLocalPilotJsonStore)
    for forbidden in (
        "requests.",
        "urllib",
        "socket.",
        "wordpress",
        "publish",
        "sendBeacon",
        "fetch(",
        "affiliate_url",
    ):
        assert forbidden not in source
