"""Deterministic owner-generation checks for ST-0602 V2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_st0602_fact_extraction_runtime as generator


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def test_render_is_deterministic_and_installed_bytes_match() -> None:
    first = generator._render()  # noqa: SLF001
    second = generator._render()  # noqa: SLF001
    assert first == second
    assert (generator.REPO_ROOT / generator.OUTPUT).read_bytes() == first[0]
    assert (generator.REPO_ROOT / generator.MANIFEST).read_bytes() == first[1]


def test_check_mode_is_no_write() -> None:
    before = {
        path: (generator.REPO_ROOT / path).read_bytes()
        for path in (generator.OUTPUT, generator.MANIFEST)
    }
    assert generator.main(["--check"]) == 0
    after = {
        path: (generator.REPO_ROOT / path).read_bytes()
        for path in (generator.OUTPUT, generator.MANIFEST)
    }
    assert after == before


def test_report_keeps_identity_confidence_and_authority_closed() -> None:
    report = _json(generator.REPO_ROOT / generator.OUTPUT)
    assert report["story_id"] == "ST-0602"
    assert report["local_implementation_status"] == "LOCAL_CODE_COMPLETE"
    assert report["canonical_status"] == "UNCHANGED"
    fact = report["fact_boundary"]
    confidence = report["confidence_boundary"]
    authority = report["authority_boundary"]
    formal = report["formal_evidence"]
    assert isinstance(fact, dict) and fact["subject_type"] == "OFFER"
    assert fact["product_fact"] is False
    assert fact["canonical_product_id"] is False
    assert isinstance(confidence, dict) and confidence["value"] == "1.0000"
    assert confidence["meaning"] == "EXTRACTION_FIDELITY_ONLY"
    assert confidence["truth_attestation"] == "NOT_ATTESTED"
    assert isinstance(authority, dict) and authority["production_authority"] == "NONE"
    assert authority["external_action_count"] == 0
    assert isinstance(formal, dict)
    assert formal["TST-005"] == "LOCAL_ANALOG_ONLY_FORMAL_NOT_EXECUTED"
    assert formal["TST-007"] == "LOCAL_ANALOG_ONLY_FORMAL_NOT_EXECUTED"
    assert (
        formal["staging"] == formal["release"] == formal["production"] == "NOT_EXECUTED"
    )


def test_generated_material_contains_no_raw_url_or_provider_text() -> None:
    for path in (generator.OUTPUT, generator.MANIFEST, generator.FIXTURE):
        payload = (generator.REPO_ROOT / path).read_bytes().lower()
        assert b"https://" not in payload
        assert b"affiliate.example" not in payload
        assert b"synthetic shop" not in payload


def test_manifest_binds_every_owner_source_and_generated_report() -> None:
    manifest = _json(generator.REPO_ROOT / generator.MANIFEST)
    source_hashes = manifest["source_sha256"]
    generated_hashes = manifest["generated_sha256"]
    assert isinstance(source_hashes, dict)
    assert isinstance(generated_hashes, dict)
    expected_sources = {
        str(path)
        for path in (
            *generator.CANONICAL,
            *generator.DEPENDENCY_SOURCE,
            *generator.RUNTIME_SOURCE,
            *generator.OWNED_TEST_SOURCE,
            *generator.DOCUMENTATION,
            generator.CONTRACT,
            generator.FIXTURE,
            generator.GENERATOR,
        )
    }
    assert set(source_hashes) == expected_sources
    for relative, digest in source_hashes.items():
        assert (
            hashlib.sha256((generator.REPO_ROOT / relative).read_bytes()).hexdigest()
            == digest
        )
    assert generated_hashes == {
        str(generator.OUTPUT): hashlib.sha256(
            (generator.REPO_ROOT / generator.OUTPUT).read_bytes()
        ).hexdigest()
    }


@pytest.mark.parametrize(
    ("path", "mutation"),
    [
        (
            generator.CONTRACT,
            lambda value: value["authority_boundary"].__setitem__("publication", True),
        ),
        (
            generator.CONTRACT,
            lambda value: value["confidence_boundary"].__setitem__(
                "meaning", "TRUTH_ATTESTATION"
            ),
        ),
        (
            generator.FIXTURE,
            lambda value: value.__setitem__("contains_raw_or_affiliate_url", True),
        ),
    ],
)
def test_closed_contract_and_fixture_mutations_are_rejected(
    monkeypatch, path: Path, mutation
) -> None:
    original = generator._json_object  # noqa: SLF001

    def changed(relative: Path) -> dict[str, object]:
        value = original(relative)
        if relative == path:
            mutation(value)
        return value

    monkeypatch.setattr(generator, "_json_object", changed)
    with pytest.raises(generator.BuildError):
        generator._render()  # noqa: SLF001
