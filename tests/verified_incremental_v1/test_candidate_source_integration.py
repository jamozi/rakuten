"""Synthetic owner integration, not audit evidence or a live publication.

Only I/O and upstream audit/browser observations are stand-ins. Candidate
production, reconstruction, manifest validation and release construction are real.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import importlib.util
from pathlib import Path

import pytest

from raos.application.editorial import verified_incremental_release_v1 as release
from raos.application.editorial.verified_incremental_audit_v1 import (
    VerifiedIncrementalAuditBindingV1,
)
from scripts import raos_wordpress_incremental_publication as port

spec = importlib.util.spec_from_file_location(
    "synthetic_candidate_source_examples", Path(__file__).with_name("test_candidate.py")
)
assert spec is not None and spec.loader is not None
examples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(examples)


@pytest.fixture
def owner_inputs(monkeypatch, tmp_path):
    inputs = examples.sample(selected=(1,))
    portfolio = inputs["portfolio"]
    inputs["portfolio"] = replace(
        portfolio,
        articles=(
            replace(portfolio.articles[0], product_ids=(), cta_bindings=()),
            *portfolio.articles[1:],
        ),
    )
    inputs["articles"] = (
        replace(
            inputs["articles"][0],
            block_markup=(
                '<div class="raos-editorial-v2">'
                '<dl class="raos-article-facts"><dt>実機</dt><dd>未使用</dd></dl>'
                "<p>合成の型番確認ガイド。</p></div>"
            ),
        ),
    )
    sources = inputs["sources"]
    source = sources.sources["source-article-1"]
    sources = replace(
        sources,
        sources={
            **sources.sources,
            "policy-source": replace(
                source, source_ref="policy-source", claim_statement_sha256={}
            ),
        },
        article_source_refs={"article-1": ("source-article-1", "policy-source")},
    )
    inputs["sources"] = sources
    manifest, artifacts, preparation = (
        port.candidate_owner.prepare_noncommercial_candidate(**inputs)
    )
    path = tmp_path / port.digest(port.canonical(manifest))
    browser_raw = b"synthetic browser stand-in; never a real audit"
    audit_inputs = {
        **artifacts,
        "manifest": port.canonical(manifest),
        "candidate-preparation": port.canonical(preparation),
        "live-snapshot": port.publication.canonical_json_bytes(inputs["snapshot"]),
        "source-replay": port.canonical(sources.to_document()),
        "mixed-browser-report": browser_raw,
    }
    report = {
        "artifact_hashes": {key: port.digest(raw) for key, raw in audit_inputs.items()},
        "evidence_artifact_hashes": {},
    }
    documents = {
        "manifest.v1.json": manifest,
        "candidate-preparation.v1.json": preparation,
        preparation["snapshot_name"]: inputs["snapshot"],
        "report.v1.json": report,
    }
    byte_files = {
        preparation["artifact_files"][key]: raw for key, raw in artifacts.items()
    } | {f"{port.digest(raw)}.bin": raw for raw in audit_inputs.values()}
    current = {"sources": sources, "audit_calls": 0, "browser_calls": 0}
    monkeypatch.setattr(port, "_candidate_directory", lambda _: None)
    monkeypatch.setattr(
        port,
        "read_json",
        lambda _, name: (deepcopy(documents[name]), port.canonical(documents[name])),
    )
    monkeypatch.setattr(port, "read_bytes", lambda _, name: byte_files[name])
    monkeypatch.setattr(
        port, "load_editorial_portfolio_v3", lambda _: inputs["portfolio"]
    )
    monkeypatch.setattr(port.publication, "load_articles", lambda _: inputs["articles"])
    monkeypatch.setattr(
        port, "validate_selected_official_sources", lambda *_: current["sources"]
    )

    def synthetic_audit(_report, **kwargs):
        current["audit_calls"] += 1
        return VerifiedIncrementalAuditBindingV1(
            "1" * 64,
            kwargs["manifest_sha256"],
            release._digest(kwargs["scope"].to_document()),
            release._digest(kwargs["expected_artifact_hashes"]),
            "2" * 64,
            sources.evaluated_at,
            (examples.NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "OWNER_CONFIRMED",
        )

    def synthetic_browser(**_kwargs):
        current["browser_calls"] += 1
        return {
            "report_sha256": port.digest(browser_raw),
            "manifest_sha256": path.name,
        }

    monkeypatch.setattr(port, "validate_verified_incremental_audit_v1", synthetic_audit)
    return path, current, synthetic_browser


def test_actual_candidate_owner_accepts_claims_plus_supporting_captures(owner_inputs):
    path, current, browser = owner_inputs
    result = port.load_candidate(
        path,
        implementation_execution_ids=("synthetic-implementer",),
        now=examples.NOW,
        browser_validator=browser,
    )
    assert set(result.manifest["articles"][0]["source_receipts"]) == {
        "source-article-1"
    }
    assert set(result.context.to_document()["source_receipts"]) == {
        "source-article-1",
        "policy-source",
    }
    assert current["audit_calls"] == current["browser_calls"] == 1


@pytest.mark.parametrize(
    "field", ["body_file_sha256", "response_sha256", "locator_binding_sha256"]
)
def test_owner_rejects_supporting_capture_drift_before_any_audit(owner_inputs, field):
    path, current, browser = owner_inputs
    sources = current["sources"]
    current["sources"] = replace(
        sources,
        sources={
            **sources.sources,
            "policy-source": replace(
                sources.sources["policy-source"], **{field: "9" * 64}
            ),
        },
    )
    with pytest.raises(
        port.publication.PublicationFailure, match="CANDIDATE_PREPARATION_CHANGED"
    ):
        port.load_candidate(
            path,
            implementation_execution_ids=("synthetic-implementer",),
            now=examples.NOW,
            browser_validator=browser,
        )
    assert current["audit_calls"] == current["browser_calls"] == 0


def test_owner_replay_clock_moves_without_recapturing_sources(owner_inputs):
    path, current, browser = owner_inputs
    current["sources"] = replace(
        current["sources"],
        evaluated_at=(examples.NOW + timedelta(seconds=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    )
    result = port.load_candidate(
        path,
        implementation_execution_ids=("synthetic-implementer",),
        now=examples.NOW + timedelta(seconds=10),
        browser_validator=browser,
    )
    assert (
        result.preparation["source_evidence"]["evaluated_at"] == "2026-09-05T02:00:00Z"
    )
