"""Fixed synthetic inputs for the executable local ST-1604 boundary."""

from __future__ import annotations

from pathlib import Path
import sys
from uuid import UUID

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
for path in (PYTHON_ROOT, REPOSITORY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from raos.domain.ops.performance_load import (  # noqa: E402
    LoadEvidenceSource,
    LoadSurface,
    PerformanceLoadRequest,
    SurfaceBudget,
    SurfaceObservation,
)


def make_request(
    *,
    run_id: UUID = UUID("16040000-0000-4000-8000-000000000001"),
) -> PerformanceLoadRequest:
    budgets = tuple(
        SurfaceBudget(
            surface=surface,
            concurrent_units=index,
            duration_ms=1_000,
            max_p95_duration_ms=250 + index * 10,
            max_p99_duration_ms=350 + index * 10,
            max_error_basis_points=500,
            min_throughput_milliops_per_second=10_000,
            max_db_connections=10 + index,
            max_queue_age_p95_ms=600_000 if surface is LoadSurface.WORKER else None,
        )
        for index, surface in enumerate(LoadSurface, start=1)
    )
    observations = tuple(
        SurfaceObservation(
            surface=surface,
            concurrent_units=index,
            duration_ms=1_000,
            successful_operations=20,
            duration_samples_ms=tuple(80 + index + offset for offset in range(20)),
            max_db_connections=5 + index,
            queue_age_samples_ms=(
                tuple(offset * 1_000 for offset in range(20))
                if surface is LoadSurface.WORKER
                else None
            ),
        )
        for index, surface in enumerate(LoadSurface, start=1)
    )
    return PerformanceLoadRequest(
        run_id=run_id,
        observed_at="2026-08-25T00:00:00Z",
        evidence_source=LoadEvidenceSource.SYNTHETIC_RECORDED_FIXTURE,
        source_artifact_sha256="a" * 64,
        dataset_id="ST1604-SYNTHETIC-BASELINE-V2",
        budgets=budgets,
        observations=observations,
    )


@pytest.fixture()
def perf_request() -> PerformanceLoadRequest:
    return make_request()


@pytest.fixture()
def private_root(tmp_path: Path) -> Path:
    path = tmp_path / "owner-private"
    path.mkdir(mode=0o700)
    return path
