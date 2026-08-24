"""Shared fixed inputs for the ST-1206 local Story suite."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import shutil
import sys
from typing import Protocol
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
for candidate in (str(PYTHON_ROOT), str(REPOSITORY_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from raos.adapters.recorded_keyword_rank import (  # noqa: E402
    RecordedKeywordRankCsvSource,
)
from raos.application.analytics.keyword_rank_import import (  # noqa: E402
    KeywordRankEvaluationService,
)
from raos.domain.analytics.keyword_rank import (  # noqa: E402
    KeywordRankEvaluationCommand,
    KeywordRankPeriod,
    KeywordRankScope,
    Sha256Digest,
)


FIXTURE_PATH = Path("changes/st-1206/fixtures/recorded/keyword-rank-synthetic.v1.csv")
FIXTURE_BYTES = (REPOSITORY_ROOT / FIXTURE_PATH).read_bytes()
SITE_ID = UUID("018f3e90-7b00-7000-8000-000000001200")


def command_for(
    payload: bytes = FIXTURE_BYTES,
    *,
    scope: KeywordRankScope = KeywordRankScope.RECORDED_SYNTHETIC_EVALUATION_ONLY,
    date_from: date = date(2026, 8, 1),
    date_to: date = date(2026, 8, 2),
) -> KeywordRankEvaluationCommand:
    return KeywordRankEvaluationCommand(
        recording_id="complete",
        site_id=SITE_ID,
        source_sha256=Sha256Digest.of(payload),
        source_bytes=len(payload),
        period=KeywordRankPeriod(date_from=date_from, date_to=date_to),
        scope=scope,
    )


def service_for(payload: bytes = FIXTURE_BYTES) -> KeywordRankEvaluationService:
    return KeywordRankEvaluationService(source=RecordedKeywordRankCsvSource(payload))


class _BuilderShape(Protocol):
    SOURCE_PATHS: tuple[Path, ...]
    AUTHORITY_HASHES: dict[Path, str]
    PREDECESSOR_HASHES: dict[Path, str]
    CANONICAL_CONTRACT_HASHES: dict[Path, str]
    GENERATED_PATHS: tuple[Path, ...]


def copy_owner_root(
    destination: Path, builder: _BuilderShape, *, include_outputs: bool = True
) -> Path:
    paths = set(builder.SOURCE_PATHS)
    paths.update(builder.AUTHORITY_HASHES)
    paths.update(builder.PREDECESSOR_HASHES)
    paths.update(builder.CANONICAL_CONTRACT_HASHES)
    if include_outputs:
        paths.update(builder.GENERATED_PATHS)
    for relative in sorted(paths):
        source = REPOSITORY_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination
