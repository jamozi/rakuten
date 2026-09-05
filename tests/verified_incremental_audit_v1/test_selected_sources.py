"""Selected source replay using real private readers and synthetic captures only."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path

import pytest

from raos.adapters import self_hosted_editorial_source_capture as capture
from raos.adapters.self_hosted_editorial_pilot_json import (
    source_body_relative_path,
    source_evidence_relative_path,
)
from raos.application.editorial import verified_incremental_sources_v1 as sources
from raos.domain.editorial.self_hosted_editorial_pilot import canonical_json_bytes

ARTICLE = "st1703-first-suitcase-comparison"
OTHER_ARTICLE = "st1704-portable-power-station-guide"
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
FRAGMENT = "Synthetic official dimension 21 cm"
OTHER_FRAGMENT = "Synthetic official capacity 30 L"
BODY = f"<!doctype html><html><body><p>{FRAGMENT}</p><p>{OTHER_FRAGMENT}</p></body></html>".encode()


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    repository = tmp_path / "contracts"
    evidence = tmp_path / "captures"
    repository.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    target = capture.SourceCaptureTarget(
        "SRC-SHARED",
        "https://official.example/specifications",
        "official.example",
        "/specifications",
        date(2026, 9, 4),
        None,
        "READY",
        (
            capture.SourceLocator("CLAIM-A", "a" * 64, (FRAGMENT,)),
            capture.SourceLocator("CLAIM-B", "b" * 64, (OTHER_FRAGMENT,)),
        ),
    )
    other = replace(target, source_ref="SRC-UNSELECTED", locators=(target.locators[1],))
    plan = capture.SourceCapturePlan(
        (target, other),
        ((ARTICLE, ("SRC-SHARED",)), (OTHER_ARTICLE, ("SRC-SHARED", "SRC-UNSELECTED"))),
    )
    registry = {
        "source_packets": [
            {
                "article_id": ARTICLE,
                "claims": [{"claim_id": "CLAIM-A", "evidence_refs": ["SRC-SHARED"]}],
            },
            {
                "article_id": OTHER_ARTICLE,
                "claims": [
                    {
                        "claim_id": "CLAIM-B",
                        "evidence_refs": ["SRC-SHARED", "SRC-UNSELECTED"],
                    }
                ],
            },
        ]
    }
    registry_path = repository / capture.SOURCE_REGISTRY_RELATIVE_PATH
    registry_path.parent.mkdir(parents=True)
    registry_path.write_bytes(canonical_json_bytes(registry))
    (repository / capture.LOCATOR_CONTRACT_RELATIVE_PATH).write_bytes(
        b'{"test_contract":true}'
    )
    monkeypatch.setattr(sources, "load_source_capture_plan", lambda root: plan)
    capture._persist_capture(
        evidence,
        capture.FetchedSource(target, "2026-09-05T11:00:00Z", "text/html", BODY),
    )
    return repository, evidence, plan


def replay(recorded, article_ids=(ARTICLE,), now=NOW):
    repository, evidence, _plan = recorded
    return sources.validate_selected_official_sources(
        repository, evidence, article_ids, now
    )


def overwrite_capture(recorded, **changes):
    _repository, evidence, plan = recorded
    fetched = capture.FetchedSource(
        plan.target("SRC-SHARED"), "2026-09-05T11:00:00Z", "text/html", BODY
    )
    capture._persist_capture(evidence, replace(fetched, **changes))


def test_selected_capture_verifies_without_other_article_files(recorded):
    result = replay(recorded).require_complete()
    assert result.status == "VERIFIED"
    assert set(result.sources) == {"SRC-SHARED"}
    assert result.article_claim_sources == {ARTICLE: {"CLAIM-A": ("SRC-SHARED",)}}
    assert result.article_source_refs == {ARTICLE: ("SRC-SHARED",)}
    assert result.expires_at == "2026-09-06T11:00:00Z"
    assert len(result.source_receipt_sha256["SRC-SHARED"]) == 64
    raw = (recorded[1] / source_evidence_relative_path("SRC-SHARED")).read_bytes()
    assert (
        result.sources["SRC-SHARED"].evidence_file_sha256
        == hashlib.sha256(raw).hexdigest()
    )
    document = result.to_document()
    assert document["publication_authority"] is False
    assert document["network_requests"] == document["external_writes"] == 0
    serialized = json.dumps(document)
    assert FRAGMENT not in serialized and OTHER_FRAGMENT not in serialized
    assert "https://" not in serialized and str(recorded[1]) not in serialized
    assert "owner_attested" not in serialized


def test_other_missing_article_is_issues_not_a_full_portfolio_gate(recorded):
    result = replay(recorded, (ARTICLE, OTHER_ARTICLE))
    assert result.status == "BLOCKED" and result.expires_at is None
    assert set(result.sources) == {"SRC-SHARED"}
    assert [issue.code for issue in result.issues] == ["CAPTURE_MISSING"]
    assert result.issues[0].article_ids == (OTHER_ARTICLE,)
    with pytest.raises(
        sources.SelectedOfficialSourcesFailure, match="SELECTED_SET_INCOMPLETE"
    ):
        result.require_complete()


@pytest.mark.parametrize(
    "capture_time,code",
    [
        ("2026-09-04T12:00:00Z", "CAPTURE_EXPIRED_OR_FUTURE"),
        ("2026-09-04T11:59:59Z", "CAPTURE_EXPIRED_OR_FUTURE"),
        ("2026-09-05T12:00:01Z", "CAPTURE_EXPIRED_OR_FUTURE"),
        ("2026-09-03T12:00:00Z", "CAPTURE_BEFORE_OBSERVED_FLOOR"),
    ],
)
def test_24_hour_floor_future_and_observed_dates_are_enforced(
    recorded, capture_time, code
):
    overwrite_capture(recorded, retrieved_at=capture_time)
    result = replay(recorded)
    assert result.status == "BLOCKED" and result.issues[0].code == code


def test_just_inside_24_hours_is_verified(recorded):
    overwrite_capture(recorded, retrieved_at="2026-09-04T12:00:01Z")
    assert replay(recorded).status == "VERIFIED"


@pytest.mark.parametrize(
    "change,code",
    [
        (
            {
                "url": "https://different.example/specifications",
                "host": "different.example",
            },
            "TARGET_MISMATCH",
        ),
        (
            {
                "locators": (
                    capture.SourceLocator("CLAIM-A", "c" * 64, (FRAGMENT,)),
                    capture.SourceLocator("CLAIM-B", "b" * 64, (OTHER_FRAGMENT,)),
                )
            },
            "CURRENT_LOCATOR_MISMATCH",
        ),
        (
            {
                "locators": (
                    capture.SourceLocator("CLAIM-A", "a" * 64, (OTHER_FRAGMENT,)),
                    capture.SourceLocator("CLAIM-B", "b" * 64, (OTHER_FRAGMENT,)),
                )
            },
            "CURRENT_LOCATOR_MISMATCH",
        ),
        (
            {"locators": (capture.SourceLocator("CLAIM-A", "a" * 64, (FRAGMENT,)),)},
            "CURRENT_LOCATOR_MISMATCH",
        ),
    ],
)
def test_current_target_or_locator_drift_is_rejected_despite_valid_capture(
    recorded, change, code
):
    target = replace(recorded[2].target("SRC-SHARED"), **change)
    overwrite_capture(recorded, target=target)
    assert replay(recorded).issues[0].code == code


def test_media_type_is_compared_to_current_plan(recorded, monkeypatch):
    plan = recorded[2]
    target = replace(
        plan.target("SRC-SHARED"), media_type="application/pdf", charset=None
    )
    monkeypatch.setattr(
        sources, "load_source_capture_plan", lambda _: replace(plan, targets=(target,))
    )
    assert replay(recorded).issues[0].code == "TARGET_MISMATCH"


def test_javascript_is_not_relabelled_to_make_old_reader_accept_it(
    recorded, monkeypatch
):
    plan = recorded[2]
    target = replace(plan.target("SRC-SHARED"), media_type="text/javascript")
    monkeypatch.setattr(
        sources, "load_source_capture_plan", lambda _: replace(plan, targets=(target,))
    )
    assert replay(recorded).issues[0].code == "MEDIA_TYPE_UNSUPPORTED_BY_READER"


def test_pending_locators_do_not_open_raw_captures(recorded, monkeypatch):
    plan = recorded[2]
    target = replace(
        plan.target("SRC-SHARED"), locator_status="LOCATORS_PENDING", locators=()
    )
    monkeypatch.setattr(
        sources, "load_source_capture_plan", lambda _: replace(plan, targets=(target,))
    )
    monkeypatch.setattr(
        sources,
        "read_official_source_capture_evidence",
        lambda *_a, **_k: pytest.fail("pending raw capture read"),
    )
    assert replay(recorded).issues[0].code == "LOCATORS_PENDING"


def test_body_hash_tampering_is_replayed_not_trusted(recorded):
    body_path = recorded[1] / source_body_relative_path("SRC-SHARED")
    body_path.write_bytes(BODY + b" changed")
    assert replay(recorded).issues[0].code == "CAPTURE_INVALID"


def test_duplicate_body_fragment_even_after_hash_updates_is_invalid(recorded):
    evidence_path = recorded[1] / source_evidence_relative_path("SRC-SHARED")
    body_path = recorded[1] / source_body_relative_path("SRC-SHARED")
    duplicated = BODY.replace(b"</body>", f"<p>{FRAGMENT}</p></body>".encode())
    body_path.write_bytes(duplicated)
    document = json.loads(evidence_path.read_bytes())
    document["body_sha256"] = hashlib.sha256(duplicated).hexdigest()
    material = {
        key: value
        for key, value in document.items()
        if key not in {"locators", "response_sha256"}
    }
    document["response_sha256"] = hashlib.sha256(
        canonical_json_bytes(material)
    ).hexdigest()
    evidence_path.write_bytes(canonical_json_bytes(document))
    assert replay(recorded).issues[0].code == "CAPTURE_INVALID"


@pytest.mark.parametrize("unsafe", ["mode", "symlink", "hardlink"])
def test_unsafe_private_files_are_rejected(recorded, unsafe):
    evidence_path = recorded[1] / source_evidence_relative_path("SRC-SHARED")
    if unsafe == "mode":
        evidence_path.chmod(0o644)
    elif unsafe == "symlink":
        moved = evidence_path.with_name("synthetic-moved.json")
        evidence_path.rename(moved)
        evidence_path.symlink_to(moved.name)
    else:
        evidence_path.with_name("synthetic-link.json").hardlink_to(evidence_path)
    assert replay(recorded).status == "BLOCKED"


def test_evidence_root_symlink_rejected(recorded):
    repository, evidence, plan = recorded
    linked = evidence.with_name("linked-captures")
    linked.symlink_to(evidence, target_is_directory=True)
    assert replay((repository, linked, plan)).status == "BLOCKED"


def test_replaced_capture_during_replay_is_not_bound(recorded, monkeypatch):
    original = sources.read_official_source_capture_evidence
    calls = 0

    def changing(root, *, source_ref):
        nonlocal calls
        calls += 1
        if calls == 2:
            overwrite_capture(recorded, retrieved_at="2026-09-05T11:01:00Z")
        return original(root, source_ref=source_ref)

    monkeypatch.setattr(sources, "read_official_source_capture_evidence", changing)
    assert replay(recorded).issues[0].code == "CAPTURE_CHANGED_DURING_READ"


def test_contract_drift_during_load_is_fatal(recorded, monkeypatch):
    def changed(root):
        (root / capture.LOCATOR_CONTRACT_RELATIVE_PATH).write_bytes(
            b'{"test_contract":false}'
        )
        return recorded[2]

    monkeypatch.setattr(sources, "load_source_capture_plan", changed)
    with pytest.raises(
        sources.SelectedOfficialSourcesFailure, match="CONTRACT_CHANGED"
    ):
        replay(recorded)


@pytest.mark.parametrize(
    "article_ids", [(), (ARTICLE, ARTICLE), ("unknown",), ("../escape",), ARTICLE]
)
def test_invalid_article_selections_never_expand_capture_scope(recorded, article_ids):
    with pytest.raises(sources.SelectedOfficialSourcesFailure):
        replay(recorded, article_ids)


def test_naive_clock_rejected(recorded):
    with pytest.raises(sources.SelectedOfficialSourcesFailure, match="ARGUMENT"):
        replay(recorded, now=NOW.replace(tzinfo=None))


def test_selected_real_contract_does_not_require_unselected_capture_files(tmp_path):
    repository = Path(__file__).resolve().parents[2]
    result = sources.validate_selected_official_sources(
        repository, tmp_path, (ARTICLE,), NOW
    )
    plan = capture.load_source_capture_plan(repository)
    expected = {target.source_ref for target in plan.for_article(ARTICLE)}
    assert {issue.source_ref for issue in result.issues} == expected
    assert set(result.article_claim_sources) == {ARTICLE}
    assert len(result.issues) < len(plan.targets)


def test_expiry_does_not_use_evaluation_time_to_refresh_capture(recorded):
    first = replay(recorded)
    later = replay(recorded, now=NOW + timedelta(minutes=30))
    assert first.expires_at == later.expires_at
    assert first.source_receipt_sha256 == later.source_receipt_sha256
