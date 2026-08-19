#!/usr/bin/env python3
"""Validate ST-1506 Production admission evidence without external I/O."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass

SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
GIT_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
ZERO_SHA256 = "0" * 64


class AdmissionError(ValueError):
    pass


def _digest(name: str, value: str) -> str:
    if SHA256.fullmatch(value) is None or value == ZERO_SHA256:
        raise AdmissionError(f"{name}:INVALID_SHA256")
    return value


def _commit(value: str) -> str:
    if GIT_COMMIT.fullmatch(value) is None:
        raise AdmissionError("commit:INVALID_GIT_OBJECT_ID")
    return value


@dataclass(frozen=True, slots=True)
class ProductionAdmission:
    release_decision_sha256: str
    gate_report_sha256: str
    security_approval_sha256: str
    operations_approval_sha256: str
    staging_artifact_sha256: str
    staging_evidence_sha256: str
    rollback_artifact_sha256: str
    commit_sha: str

    def validate_independence(self) -> None:
        gate_values = (
            self.release_decision_sha256,
            self.gate_report_sha256,
            self.security_approval_sha256,
            self.operations_approval_sha256,
        )
        if len(set(gate_values)) != 4:
            raise AdmissionError("approval_gates:NOT_INDEPENDENT")
        if self.staging_artifact_sha256 == self.rollback_artifact_sha256:
            raise AdmissionError("rollback_artifact:SAME_AS_STAGING_ARTIFACT")
        if self.staging_evidence_sha256 in gate_values:
            raise AdmissionError("staging_evidence:COLLIDES_WITH_APPROVAL_GATE")

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-decision-sha256", required=True)
    parser.add_argument("--gate-report-sha256", required=True)
    parser.add_argument("--security-approval-sha256", required=True)
    parser.add_argument("--operations-approval-sha256", required=True)
    parser.add_argument("--staging-artifact-sha256", required=True)
    parser.add_argument("--staging-evidence-sha256", required=True)
    parser.add_argument("--rollback-artifact-sha256", required=True)
    parser.add_argument("--commit-sha", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        admission = ProductionAdmission(
            release_decision_sha256=_digest(
                "release_decision", args.release_decision_sha256
            ),
            gate_report_sha256=_digest("gate_report", args.gate_report_sha256),
            security_approval_sha256=_digest(
                "security_approval", args.security_approval_sha256
            ),
            operations_approval_sha256=_digest(
                "operations_approval", args.operations_approval_sha256
            ),
            staging_artifact_sha256=_digest(
                "staging_artifact", args.staging_artifact_sha256
            ),
            staging_evidence_sha256=_digest(
                "staging_evidence", args.staging_evidence_sha256
            ),
            rollback_artifact_sha256=_digest(
                "rollback_artifact", args.rollback_artifact_sha256
            ),
            commit_sha=_commit(args.commit_sha),
        )
        admission.validate_independence()
    except AdmissionError as error:
        print(str(error))
        return 2

    print(
        json.dumps(
            {
                "schema": "RAOS_ST1506_PRODUCTION_ADMISSION_V1",
                "environment": "PRODUCTION",
                "admission_sha256": admission.fingerprint,
                "deployment_enabled": False,
                "production_action_count": 0,
                "traffic_change_count": 0,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
