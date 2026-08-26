from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path

import pytest

from raos.domain.portfolio.scale_decision import (
    FixtureByteLength,
    PROGRAM,
    PortfolioDecisionCommand,
    Sha256Digest,
)
from scripts import build_st1805_portfolio_decision as builder


@pytest.fixture
def fixture_bytes() -> bytes:
    return (builder.REPO_ROOT / builder.FIXTURE_PATH).read_bytes()


@pytest.fixture
def command_factory() -> Callable[..., PortfolioDecisionCommand]:
    def factory(
        fixture: bytes,
        *,
        input_sha256: str | None = None,
        source_pack_sha256: str | None = None,
        recording_id: str = "blocked-synthetic-no-decision",
    ) -> PortfolioDecisionCommand:
        document = json.loads(fixture)
        assert isinstance(document, dict)
        evidence = document["evidence"]
        assert isinstance(evidence, dict)
        return PortfolioDecisionCommand(
            recording_id=recording_id,
            fixture_digest=Sha256Digest.of(fixture),
            fixture_length=FixtureByteLength(len(fixture)),
            contract_digest=Sha256Digest(document["contract_sha256"]),
            expected_input_digest=Sha256Digest(
                document["input_sha256"] if input_sha256 is None else input_sha256
            ),
            expected_source_pack_digest=Sha256Digest(
                evidence["source_pack_sha256"]
                if source_pack_sha256 is None
                else source_pack_sha256
            ),
            program_id=PROGRAM,
        )

    return factory


@pytest.fixture
def mutate_fixture() -> Callable[[bytes, Callable[[dict[str, object]], None]], bytes]:
    def mutate(
        fixture: bytes,
        operation: Callable[[dict[str, object]], None],
    ) -> bytes:
        document = json.loads(fixture)
        assert isinstance(document, dict)
        operation(document)
        return (
            json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()

    return mutate


@pytest.fixture
def generated_pack() -> dict[str, object]:
    document = json.loads(builder.render_pack())
    assert isinstance(document, dict)
    return document


@pytest.fixture
def output_path() -> Path:
    return builder.REPO_ROOT / builder.OUTPUT_PATH
