"""Owner generation, provenance, and recorded binding checks for ST-1403."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from collections.abc import Callable
from typing import cast

import pytest

from raos.adapters.recorded_refresh_proposal import (
    RecordedRefreshProposalAdapter,
    RecordedRefreshProposalBinding,
    load_recorded_refresh_proposal_bindings,
)
from raos.application.freshness.refresh_proposal import (
    RefreshProposalService,
    bind_refresh_proposal_request,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.freshness.refresh_proposal import (
    RefreshProposalFailure,
    RefreshProposalRequest,
    build_refresh_proposal,
)

from .support import (
    freshness_request,
    freshness_result,
    policy_result,
    proposal_candidate,
    valid_policy_input,
)

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts/build_st1403_refresh_proposal_runtime.py"
CONTRACT = ROOT / "changes/st-1403/contracts/refresh-proposal-runtime.v2.json"
RECORD = ROOT / "changes/st-1403/generated/refresh-proposal-recorded.v2.json"
MANIFEST = ROOT / "changes/st-1403/runtime-manifest.v2.json"


def _run_generator(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": f"{ROOT / 'python'}:{ROOT}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": "/tmp",
            "TMP": "/tmp",
            "TEMP": "/tmp",
        },
    )


def _bound_request() -> RefreshProposalRequest:
    exact_freshness_request = freshness_request()
    exact_policy_request = valid_policy_input()
    return bind_refresh_proposal_request(
        candidate=proposal_candidate(),
        freshness_request=exact_freshness_request,
        freshness_result=freshness_result(request=exact_freshness_request),
        policy_request=exact_policy_request,
        policy_result=policy_result(exact_policy_request),
    )


def _payload() -> dict[str, object]:
    value = json.loads(RECORD.read_text(encoding="utf-8"))
    assert type(value) is dict
    return cast(dict[str, object], value)


def test_owner_generator_check_is_read_only_and_exact() -> None:
    before = (RECORD.read_bytes(), MANIFEST.read_bytes())

    result = _run_generator("--check")

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert (RECORD.read_bytes(), MANIFEST.read_bytes()) == before


def test_generated_binding_matches_owner_record_and_adapter_accepts_exact_binding() -> (
    None
):
    bindings = load_recorded_refresh_proposal_bindings(RECORD.read_bytes())
    raw_bindings = cast(list[dict[str, str]], _payload()["fixtureBindings"])
    assert bindings == tuple(
        RecordedRefreshProposalBinding(
            request_fingerprint=item["requestFingerprint"],
            proposal_fingerprint=item["proposalFingerprint"],
        )
        for item in raw_bindings
    )

    request = _bound_request()
    proposal = build_refresh_proposal(request)
    exact_binding = (
        RecordedRefreshProposalBinding(
            request_fingerprint=request.fingerprint,
            proposal_fingerprint=proposal.fingerprint,
        ),
    )
    adapter = RecordedRefreshProposalAdapter(
        environment=RuntimeEnvironment.CI,
        fixture_capacity=1,
        bindings=exact_binding,
    )
    service = RefreshProposalService(
        environment=RuntimeEnvironment.CI,
        exchange=adapter,
    )
    exact_freshness_request = freshness_request()
    exact_policy_request = valid_policy_input()
    result = service.propose(
        candidate=request.candidate,
        freshness_request=exact_freshness_request,
        freshness_result=freshness_result(request=exact_freshness_request),
        policy_request=exact_policy_request,
        policy_result=policy_result(exact_policy_request),
    )
    assert result.fingerprint == proposal.fingerprint
    assert result.automatic_reordering_authorized is False


def test_runtime_manifest_binds_every_owner_source_and_artifact() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert type(manifest) is dict
    root = cast(dict[str, object], manifest)
    assert root["generatorOwnerId"] == "build_st1403_refresh_proposal_runtime"
    assert root["generatorVersion"] == "2"
    assert "integrationBaseSha" not in root
    assert "ownerCommand" not in root
    assert "checkCommand" not in root
    sources = cast(list[dict[str, object]], root["sources"])
    for item in sources:
        payload = (ROOT / cast(str, item["path"])).read_bytes()
        assert item["bytes"] == len(payload)
        assert item["sha256"] == hashlib.sha256(payload).hexdigest()
    artifacts = cast(list[dict[str, object]], root["artifacts"])
    assert artifacts == [
        {
            "path": "changes/st-1403/generated/refresh-proposal-recorded.v2.json",
            "sha256": hashlib.sha256(RECORD.read_bytes()).hexdigest(),
            "bytes": len(RECORD.read_bytes()),
        }
    ]
    assert set(cast(dict[str, object], root["authority"]).values()) == {False}


def test_contract_source_bindings_are_current_and_complete() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    bindings = cast(dict[str, dict[str, str]], contract["bindings"])
    assert len(bindings) == 13
    for binding in bindings.values():
        payload = (ROOT / binding["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == binding["sha256"]


@pytest.mark.parametrize(
    "mutator",
    (
        lambda value: value.update({"unknown": True}),
        lambda value: value.update({"schemaVersion": 3}),
        lambda value: value.update({"storyId": "ST-9999"}),
        lambda value: cast(dict[str, object], value["authority"]).update(
            {"publicationAuthorized": True}
        ),
        lambda value: cast(dict[str, object], value["formalStatus"]).update(
            {"TST-020": "PASS"}
        ),
        lambda value: value.update({"fixtureBindings": []}),
        lambda value: value.update({"contractSha256": 0}),
        lambda value: cast(dict[str, object], value["dependencyBindings"]).update(
            {"storyBacklog": 0}
        ),
        lambda value: cast(list[object], value["fixtureBindings"]).append(
            cast(list[object], value["fixtureBindings"])[0]
        ),
        lambda value: cast(list[dict[str, object]], value["fixtureBindings"]).append(
            {
                "requestFingerprint": cast(
                    list[dict[str, object]], value["fixtureBindings"]
                )[0]["requestFingerprint"],
                "proposalFingerprint": "0" * 64,
            }
        ),
    ),
)
def test_recorded_loader_rejects_unknown_authority_and_binding_drift(
    mutator: Callable[[dict[str, object]], None],
) -> None:
    payload = _payload()
    mutator(payload)
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    with pytest.raises(RefreshProposalFailure):
        load_recorded_refresh_proposal_bindings(encoded)


def test_recorded_loader_rejects_duplicate_keys_bom_and_oversize() -> None:
    original = RECORD.read_bytes()
    duplicate = original.replace(
        b'{"authority":', b'{"storyId":"ST-1403","authority":', 1
    )
    for payload in (
        duplicate,
        b"\xef\xbb\xbf" + original,
        b"{" + (b" " * (64 * 1024)),
    ):
        with pytest.raises(RefreshProposalFailure):
            load_recorded_refresh_proposal_bindings(payload)


def test_recorded_binding_is_redacted_immutable_and_revalidated() -> None:
    binding = load_recorded_refresh_proposal_bindings(RECORD.read_bytes())[0]
    assert "018f3e90" not in repr(binding)
    object.__setattr__(binding, "request_fingerprint", "invalid")

    with pytest.raises(RefreshProposalFailure):
        RecordedRefreshProposalAdapter(
            environment=RuntimeEnvironment.CI,
            fixture_capacity=1,
            bindings=(binding,),
        )


def test_unknown_generator_argument_fails_without_writing_outputs() -> None:
    before = (RECORD.read_bytes(), MANIFEST.read_bytes())

    result = _run_generator("--unsupported")

    assert result.returncode != 0
    assert (RECORD.read_bytes(), MANIFEST.read_bytes()) == before


def test_generated_record_contains_no_raw_or_finance_material() -> None:
    lowered = RECORD.read_text(encoding="utf-8").lower()
    for forbidden in (
        "affiliate_rate",
        "commission_amount",
        "revenue_by_product",
        "rakuten_review_body",
        "before_value",
        "after_value",
        "credential",
        "raw_prompt",
    ):
        assert forbidden not in lowered
    assert set(cast(dict[str, object], _payload()["authority"]).values()) == {
        False,
        True,
    }


def test_binding_fingerprint_tamper_is_rejected_by_adapter() -> None:
    binding = load_recorded_refresh_proposal_bindings(RECORD.read_bytes())[0]
    tampered = replace(binding, proposal_fingerprint="0" * 64)
    adapter = RecordedRefreshProposalAdapter(
        environment=RuntimeEnvironment.CI,
        fixture_capacity=1,
        bindings=(tampered,),
    )

    with pytest.raises(RefreshProposalFailure) as caught:
        adapter.propose(_bound_request())
    assert caught.value.code == "PROPOSER_UNAVAILABLE"
