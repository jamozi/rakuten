from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import socket

import pytest

from raos.adapters.owner_local_pilot_json import (
    INPUT_FILE,
    LEDGER_FILE,
    MAX_INPUT_BYTES,
    OwnerLocalPilotJsonStore,
    PILOT_DIRECTORY,
    STAGE_FILE,
    decode_strict_json,
)
from raos.application.editorial.owner_local_pilot import OwnerLocalPilotService
from raos.domain.editorial.owner_local_pilot import (
    AppendDisposition,
    ImprovementDecision,
    MetricObservation,
    PILOT_POLICY,
    PilotFailure,
    PilotFailureCode,
    PilotObservation,
    append_observation,
    build_report,
    canonical_bytes,
    empty_ledger,
    parse_ledger,
)


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = (
    ROOT / "changes/st-1704/owner-local-pilot-v1/examples/"
    "bootstrap-first-publication.v1.json"
)


def example() -> dict[str, object]:
    value = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def setup_store(tmp_path: Path) -> OwnerLocalPilotJsonStore:
    store = OwnerLocalPilotJsonStore(tmp_path)
    ledger, created = store.initialize()
    assert created
    assert not ledger.events
    return store


def write_input(tmp_path: Path, payload: dict[str, object]) -> Path:
    target = tmp_path / ".secrets" / PILOT_DIRECTORY / INPUT_FILE
    target.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    target.chmod(0o600)
    return target


def complete(slot: int, *, critical: int = 0) -> dict[str, object]:
    payload = example()
    payload["observation_id"] = f"PILOT-ARTICLE-{slot:02d}-COMPLETE-V1"
    payload["observed_at_utc"] = "2026-09-05T23:00:00Z"
    payload["article"] = {
        "article_ref_sha256": None,
        "public_slug": f"pilot-article-{slot}",
        "slot": slot,
    }
    payload["review"] = {
        "reviewed_at_utc": "2026-08-23T01:00:00Z",
        "reviewer_role": "OWNER",
        "status": "HUMAN_REVIEW_COMPLETE",
    }
    payload["work_minutes"] = {"state": "OBSERVED_VALUE", "value": 60}
    payload["incremental_cost_jpy"] = {
        "state": "OBSERVED_VALUE",
        "value": 100,
    }
    payload["defects"] = {
        "critical": {
            "state": "OBSERVED_ZERO" if critical == 0 else "OBSERVED_VALUE",
            "value": critical,
        },
        "major": {"state": "OBSERVED_ZERO", "value": 0},
        "minor": {"state": "OBSERVED_ZERO", "value": 0},
    }
    metric = {
        "input_sha256": f"{slot}" * 64,
        "period_end": "2026-09-05",
        "period_start": "2026-08-23",
        "state": "OBSERVED_ZERO",
        "value": 0,
    }
    payload["metrics"] = {
        "article_views": {
            **deepcopy(metric),
            "attribution_basis": "NOT_APPLICABLE",
            "source_kind": "WORDPRESS_ADMIN_AGGREGATE",
        },
        "affiliate_clicks": {
            **deepcopy(metric),
            "attribution_basis": "NOT_APPLICABLE",
            "source_kind": "FIRST_PARTY_AGGREGATE",
        },
        "organic_clicks": {
            **deepcopy(metric),
            "attribution_basis": "NOT_APPLICABLE",
            "source_kind": "SEARCH_CONSOLE_AGGREGATE",
        },
        "revenue_jpy": {
            "provider_total_jpy": {
                **deepcopy(metric),
                "attribution_basis": "OWNER_REPORTED_PROVIDER_TOTAL",
                "source_kind": "RAKUTEN_REPORT_AGGREGATE",
            },
            "direct_jpy": {
                **deepcopy(metric),
                "attribution_basis": "OWNER_REPORTED_DIRECT",
                "source_kind": "RAKUTEN_REPORT_AGGREGATE",
            },
            "estimated_jpy": {
                **deepcopy(metric),
                "attribution_basis": "OWNER_REPORTED_ESTIMATED",
                "source_kind": "OWNER_MANUAL_AGGREGATE",
            },
            "unattributed_jpy": {
                **deepcopy(metric),
                "attribution_basis": "OWNER_REPORTED_UNATTRIBUTED",
                "source_kind": "OWNER_MANUAL_AGGREGATE",
            },
        },
    }
    return payload


def observation_metrics(
    observation: PilotObservation,
) -> tuple[MetricObservation, ...]:
    return (
        observation.article_views,
        observation.affiliate_clicks,
        observation.organic_clicks,
        observation.revenue_jpy.provider_total_jpy,
        observation.revenue_jpy.direct_jpy,
        observation.revenue_jpy.estimated_jpy,
        observation.revenue_jpy.unattributed_jpy,
    )


def test_policy_is_exact_owner_local_decision() -> None:
    assert PILOT_POLICY == {
        "article_slots": 5,
        "automatic_publication": "DISABLED",
        "duration_days": 14,
        "first_five_drafts": "CODEX_NOT_OPENAI_API",
        "improvement_output": "PROPOSAL_AND_DIFF_ONLY",
        "labor_cost_per_hour_jpy": 3000,
        "monthly_incremental_cost_cap_jpy": 2000,
        "nonessential_tracking": "DISABLED_OD_012",
        "site_origin": "https://kurashinoshirube.com",
    }


def test_first_publication_bootstrap_keeps_metrics_not_observed() -> None:
    observation = PilotObservation.parse(example())
    assert observation.publication.status.value == "HUMAN_CONFIRMED_PUBLISHED"
    assert observation.review.status.value == "NOT_OBSERVED"
    assert observation.pilot_window.payload() == {
        "duration_days": 14,
        "end_exclusive_date": "2026-09-06",
        "start_date": "2026-08-23",
    }
    for metric in observation_metrics(observation):
        assert metric.state.value == "NOT_OBSERVED"
        assert metric.value is None
        assert metric.period_start is None
        assert metric.input_sha256 is None
    report = build_report(append_observation(empty_ledger(), observation)[0])
    assert report["decision"] == ImprovementDecision.INSUFFICIENT_EVIDENCE.value
    assert report["status"] == {
        "ST-1704": "NOT_STARTED",
        "TST-018": "NOT_EXECUTED",
        "TST-020": "NOT_EXECUTED",
        "TST-032": "NOT_EXECUTED",
        "production": "NOT_READY",
    }


def test_explicit_zero_is_not_unknown() -> None:
    unknown = PilotObservation.parse(example())
    zero = PilotObservation.parse(complete(1))
    assert unknown.article_views.value is None
    assert unknown.article_views.state.value == "NOT_OBSERVED"
    assert zero.article_views.value == 0
    assert zero.article_views.state.value == "OBSERVED_ZERO"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"email": "owner@example.test"}),
        lambda value: value["article"].update(
            {"public_slug": "https://example.test/a?affiliate=secret"}
        ),
        lambda value: value["metrics"]["article_views"].update({"raw_ip": "127.0.0.1"}),
        lambda value: value["metrics"]["article_views"].update(
            {"source_kind": "GA4_LIVE"}
        ),
        lambda value: value["metrics"]["article_views"].update(
            {"state": "OBSERVED_ZERO", "value": None}
        ),
        lambda value: value["metrics"]["article_views"].update(
            {"state": "NOT_OBSERVED", "value": 0}
        ),
        lambda value: value["metrics"].update(
            {"clicks": deepcopy(value["metrics"]["affiliate_clicks"])}
        ),
    ],
)
def test_rejects_sensitive_unknown_or_state_confusion(mutation: object) -> None:
    payload = example()
    mutation(payload)  # type: ignore[operator]
    with pytest.raises(PilotFailure) as captured:
        PilotObservation.parse(payload)
    assert str(captured.value) == "INVALID_DOCUMENT"
    assert "owner@example" not in repr(captured.value)


def test_duplicate_json_key_and_float_are_rejected() -> None:
    with pytest.raises(PilotFailure):
        decode_strict_json(b'{"schema":"x","schema":"y"}')
    with pytest.raises(PilotFailure):
        decode_strict_json(b'{"value":1.0}')


def test_initialize_record_replay_and_report_are_local(tmp_path: Path) -> None:
    store = setup_store(tmp_path)
    write_input(tmp_path, example())
    service = OwnerLocalPilotService(store=store, observation_input=store)
    recorded = service.record()
    assert recorded["disposition"] == AppendDisposition.APPENDED.value
    replayed = service.record()
    assert replayed["disposition"] == AppendDisposition.REPLAYED.value
    assert replayed["event_count"] == 1
    doctor = service.doctor()
    assert doctor["writes"] == 0
    assert doctor["network_requests"] == 0
    report = service.report()
    assert report["event_count"] == 1
    assert report["boundaries"] == {
        "analytics_activation": "NOT_EXECUTED",
        "automatic_publication": "DISABLED",
        "finance_as_recommendation_input": "FORBIDDEN",
        "network_requests": 0,
        "provider_proof": "NOT_EXECUTED",
        "tracking": "DISABLED_OD_012",
        "wordpress_writes": 0,
    }


def test_same_id_changed_content_is_rejected_without_write(tmp_path: Path) -> None:
    store = setup_store(tmp_path)
    original = example()
    write_input(tmp_path, original)
    store.append(store.read_observation())
    ledger_path = tmp_path / ".secrets" / PILOT_DIRECTORY / LEDGER_FILE
    before = ledger_path.read_bytes()
    changed = example()
    changed["observed_at_utc"] = "2026-08-23T00:00:01Z"
    write_input(tmp_path, changed)
    with pytest.raises(PilotFailure) as captured:
        store.append(store.read_observation())
    assert captured.value.code is PilotFailureCode.OBSERVATION_ID_CONFLICT
    assert ledger_path.read_bytes() == before


def test_tampered_chain_is_rejected(tmp_path: Path) -> None:
    store = setup_store(tmp_path)
    write_input(tmp_path, example())
    store.append(store.read_observation())
    ledger_path = tmp_path / ".secrets" / PILOT_DIRECTORY / LEDGER_FILE
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["events"][0]["observation"]["observed_at_utc"] = "2026-08-23T00:00:01Z"
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")
    ledger_path.chmod(0o600)
    with pytest.raises(PilotFailure) as captured:
        store.read()
    assert captured.value.code is PilotFailureCode.LEDGER_TAMPERED


@pytest.mark.parametrize("invalid_sequence", [True, False])
def test_ledger_sequence_rejects_boolean_type_confusion(
    invalid_sequence: bool,
) -> None:
    ledger = append_observation(
        empty_ledger(),
        PilotObservation.parse(example()),
    )[0]
    payload = ledger.payload()
    payload["events"][0]["sequence"] = invalid_sequence
    with pytest.raises(PilotFailure) as captured:
        parse_ledger(payload)
    assert captured.value.code is PilotFailureCode.LEDGER_TAMPERED


def test_reports_stop_for_critical_defect() -> None:
    ledger = empty_ledger()
    for slot in range(1, 6):
        observation = PilotObservation.parse(
            complete(slot, critical=1 if slot == 3 else 0)
        )
        ledger = append_observation(ledger, observation)[0]
    report = build_report(ledger)
    assert report["decision"] == ImprovementDecision.STOP_AND_REVIEW.value
    assert "REVIEW_MAJOR_MINOR_DEFECTS" not in report["proposal_candidates"]


def test_complete_zero_dataset_is_review_candidates_only_and_deterministic() -> None:
    ledger = empty_ledger()
    for slot in range(1, 6):
        ledger = append_observation(ledger, PilotObservation.parse(complete(slot)))[0]
    first = build_report(ledger)
    second = build_report(parse_ledger(ledger.payload()))
    assert first == second
    assert first["decision"] == ImprovementDecision.REVIEW_CANDIDATES_ONLY.value
    assert first["proposal_candidates"] == []


def test_doctor_and_report_do_not_change_files(tmp_path: Path) -> None:
    store = setup_store(tmp_path)
    write_input(tmp_path, example())
    store.append(store.read_observation())
    service = OwnerLocalPilotService(store=store, observation_input=store)
    directory = tmp_path / ".secrets" / PILOT_DIRECTORY

    def snapshot() -> dict[str, tuple[int, int, int, int]]:
        return {
            path.name: (
                path.lstat().st_ino,
                path.lstat().st_size,
                path.lstat().st_mtime_ns,
                path.lstat().st_ctime_ns,
            )
            for path in directory.iterdir()
        }

    before = snapshot()
    service.doctor()
    service.report()
    assert snapshot() == before


@pytest.mark.parametrize("unsafe", ["mode", "hardlink", "symlink"])
def test_rejects_unsafe_ledger_file(tmp_path: Path, unsafe: str) -> None:
    store = setup_store(tmp_path)
    ledger = tmp_path / ".secrets" / PILOT_DIRECTORY / LEDGER_FILE
    if unsafe == "mode":
        ledger.chmod(0o644)
    elif unsafe == "hardlink":
        os.link(ledger, ledger.with_name("ledger-copy"))
    else:
        raw = ledger.read_bytes()
        ledger.unlink()
        outside = tmp_path / "outside-ledger"
        outside.write_bytes(raw)
        outside.chmod(0o600)
        ledger.symlink_to(outside)
    with pytest.raises(PilotFailure) as captured:
        store.read()
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE


def test_rejects_symlinked_pilot_directory(tmp_path: Path) -> None:
    secrets = tmp_path / ".secrets"
    secrets.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (secrets / PILOT_DIRECTORY).symlink_to(outside, target_is_directory=True)
    with pytest.raises(PilotFailure) as captured:
        OwnerLocalPilotJsonStore(tmp_path).initialize()
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE


def test_rejects_oversized_input_before_decode(tmp_path: Path) -> None:
    store = setup_store(tmp_path)
    target = write_input(tmp_path, example())
    target.write_bytes(b"{" + b" " * MAX_INPUT_BYTES + b"}")
    target.chmod(0o600)
    with pytest.raises(PilotFailure) as captured:
        store.read_observation()
    assert captured.value.code is PilotFailureCode.STORE_UNSAFE


def test_read_only_operations_require_explicit_recovery(tmp_path: Path) -> None:
    store = setup_store(tmp_path)
    stage = tmp_path / ".secrets" / PILOT_DIRECTORY / STAGE_FILE
    stage.write_bytes(canonical_bytes(empty_ledger().payload()) + b"\n")
    stage.chmod(0o600)
    with pytest.raises(PilotFailure) as captured:
        store.read()
    assert captured.value.code is PilotFailureCode.RECOVERY_REQUIRED
    ledger, created = store.initialize()
    assert not created
    assert not ledger.events
    assert not stage.exists()


def test_no_network_is_needed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def denied(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket, "socket", denied)
    store = setup_store(tmp_path)
    write_input(tmp_path, example())
    service = OwnerLocalPilotService(store=store, observation_input=store)
    service.record()
    service.doctor()
    service.report()
