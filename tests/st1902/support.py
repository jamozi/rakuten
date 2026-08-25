"""Shared exact-fixture helpers for ST-1902."""

from __future__ import annotations

from pathlib import Path

from raos.adapters.recorded_champion_challenger import (
    RecordedChampionChallengerSource,
)
from raos.application.ai.champion_challenger import (
    ChampionChallengerShadowService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.champion_challenger import (
    ChampionChallengerScope,
    ShadowRoutingCommand,
    Sha256Digest,
    TARGET_ROUTE_CODE,
    TARGET_TASK_CODE,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(
    "changes/st-1902/fixtures/recorded/champion-challenger-shadow.v1.json"
)
RECORDING_ID = "st1902_recorded_shadow_v1"
POLICY_VERSION = "st1902-disabled-shadow.v1"


def fixture_bytes() -> bytes:
    return (REPOSITORY_ROOT / FIXTURE_PATH).read_bytes()


def command_for(
    payload: bytes | None = None,
    *,
    scope: ChampionChallengerScope = (
        ChampionChallengerScope.RECORDED_SYNTHETIC_SHADOW_ONLY
    ),
) -> ShadowRoutingCommand:
    content = fixture_bytes() if payload is None else payload
    return ShadowRoutingCommand(
        recording_id=RECORDING_ID,
        task_code=TARGET_TASK_CODE,
        route_code=TARGET_ROUTE_CODE,
        source_sha256=Sha256Digest.of(content),
        source_bytes=len(content),
        policy_version=POLICY_VERSION,
        scope=scope,
    )


def service_for(
    payload: bytes | None = None,
    *,
    environment: RuntimeEnvironment = RuntimeEnvironment.CI,
) -> ChampionChallengerShadowService:
    content = fixture_bytes() if payload is None else payload
    return ChampionChallengerShadowService(
        environment=environment,
        source=RecordedChampionChallengerSource(content),
    )
