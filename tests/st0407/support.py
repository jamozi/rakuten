"""Import isolation and synthetic metadata fixtures for ST-0407."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.config.runtime import (  # noqa: E402
    LogLevel,
    RuntimeConfig,
    RuntimeEnvironment,
    SecretReference,
)
from raos.domain.iam.workload_credentials import (  # noqa: E402
    CredentialAlias,
    CredentialLeaseMetadata,
    CredentialPurpose,
    CredentialRequest,
    WorkloadBinding,
    WorkloadEnvironment,
)


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
MAXIMUM_LEASE_LIFETIME = timedelta(minutes=15)
LOGICAL_REFERENCE_CANARY = "logical-reference-private-canary-0407"


def runtime_config(
    *,
    environment: RuntimeEnvironment = RuntimeEnvironment.ENV_DEV,
    service_name: str = "catalog-worker",
    aliases: tuple[str, ...] = ("provider_api", "database_primary", "ci_deploy"),
) -> RuntimeConfig:
    references = {
        alias: SecretReference(
            "".join(("sec", "ret", "://fixture/", LOGICAL_REFERENCE_CANARY, "/", alias))
        )
        for alias in aliases
    }
    return RuntimeConfig(
        schema_version=1,
        environment=environment,
        service_name=service_name,
        log_level=LogLevel.INFO,
        secret_references=references,
    )


def request(
    *,
    environment: WorkloadEnvironment = WorkloadEnvironment.ENV_DEV,
    service_name: str = "catalog-worker",
    purpose: CredentialPurpose = CredentialPurpose.PROVIDER_API,
    alias: str = "provider_api",
) -> CredentialRequest:
    return CredentialRequest(
        binding=WorkloadBinding(
            service_name=service_name,
            environment=environment,
        ),
        purpose=purpose,
        alias=CredentialAlias(alias),
    )


def metadata(
    *,
    credential_request: CredentialRequest | None = None,
    lease_id: str = "lease-fixture-1",
    issued_at: datetime = NOW - timedelta(seconds=5),
    not_before: datetime = NOW - timedelta(seconds=1),
    expires_at: datetime = NOW + timedelta(minutes=5),
) -> CredentialLeaseMetadata:
    return CredentialLeaseMetadata(
        request=credential_request or request(),
        lease_id=lease_id,
        issued_at=issued_at,
        not_before=not_before,
        expires_at=expires_at,
    )


@pytest.fixture
def config() -> RuntimeConfig:
    return runtime_config()


@pytest.fixture
def provider_request() -> CredentialRequest:
    return request()


@pytest.fixture
def provider_metadata(provider_request: CredentialRequest) -> CredentialLeaseMetadata:
    return metadata(credential_request=provider_request)
