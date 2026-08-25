"""Sanitized value factories for ST-1904 focused tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from raos.adapters.recorded_multi_category import (
    CallerBytesRecordedMultiCategorySource,
)
from raos.domain.catalog.multi_category import (
    MultiCategoryEvaluationCommand,
    MultiCategoryScope,
    RecordedMultiCategoryBundle,
    binding_set_sha256,
    sha256_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / ("changes/st-1904/fixtures/recorded/multi-category.synthetic.v1.json")


def fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def fixture_document() -> dict[str, Any]:
    parsed: object = json.loads(fixture_bytes())
    assert type(parsed) is dict
    return cast(dict[str, Any], parsed)


def command(
    *,
    source: bytes | None = None,
    scope: MultiCategoryScope = (
        MultiCategoryScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY
    ),
    expected_binding_set_sha256: str | None = None,
) -> MultiCategoryEvaluationCommand:
    content = fixture_bytes() if source is None else source
    expected = (
        binding_set_sha256(recorded_bundle().bindings)
        if expected_binding_set_sha256 is None
        else expected_binding_set_sha256
    )
    return MultiCategoryEvaluationCommand(
        recording_id="st1904_recorded_multi_category_v1",
        source_sha256=sha256_bytes(content),
        source_bytes=len(content),
        expected_binding_set_sha256=expected,
        scope=scope,
    )


def recorded_bundle() -> RecordedMultiCategoryBundle:
    content = fixture_bytes()
    expected = fixture_document()["bindings"]
    import hashlib

    expected_digest = hashlib.sha256(
        json.dumps(
            expected,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()
    source = CallerBytesRecordedMultiCategorySource(content)
    return source.read(
        MultiCategoryEvaluationCommand(
            recording_id="st1904_recorded_multi_category_v1",
            source_sha256=sha256_bytes(content),
            source_bytes=len(content),
            expected_binding_set_sha256=expected_digest,
            scope=(MultiCategoryScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY),
        )
    )


__all__ = (
    "FIXTURE",
    "ROOT",
    "command",
    "fixture_bytes",
    "fixture_document",
    "recorded_bundle",
)
