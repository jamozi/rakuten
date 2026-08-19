#!/usr/bin/env python3
"""Validate immutable ST-1505 staging inputs without performing external I/O."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, asdict

SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}\Z", re.ASCII)


class AdmissionError(ValueError):
    pass


def _digest(name: str, value: str) -> str:
    if SHA256.fullmatch(value) is None:
        raise AdmissionError(f"{name}:INVALID_SHA256")
    return value


def _token(name: str, value: str) -> str:
    if SAFE_TOKEN.fullmatch(value) is None:
        raise AdmissionError(f"{name}:INVALID_TOKEN")
    lowered = value.lower()
    if "production" in lowered or lowered == "prod":
        raise AdmissionError(f"{name}:PRODUCTION_FORBIDDEN")
    return value


@dataclass(frozen=True, slots=True)
class Admission:
    artifact_sha256: str
    sbom_sha256: str
    vulnerability_scan_sha256: str
    provenance_sha256: str
    rollback_artifact_sha256: str
    migration_version: str
    commit_sha: str

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--sbom-sha256", required=True)
    parser.add_argument("--vulnerability-scan-sha256", required=True)
    parser.add_argument("--provenance-sha256", required=True)
    parser.add_argument("--rollback-artifact-sha256", required=True)
    parser.add_argument("--migration-version", required=True)
    parser.add_argument("--commit-sha", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        admission = Admission(
            artifact_sha256=_digest("artifact", args.artifact_sha256),
            sbom_sha256=_digest("sbom", args.sbom_sha256),
            vulnerability_scan_sha256=_digest(
                "vulnerability_scan", args.vulnerability_scan_sha256
            ),
            provenance_sha256=_digest("provenance", args.provenance_sha256),
            rollback_artifact_sha256=_digest(
                "rollback_artifact", args.rollback_artifact_sha256
            ),
            migration_version=_token("migration_version", args.migration_version),
            commit_sha=_digest("commit", args.commit_sha),
        )
    except AdmissionError as error:
        print(str(error))
        return 2
    print(
        json.dumps(
            {
                "schema": "RAOS_ST1505_ADMISSION_V1",
                "environment": "STAGING",
                "admission_sha256": admission.fingerprint,
                "external_write_count": 0,
                "production_action_count": 0,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
