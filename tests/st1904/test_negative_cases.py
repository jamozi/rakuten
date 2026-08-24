"""Hostile input and integrity-negative tests for ST-1904."""

from __future__ import annotations

from dataclasses import replace
import json
import pickle
from typing import Callable

import pytest

from raos.adapters.recorded_multi_category import (
    CallerBytesRecordedMultiCategorySource,
    RecordedMultiCategorySourceError,
)
from raos.application.catalog.multi_category import (
    evaluate_recorded_multi_category,
)
from raos.domain.catalog.multi_category import (
    MAX_MULTI_CATEGORY_SOURCE_BYTES,
    MultiCategoryFailure,
    MultiCategoryFailureCode,
    MultiCategoryScope,
    sha256_bytes,
)
from tests.st1904.support import (
    command,
    fixture_bytes,
    fixture_document,
    recorded_bundle,
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda data: data + b" ",
        lambda data: data.replace(b'{"authority":', b'{"authority":{},"authority":', 1),
        lambda data: data.replace(b'"synthetic":true', b'"synthetic":1.0', 1),
        lambda data: b"x" * (MAX_MULTI_CATEGORY_SOURCE_BYTES + 1),
        lambda data: b"\xff" + data,
    ),
)
def test_noncanonical_duplicate_float_oversize_and_invalid_utf8_fail_closed(
    mutation: Callable[[bytes], bytes],
) -> None:
    with pytest.raises(RecordedMultiCategorySourceError):
        CallerBytesRecordedMultiCategorySource(mutation(fixture_bytes()))


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("document", "provider", "forbidden"),
        ("document", "api_key", "forbidden"),
        ("document", "real_category", "forbidden"),
        ("authority", "publication_allowed", True),
        ("authority", "release_decision", "approved"),
        ("authority", "template_activation", True),
    ),
)
def test_unknown_provider_credential_real_category_and_authority_fields_fail_closed(
    section: str,
    field: str,
    value: object,
) -> None:
    parsed = fixture_document()
    parsed[section][field] = value
    content = _canonical(parsed)
    source = CallerBytesRecordedMultiCategorySource(content)
    with pytest.raises(MultiCategoryFailure) as caught:
        source.read(command(source=content))
    assert caught.value.code is MultiCategoryFailureCode.SOURCE_DOCUMENT_INVALID


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("categories", 0, "synthetic"), False),
        (("categories", 0, "real_category_selected"), True),
        (("categories", 0, "identity", "automatic_merge_enabled"), True),
        (("categories", 0, "identity", "automatic_split_enabled"), True),
        (("categories", 0, "identity", "disposition"), "AUTO_MERGE"),
        (("categories", 0, "freshness", "category_override"), "24h"),
        (("categories", 0, "freshness", "provider_override"), "12h"),
        (("categories", 0, "freshness", "stale_never_fresh"), False),
        (("categories", 0, "freshness", "recommendation_auto_reorder"), "ALLOWED"),
        (("categories", 0, "template", "active"), True),
        (("authority", "provider_access_enabled"), True),
        (("authority", "network_enabled"), True),
        (("authority", "persistence_enabled"), True),
        (("authority", "editorial_mutation_enabled"), True),
        (("authority", "recommendation_mutation_enabled"), True),
        (("authority", "publication_authorized"), True),
        (("authority", "release_authorized"), True),
        (("authority", "production_authorized"), True),
    ),
)
def test_operational_identity_freshness_template_and_mutation_claims_fail_closed(
    path: tuple[object, ...], value: object
) -> None:
    parsed: object = fixture_document()
    target: object = parsed
    for part in path[:-1]:
        if type(part) is int:
            assert type(target) is list
            target = target[part]
        else:
            assert type(part) is str and type(target) is dict
            target = target[part]
    last = path[-1]
    if type(last) is int:
        assert type(target) is list
        target[last] = value
    else:
        assert type(last) is str and type(target) is dict
        target[last] = value
    content = _canonical(parsed)
    source = CallerBytesRecordedMultiCategorySource(content)
    with pytest.raises(MultiCategoryFailure):
        source.read(command(source=content))


def test_duplicate_category_binding_order_and_template_hash_drift_fail_closed() -> None:
    mutations: list[dict[str, object]] = []
    duplicate = fixture_document()
    duplicate["categories"][1]["category_id"] = duplicate["categories"][0][
        "category_id"
    ]
    mutations.append(duplicate)
    binding_order = fixture_document()
    binding_order["bindings"][0], binding_order["bindings"][1] = (
        binding_order["bindings"][1],
        binding_order["bindings"][0],
    )
    mutations.append(binding_order)
    template_hash = fixture_document()
    template_hash["categories"][0]["template"]["sha256"] = "f" * 64
    mutations.append(template_hash)
    for parsed in mutations:
        content = _canonical(parsed)
        source = CallerBytesRecordedMultiCategorySource(content)
        with pytest.raises(MultiCategoryFailure):
            source.read(command(source=content))


def test_source_and_expected_binding_hash_drift_fail_closed() -> None:
    content = fixture_bytes()
    source = CallerBytesRecordedMultiCategorySource(content)
    drifted = replace(command(), source_sha256="f" * 64)
    with pytest.raises(MultiCategoryFailure) as caught_source:
        source.read(drifted)
    assert caught_source.value.code is MultiCategoryFailureCode.SOURCE_BYTES_MISMATCH
    source = CallerBytesRecordedMultiCategorySource(content)
    with pytest.raises(MultiCategoryFailure) as caught_binding:
        source.read(command(expected_binding_set_sha256="f" * 64))
    assert caught_binding.value.code is MultiCategoryFailureCode.BINDING_SET_MISMATCH


def test_post_load_mutation_is_detected() -> None:
    bundle = recorded_bundle()
    object.__setattr__(bundle.categories[0], "template_active", True)
    with pytest.raises(MultiCategoryFailure):
        evaluate_recorded_multi_category(bundle)


def test_errors_values_commands_and_reports_are_redacted_and_nonserializable() -> None:
    canary = "secret-canary-st1904"
    parsed = fixture_document()
    parsed["document"]["api_key"] = canary
    content = _canonical(parsed)
    source = CallerBytesRecordedMultiCategorySource(content)
    with pytest.raises(MultiCategoryFailure) as caught:
        source.read(command(source=content))
    assert canary not in f"{caught.value!s} {caught.value!r}"
    with pytest.raises(TypeError):
        pickle.dumps(caught.value)
    values = (
        command(),
        recorded_bundle(),
        evaluate_recorded_multi_category(recorded_bundle()),
    )
    for value in values:
        assert canary not in f"{value!s} {value!r}"
        with pytest.raises(TypeError):
            pickle.dumps(value)


def test_source_scope_is_explicit_and_disabled_source_never_consumes() -> None:
    content = fixture_bytes()
    source = CallerBytesRecordedMultiCategorySource(content)
    with pytest.raises(MultiCategoryFailure) as caught:
        source.read(command(scope=MultiCategoryScope.DISABLED))
    assert caught.value.code is MultiCategoryFailureCode.FEATURE_DISABLED
    assert source.read(command()).source_sha256 == sha256_bytes(content)
