#!/usr/bin/env python3
"""Build the deterministic RAOS V2 successor specification and contracts.

The imported design package is an immutable, design-only source layer.  This
owner never executes the package's prompt and never performs network I/O.  Live
observations, when explicitly captured by the validator, are sanitized into a
tracked recorded input before this owner consumes them.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
from pathlib import Path
import re
import stat
import sys
from typing import Any, Final, NoReturn

import yaml

try:
    from scripts.raos_build_core import atomic_write, canonical_json_bytes
    from scripts.validate_raos_v2_successor import (
        _read_local_evidence_file,
        ValidationFailure,
        load_json_strict,
        load_yaml_strict,
        protected_path_changes,
        simulate_route_round_trip,
        verify_local_test_evidence,
        verify_visual_review_evidence,
    )
except ModuleNotFoundError:  # direct ``python scripts/...`` execution
    from raos_build_core import atomic_write, canonical_json_bytes
    from validate_raos_v2_successor import (
        _read_local_evidence_file,
        ValidationFailure,
        load_json_strict,
        load_yaml_strict,
        protected_path_changes,
        simulate_route_round_trip,
        verify_local_test_evidence,
        verify_visual_review_evidence,
    )


ROOT: Final = Path(__file__).resolve().parents[1]
SOURCE_ROOT: Final = Path("changes/raos-v2/source-package/2.0.0-design")
RECORDED_INPUT_PATH: Final = Path(
    "changes/raos-v2/recorded-inputs/phase0-capture.v1.json"
)
PHASE0_VISUAL_EVIDENCE_PATH: Final = Path(
    "changes/raos-v2/recorded-inputs/phase0-visual-evidence.v1.json"
)
PHASE2_DATA_PATHS: Final = (
    Path("changes/raos-v2/phase-2/content/article-definitions.v2.yaml"),
    Path("changes/raos-v2/phase-2/content/carry-on-comparison.v2.yaml"),
    Path("changes/raos-v2/phase-2/content/carry-on-rules-guide.v2.yaml"),
    Path("changes/raos-v2/phase-2/content/comparison-policy.v2.yaml"),
    Path("changes/raos-v2/phase-2/content/difference-template-fixture.v2.yaml"),
    Path("changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json"),
    Path("changes/raos-v2/phase-2/editorial/editorial-decisions.v2.yaml"),
    Path("changes/raos-v2/phase-2/events/event-catalog.v2.yaml"),
    Path("changes/raos-v2/phase-2/fixtures/negative-product-identity.v2.json"),
    Path("changes/raos-v2/phase-2/fixtures/recorded-airline-rules.v2.json"),
    Path(
        "changes/raos-v2/phase-2/fixtures/recorded-rakuten-item-search-2026-07-01.json"
    ),
    Path("changes/raos-v2/phase-2/media/media-policy.v2.yaml"),
    Path("changes/raos-v2/phase-2/reviews/review-packet.v2.yaml"),
    Path("changes/raos-v2/phase-2/rules/airline-rule-sets.v2.yaml"),
    Path("changes/raos-v2/phase-2/sources/source-registry.v2.yaml"),
)
PHASE2_PREVIEW_INPUT_PATHS: Final = (
    Path(
        "packages/web-ui/src/decision-support-v2/preview/checker-parity-cases.v2.json"
    ),
    Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json"),
    Path("packages/web-ui/src/decision-support-v2/preview/styles.css"),
    Path("packages/web-ui/src/decision-support-v2/preview/checker.js"),
    Path("packages/web-ui/src/decision-support-v2/preview/render_preview.py"),
)
PHASE2_RECORDED_EVIDENCE_PATHS: Final = (
    Path("changes/raos-v2/recorded-inputs/phase2-browser-evidence.v1.json"),
    Path("changes/raos-v2/recorded-inputs/phase2-local-test-evidence.v1.json"),
    Path("changes/raos-v2/recorded-inputs/phase2-visual-evidence.v1.json"),
)
PHASE2_IMPLEMENTATION_PATHS: Final = (
    Path("packages/web-ui/src/decision-support-v2/checker.ts"),
    Path("packages/web-ui/src/decision-support-v2/contracts.ts"),
    Path("packages/web-ui/src/decision-support-v2/renderer.ts"),
    Path("python/raos/adapters/decision_support_v2/__init__.py"),
    Path("python/raos/adapters/decision_support_v2/errors.py"),
    Path("python/raos/adapters/decision_support_v2/local_events.py"),
    Path("python/raos/adapters/decision_support_v2/recorded_airline.py"),
    Path("python/raos/adapters/decision_support_v2/recorded_catalog.py"),
    Path("python/raos/adapters/decision_support_v2/recorded_rakuten.py"),
    Path("python/raos/adapters/decision_support_v2/strict_json.py"),
    Path("python/raos/adapters/decision_support_v2/wordpress_disabled.py"),
    Path("python/raos/application/decision_support_v2/__init__.py"),
    Path("python/raos/application/decision_support_v2/checker.py"),
    Path("python/raos/application/decision_support_v2/offer_lookup.py"),
    Path("python/raos/application/decision_support_v2/publication.py"),
    Path("python/raos/application/decision_support_v2/selection.py"),
    Path("python/raos/domain/decision_support_v2/__init__.py"),
    Path("python/raos/domain/decision_support_v2/business.py"),
    Path("python/raos/domain/decision_support_v2/content_quality.py"),
    Path("python/raos/domain/decision_support_v2/decision.py"),
    Path("python/raos/domain/decision_support_v2/events.py"),
    Path("python/raos/domain/decision_support_v2/freshness.py"),
    Path("python/raos/domain/decision_support_v2/media.py"),
    Path("python/raos/domain/decision_support_v2/models.py"),
    Path("python/raos/domain/decision_support_v2/publication.py"),
    Path("python/raos/domain/decision_support_v2/selection.py"),
    Path("python/raos/ports/decision_support_v2/__init__.py"),
    Path("python/raos/ports/decision_support_v2/protocols.py"),
)
PHASE2_TEST_SOURCE_PATHS: Final = (
    Path("tests/raos_v2/browser-validation.mjs"),
    Path("tests/raos_v2/conftest.py"),
    Path("tests/raos_v2/test_adapters_recorded.py"),
    Path("tests/raos_v2/test_browser_contract.py"),
    Path("tests/raos_v2/test_content_quality.py"),
    Path("tests/raos_v2/test_contracts_phase1.py"),
    Path("tests/raos_v2/test_decision_engine.py"),
    Path("tests/raos_v2/test_events_privacy.py"),
    Path("tests/raos_v2/test_phase0_contracts.py"),
    Path("tests/raos_v2/test_publication_contract.py"),
    Path("tests/raos_v2/test_selection_contract.py"),
    Path("tests/raos_v2/test_source_import.py"),
    Path("tests/raos_v2/test_traceability_phase0_phase2.py"),
    Path("tests/raos_v2/test_ui_contracts.py"),
    Path("tests/raos_v2/test_ui_parity.py"),
    Path("tests/raos_v2/test_visual_contract.py"),
    Path("tests/raos_v2/ui-parity.mjs"),
    Path("tests/raos_v2/visual-validation.mjs"),
)
PHASE2_SOURCE_PATHS: Final = (
    *PHASE2_DATA_PATHS,
    *PHASE2_PREVIEW_INPUT_PATHS,
    *PHASE2_RECORDED_EVIDENCE_PATHS,
    *PHASE2_IMPLEMENTATION_PATHS,
    *PHASE2_TEST_SOURCE_PATHS,
)
SOURCE_PATHS: Final = (
    Path("changes/raos-v2/source-package/2.0.0-design/00_EXECUTIVE_DECISIONS.md"),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/01_CURRENT_STATE_AND_RESEARCH.md"
    ),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/02_PRODUCT_BRAND_CATEGORY_STRATEGY.md"
    ),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/03_CONTENT_SEO_EDITORIAL_SYSTEM.md"
    ),
    Path("changes/raos-v2/source-package/2.0.0-design/04_UX_DESIGN_SYSTEM.md"),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/05_TECHNICAL_DATA_ANALYTICS_ARCHITECTURE.md"
    ),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/06_MIGRATION_ROADMAP_AND_BACKLOG.md"
    ),
    Path("changes/raos-v2/source-package/2.0.0-design/07_DECISION_TRACEABILITY.yaml"),
    Path("changes/raos-v2/source-package/2.0.0-design/08_TEST_AND_ACCEPTANCE_PLAN.md"),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/09_EVIDENCE_AND_SOURCE_REGISTER.yaml"
    ),
    Path("changes/raos-v2/source-package/2.0.0-design/10_INTERFACE_CONTRACTS.yaml"),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/11_EXTERNAL_ACTIONS_REGISTER.yaml"
    ),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/12_INDEPENDENT_QUALITY_REVIEW.md"
    ),
    Path(
        "changes/raos-v2/source-package/2.0.0-design/CONTROL/implementation_contract.yaml"
    ),
    Path("changes/raos-v2/source-package/2.0.0-design/CONTROL/package_validation.json"),
    Path("changes/raos-v2/source-package/2.0.0-design/CONTROL/source_integrity.json"),
    Path("changes/raos-v2/source-package/2.0.0-design/MANIFEST.sha256"),
    Path("changes/raos-v2/source-package/2.0.0-design/README.md"),
    Path("changes/raos-v2/source-package/2.0.0-design/package_manifest.json"),
    RECORDED_INPUT_PATH,
    PHASE0_VISUAL_EVIDENCE_PATH,
    *PHASE2_SOURCE_PATHS,
    Path("scripts/build_raos_v2_successor.py"),
    Path("scripts/raos_build_core.py"),
    Path("scripts/validate_raos_v2_successor.py"),
)
OUTPUT_PATHS: Final = (
    Path("changes/raos-v2/source-import.v1.json"),
    Path("changes/raos-v2/clarifications.v1.yaml"),
    Path("changes/raos-v2/phase-0/preflight-report.json"),
    Path("changes/raos-v2/phase-0/source-audit-report.json"),
    Path("changes/raos-v2/phase-0/public-url-inventory.yaml"),
    Path("changes/raos-v2/phase-0/production-observation-plan.md"),
    Path("changes/raos-v2/phase-0/metric-dictionary.yaml"),
    Path("changes/raos-v2/phase-0/deprecation-ledger.yaml"),
    Path("changes/raos-v2/phase-0/pilot-reconciliation.yaml"),
    Path("changes/raos-v2/phase-0/rollback-contract.yaml"),
    Path("changes/raos-v2/phase-0/phase-0-report.md"),
    Path("changes/raos-v2/product-spec.v2.yaml"),
    Path("changes/raos-v2/route-registry.v2.yaml"),
    Path("changes/raos-v2/design/design-tokens.v2.json"),
    Path("changes/raos-v2/design/component-states.yaml"),
    Path("changes/raos-v2/generated/decision-traceability.effective.v1.yaml"),
    Path("changes/raos-v2/generated/phase-1-validation.v1.json"),
    Path("changes/raos-v2/phase-1-report.md"),
    Path("contracts/raos-v2/v1/source-record.schema.json"),
    Path("contracts/raos-v2/v1/claim.schema.json"),
    Path("contracts/raos-v2/v1/product-model.schema.json"),
    Path("contracts/raos-v2/v1/product-variant.schema.json"),
    Path("contracts/raos-v2/v1/offer-observation.schema.json"),
    Path("contracts/raos-v2/v1/airline-rule-set.schema.json"),
    Path("contracts/raos-v2/v1/article-definition.schema.json"),
    Path("contracts/raos-v2/v1/editorial-decision.schema.json"),
    Path("contracts/raos-v2/v1/publication-package.schema.json"),
    Path("contracts/raos-v2/v1/analytics-event.schema.json"),
    Path("contracts/raos-v2/v1/ports.v1.yaml"),
    Path("changes/raos-v2/phase-2/claims/claim-ledger.v2.yaml"),
    Path("changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"),
    Path("changes/raos-v2/phase-2/generated/publication-candidate.v2.json"),
    Path("changes/raos-v2/phase-2/generated/synthetic-seal-receipt.v2.json"),
    Path("changes/raos-v2/phase-2/generated/sitemap-candidates.v2.yaml"),
    Path("changes/raos-v2/phase-2/generated/phase-2-validation.v2.json"),
    Path("changes/raos-v2/phase-2/generated/local-evidence-bundle.v2.json"),
    Path("changes/raos-v2/phase-2/phase-2-report.md"),
    Path("changes/raos-v2/phase-2/integration-pr-body.md"),
    Path("changes/raos-v2/phase-2/preview/index.html"),
    Path("changes/raos-v2/phase-2/preview/carry-on/index.html"),
    Path("changes/raos-v2/phase-2/preview/tools/carry-on-size-checker/index.html"),
    Path("changes/raos-v2/phase-2/preview/guides/carry-on-baggage-rules/index.html"),
    Path(
        "changes/raos-v2/phase-2/preview/guides/low-cost-carrier-7kg-packing/index.html"
    ),
    Path("changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html"),
    Path("changes/raos-v2/phase-2/preview/guides/carry-on-bag-measurement/index.html"),
    Path(
        "changes/raos-v2/phase-2/preview/policy/how-we-compare-carry-on-products/index.html"
    ),
    Path(
        "changes/raos-v2/phase-2/preview/differences/ace-cresta-vs-difference-vs-maxpass4/index.html"
    ),
)
TEST_PATHS: Final = (Path("tests/raos_v2"),)

PACKAGE_SHA256: Final = (
    "7ea856e74d73589ae37d1248e08e685e5d022b90bfc45c9bf1d6cb414b5fc42a"
)
IMMUTABLE_BASE_HEAD: Final = "ae92eb8f50e9d439c1c292cc6c76d5a9c50f85c7"
SOURCE_MANIFEST_SHA256: Final = (
    "db9dc42bebd84090b18103cc9a48a6098f9d890af3f52b93cc33a6d52f821a44"
)
PROMPT_PATH: Final = "CODEX_MASTER_IMPLEMENTATION_PROMPT.md"
PROMPT_SHA256: Final = (
    "a122782725efb57b9fbaa7c916e821252736c0556c993b15604872f2a424f54f"
)
PROMPT_BYTES: Final = 22093
SOURCE_PACKAGE_GENERATED_AT: Final = "2026-08-28T22:30:00+09:00"
SCHEMA_URI_ROOT: Final = "https://kurashinoshirube.com/contracts/raos-v2/v1"
BROWSER_EVIDENCE_INPUT_PATH: Final = PHASE2_RECORDED_EVIDENCE_PATHS[0]
LOCAL_TEST_EVIDENCE_INPUT_PATH: Final = PHASE2_RECORDED_EVIDENCE_PATHS[1]
VISUAL_EVIDENCE_INPUT_PATH: Final = PHASE2_RECORDED_EVIDENCE_PATHS[2]


class BuildFailure(RuntimeError):
    """A sanitized, deterministic successor build failure."""


def fail(code: str) -> NoReturn:
    raise BuildFailure(code) from None


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def exact_file_set_sha256(paths: Sequence[Path]) -> str:
    """Bind every byte and filename in a small semantic input set."""

    rows: list[dict[str, object]] = []
    for path in paths:
        try:
            payload = (ROOT / path).read_bytes()
        except OSError:
            fail("RAOS_V2_PUBLICATION_INPUT_MISSING")
        rows.append(
            {
                "path": path.as_posix(),
                "bytes": len(payload),
                "sha256": sha256(payload),
            }
        )
    return sha256(canonical_json_bytes({"files": rows}))


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def yaml_bytes(value: object) -> bytes:
    return yaml.dump(
        value,
        Dumper=_NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    ).encode("utf-8")


def _read_json(path: Path) -> Any:
    try:
        return load_json_strict((ROOT / path).read_bytes())
    except (OSError, ValidationFailure):
        fail("RAOS_V2_SOURCE_JSON_INVALID")


def _read_yaml(path: Path) -> Any:
    try:
        return load_yaml_strict((ROOT / path).read_bytes())
    except (OSError, ValidationFailure):
        fail("RAOS_V2_SOURCE_YAML_INVALID")


def _manifest_hashes() -> dict[str, str]:
    path = ROOT / SOURCE_ROOT / "MANIFEST.sha256"
    result: dict[str, str] = {}
    try:
        payload = path.read_bytes()
        if sha256(payload) != SOURCE_MANIFEST_SHA256:
            fail("RAOS_V2_SOURCE_MANIFEST_ANCHOR_MISMATCH")
        lines = payload.decode("utf-8").splitlines()
    except (OSError, UnicodeError):
        fail("RAOS_V2_SOURCE_MANIFEST_INVALID")
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or parts[1] in result:
            fail("RAOS_V2_SOURCE_MANIFEST_INVALID")
        result[parts[1]] = parts[0]
    return result


def source_import_document(capture: Mapping[str, object]) -> dict[str, object]:
    manifest = _manifest_hashes()
    imported: list[dict[str, object]] = []
    expected_paths = {
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_PATHS
        if path.is_relative_to(SOURCE_ROOT)
    }
    if PROMPT_PATH in expected_paths or PROMPT_PATH not in manifest:
        fail("RAOS_V2_PROMPT_BOUNDARY_INVALID")
    for relative in sorted(expected_paths):
        path = ROOT / SOURCE_ROOT / relative
        try:
            payload = path.read_bytes()
        except OSError:
            fail("RAOS_V2_SOURCE_FILE_MISSING")
        expected_hash = manifest.get(relative)
        if relative == "MANIFEST.sha256":
            expected_hash = sha256(payload)
        if expected_hash is None or sha256(payload) != expected_hash:
            fail("RAOS_V2_SOURCE_FILE_HASH_MISMATCH")
        imported.append(
            {"path": relative, "bytes": len(payload), "sha256": sha256(payload)}
        )
    package_manifest = _read_json(SOURCE_ROOT / "package_manifest.json")
    if not isinstance(package_manifest, dict):
        fail("RAOS_V2_PACKAGE_MANIFEST_INVALID")
    prompt_row = next(
        (
            row
            for row in package_manifest.get("files", [])
            if isinstance(row, dict) and row.get("path") == PROMPT_PATH
        ),
        None,
    )
    if prompt_row != {
        "path": PROMPT_PATH,
        "sha256": PROMPT_SHA256,
        "size_bytes": PROMPT_BYTES,
    }:
        fail("RAOS_V2_PROMPT_RECEIPT_INVALID")
    return {
        "schema": "RAOS_V2_SOURCE_IMPORT_V1",
        "source_layer": "IMMUTABLE_SUCCESSOR_DESIGN_SOURCE",
        "package_sha256": PACKAGE_SHA256,
        "package_version": "2.0.0-design",
        "source_package_generated_at": SOURCE_PACKAGE_GENERATED_AT,
        "import_observed_at": capture.get("captured_at"),
        "imported_files": imported,
        "excluded_files": [
            {
                "path": PROMPT_PATH,
                "bytes": PROMPT_BYTES,
                "sha256": PROMPT_SHA256,
                "reason": "PROMPT_IS_DATA_NOT_EXECUTABLE_AUTHORITY",
            }
        ],
        "rules": {
            "source_files_mutable": False,
            "clarifications_are_separate_overlay": True,
            "external_actions_authorized": False,
        },
    }


def clarifications_document() -> dict[str, object]:
    return {
        "schema": "RAOS_V2_CLARIFICATIONS_V1",
        "version": "1.0.0",
        "authority": "USER_PLAN_AND_REPOSITORY_POLICY_OVER_DESIGN_SOURCE",
        "source_package_sha256": PACKAGE_SHA256,
        "clarifications": [
            {
                "id": "C-V2-001",
                "decision": "successor source layer lives below changes/raos-v2",
                "supersedes": "any source suggestion to mutate canonical/upstream/zip",
            },
            {
                "id": "C-V2-002",
                "decision": "the machine contract has seven templates",
                "value": [
                    "HOME",
                    "HUB",
                    "GUIDE",
                    "COMPARISON",
                    "DIFFERENCE",
                    "TOOL",
                    "POLICY",
                ],
                "supersedes": "prose references to six templates",
            },
            {
                "id": "C-V2-003",
                "decision": "Phase 0 owns T-V2-001..006, T-V2-040 and T-V2-051; T-V2-007 starts Phase 1",
            },
            {
                "id": "C-V2-004",
                "decision": "effective phase planning ceilings are P0=16h, P1=40h and P2=80h",
                "note": "backlog row sums are reconciliation information, not additive gates",
            },
            {
                "id": "C-V2-005",
                "decision": "B-V2-009 depends on every B-V2-001..008 artifact",
            },
            {
                "id": "C-V2-006",
                "decision": "ArticleDefinition requires ordered blocks and temporal source fields are mandatory",
            },
            {
                "id": "C-V2-007",
                "decision": "Phase 0-2 real content cannot be human-reviewed or sealed; only synthetic fixtures may reach PACKAGE_SEALED",
            },
            {
                "id": "C-V2-008",
                "decision": "B-V2-017 defines the WordPress port; its disabled adapter is Phase 2",
            },
            {
                "id": "C-V2-009",
                "decision": "T-V2-027 route collisions fail closed",
            },
            {
                "id": "C-V2-010",
                "decision": "B-V2-031 also waits B-V2-030; B-V2-033 waits B-V2-027/B-V2-029/B-V2-030; B-V2-034 waits B-V2-019..033",
            },
            {
                "id": "C-V2-011",
                "decision": "airline rules without a published effective date use a null effective_from plus observed_applicable_from and OBSERVED_CURRENT_AT_CAPTURE_NO_PUBLISHED_EFFECTIVE_DATE; only an official date may use OFFICIAL_EFFECTIVE_DATE",
            },
            {
                "id": "C-V2-012",
                "decision": "airline effective intervals are machine-defined as FROM_INCLUSIVE_TO_EXCLUSIVE",
            },
            {
                "id": "C-V2-013",
                "decision": "packages/web-ui/src/decision-support-v2 is the authoritative UI source; its preview subtree is the sole deterministic preview input and changes/raos-v2/phase-2/preview contains generated output only",
                "supersedes": "the former duplicated changes/raos-v2/phase-2/ui-source input location",
            },
        ],
    }


def _capture_input() -> dict[str, object]:
    value = _read_json(RECORDED_INPUT_PATH)
    repository = value.get("repository") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("schema") != "RAOS_V2_PHASE0_CAPTURE_V1"
        or not isinstance(repository, dict)
        or repository.get("head") != IMMUTABLE_BASE_HEAD
        or protected_path_changes(IMMUTABLE_BASE_HEAD, root=ROOT)
    ):
        fail("RAOS_V2_CAPTURE_INPUT_INVALID")
    return value


def preflight_document(capture: Mapping[str, object]) -> dict[str, object]:
    repository = capture.get("repository")
    if not isinstance(repository, dict):
        fail("RAOS_V2_CAPTURE_REPOSITORY_INVALID")
    if repository.get("head") != IMMUTABLE_BASE_HEAD:
        fail("RAOS_V2_CAPTURE_REPOSITORY_INVALID")
    return {
        "schema": "RAOS_V2_PREFLIGHT_REPORT_V1",
        "captured_at": capture.get("captured_at"),
        "repository": repository,
        "immutable_base_head": IMMUTABLE_BASE_HEAD,
        "package": {
            "sha256": PACKAGE_SHA256,
            "source_import": "changes/raos-v2/source-import.v1.json",
            "prompt_executed": False,
        },
        "boundaries": {
            "immutable_paths": ["docs/canonical/**", "docs/upstream/**", "zip/**"],
            "external_actions": "NOT_EXECUTED",
            "public_observation": capture.get("public_observation_status"),
            "local_evidence_label": "PASSED_LOCAL",
            "generator_owner": "scripts/build_raos_v2_successor.py",
        },
        "backlog_id": "B-V2-001",
        "test_ids": ["T-V2-001", "T-V2-002", "T-V2-003", "T-V2-051"],
    }


def source_audit_document() -> dict[str, object]:
    trace = _read_yaml(SOURCE_ROOT / "07_DECISION_TRACEABILITY.yaml")
    interfaces = _read_yaml(SOURCE_ROOT / "10_INTERFACE_CONTRACTS.yaml")
    if not isinstance(trace, dict) or not isinstance(interfaces, dict):
        fail("RAOS_V2_SOURCE_MACHINE_DOCUMENT_INVALID")
    counts = {
        key: len(trace.get(key, []))
        for key in ("decisions", "requirements", "backlog", "tests")
    }
    if counts != {"decisions": 34, "requirements": 36, "backlog": 49, "tests": 51}:
        fail("RAOS_V2_SOURCE_TRACEABILITY_COUNT_MISMATCH")
    return {
        "schema": "RAOS_V2_SOURCE_AUDIT_REPORT_V1",
        "status": "PASSED_LOCAL",
        "source_package_sha256": PACKAGE_SHA256,
        "source_layer_file_count": 19,
        "excluded_prompt_count": 1,
        "traceability_counts": counts,
        "interface_entities": sorted(interfaces.get("entities", {})),
        "interface_ports": sorted(interfaces.get("ports", {})),
        "interpretation": "DESIGN_INPUT_NOT_EXECUTABLE_INSTRUCTIONS",
        "freshness": "REVALIDATE_EXTERNAL_FACTS_BEFORE_PUBLICATION",
        "backlog_id": "B-V2-002",
        "test_ids": ["T-V2-002", "T-V2-003"],
    }


def _phase0_visual_evidence() -> dict[str, object]:
    value = _read_json(PHASE0_VISUAL_EVIDENCE_PATH)
    if (
        not isinstance(value, dict)
        or value.get("schema")
        != "RAOS_V2_RECORDED_PHASE0_VISUAL_EVIDENCE_V1"
        or value.get("evidence_class") != "PUBLIC_READ_ONLY_MANUAL_RECORDED"
        or value.get("raw_images") != "LOCAL_ONLY_NOT_TRACKED_NOT_REVERIFIED"
        or value.get("external_actions") != "NOT_EXECUTED"
    ):
        fail("RAOS_V2_PHASE0_VISUAL_EVIDENCE_INVALID")
    rows = value.get("screenshots")
    if not isinstance(rows, list) or len(rows) != 12:
        fail("RAOS_V2_PHASE0_VISUAL_EVIDENCE_INVALID")
    expected_paths = {
        "/",
        "/carry-on-suitcase-comparison/",
        "/portable-power-station-guide/",
        "/anker-solix-c300-c800-c1000-differences/",
    }
    expected_viewports = {"390x844", "768x1024", "1440x900"}
    observed_pairs: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "bytes",
            "path",
            "sha256",
            "viewport",
        }:
            fail("RAOS_V2_PHASE0_VISUAL_EVIDENCE_INVALID")
        path = row.get("path")
        viewport = row.get("viewport")
        byte_count = row.get("bytes")
        digest = row.get("sha256")
        if (
            path not in expected_paths
            or viewport not in expected_viewports
            or not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count <= 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            fail("RAOS_V2_PHASE0_VISUAL_EVIDENCE_INVALID")
        observed_pairs.add((str(path), str(viewport)))
    if observed_pairs != {
        (path, viewport)
        for path in expected_paths
        for viewport in expected_viewports
    }:
        fail("RAOS_V2_PHASE0_VISUAL_EVIDENCE_INVALID")
    return value


def public_url_inventory(capture: Mapping[str, object]) -> dict[str, object]:
    observations = capture.get("public_urls")
    by_path: dict[str, object] = {}
    if isinstance(observations, list):
        by_path = {
            str(row.get("path")): row
            for row in observations
            if isinstance(row, dict) and isinstance(row.get("path"), str)
        }
    initial = [
        ("/", "KEEP_CURRENT", "home"),
        ("/carry-on-suitcase-comparison/", "MIGRATE_AFTER_VERTICAL_SLICE", "pilot"),
        ("/portable-power-station-guide/", "KEEP_CURRENT_DEFER_V2", "pilot"),
        (
            "/anker-solix-c300-c800-c1000-differences/",
            "KEEP_CURRENT_DEFER_V2",
            "pilot",
        ),
        (
            "/countertop-dishwasher-for-small-households/",
            "NO_ROUTE_OR_REDIRECT",
            "pilot",
        ),
        ("/compact-robot-vacuum-shortlist/", "NO_ROUTE_OR_REDIRECT", "pilot"),
        ("/about-ad-policy/", "KEEP_CURRENT", "policy"),
        ("/advertising-policy/", "NO_ROUTE_OR_REDIRECT", "observed_candidate"),
        ("/privacy-policy/", "KEEP_CURRENT", "policy"),
    ]
    rows: list[dict[str, object]] = []
    for path, disposition, role in initial:
        observation = by_path.get(path)
        if isinstance(observation, dict):
            observed = deepcopy(observation)
        else:
            observed = {
                "status": "UNAVAILABLE",
                "redirect_chain": [],
                "canonical": "UNAVAILABLE",
                "robots": "UNAVAILABLE",
                "h1": "UNAVAILABLE",
                "sitemap_membership": "UNAVAILABLE",
                "body_sha256": "UNAVAILABLE",
                "observed_at": "UNAVAILABLE",
            }
        rows.append(
            {
                "url": f"https://kurashinoshirube.com{path}",
                "path": path,
                "role": role,
                "safe_initial_disposition": disposition,
                "observation": observed,
            }
        )
    supporting = capture.get("supporting_resources")
    visual_evidence = _phase0_visual_evidence()
    return {
        "schema": "RAOS_V2_PUBLIC_URL_INVENTORY_V1",
        "evidence_class": capture.get("public_observation_status"),
        "capture_contract": {
            "scope": supporting.get("capture_scope")
            if isinstance(supporting, dict)
            else "UNAVAILABLE",
            "maximum_urls": supporting.get("maximum_capture_urls")
            if isinstance(supporting, dict)
            else "UNAVAILABLE",
            "unlisted_sitemap_urls_are_silently_dropped": False,
        },
        "automatic_public_mutation": False,
        "visual_baseline_evidence": {
            "source": PHASE0_VISUAL_EVIDENCE_PATH.as_posix(),
            "classification": visual_evidence.get("evidence_class"),
            "raw_images": visual_evidence.get("raw_images"),
            "capture_contract": visual_evidence.get("capture_contract"),
        },
        "visual_baseline": deepcopy(visual_evidence["screenshots"]),
        "urls": rows,
        "backlog_id": "B-V2-003",
        "test_ids": ["T-V2-004", "T-V2-005"],
    }


def metric_dictionary() -> dict[str, object]:
    rows = [
        (
            "QDS",
            "distinct eligible 30-minute sessions with tool result OR comparison/evidence followed by official-source or affiliate activation",
            "LOCAL_FIRST_PARTY_EVENTS",
            "EVENT_OBSERVED",
        ),
        (
            "NON_BRAND_ORGANIC_SESSIONS",
            "Search Console organic sessions excluding approved brand query set",
            "SEARCH_CONSOLE_EXPORT",
            "GSC_FINAL",
        ),
        (
            "NON_BRAND_IMPRESSIONS",
            "Search Console impressions excluding approved brand query set",
            "SEARCH_CONSOLE_EXPORT",
            "GSC_FINAL",
        ),
        (
            "NON_BRAND_QUERY_WIDTH",
            "count(distinct eligible non-brand queries)",
            "SEARCH_CONSOLE_EXPORT",
            "GSC_FINAL",
        ),
        (
            "AFFILIATE_OUTBOUND_CTR",
            "verified affiliate outbound activations / eligible decision sessions",
            "LOCAL_FIRST_PARTY_EVENTS",
            "EVENT_OBSERVED",
        ),
        (
            "CONFIRMED_EPC",
            "mature confirmed reward JPY / attributable verified outbound clicks",
            "SANITIZED_RAKUTEN_EXPORT",
            "CONFIRMED",
        ),
        (
            "CONFIRMED_RPM",
            "mature confirmed reward JPY / eligible sessions * 1000",
            "SANITIZED_RAKUTEN_EXPORT_AND_EVENTS",
            "CONFIRMED",
        ),
        (
            "CASH_CONTRIBUTION_PROFIT",
            "confirmed reward JPY - paid variable cash cost JPY",
            "FINANCE_LEDGER",
            "CONFIRMED",
        ),
        (
            "ECONOMIC_CONTRIBUTION_PROFIT",
            "confirmed reward JPY - variable cash cost JPY - human hours * internal hourly cost JPY",
            "FINANCE_AND_TIME_LEDGER",
            "CONFIRMED",
        ),
        (
            "MONTHLY_CONFIRMED_CONTRIBUTION_PROFIT",
            "monthly confirmed reward JPY - monthly variable cash cost JPY - monthly human hours * internal hourly cost JPY",
            "FINANCE_AND_TIME_LEDGER",
            "CONFIRMED",
        ),
        (
            "ARTICLE_PAYBACK_MONTHS",
            "article production economic cost / mature monthly article contribution",
            "ATTRIBUTION_AND_COST_LEDGER",
            "CONFIRMED",
        ),
        (
            "CATEGORY_PAYBACK_MONTHS",
            "category production and maintenance economic cost / mature monthly confirmed category contribution",
            "CATEGORY_ATTRIBUTION_AND_COST_LEDGER",
            "CONFIRMED",
        ),
        (
            "DIRECT_AND_RETURN_RATE",
            "eligible direct or returning sessions / eligible sessions",
            "LOCAL_FIRST_PARTY_EVENTS",
            "EVENT_OBSERVED",
        ),
        (
            "CORRECTION_RATE",
            "published corrections / reviewed published assets",
            "EDITORIAL_LEDGER",
            "HUMAN_REVIEWED",
        ),
        (
            "MAJOR_FACT_DEFECTS",
            "count of confirmed high-severity factual defects",
            "EDITORIAL_INCIDENT_LEDGER",
            "HUMAN_CONFIRMED",
        ),
        (
            "COMPLAINT_FIRST_RESPONSE_WITHIN_72H_RATE",
            "eligible complaints receiving a recorded first response within 72 hours / eligible complaints",
            "EDITORIAL_COMPLAINT_LEDGER",
            "HUMAN_CONFIRMED",
        ),
        (
            "STALE_EXPOSURE_RATE",
            "sessions exposed to overdue claims / eligible sessions",
            "FRESHNESS_AND_EVENT_LEDGER",
            "EVENT_OBSERVED",
        ),
        (
            "HUMAN_HOURS_PER_ARTICLE",
            "human logged production hours / completed articles",
            "TIME_LEDGER",
            "HUMAN_RECORDED",
        ),
        (
            "UPDATE_COST_PER_PAGE",
            "human update hours * internal hourly cost / updated pages",
            "TIME_LEDGER",
            "HUMAN_RECORDED",
        ),
    ]
    return {
        "schema": "RAOS_V2_METRIC_DICTIONARY_V1",
        "currency": "JPY",
        "timezone": "Asia/Tokyo",
        "rules": {
            "missing_value": "UNAVAILABLE",
            "missing_never_equals_zero": True,
            "pending_never_equals_confirmed": True,
            "unattributed_program_total_never_populates_article_reward": True,
        },
        "metrics": [
            {
                "id": identifier,
                "formula": formula,
                "source": source,
                "required_maturity": maturity,
                "current_value": "UNAVAILABLE",
                "unavailable_rule": "return UNAVAILABLE when any required numerator, denominator, maturity or attribution input is absent",
            }
            for identifier, formula, source, maturity in rows
        ],
        "backlog_id": "B-V2-005",
        "test_ids": ["T-V2-006"],
    }


def deprecation_ledger() -> dict[str, object]:
    keep_gate = "NO_DELETION_SUCCESSOR_REVIEW_REQUIRED"
    removal_gate = "MINIMUM_2_RELEASES_AND_30_DAYS_UNUSED_PLUS_HUMAN_APPROVAL"
    assets = [
            {
                "asset": "root development policy/build/generator ownership",
                "decision": "KEEP",
                "reason": "dirty protection, standard commands and one generated owner are implementation safety",
                "migration": "register V2 owner in the existing graph and retain root workflow",
                "deletion_gate": keep_gate,
            },
            {
                "asset": "docs/canonical docs/upstream and zip baselines",
                "decision": "KEEP",
                "reason": "immutable V1 evidence and authority cannot be rewritten by the successor",
                "migration": "read-only reference from changes/raos-v2 overlay",
                "deletion_gate": "NEVER_FROM_V2",
            },
            {
                "asset": "secret scan denied-network authz and public/internal isolation",
                "decision": "KEEP",
                "reason": "validated security boundaries remain necessary",
                "migration": "inherit as local tests and deny-default adapter policy",
                "deletion_gate": keep_gate,
            },
            {
                "asset": "publication operator journal and rollback concepts",
                "decision": "REWORK",
                "reason": "human gate, hash binding and rollback are valuable but the old breadth is excessive",
                "migration": "reduce to local package states, synthetic seal test and disabled dry-run port",
                "deletion_gate": removal_gate,
            },
            {
                "asset": "claim evidence and editorial domain",
                "decision": "REWORK",
                "reason": "purpose is retained while the generic type surface is too broad",
                "migration": "narrow to A_OFFICIAL_FACT D_EDITORIAL_JUDGEMENT and UNKNOWN",
                "deletion_gate": removal_gate,
            },
            {
                "asset": "Rakuten adapter",
                "decision": "REWORK",
                "reason": "exact identity and current provider constraints require a smaller boundary",
                "migration": "RECORDED_ONLY fixture first; live mode absent through Phase 2",
                "deletion_gate": removal_gate,
            },
            {
                "asset": "public WordPress theme and Yoast integration",
                "decision": "MIGRATE",
                "reason": "public URLs must survive while UX and IA change",
                "migration": "disabled adapter then one-URL-at-a-time human-gated migration",
                "deletion_gate": removal_gate,
            },
            {
                "asset": "published carry-on comparison article",
                "decision": "MIGRATE",
                "reason": "current search and reader-learning asset in the selected wedge",
                "migration": "preserve slug/canonical until a verified V2 replacement is approved",
                "deletion_gate": "NO_DELETE_SLUG_PRESERVING_REPLACEMENT_ONLY",
            },
            {
                "asset": "portable power Anker dishwasher and robot-vacuum assets",
                "decision": "DEFER",
                "reason": "outside the wedge with unresolved evidence/media/safety cost",
                "migration": "preserve current public state; re-score only after Phase 6 gate",
                "deletion_gate": removal_gate,
            },
            {
                "asset": "empty 家事 and 備え category UI",
                "decision": "RETIRE",
                "reason": "empty navigation harms trust and crawl quality",
                "migration": "remove only from successor navigation after URL inventory decision",
                "deletion_gate": removal_gate,
            },
            {
                "asset": "Next.js or headless public application",
                "decision": "DEFER",
                "reason": "would duplicate the retained WordPress renderer",
                "migration": "reconsider only after measured WordPress limits",
                "deletion_gate": keep_gate,
            },
            {
                "asset": "custom admin and review UI",
                "decision": "DEFER",
                "reason": "maintenance exceeds value at 25-page scale",
                "migration": "reconsider at 50 pages or measured admin friction over 4h/week",
                "deletion_gate": removal_gate,
            },
            {
                "asset": "advanced causal attribution rank provider and paid dashboard",
                "decision": "DEFER",
                "reason": "provider evidence and zero-spend constraints do not support it",
                "migration": "begin with GSC, first-party events and monthly sanitized reports",
                "deletion_gate": removal_gate,
            },
            {
                "asset": "automatic or partial publication",
                "decision": "RETIRE",
                "reason": "initial reader and production risk exceeds value",
                "migration": "remove capability; retain only explicit human-gated contracts",
                "deletion_gate": removal_gate,
            },
            {
                "asset": "general Postgres and object-storage persistence",
                "decision": "DEFER",
                "reason": "versioned JSON/YAML is sufficient at current scale",
                "migration": "reconsider after >10k records, measured latency or merge conflicts",
                "deletion_gate": keep_gate,
            },
        ]
    for row in assets:
        decision = str(row["decision"])
        row["usage_evidence"] = {
            "status": (
                "CURRENT_OR_REFERENCED"
                if decision in {"KEEP", "REWORK", "MIGRATE"}
                else "NOT_ADOPTED_IN_V2_CURRENT_USAGE_UNAVAILABLE"
            ),
            "source": "REPOSITORY_AND_PUBLIC_URL_INVENTORY",
            "verified_unused": False,
        }
        row["replacement"] = {
            "status": (
                "NOT_APPLICABLE_RETAINED"
                if decision == "KEEP"
                else "SAFE_DEFAULT_PRESERVE_OR_DO_NOT_INTRODUCE"
                if decision == "DEFER"
                else "SUCCESSOR_DEFINED"
            ),
            "plan": row["migration"],
        }
        row["rollback"] = {
            "status": "NOT_APPLICABLE_RETAINED" if decision == "KEEP" else "LOCAL_PLAN_ONLY",
            "plan": (
                "asset remains retained; no retirement rollback is applicable"
                if decision == "KEEP"
                else "restore the prior owner/configuration from version control and rerun focused contracts before any external action"
            ),
            "production_execution": "NOT_EXECUTED",
        }
        row["removal_readiness"] = (
            "BLOCKED_USAGE_NOT_VERIFIED_UNUSED"
            if decision == "RETIRE"
            else "NOT_REQUESTED"
        )
    document = {
        "schema": "RAOS_V2_DEPRECATION_LEDGER_V1",
        "automatic_deletion": False,
        "default_removal_gate": removal_gate,
        "retire_requires_verified_unused": True,
        "assets": assets,
        "backlog_id": "B-V2-006",
        "test_ids": ["T-V2-051"],
    }
    validate_deprecation_ledger_document(document)
    return document


def validate_deprecation_ledger_document(document: Mapping[str, object]) -> None:
    rows = document.get("assets")
    if (
        document.get("automatic_deletion") is not False
        or document.get("retire_requires_verified_unused") is not True
        or not isinstance(rows, list)
        or len(rows) != 15
    ):
        fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
    observed_assets: set[str] = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("asset"), str)
            or not row["asset"]
            or row["asset"] in observed_assets
            or row.get("decision")
            not in {"KEEP", "REWORK", "MIGRATE", "RETIRE", "DEFER"}
            or not all(
            isinstance(row.get(key), dict)
            for key in ("usage_evidence", "replacement", "rollback")
            )
        ):
            fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
        observed_assets.add(str(row["asset"]))
        usage = row["usage_evidence"]
        replacement = row["replacement"]
        rollback = row["rollback"]
        assert isinstance(usage, dict)
        assert isinstance(replacement, dict)
        assert isinstance(rollback, dict)
        if (
            not isinstance(usage.get("status"), str)
            or not usage["status"]
            or not isinstance(usage.get("source"), str)
            or not usage["source"]
            or not isinstance(usage.get("verified_unused"), bool)
            or not isinstance(replacement.get("status"), str)
            or not replacement["status"]
            or not isinstance(replacement.get("plan"), str)
            or not replacement["plan"]
            or not isinstance(rollback.get("status"), str)
            or not rollback["status"]
            or not isinstance(rollback.get("plan"), str)
            or not rollback["plan"]
            or rollback.get("production_execution") != "NOT_EXECUTED"
            or not isinstance(row.get("deletion_gate"), str)
            or not row["deletion_gate"]
        ):
            fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")
        if row.get("decision") == "RETIRE" and (
            usage.get("verified_unused") is not False
            or row.get("removal_readiness")
            != "BLOCKED_USAGE_NOT_VERIFIED_UNUSED"
        ):
            fail("RAOS_V2_DEPRECATION_LEDGER_INVALID")


def pilot_reconciliation(capture: Mapping[str, object]) -> dict[str, object]:
    observations = capture.get("public_urls")
    by_path = (
        {
            str(row.get("path")): row
            for row in observations
            if isinstance(row, dict) and isinstance(row.get("path"), str)
        }
        if isinstance(observations, list)
        else {}
    )

    def observed(path: str) -> dict[str, object]:
        value = by_path.get(path)
        if not isinstance(value, dict):
            fail("RAOS_V2_PILOT_OBSERVATION_MISSING")
        return {
            "status": value.get("status"),
            "canonical": value.get("canonical"),
            "sitemap_membership": value.get("sitemap_membership"),
            "body_sha256": value.get("body_sha256"),
            "observed_at": value.get("observed_at"),
            "evidence_class": capture.get("public_observation_status"),
        }

    return {
        "schema": "RAOS_V2_PILOT_RECONCILIATION_V1",
        "automatic_public_action": False,
        "articles": [
            {
                "article_id": "st1703-first-suitcase-comparison",
                "route": "/carry-on-suitcase-comparison/",
                "safe_action": "KEEP_PUBLIC_AND_MIGRATE",
                "observation": observed("/carry-on-suitcase-comparison/"),
            },
            {
                "article_id": "st1704-portable-power-station-guide",
                "route": "/portable-power-station-guide/",
                "safe_action": "KEEP_PUBLIC_DEFER_V2",
                "observation": observed("/portable-power-station-guide/"),
            },
            {
                "article_id": "st1704-anker-solix-c300-c800-c1000-differences",
                "route": "/anker-solix-c300-c800-c1000-differences/",
                "safe_action": "KEEP_PUBLIC_DEFER_V2",
                "observation": observed("/anker-solix-c300-c800-c1000-differences/"),
            },
            {
                "article_id": "st1704-countertop-dishwasher-for-small-households",
                "route": "/countertop-dishwasher-for-small-households/",
                "safe_action": "NO_NEW_ROUTE_NO_REDIRECT",
                "observation": observed("/countertop-dishwasher-for-small-households/"),
            },
            {
                "article_id": "st1704-compact-robot-vacuum-shortlist",
                "route": "/compact-robot-vacuum-shortlist/",
                "safe_action": "NO_NEW_ROUTE_NO_REDIRECT",
                "observation": observed("/compact-robot-vacuum-shortlist/"),
            },
        ],
        "backlog_id": "B-V2-007",
        "test_ids": ["T-V2-004", "T-V2-005", "T-V2-051"],
    }


def rollback_contract() -> dict[str, object]:
    round_trip = simulate_route_round_trip(
        (
            "/carry-on-suitcase-comparison/",
            200,
            "https://kurashinoshirube.com/carry-on-suitcase-comparison/",
            "index,follow",
        ),
        (
            "/carry-on-suitcase-comparison/",
            200,
            "https://kurashinoshirube.com/carry-on-suitcase-comparison/",
            "noindex,nofollow",
        ),
    )
    return {
        "schema": "RAOS_V2_ROLLBACK_CONTRACT_V1",
        "scope": "LOCAL_SIMULATION_ONLY",
        "production_backup": "NOT_EXECUTED",
        "production_restore": "NOT_EXECUTED",
        "public_mutation": "NOT_EXECUTED",
        "invariants": [
            "existing public URL remains unchanged through Phase 2",
            "redirect chain length is at most one hop",
            "redirect loops are rejected",
            "many unrelated sources cannot redirect to home",
            "rollback restores the exact prior route/canonical/robots tuple",
            "sealed-package round trip preserves every input hash",
        ],
        "simulation": {
            "states": [
                "BASELINE_CAPTURED",
                "CANDIDATE_RENDERED",
                "DIFF_VERIFIED",
                "ROLLBACK_SIMULATED",
            ],
            "result": "PASSED_LOCAL",
            "route_tuple_round_trip": round_trip,
            "redirect_rules": [],
        },
        "backlog_id": "B-V2-008",
        "test_ids": ["T-V2-005", "T-V2-040"],
    }


OBSERVATION_PLAN: Final = """# RAOS V2 production observation plan

Status: **NOT_EXECUTED**. This is a read-only plan, not permission to access an
admin surface or change production.

## Allowed public observation

- Credential- and cookie-free HTTPS GET/HEAD against `kurashinoshirube.com` only.
- Known public URLs and same-origin sitemap URLs, with a hard item/byte/time cap.
- Record status, one-hop redirect evidence, canonical, robots, one H1, sitemap
  membership, body SHA-256 and JST observation time. Never store the response body.
- Capture home and confirmed-public pilot reader surfaces at 390, 768 and 1440px.
  Policy pages receive metadata-only observation.

## Denied surfaces and actions

Admin/login/preview/private/query-bearing URLs, credentials, cookies, WordPress or
Yoast writes, plugin/theme changes, publication, deployment and provider writes are
denied. A changed live state never triggers delete, unpublish, noindex or redirect.

## Human/external boundary

WordPress inventory, backup/restore, deployment, credentials and production
analytics configuration remain `NOT_EXECUTED` until separately authorized. Local
fixtures and rollback simulation may be executed and labelled `PASSED_LOCAL`.

Backlog: B-V2-004. Tests: T-V2-004, T-V2-005, T-V2-039.
"""


PHASE0_REPORT: Final = """# RAOS V2 Phase 0 report

Phase 0's nine artifacts are generated from the checksum-bound successor source
layer and a sanitized recorded capture. B-V2-001 through B-V2-008 are terminal
before this B-V2-009 report is emitted.

| Boundary | Result |
|---|---|
| Source package/import integrity | PASSED_LOCAL |
| Attached ZIP container | PASSED_LOCAL when local attachment is present; CI may skip only this container check while committed 19-file manifest/hash checks remain mandatory |
| Strict JSON/YAML/schema/traceability checks | PASSED_LOCAL |
| Local rollback simulation | PASSED_LOCAL |
| Public read-only observation | See `public-url-inventory.yaml`; unavailable fields remain `UNAVAILABLE` |
| Production backup/restore/write | NOT_EXECUTED |
| Deployment/publication/credentials/spend | NOT_EXECUTED |

Safe defaults keep current public surfaces unchanged, migrate only the existing
carry-on comparison after a verified vertical slice, defer the power articles,
and create no routes or redirects for the expected dishwasher/robot-vacuum 404s.

Effective planning ceiling: 16 hours. Backlog row estimates are reconciliation
information and are not additive stop gates. External spend ceiling: JPY 0.

Backlog: B-V2-009. Tests: T-V2-001..006, T-V2-040, T-V2-051.
"""


PORTFOLIO: Final = (
    ("A01", "/carry-on/", "機内持ち込み荷物の条件から選ぶ", "HUB", "RULE", 1),
    (
        "A02",
        "/tools/carry-on-size-checker/",
        "機内持ち込みサイズ・重量チェッカー",
        "TOOL",
        "DECISION",
        1,
    ),
    (
        "A03",
        "/guides/carry-on-baggage-rules/",
        "機内持ち込み手荷物の基本ルール",
        "GUIDE",
        "RULE",
        1,
    ),
    (
        "A04",
        "/guides/low-cost-carrier-7kg-packing/",
        "LCC 7kg以内に収める考え方",
        "GUIDE",
        "TASK",
        1,
    ),
    (
        "A05",
        "/carry-on-suitcase-comparison/",
        "機内持ち込みスーツケース3モデル条件別比較",
        "COMPARISON",
        "PRODUCT",
        1,
    ),
    (
        "A06",
        "/guides/carry-on-bag-measurement/",
        "キャスター・持ち手込みで測る方法",
        "GUIDE",
        "HOW_TO",
        1,
    ),
    (
        "A07",
        "/guides/domestic-airline-carry-on-size/",
        "国内線100席以上・未満のサイズ差",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A08",
        "/guides/ana-carry-on-baggage/",
        "ANAの機内持ち込み条件",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A09",
        "/guides/jal-carry-on-baggage/",
        "JALの機内持ち込み条件",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A10",
        "/guides/peach-carry-on-baggage/",
        "Peachの機内持ち込み条件",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A11",
        "/guides/jetstar-carry-on-baggage/",
        "Jetstarの機内持ち込み条件",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A12",
        "/guides/carry-on-expanded-suitcase/",
        "拡張機能を使うと持ち込めない場合",
        "GUIDE",
        "RISK",
        2,
    ),
    (
        "A13",
        "/guides/carry-on-personal-item/",
        "身の回り品と手荷物の違い",
        "GUIDE",
        "RULE",
        2,
    ),
    (
        "A14",
        "/guides/carry-on-weight-calculator/",
        "荷物の合計重量を見積もる方法",
        "TOOL",
        "DECISION",
        2,
    ),
    (
        "A15",
        "/comparisons/lightweight-carry-on-suitcases/",
        "公称重量で比べる軽量機内持ち込み候補",
        "COMPARISON",
        "PRODUCT",
        3,
    ),
    (
        "A16",
        "/comparisons/front-open-carry-on-suitcases/",
        "フロントオープン候補の条件比較",
        "COMPARISON",
        "PRODUCT",
        3,
    ),
    (
        "A17",
        "/comparisons/carry-on-suitcases-with-stopper/",
        "ストッパー付き候補の条件比較",
        "COMPARISON",
        "PRODUCT",
        3,
    ),
    (
        "A18",
        "/comparisons/soft-vs-hard-carry-on/",
        "ソフトとハードの仕様差から選ぶ",
        "DIFFERENCE",
        "DECISION",
        3,
    ),
    (
        "A19",
        "/differences/ace-cresta-vs-difference-vs-maxpass4/",
        "ACE 3モデルの違い",
        "DIFFERENCE",
        "PRODUCT",
        3,
    ),
    (
        "A20",
        "/guides/business-trip-carry-on/",
        "1〜2泊出張で先に決める条件",
        "GUIDE",
        "TASK",
        3,
    ),
    (
        "A21",
        "/guides/weekend-trip-carry-on/",
        "週末旅行の荷物から容量を決める",
        "GUIDE",
        "TASK",
        3,
    ),
    (
        "A22",
        "/guides/carry-on-laptop-size/",
        "PC収納と外寸を同時に確認する",
        "GUIDE",
        "TASK",
        4,
    ),
    (
        "A23",
        "/guides/carry-on-liquid-rules/",
        "液体物ルールの公式確認手順",
        "GUIDE",
        "RULE",
        4,
    ),
    (
        "A24",
        "/guides/carry-on-battery-rules/",
        "モバイルバッテリー持ち込み確認手順",
        "GUIDE",
        "RISK",
        4,
    ),
    (
        "A25",
        "/policy/how-we-compare-carry-on-products/",
        "機内持ち込み用品の比較方法",
        "POLICY",
        "TRUST",
        1,
    ),
)


def product_specification() -> dict[str, object]:
    portfolio = [
        {
            "article_id": article_id,
            "route": route,
            "working_title": title,
            "template": template,
            "intent_class": intent,
            "wave": wave,
            "phase_1_state": (
                "LOCAL_VERTICAL_SLICE_CANDIDATE" if wave == 1 else "PLANNED_LOCKED"
            ),
        }
        for article_id, route, title, template, intent, wave in PORTFOLIO
    ]
    return {
        "schema": "RAOS_V2_PRODUCT_SPEC_V2",
        "version": "2.0.0",
        "brand": {
            "public_name": "暮らしのしるべ",
            "internal_name": "RAOS V2",
            "positioning": "公式ルールと製品仕様を照合し、条件に合う候補だけを残す購買支援",
            "public_no_1_claim_allowed": False,
            "voice": ["具体的", "静か", "非誇張", "不明を不明と表示"],
        },
        "wedge": {
            "id": "WEDGE-CARRY-ON-JP-V1",
            "name": "旅の機内持ち込み条件と荷物選び",
            "market": "JP",
            "currency": "JPY",
            "timezone": "Asia/Tokyo",
            "single_wedge": True,
            "value_mechanisms": [
                "condition_input_decision_flow",
                "official_rule_and_product_spec_normalization",
                "fit_non_fit_and_unknown_visibility",
                "source_level_checked_at_and_change_tracking",
            ],
        },
        "templates": [
            "HOME",
            "HUB",
            "GUIDE",
            "COMPARISON",
            "DIFFERENCE",
            "TOOL",
            "POLICY",
        ],
        "portfolio": portfolio,
        "wave_1_contract": {
            "six_primary_assets": [f"A0{value}" for value in range(1, 7)],
            "support_policy": "A25",
            "public_action": "PHASE_3_HUMAN_GATED",
        },
        "gates": {
            "day_30": {
                "continue": [
                    "critical_defects=0",
                    "source_sla=100%",
                    "index_canonical_issues=0",
                    "QDS instrumentation AVAILABLE or approved UNAVAILABLE explanation",
                    "at least 2 non-brand query families observed",
                ],
                "otherwise": ["REPAIR", "EXTEND", "RETREAT"],
            },
            "day_90": {
                "continue": [
                    "at least 3 query families",
                    "500 monthly non-brand sessions or improving valid sample",
                    "QDS rate >=20%",
                    "affiliate outbound CTR >=3% planning signal",
                    "major defects=0",
                    "broken affiliate links=0",
                ],
                "threshold_origin": "PLANNING_HYPOTHESIS_NOT_MARKET_BENCHMARK",
                "otherwise": ["REPAIR", "CONSOLIDATE", "RETREAT", "EXTEND"],
            },
            "month_12": {
                "expand_only_if": [
                    "all quality guardrails pass",
                    "mature economic contribution profit positive for 3 months",
                    "update labor remains within ceiling",
                ],
                "if_not": "STOP_NEW_ARTICLES_AND_IMPROVE_CONSOLIDATE_OR_RETREAT",
            },
        },
        "north_star_hypotheses": {
            "rebaseline": "after Day 90 cohort and again at P5",
            "12_month": {
                "assets": "24-25",
                "qds_monthly": 1500,
                "qds_rate_min": "0.30",
                "outbound_ctr_min": "0.06",
                "confirmed_epc_jpy_min": 30,
                "confirmed_rpm_jpy_min": 1800,
                "economic_contribution_jpy_min": 60000,
            },
            "24_month": {
                "assets": "45-50",
                "qds_monthly": 8000,
                "qds_rate_min": "0.32",
                "outbound_ctr_min": "0.07",
                "confirmed_epc_jpy_min": 40,
                "confirmed_rpm_jpy_min": 2800,
                "economic_contribution_jpy_min": 250000,
            },
            "36_month": {
                "assets": "75-85",
                "qds_monthly": 25000,
                "qds_rate_min": "0.33",
                "outbound_ctr_min": "0.08",
                "confirmed_epc_jpy_min": 50,
                "confirmed_rpm_jpy_min": 4000,
                "economic_contribution_jpy_min": 700000,
            },
            "classification": "INTERNAL_PLANNING_HYPOTHESES_NOT_PUBLIC_NO_1_EVIDENCE",
        },
        "guardrails": {
            "external_spend_jpy": 0,
            "hands_on_claims_without_use": "FORBIDDEN",
            "product_facts": "ALLOWED_PRIMARY_SOURCES_ONLY",
            "competitor_content": "UX_RESEARCH_ONLY",
            "recommendation_business_score_coupling": "FORBIDDEN",
            "automatic_publication": False,
        },
        "phase_planning_ceiling_hours": {"P0": 16, "P1": 40, "P2": 80},
        "backlog_id": "B-V2-010",
        "test_ids": ["T-V2-007"],
    }


def route_registry() -> dict[str, object]:
    policy_route = "/policy/how-we-compare-carry-on-products/"
    routes: list[dict[str, object]] = [
        {
            "route": "/",
            "article_id": "HOME",
            "primary_intent_id": "INT-HOME",
            "template": "HOME",
            "parent_hub": None,
            "taxonomy": [],
            "breadcrumbs": [{"label": "ホーム", "route": "/"}],
            "internal_links": ["/carry-on/", policy_route],
            "index_state": "PRESERVE_CURRENT",
            "phase": "CURRENT_PUBLIC_UNCHANGED",
        }
    ]
    all_asset_routes = [row[1] for row in PORTFOLIO]
    for article_id, route, title, template, _intent, wave in PORTFOLIO:
        is_hub = article_id == "A01"
        links = (
            [value for value in all_asset_routes if value != route]
            if is_hub
            else ["/carry-on/", policy_route]
        )
        if route == policy_route:
            links = ["/carry-on/", "/tools/carry-on-size-checker/"]
        routes.append(
            {
                "route": route,
                "article_id": article_id,
                "primary_intent_id": f"INT-{article_id}",
                "template": template,
                "parent_hub": "/" if is_hub else "/carry-on/",
                "taxonomy": ["carry-on"],
                "breadcrumbs": [
                    {"label": "ホーム", "route": "/"},
                    *(
                        []
                        if is_hub
                        else [{"label": "機内持ち込み", "route": "/carry-on/"}]
                    ),
                    {"label": title, "route": route},
                ],
                "internal_links": list(dict.fromkeys(links)),
                "index_state": (
                    "PRESERVE_CURRENT"
                    if article_id == "A05"
                    else "LOCAL_CANDIDATE_NOINDEX"
                    if wave == 1
                    else "PLANNED_LOCKED_NOINDEX"
                ),
                "phase": "PHASE_2_LOCAL" if wave == 1 else "POST_GATE",
            }
        )
    return {
        "schema": "RAOS_V2_ROUTE_REGISTRY_V2",
        "origin": "https://kurashinoshirube.com",
        "public_mutation_authorized": False,
        "collision_policy": "FAIL_CLOSED",
        "empty_indexable_taxonomy_allowed": False,
        "routes": routes,
        "backlog_id": "B-V2-011",
        "test_ids": ["T-V2-009", "T-V2-010", "T-V2-027"],
    }


def validate_cross_ledger_identity(
    product: Mapping[str, object],
    routes: Mapping[str, object],
    *,
    article_definitions: Mapping[str, object] | None = None,
    pages: Mapping[str, object] | None = None,
) -> None:
    """Fail closed when route/article/intent IDs drift across V2 ledgers."""

    if article_definitions is None:
        value = _read_yaml(
            Path("changes/raos-v2/phase-2/content/article-definitions.v2.yaml")
        )
        article_definitions = value if isinstance(value, dict) else None
    if pages is None:
        value = _read_json(
            Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
        )
        pages = value if isinstance(value, dict) else None
    if not isinstance(article_definitions, Mapping) or not isinstance(pages, Mapping):
        fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    portfolio = product.get("portfolio")
    route_rows = routes.get("routes")
    article_rows = article_definitions.get("articles")
    page_rows = pages.get("pages")
    if not all(isinstance(value, list) for value in (portfolio, route_rows, article_rows, page_rows)):
        fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")

    def index(rows: object, key: str) -> dict[str, Mapping[str, object]]:
        assert isinstance(rows, list)
        result: dict[str, Mapping[str, object]] = {}
        for row in rows:
            if not isinstance(row, Mapping) or not isinstance(row.get(key), str):
                fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
            identifier = str(row[key])
            if identifier in result:
                fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
            result[identifier] = row
        return result

    portfolio_by_route = index(portfolio, "route")
    routes_by_route = index(route_rows, "route")
    articles_by_route = index(article_rows, "route")
    pages_by_route = index(page_rows, "route")
    if set(portfolio_by_route) != set(routes_by_route) - {"/"}:
        fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    for route, portfolio_row in portfolio_by_route.items():
        route_row = routes_by_route[route]
        if any(
            route_row.get(field) != portfolio_row.get(field)
            for field in ("article_id", "template")
        ):
            fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    for route, article_row in articles_by_route.items():
        route_row = routes_by_route.get(route)
        if not isinstance(route_row, Mapping) or any(
            route_row.get(field) != article_row.get(field)
            for field in (
                "article_id",
                "primary_intent_id",
                "template",
                "parent_hub",
            )
        ):
            fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")
    for route, page_row in pages_by_route.items():
        route_row = routes_by_route.get(route)
        if not isinstance(route_row, Mapping) or any(
            route_row.get(field) != page_row.get(field)
            for field in ("article_id", "template")
        ):
            fail("RAOS_V2_CROSS_LEDGER_IDENTITY_INVALID")


def validate_authoritative_ui_parity(
    pages: Mapping[str, object],
    *,
    route_contract: str | None = None,
    typescript_checker: str | None = None,
    preview_checker: str | None = None,
) -> None:
    """Keep package-owned preview inputs aligned with the TypeScript contract."""

    package_root = ROOT / "packages/web-ui/src/decision-support-v2"
    try:
        route_contract = (
            route_contract
            if route_contract is not None
            else (package_root / "contracts.ts").read_text(encoding="utf-8")
        )
        typescript_checker = (
            typescript_checker
            if typescript_checker is not None
            else (package_root / "checker.ts").read_text(encoding="utf-8")
        )
        preview_checker = (
            preview_checker
            if preview_checker is not None
            else (package_root / "preview/checker.js").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError):
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
    rows = pages.get("pages")
    if not isinstance(rows, list) or pages.get("preview_robots") != "noindex,nofollow":
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
    route_pattern = re.compile(
        r"\{\s*route: '([^']+)',\s*template: '([^']+)',\s*"
        r"articleId: '([^']+)',\s*publicationState: '([^']+)',\s*"
        r"publicCandidate: (true|false),\s*"
        r"intendedIndexCandidate: (true|false),\s*"
        r"previewRobots: '([^']+)',\s*\}",
        re.DOTALL,
    )
    contract_rows = [
        {
            "route": route,
            "template": template,
            "article_id": article_id,
            "publication_state": publication_state,
            "public_candidate": public_candidate == "true",
            "intended_index_candidate": intended == "true",
            "preview_robots": robots,
        }
        for (
            route,
            template,
            article_id,
            publication_state,
            public_candidate,
            intended,
            robots,
        ) in route_pattern.findall(route_contract)
    ]
    page_contract_rows: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
        page_contract_rows.append(
            {
                "route": row.get("route"),
                "template": row.get("template"),
                "article_id": row.get("article_id"),
                "publication_state": row.get("publication_state"),
                "public_candidate": row.get("public_candidate"),
                "intended_index_candidate": row.get("intended_index_candidate"),
                "preview_robots": pages.get("preview_robots"),
            }
        )
    if contract_rows != page_contract_rows:
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")

    state_pattern = re.compile(r"'(PASS|FAIL|UNKNOWN|STALE|BLOCKED|NO_MATCH)'")
    contract_state_region = route_contract.split(
        "DECISION_SUPPORT_V2_RESULT_STATES", 1
    )[-1].split("] as const", 1)[0]
    preview_state_region = preview_checker.split("const RESULT_STATES", 1)[-1].split(
        ");", 1
    )[0]
    if state_pattern.findall(contract_state_region) != state_pattern.findall(
        preview_state_region
    ):
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")

    def priorities(source: str) -> dict[str, int]:
        match = re.search(
            r"const STATE_PRIORITY[^=]*= Object\.freeze\(\{(.*?)\}\);",
            source,
            re.DOTALL,
        )
        if match is None:
            fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
        return {
            state: int(value)
            for state, value in re.findall(
                r"\b(PASS|FAIL|UNKNOWN|STALE|BLOCKED|NO_MATCH):\s*(\d+)",
                match.group(1),
            )
        }

    typescript_priority = priorities(typescript_checker)
    preview_priority = priorities(preview_checker)
    if (
        typescript_priority != preview_priority
        or set(typescript_priority)
        != {"PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH"}
        or typescript_priority["PASS"] != 0
        or typescript_priority["UNKNOWN"] <= typescript_priority["NO_MATCH"]
    ):
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")
    semantic_tokens = {
        "BigInt": "BigInt",
        "permutations": "permutations",
        "journeyScope": "journeyScope",
        "effectiveUntil": "effectiveUntil",
        "sourceNextReviewAt": "nextReviewAt",
        "personalItemUnderseatConfirmed": "personalItemUnderseatConfirmed",
        "appendagesIncluded": "appendagesIncluded",
    }
    if any(
        typescript_token not in typescript_checker
        or preview_token not in preview_checker
        for typescript_token, preview_token in semantic_tokens.items()
    ):
        fail("RAOS_V2_AUTHORITATIVE_UI_PARITY_INVALID")


def sitemap_candidates_document(
    pages: Mapping[str, object], preview: Mapping[Path, bytes]
) -> dict[str, object]:
    """Describe future sitemap eligibility without creating a public sitemap."""

    page_rows = pages.get("pages")
    if not isinstance(page_rows, list):
        fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
    entries: list[dict[str, object]] = []
    for row in page_rows:
        if not isinstance(row, dict):
            fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
        route = row.get("route")
        if not isinstance(route, str):
            fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
        relative = (
            Path("changes/raos-v2/phase-2/preview/index.html")
            if route == "/"
            else Path("changes/raos-v2/phase-2/preview")
            / route.strip("/")
            / "index.html"
        )
        payload = preview.get(relative)
        if not isinstance(payload, bytes):
            fail("RAOS_V2_SITEMAP_CANDIDATE_INVALID")
        intended = row.get("intended_index_candidate") is True
        entries.append(
            {
                "route": route,
                "article_id": row.get("article_id"),
                "title": row.get("title"),
                "description": row.get("description"),
                "canonical_candidate": f"https://kurashinoshirube.com{route}",
                "preview_robots": "noindex,nofollow",
                "phase2_sitemap_included": False,
                "phase3_intended_candidate": intended,
                "lastmod": "UNAVAILABLE",
                "render_sha256": sha256(payload),
            }
        )
    return {
        "schema": "RAOS_V2_SITEMAP_CANDIDATES_V1",
        "mode": "LOCAL_CONTRACT_ONLY",
        "target_origin": "https://kurashinoshirube.com",
        "production_sitemap_write": "NOT_EXECUTED",
        "candidate_count": sum(
            entry["phase3_intended_candidate"] is True for entry in entries
        ),
        "entries": entries,
        "backlog_id": "B-V2-031",
        "requirement_ids": ["R-V2-022"],
        "test_ids": ["T-V2-035"],
    }


def design_tokens() -> dict[str, object]:
    return {
        "schema": "RAOS_V2_DESIGN_TOKENS_V2",
        "version": "2.0.0",
        "color": {
            "ink": "#17213A",
            "paper": "#FBF8F1",
            "surface": "#FFFFFF",
            "muted": "#F1F5F4",
            "indigo": "#243B6B",
            "indigo_dark": "#172A52",
            "accent": "#A4492C",
            "success": "#216E5A",
            "warning": "#8A5A00",
            "danger": "#A23434",
            "focus": "#005FCC",
            "border": "#D9D5CB",
        },
        "contrast_pairs": [
            {"foreground": "ink", "background": "paper", "minimum": "4.5"},
            {"foreground": "indigo", "background": "surface", "minimum": "4.5"},
            {"foreground": "accent", "background": "surface", "minimum": "4.5"},
            {"foreground": "focus", "background": "surface", "minimum": "4.5"},
        ],
        "typography": {
            "font_family": "system-ui, -apple-system, BlinkMacSystemFont, 'Noto Sans JP', sans-serif",
            "body": {"size_px": 16, "line_height": "1.8"},
            "meta": {"size_px": 14, "line_height": "1.6"},
            "external_font_requests": 0,
        },
        "layout": {
            "reading_max_px": 720,
            "wide_max_px": 1120,
            "shell_max_px": 1280,
            "gutter_px": {"mobile": 16, "tablet": 24, "desktop": 32},
            "viewports_px": [390, 768, 1440],
        },
        "spacing_px": [4, 8, 12, 16, 24, 32, 48, 64, 96],
        "radius_px": [6, 12, 20],
        "minimum_target_px": 44,
        "motion": {"reduced_motion_respected": True, "essential_motion_only": True},
        "accessibility_target": "WCAG_2_2_AA",
        "backlog_id": "B-V2-012",
        "test_ids": ["T-V2-008"],
    }


def component_states() -> dict[str, object]:
    states = ["DEFAULT", "LOADING", "EMPTY", "ERROR", "STALE", "BLOCKED", "DISABLED"]
    components = [
        "SemanticShell",
        "DisclosureBar",
        "DecisionHero",
        "ConditionForm",
        "ResultPanel",
        "GuideCard",
        "TrustStrip",
        "SourceChip",
        "ComparisonMatrix",
        "ProductCard",
        "AffiliateCTA",
        "ChangeLog",
        "CorrectionLink",
        "ConsentSurface",
    ]
    return {
        "schema": "RAOS_V2_COMPONENT_STATES_V1",
        "components": [
            {
                "id": component,
                "states": states,
                "keyboard_operable": True,
                "minimum_target_px": 44,
                "status_never_color_only": True,
            }
            for component in components
        ],
        "decision_states": ["PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH"],
        "affiliate_cta": {
            "requires": [
                "exact_product_identity",
                "current_offer_or_nonvolatile_link",
                "advertising_disclosure",
            ],
            "blocked_fallback": "show reason and official/product evidence; do not fabricate CTA",
        },
        "responsive_checks": [
            "390x844",
            "768x1024",
            "1440x900",
            "360px regression",
            "200% text",
            "forced colors",
            "reduced motion",
            "no horizontal overflow",
        ],
        "backlog_id": "B-V2-012",
        "test_ids": ["T-V2-008"],
    }


DECIMAL_PATTERN: Final = r"^(0|[1-9][0-9]*)(\.[0-9]+)?$"
POSITIVE_DECIMAL_PATTERN: Final = r"^(?:[1-9][0-9]*(?:\.[0-9]+)?|0\.(?:0*[1-9][0-9]*))$"
HEX64_PATTERN: Final = r"^[0-9a-f]{64}$"
DATE_PATTERN: Final = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
DATETIME_PATTERN: Final = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
JST_DATETIME_PATTERN: Final = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?\+09:00$"
)


def _object_schema(
    name: str,
    required: Sequence[str],
    properties: Mapping[str, object],
    *,
    all_of: Sequence[object] = (),
) -> dict[str, object]:
    document: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_URI_ROOT}/{name}.schema.json",
        "title": name,
        "type": "object",
        "required": list(required),
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if all_of:
        document["allOf"] = list(all_of)
    return document


def source_record_schema() -> dict[str, object]:
    nullable_time = {
        "type": ["string", "null"],
        "pattern": DATETIME_PATTERN,
        "format": "date-time",
    }
    return _object_schema(
        "source-record",
        (
            "schema_version",
            "source_id",
            "source_class",
            "publisher",
            "title",
            "canonical_url",
            "published_at",
            "effective_from",
            "effective_to",
            "checked_at",
            "next_review_at",
            "content_sha256",
            "capture_provenance",
            "status",
        ),
        {
            "schema_version": {"const": "1.0.0"},
            "source_id": {"type": "string", "pattern": r"^SRC-[A-Z0-9-]+$"},
            "source_class": {
                "enum": [
                    "MANUFACTURER_PRIMARY",
                    "AIRLINE_PRIMARY",
                    "GOVERNMENT_PRIMARY",
                    "RAKUTEN_PERMITTED_DATA",
                    "COMPETITOR_UX_ONLY",
                ]
            },
            "publisher": {"type": "string", "minLength": 1},
            "title": {"type": "string", "minLength": 1},
            "canonical_url": {
                "type": "string",
                "pattern": (
                    r"^https://(?![^/?#]*@)"
                    r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])"
                    r"(?::443)?(?:/[^?#]*)?$"
                ),
            },
            "published_at": nullable_time,
            "effective_from": nullable_time,
            "effective_to": nullable_time,
            "checked_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "next_review_at": {
                "type": "string",
                "pattern": DATETIME_PATTERN,
                "format": "date-time",
            },
            "content_sha256": {"type": "string", "pattern": HEX64_PATTERN},
            "capture_provenance": {
                "type": "object",
                "required": ["mode", "captured_at"],
                "properties": {
                    "mode": {
                        "enum": [
                            "PUBLIC_READ_ONLY",
                            "RECORDED_FIXTURE",
                            "OWNER_SUPPLIED",
                        ]
                    },
                    "captured_at": {
                        "type": "string",
                        "pattern": DATETIME_PATTERN,
                        "format": "date-time",
                    },
                },
                "additionalProperties": False,
            },
            "status": {
                "enum": [
                    "FRESH",
                    "DUE",
                    "SOFT_STALE",
                    "HARD_STALE",
                    "UNAVAILABLE",
                    "REJECTED",
                ]
            },
        },
    )


def claim_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "claim_id": {"type": "string", "pattern": r"^CLM-[A-Z0-9-]+$"},
        "claim_type": {"enum": ["A_OFFICIAL_FACT", "D_EDITORIAL_JUDGEMENT", "UNKNOWN"]},
        "subject_id": {
            "type": "string",
            "pattern": r"^[A-Z0-9][A-Z0-9._:-]{0,127}$",
        },
        "predicate": {"type": "string", "pattern": r"^[a-z][a-z0-9_.-]{0,63}$"},
        "value": {
            "type": [
                "string",
                "number",
                "integer",
                "boolean",
                "object",
                "array",
                "null",
            ]
        },
        "unit": {"type": ["string", "null"]},
        "source_ids": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": r"^SRC-[A-Z0-9][A-Z0-9-]{0,127}$",
            },
            "maxItems": 32,
            "uniqueItems": True,
        },
        "logic_inputs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["input_id", "value_ref"],
                "properties": {
                    "input_id": {
                        "type": "string",
                        "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
                    },
                    "value_ref": {
                        "type": "string",
                        "pattern": r"^[A-Z0-9][A-Z0-9._:-]{0,127}$",
                    },
                },
                "additionalProperties": False,
            },
            "maxItems": 32,
        },
        "checked_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "next_review_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "risk_class": {"enum": ["LOW", "MEDIUM", "HIGH"]},
        "status": {"enum": ["DRAFT", "VERIFIED", "STALE", "BLOCKED"]},
    }
    all_of = [
        {
            "if": {"properties": {"claim_type": {"const": "A_OFFICIAL_FACT"}}},
            "then": {
                "properties": {
                    "source_ids": {"minItems": 1},
                    "value": {"not": {"type": "null"}},
                }
            },
        },
        {
            "if": {"properties": {"claim_type": {"const": "D_EDITORIAL_JUDGEMENT"}}},
            "then": {"properties": {"logic_inputs": {"minItems": 1}}},
        },
        {
            "if": {"properties": {"claim_type": {"const": "UNKNOWN"}}},
            "then": {
                "properties": {
                    "value": {"type": "null"},
                    "unit": {"type": "null"},
                    "status": {"enum": ["DRAFT", "BLOCKED"]},
                }
            },
        },
    ]
    return _object_schema(
        "claim",
        tuple(properties),
        properties,
        all_of=all_of,
    )


def product_variant_schema() -> dict[str, object]:
    dimensions = {
        "type": "object",
        "required": [
            "edges_cm",
            "orientation",
            "includes_wheels_and_handles",
        ],
        "properties": {
            "edges_cm": {
                "type": "array",
                "prefixItems": [
                    {"type": "string", "pattern": POSITIVE_DECIMAL_PATTERN},
                    {"type": "string", "pattern": POSITIVE_DECIMAL_PATTERN},
                    {"type": "string", "pattern": POSITIVE_DECIMAL_PATTERN},
                ],
                "minItems": 3,
                "maxItems": 3,
            },
            "orientation": {"const": "ORDERED"},
            "includes_wheels_and_handles": {"const": True},
        },
        "additionalProperties": False,
    }
    nullable_decimal = {
        "type": ["string", "null"],
        "pattern": POSITIVE_DECIMAL_PATTERN,
    }
    return _object_schema(
        "product-variant",
        (
            "schema_version",
            "variant_id",
            "external_dimensions_cm",
            "expanded_dimensions_cm",
            "mass_kg",
            "capacity_l",
            "declared_features",
            "unknown_fields",
        ),
        {
            "schema_version": {"const": "1.0.0"},
            "variant_id": {
                "type": "string",
                "pattern": r"^[A-Z0-9][A-Z0-9-]{0,127}$",
            },
            "external_dimensions_cm": dimensions,
            "expanded_dimensions_cm": {"anyOf": [dimensions, {"type": "null"}]},
            "mass_kg": {"type": "string", "pattern": POSITIVE_DECIMAL_PATTERN},
            "capacity_l": {
                "type": "string",
                "pattern": POSITIVE_DECIMAL_PATTERN,
            },
            "expanded_capacity_l": nullable_decimal,
            "declared_features": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
                },
                "maxItems": 64,
                "uniqueItems": True,
            },
            "unknown_fields": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
                },
                "maxItems": 64,
                "uniqueItems": True,
            },
        },
    )


def product_model_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "product_id": {"type": "string", "pattern": r"^PRD-[A-Z0-9-]+$"},
        "manufacturer": {"type": "string", "minLength": 1},
        "brand": {"type": "string", "minLength": 1},
        "model_name": {"type": "string", "minLength": 1},
        "model_number": {"type": "string", "minLength": 1},
        "generation": {"type": "string", "minLength": 1},
        "variants": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "product-variant.schema.json"},
        },
        "official_source_ids": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": r"^SRC-[A-Z0-9][A-Z0-9-]{0,127}$",
            },
            "maxItems": 32,
            "uniqueItems": True,
        },
        "identity_status": {"enum": ["EXACT", "AMBIGUOUS", "REJECTED", "UNRESOLVED"]},
    }
    return _object_schema(
        "product-model",
        tuple(properties),
        properties,
        all_of=[
            {
                "if": {"properties": {"identity_status": {"const": "EXACT"}}},
                "then": {
                    "properties": {
                        "model_number": {"type": "string", "minLength": 1},
                        "official_source_ids": {"minItems": 1},
                    }
                },
            }
        ],
    )


def offer_observation_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "offer_id": {
            "type": "string",
            "pattern": r"^[A-Z0-9][A-Z0-9-]{0,127}$",
        },
        "product_id": {"type": "string", "pattern": r"^PRD-[A-Z0-9-]+$"},
        "provider": {"const": "RAKUTEN"},
        "mode": {"enum": ["RECORDED_ONLY", "LIVE_APPROVED"]},
        "item_code": {
            "type": ["string", "null"],
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$",
        },
        "shop_code": {
            "type": ["string", "null"],
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$",
        },
        "observed_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "price_jpy": {
            "type": ["string", "null"],
            "pattern": POSITIVE_DECIMAL_PATTERN,
        },
        "availability": {
            "type": ["string", "null"],
            "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
        },
        "affiliate_url_ref": {
            "type": ["string", "null"],
            "pattern": r"^OPAQUE-[A-Z0-9][A-Z0-9._:-]{0,127}$",
        },
        "image_ref": {
            "type": ["string", "null"],
            "pattern": r"^OPAQUE-[A-Z0-9][A-Z0-9._:-]{0,127}$",
        },
        "identity_evidence": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
            },
            "maxItems": 32,
            "uniqueItems": True,
        },
        "status": {
            "enum": [
                "CURRENT",
                "STALE",
                "OUT_OF_STOCK",
                "IDENTITY_BLOCKED",
                "UNAVAILABLE",
            ]
        },
    }
    return _object_schema("offer-observation", tuple(properties), properties)


def airline_rule_set_schema() -> dict[str, object]:
    decimal_or_null = {
        "type": ["string", "null"],
        "pattern": POSITIVE_DECIMAL_PATTERN,
    }
    variant = {
        "type": "object",
        "required": [
            "variant_id",
            "applicability",
            "bag_count",
            "personal_item_count",
            "dimension_edges_cm",
            "orientation",
            "sum_edges_cm",
            "total_weight_kg",
            "includes_wheels_and_handles",
            "notes",
            "resolution_requirements",
        ],
        "properties": {
            "variant_id": {"type": "string", "minLength": 1},
            "applicability": {
                "type": "object",
                "required": ["operator"],
                "properties": {
                    "operator": {
                        "type": ["string", "null"],
                        "pattern": r"^[A-Z0-9][A-Z0-9_-]{0,63}$",
                    },
                    "min_seat_count": {"type": ["integer", "null"], "minimum": 1},
                    "max_seat_count": {"type": ["integer", "null"], "minimum": 1},
                    "fare_classes": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": r"^[A-Z0-9][A-Z0-9_-]{0,63}$",
                        },
                        "uniqueItems": True,
                    },
                    "required_options": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": r"^[A-Z0-9][A-Z0-9_-]{0,63}$",
                        },
                        "uniqueItems": True,
                    },
                    "forbidden_options": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": r"^[A-Z0-9][A-Z0-9_-]{0,63}$",
                        },
                        "uniqueItems": True,
                    },
                },
                "additionalProperties": False,
            },
            "bag_count": {"type": "integer", "minimum": 0},
            "personal_item_count": {"type": "integer", "minimum": 0},
            "dimension_edges_cm": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": POSITIVE_DECIMAL_PATTERN,
                },
                "minItems": 3,
                "maxItems": 3,
            },
            "orientation": {"enum": ["ORDERED", "PERMUTABLE"]},
            "sum_edges_cm": decimal_or_null,
            "total_weight_kg": decimal_or_null,
            "max_per_item_weight_kg": decimal_or_null,
            "item_allowances": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "slot_id",
                        "placement",
                        "dimension_edges_cm",
                        "orientation",
                        "includes_wheels_and_handles",
                        "max_weight_kg",
                        "fit_requirement",
                    ],
                    "properties": {
                        "slot_id": {
                            "type": "string",
                            "pattern": r"^[A-Z][A-Z0-9_-]{0,63}$",
                        },
                        "placement": {"enum": ["MAIN", "UNDERSEAT", "OVERHEAD"]},
                        "dimension_edges_cm": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "string",
                                "pattern": POSITIVE_DECIMAL_PATTERN,
                            },
                            "minItems": 3,
                            "maxItems": 3,
                        },
                        "orientation": {"enum": ["ORDERED", "PERMUTABLE"]},
                        "includes_wheels_and_handles": {"type": ["boolean", "null"]},
                        "max_weight_kg": decimal_or_null,
                        "fit_requirement": {"enum": ["UNDERSEAT", None]},
                    },
                    "additionalProperties": False,
                },
                "maxItems": 4,
            },
            "includes_wheels_and_handles": {"type": "boolean"},
            "notes": {"type": "array", "items": {"type": "string"}},
            "resolution_requirements": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "rule_set_id": {"type": "string", "minLength": 1},
        "carrier": {"type": "string", "minLength": 1},
        "journey_scope": {"enum": ["DOMESTIC", "INTERNATIONAL", "ALL"]},
        "effective_interval_semantics": {"const": "FROM_INCLUSIVE_TO_EXCLUSIVE"},
        "effective_from": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "string",
                    "pattern": DATETIME_PATTERN,
                    "format": "date-time",
                },
            ],
        },
        "observed_applicable_from": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "applicability_basis": {
            "enum": [
                "OBSERVED_CURRENT_AT_CAPTURE_NO_PUBLISHED_EFFECTIVE_DATE",
                "OFFICIAL_EFFECTIVE_DATE",
            ]
        },
        "effective_to": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "string",
                    "pattern": DATETIME_PATTERN,
                    "format": "date-time",
                },
            ]
        },
        "variants": {"type": "array", "items": variant, "minItems": 1},
        "source_id": {
            "type": "string",
            "pattern": r"^SRC-[A-Z0-9][A-Z0-9-]{0,127}$",
        },
        "source_content_sha256": {
            "type": "string",
            "pattern": HEX64_PATTERN,
        },
        "source_next_review_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "recheck_required_before_use": {"type": "boolean"},
        "checked_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
    }
    return _object_schema(
        "airline-rule-set",
        tuple(properties),
        properties,
        all_of=[
            {
                "if": {
                    "properties": {
                        "applicability_basis": {"const": "OFFICIAL_EFFECTIVE_DATE"}
                    }
                },
                "then": {"properties": {"effective_from": {"not": {"type": "null"}}}},
            },
            {
                "if": {
                    "properties": {
                        "applicability_basis": {
                            "const": "OBSERVED_CURRENT_AT_CAPTURE_NO_PUBLISHED_EFFECTIVE_DATE"
                        }
                    }
                },
                "then": {"properties": {"effective_from": {"type": "null"}}},
            },
        ],
    )


ARTICLE_BLOCK_ORDERS: Final = {
    "HOME": (
        "MASTHEAD_DISCLOSURE",
        "HERO",
        "QUICK_CHECK",
        "VERIFIED_GUIDES",
        "DECISION_PATHS",
        "TRUST_STRIP",
        "EDITORIAL_METHOD",
        "FOOTER_POLICIES",
    ),
    "HUB": (
        "SCOPE",
        "DECISION_MAP",
        "TOOL_ENTRY",
        "AIRLINE_RULE_CARDS",
        "TASK_GUIDES",
        "PRODUCT_COMPARISONS",
        "UNKNOWN_EDGE_CASES",
        "METHOD_FRESHNESS_CORRECTION",
        "PUBLISHED_RELATED_LINKS",
    ),
    "GUIDE": (
        "DISCLOSURE",
        "PROBLEM_SCOPE",
        "THIRTY_SECOND_CONCLUSION",
        "DECISION_INPUTS",
        "OFFICIAL_FACTS",
        "HYPOTHETICAL_EXAMPLES",
        "EXCEPTIONS_UNKNOWN",
        "ALTERNATIVE_PATH",
        "CONDITIONAL_NEXT_STEP",
        "SOURCES_CHANGELOG_CORRECTION",
    ),
    "COMPARISON": (
        "DISCLOSURE_SCOPE",
        "THIRTY_SECOND_CONCLUSION",
        "FIT_NON_FIT",
        "METHOD",
        "COMPARISON_TABLE",
        "PRODUCT_CARDS",
        "DECISION_CRITERIA",
        "BUY_NONE_CONDITIONS",
        "SOURCES_CHANGELOG_CORRECTION",
        "RELATED_LINKS",
    ),
    "DIFFERENCE": (
        "SCOPE_NON_DUPLICATION",
        "DECISIVE_DIFFERENCES",
        "FACT_TABLE",
        "CONDITIONAL_BRANCH",
        "COMMON_NON_FIT",
        "SOURCES_CHECKED_DATE",
        "COMPARISON_OR_TOOL_LINK",
    ),
    "TOOL": (
        "PURPOSE_LIMITATION_PRIVACY",
        "INPUTS",
        "VALIDATION",
        "RESULT",
        "RESOLVED_RULE",
        "NON_GUARANTEE",
        "NEXT_ACTION",
        "LOCAL_RESET_COPY",
        "CTA_GUARD",
    ),
    "POLICY": (
        "SCOPE",
        "SOURCE_AND_CLAIM_LABELS",
        "NO_HANDS_ON_POLICY",
        "AI_AND_HUMAN_RESPONSIBILITY",
        "RECOMMENDATION_BUSINESS_SEPARATION",
        "AFFILIATE_AND_CTA_RULES",
        "FRESHNESS_CORRECTIONS_HISTORY",
        "PRIVACY_MEASUREMENT_LINK",
    ),
}


def article_definition_schema() -> dict[str, object]:
    block_types = sorted(
        {block_type for order in ARTICLE_BLOCK_ORDERS.values() for block_type in order}
    )
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "article_id": {"type": "string", "minLength": 1},
        "route": {"type": "string", "pattern": r"^/(?:[a-z0-9-]+/)*$"},
        "template": {
            "enum": [
                "HOME",
                "HUB",
                "GUIDE",
                "COMPARISON",
                "DIFFERENCE",
                "TOOL",
                "POLICY",
            ]
        },
        "primary_intent_id": {
            "type": "string",
            "pattern": r"^INT-[A-Z0-9-]+$",
        },
        "parent_hub": {
            "type": ["string", "null"],
            "pattern": r"^/(?:[a-z0-9-]+/)*$",
        },
        "claim_ids": {
            "type": "array",
            "items": {"type": "string", "pattern": r"^CLM-[A-Z0-9-]+$"},
            "minItems": 1,
            "uniqueItems": True,
        },
        "editorial_decisions": {
            "type": "array",
            "items": {"type": "string", "pattern": r"^ED-[A-Z0-9-]+$"},
            "minItems": 1,
            "uniqueItems": True,
        },
        "blocks": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["block_id", "block_type"],
                "properties": {
                    "block_id": {
                        "type": "string",
                        "pattern": r"^BLK-[A-Z0-9-]+$",
                    },
                    "block_type": {"enum": block_types},
                },
                "additionalProperties": False,
            },
        },
        "disclosure": {"type": "string", "minLength": 1},
        "source_checked_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "review_state": {
            "enum": ["DRAFT", "EVIDENCE_COMPLETE", "REVIEW_REQUIRED", "HUMAN_REVIEWED"]
        },
    }
    all_of = [
        {
            "if": {"properties": {"template": {"const": template}}},
            "then": {
                "properties": {
                    "blocks": {
                        "minItems": len(order),
                        "prefixItems": [
                            {"properties": {"block_type": {"const": block_type}}}
                            for block_type in order
                        ],
                    }
                }
            },
        }
        for template, order in ARTICLE_BLOCK_ORDERS.items()
    ]
    return _object_schema(
        "article-definition", tuple(properties), properties, all_of=all_of
    )


def editorial_decision_schema() -> dict[str, object]:
    decision_input = {
        "type": "object",
        "required": ["input_id", "value_ref"],
        "properties": {
            "input_id": {
                "type": "string",
                "pattern": r"^IN-[A-Z0-9-]+$",
                "not": {
                    "enum": [
                        "IN-COMMISSION",
                        "IN-EPC",
                        "IN-BUSINESS-SCORE",
                        "IN-PRICE",
                        "IN-REWARD-RATE",
                    ]
                },
            },
            "value_ref": {
                "type": "string",
                "pattern": r"^CLM-[A-Z0-9-]+$",
            },
        },
        "additionalProperties": False,
    }
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "decision_id": {"type": "string", "pattern": r"^ED-[A-Z0-9-]+$"},
        "decision_type": {
            "enum": [
                "ELIGIBILITY",
                "FIT",
                "ARTICLE_SCOPE",
                "TRADE_OFF",
                "UNKNOWN_HANDLING",
            ]
        },
        "inputs": {"type": "array", "items": decision_input, "minItems": 1},
        "logic_version": {
            "type": "string",
            "pattern": r"^LOGIC-[A-Z0-9.-]+$",
        },
        "outcome": {"type": "string", "minLength": 1},
        "rationale": {"type": "string", "minLength": 1},
        "non_fit": {"type": "array", "items": {"type": "string"}},
        "reviewer": {
            "type": ["string", "null"],
            "pattern": r"^REVIEWER-[A-Z0-9-]+$",
        },
    }
    return _object_schema("editorial-decision", tuple(properties), properties)


def publication_package_schema() -> dict[str, object]:
    base_hashes = ("article", "claims", "sources", "render", "migration")
    real_hashes = (*base_hashes, "editorial", "products", "review", "render_model")
    review_binding = {
        "anyOf": [
            {"type": "null"},
            {
                "type": "object",
                "required": [
                    "reviewer_id",
                    "reviewed_at",
                    "review_version",
                    "synthetic",
                ],
                "properties": {
                    "reviewer_id": {
                        "type": "string",
                        "pattern": r"^[A-Z0-9][A-Z0-9._:-]{0,127}$",
                    },
                    "reviewed_at": {
                        "type": "string",
                        "pattern": DATETIME_PATTERN,
                        "format": "date-time",
                    },
                    "review_version": {
                        "type": "string",
                        "pattern": r"^[A-Z0-9][A-Z0-9._:-]{0,127}$",
                    },
                    "synthetic": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        ]
    }
    migration_binding = {
        "anyOf": [
            {
                "type": "object",
                "required": ["schema", "mode", "target_route", "sha256"],
                "properties": {
                    "schema": {"const": "RAOS_V2_MIGRATION_MANIFEST_V1"},
                    "mode": {"const": "LOCAL_SIMULATION_ONLY"},
                    "target_route": {
                        "type": "string",
                        "pattern": r"^/(?:[a-z0-9-]+/)*$",
                    },
                    "sha256": {"type": "string", "pattern": HEX64_PATTERN},
                },
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["previous", "next", "wordpress_intent", "sha256"],
                "properties": {
                    "previous": {"type": "null"},
                    "next": {"const": "synthetic"},
                    "wordpress_intent": {"const": "CREATE_OR_UPDATE"},
                    "sha256": {"type": "string", "pattern": HEX64_PATTERN},
                },
                "additionalProperties": False,
            },
        ]
    }
    claim_evidence = {
        "type": "array",
        "minItems": 1,
        "items": {
            "type": "object",
            "required": ["claim_id", "risk_class", "freshness"],
            "properties": {
                "claim_id": {
                    "type": "string",
                    "pattern": r"^CLM-[A-Z0-9-]+$",
                },
                "risk_class": {"enum": ["LOW", "MEDIUM", "HIGH"]},
                "freshness": {
                    "enum": [
                        "FRESH",
                        "DUE",
                        "SOFT_STALE",
                        "HARD_STALE",
                        "UNKNOWN",
                        "UNAVAILABLE",
                        "REJECTED",
                    ]
                },
            },
            "additionalProperties": False,
        },
    }
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "package_id": {
            "type": "string",
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        },
        "target_origin": {"const": "https://kurashinoshirube.com"},
        "target_route": {"type": "string", "pattern": r"^/(?:[a-z0-9-]+/)*$"},
        "article_id": {
            "type": "string",
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        },
        "input_hashes": {
            "type": "object",
            "required": list(base_hashes),
            "properties": {
                name: {"type": "string", "pattern": HEX64_PATTERN}
                for name in real_hashes
            },
            "additionalProperties": False,
        },
        "render_hash": {"type": "string", "pattern": HEX64_PATTERN},
        "source_snapshot_hash": {"type": "string", "pattern": HEX64_PATTERN},
        "review_binding": review_binding,
        "migration_manifest": migration_binding,
        "claim_evidence": claim_evidence,
        "created_at": {
            "type": "string",
            "pattern": DATETIME_PATTERN,
            "format": "date-time",
        },
        "content_class": {"enum": ["REAL_CONTENT", "SYNTHETIC_FIXTURE"]},
        "package_digest": {
            "type": ["string", "null"],
            "pattern": HEX64_PATTERN,
        },
        "state": {
            "enum": [
                "DRAFT",
                "EVIDENCE_COMPLETE",
                "HUMAN_REVIEWED",
                "PACKAGE_SEALED",
                "BLOCKED",
                "REVIEW_REQUIRED",
            ]
        },
    }
    return _object_schema(
        "publication-package",
        tuple(properties),
        properties,
        all_of=[
            {
                "if": {"properties": {"content_class": {"const": "REAL_CONTENT"}}},
                "then": {
                    "properties": {
                        "state": {
                            "enum": [
                                "DRAFT",
                                "EVIDENCE_COMPLETE",
                                "BLOCKED",
                                "REVIEW_REQUIRED",
                            ]
                        },
                        "review_binding": {"type": "null"},
                        "input_hashes": {"required": list(real_hashes)},
                        "package_digest": {"type": "null"},
                    }
                },
            },
            {
                "if": {"properties": {"state": {"const": "PACKAGE_SEALED"}}},
                "then": {
                    "properties": {
                        "content_class": {"const": "SYNTHETIC_FIXTURE"},
                        "review_binding": {
                            "type": "object",
                            "required": ["synthetic"],
                            "properties": {"synthetic": {"const": True}},
                        },
                        "package_digest": {
                            "type": "string",
                            "pattern": HEX64_PATTERN,
                        },
                        "claim_evidence": {
                            "items": {
                                "properties": {
                                    "freshness": {"enum": ["FRESH", "DUE"]}
                                }
                            }
                        },
                    }
                },
            },
        ],
    )


def analytics_event_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        "schema_version": {"const": "1.0.0"},
        "event_name": {
            "enum": [
                "tool_result_view",
                "comparison_view",
                "evidence_link_open",
                "official_source_open",
                "affiliate_outbound_activate",
                "article_complete",
                "error_state_view",
            ]
        },
        "event_version": {"const": 1},
        "event_time_jst": {
            "type": "string",
            "pattern": JST_DATETIME_PATTERN,
            "format": "date-time",
        },
        "session_token_hmac": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
        "article_id": {
            "type": "string",
            "pattern": r"^[A-Z0-9][A-Z0-9._:-]{0,127}$",
        },
        "placement": {"type": "string", "pattern": r"^[a-z0-9_-]{1,64}$"},
        "consent_state": {"enum": ["UNKNOWN", "DENIED", "GRANTED"]},
        "result_state": {
            "enum": ["PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH", None]
        },
        "product_id": {
            "type": ["string", "null"],
            "pattern": r"^PRD-[A-Z0-9-]+$",
        },
        "source_id": {
            "type": ["string", "null"],
            "pattern": r"^SRC-[A-Z0-9][A-Z0-9-]{0,127}$",
        },
    }
    null_optional = {
        name: {"type": "null"} for name in ("result_state", "source_id", "product_id")
    }
    result_required = {
        "required": ["result_state"],
        "properties": {
            "result_state": {
                "enum": ["PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH"]
            },
            "source_id": {"type": "null"},
            "product_id": {"type": "null"},
        },
    }
    source_required = {
        "required": ["source_id"],
        "properties": {
            "result_state": {"type": "null"},
            "source_id": {
                "type": "string",
                "pattern": r"^SRC-[A-Z0-9][A-Z0-9-]{0,127}$",
            },
            "product_id": {"type": "null"},
        },
    }
    product_required = {
        "required": ["product_id"],
        "properties": {
            "result_state": {"type": "null"},
            "source_id": {"type": "null"},
            "product_id": {"type": "string", "pattern": r"^PRD-[A-Z0-9-]+$"},
        },
    }
    return _object_schema(
        "analytics-event",
        (
            "schema_version",
            "event_name",
            "event_version",
            "event_time_jst",
            "session_token_hmac",
            "article_id",
            "placement",
            "consent_state",
        ),
        properties,
        all_of=[
            {
                "if": {"properties": {"event_name": {"const": "tool_result_view"}}},
                "then": result_required,
            },
            {
                "if": {
                    "properties": {
                        "event_name": {
                            "enum": ["evidence_link_open", "official_source_open"]
                        }
                    }
                },
                "then": source_required,
            },
            {
                "if": {
                    "properties": {
                        "event_name": {"const": "affiliate_outbound_activate"}
                    }
                },
                "then": product_required,
            },
            {
                "if": {"properties": {"event_name": {"const": "error_state_view"}}},
                "then": result_required,
            },
            {
                "if": {
                    "properties": {
                        "event_name": {
                            "enum": ["comparison_view", "article_complete"]
                        }
                    }
                },
                "then": {"properties": null_optional},
            },
        ],
    )


def ports_contract() -> dict[str, object]:
    return {
        "schema": "RAOS_V2_PORTS_V1",
        "version": "1.0.0",
        "network_default": "DENY",
        "ports": {
            "RuleRegistryPort": {
                "input": "JourneyConditions@v1 + effective timestamp",
                "output": "ResolvedRuleVariant@v1 | UNKNOWN",
                "failure": "typed closed error; carrier is never inferred",
            },
            "ProductCatalogPort": {
                "input": "product/model id",
                "output": "ProductModel@v1",
                "failure": "UNRESOLVED; offer title is not product truth",
            },
            "RakutenSearchPort": {
                "input": "RakutenSearchRequest@v1",
                "output": "recorded envelope",
                "default_mode": "RECORDED_ONLY",
                "failure": [
                    "TIMEOUT",
                    "RATE_LIMIT",
                    "INVALID_RESPONSE",
                    "DISABLED",
                    "STALE",
                ],
            },
            "DecisionSupportPort": {
                "input": "user conditions + rules + product",
                "output": "PASS|FAIL|UNKNOWN|STALE|BLOCKED|NO_MATCH with segment reasons and sources",
                "failure": "UNKNOWN; no optimistic fallback",
            },
            "ArticleRendererPort": {
                "input": "ArticleDefinition@v1 + resolved data",
                "output": "deterministic local render",
                "failure": "BLOCKED; no partial affiliate CTA",
            },
            "PublicationPackagePort": {
                "input": "review-bound render bundle",
                "output": "local package state",
                "failure": "BLOCKED; no live write capability",
            },
            "WordPressDraftPort": {
                "input": "package",
                "output": "disabled dry-run diff receipt",
                "default_mode": "DISABLED_DRY_RUN",
                "live_write_capability": False,
                "receipt_contract": {
                    "schema_version": "1.0.0",
                    "required_fields": [
                        "schema_version",
                        "mode",
                        "external_action_count",
                        "request_count",
                        "target",
                        "intent",
                        "before",
                        "after",
                        "idempotency_key",
                        "package_digest",
                        "status",
                        "external_status",
                    ],
                    "constants": {
                        "mode": "DISABLED_DRY_RUN",
                        "external_action_count": 0,
                        "request_count": 0,
                        "intent": "CREATE_OR_UPDATE",
                        "status": "DRY_RUN",
                        "external_status": "NOT_EXECUTED",
                    },
                    "target_shape": ["origin", "route"],
                    "before_shape": ["state", "reason"],
                    "after_shape": [
                        "post_status",
                        "comment_status",
                        "ping_status",
                        "render_hash",
                    ],
                    "opaque_hex64_fields": ["idempotency_key", "package_digest"],
                },
            },
            "EventCollectorPort": {
                "input": "AnalyticsEvent@v1",
                "output": "local receipt",
                "default_mode": "LOCAL_SINK_ONLY",
                "failure": "reject forbidden event/field without PII enrichment",
            },
            "FreshnessMonitorPort": {
                "input": "source/claim/product clocks",
                "output": "FRESH|DUE|SOFT_STALE|HARD_STALE|UNKNOWN",
                "failure": "UNKNOWN or HARD_STALE safe state",
            },
        },
        "publication_transitions": [
            "DRAFT -> EVIDENCE_COMPLETE",
            "EVIDENCE_COMPLETE -> HUMAN_REVIEWED [human only; not executed Phase 0-2]",
            "HUMAN_REVIEWED -> PACKAGE_SEALED [synthetic fixture only Phase 0-2]",
            "PACKAGE_SEALED -> DRY_RUN_RECEIPT [disabled WordPress port]",
        ],
        "forbidden_capabilities": [
            "PUBLISHED transition",
            "live WordPress write",
            "live provider write",
            "credential input",
        ],
        "backlog_id": "B-V2-017",
        "test_ids": [
            "T-V2-014",
            "T-V2-034",
            "T-V2-037",
            "T-V2-038",
            "T-V2-045",
            "T-V2-046",
        ],
    }


def recorded_local_test_evidence() -> dict[str, object]:
    value = _read_json(LOCAL_TEST_EVIDENCE_INPUT_PATH)
    if (
        not isinstance(value, dict)
        or value.get("schema") != "RAOS_V2_RECORDED_LOCAL_TEST_EVIDENCE_V1"
        or value.get("status") not in {"NOT_EXECUTED", "PASSED_LOCAL"}
        or value.get("external_actions") != "NOT_EXECUTED"
        or value.get("formal_ci") != "NOT_CLAIMED"
    ):
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    try:
        verification = verify_local_test_evidence(value, root=ROOT)
    except ValidationFailure:
        fail("RAOS_V2_LOCAL_TEST_EVIDENCE_INVALID")
    result = deepcopy(value)
    result["claimed_status"] = value.get("status")
    result["status"] = verification["effective_status"]
    result["binding_verification"] = verification["binding_verification"]
    result["raw_verification"] = verification["raw_verification"]
    return result


def effective_traceability(*, evidence_gate_passed: bool | None = None) -> dict[str, object]:
    source = _read_yaml(SOURCE_ROOT / "07_DECISION_TRACEABILITY.yaml")
    if not isinstance(source, dict):
        fail("RAOS_V2_TRACEABILITY_INVALID")
    source_decisions = source.get("decisions")
    source_requirements = source.get("requirements")
    source_backlog = source.get("backlog")
    source_tests = source.get("tests")
    if not all(
        isinstance(rows, list)
        for rows in (
            source_decisions,
            source_requirements,
            source_backlog,
            source_tests,
        )
    ):
        fail("RAOS_V2_TRACEABILITY_INVALID")

    def indexed(rows: object) -> dict[str, dict[str, object]]:
        assert isinstance(rows, list)
        result: dict[str, dict[str, object]] = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                fail("RAOS_V2_TRACEABILITY_INVALID")
            identifier = row["id"]
            if identifier in result:
                fail("RAOS_V2_TRACEABILITY_DUPLICATE_ID")
            result[identifier] = deepcopy(row)
        return result

    decisions = indexed(source_decisions)
    requirements = indexed(source_requirements)
    backlog = indexed(source_backlog)
    tests = indexed(source_tests)
    selected_backlog_ids = {f"B-V2-{value:03d}" for value in range(1, 35)}
    selected_test_ids = {
        *(f"T-V2-{value:03d}" for value in range(1, 47)),
        "T-V2-051",
    }
    if (
        not selected_backlog_ids <= backlog.keys()
        or not selected_test_ids <= tests.keys()
    ):
        fail("RAOS_V2_TRACEABILITY_SCOPE_MISSING")

    # Build relationship unions from both sides before restricting the P0-P2
    # scope.  This repairs stale one-way lists without changing the imported
    # source layer and makes every effective edge explicitly bidirectional.
    b_to_r: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("requirement_ids", [])}
        for identifier, row in backlog.items()
    }
    b_to_t: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("test_ids", [])}
        for identifier, row in backlog.items()
    }
    r_to_d: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("decision_ids", [])}
        for identifier, row in requirements.items()
    }
    d_to_r: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("requirement_ids", [])}
        for identifier, row in decisions.items()
    }
    r_to_b: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("backlog_ids", [])}
        for identifier, row in requirements.items()
    }
    r_to_t: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("test_ids", [])}
        for identifier, row in requirements.items()
    }
    t_to_r: dict[str, set[str]] = {
        identifier: {str(value) for value in row.get("requirement_ids", [])}
        for identifier, row in tests.items()
    }
    for requirement_id, values in r_to_b.items():
        for backlog_id in values:
            b_to_r.setdefault(backlog_id, set()).add(requirement_id)
    for requirement_id, values in r_to_t.items():
        for test_id in values:
            t_to_r.setdefault(test_id, set()).add(requirement_id)
    for test_id, values in t_to_r.items():
        for requirement_id in values:
            r_to_t.setdefault(requirement_id, set()).add(test_id)
    for decision_id, values in d_to_r.items():
        for requirement_id in values:
            r_to_d.setdefault(requirement_id, set()).add(decision_id)
    for requirement_id, values in r_to_d.items():
        for decision_id in values:
            d_to_r.setdefault(decision_id, set()).add(requirement_id)

    selected_requirement_ids = {
        requirement_id
        for backlog_id in selected_backlog_ids
        for requirement_id in b_to_r.get(backlog_id, set())
    } | {
        requirement_id
        for test_id in selected_test_ids
        for requirement_id in t_to_r.get(test_id, set())
    }
    selected_decision_ids = {
        decision_id
        for requirement_id in selected_requirement_ids
        for decision_id in r_to_d.get(requirement_id, set())
    }
    # Close D<->R once in case a selected decision binds another requirement.
    selected_requirement_ids |= {
        requirement_id
        for decision_id in selected_decision_ids
        for requirement_id in d_to_r.get(decision_id, set())
    }
    selected_decision_ids |= {
        decision_id
        for requirement_id in selected_requirement_ids
        for decision_id in r_to_d.get(requirement_id, set())
    }
    if (
        not selected_requirement_ids <= requirements.keys()
        or not selected_decision_ids <= decisions.keys()
    ):
        fail("RAOS_V2_TRACEABILITY_CROSS_REFERENCE_INVALID")

    local_test = recorded_local_test_evidence()
    local_gate_passed = local_test.get("status") == "PASSED_LOCAL"
    if evidence_gate_passed is not None:
        local_gate_passed = local_gate_passed and evidence_gate_passed
    backlog_rows: list[dict[str, object]] = []
    for identifier in sorted(selected_backlog_ids):
        row = backlog[identifier]
        try:
            number = int(identifier.rsplit("-", 1)[1])
        except (ValueError, IndexError):
            fail("RAOS_V2_TRACEABILITY_INVALID")
        effective = deepcopy(row)
        dependencies = {str(value) for value in effective.get("depends_on", [])}
        if identifier == "B-V2-009":
            dependencies = {f"B-V2-{value:03d}" for value in range(1, 9)}
        elif identifier == "B-V2-031":
            dependencies.add("B-V2-030")
        elif identifier == "B-V2-033":
            dependencies.update({"B-V2-027", "B-V2-029", "B-V2-030"})
        elif identifier == "B-V2-034":
            dependencies = {f"B-V2-{value:03d}" for value in range(19, 34)}
        effective["depends_on"] = sorted(dependencies)
        effective["requirement_ids"] = sorted(
            b_to_r.get(identifier, set()) & selected_requirement_ids
        )
        effective["test_ids"] = sorted(
            b_to_t.get(identifier, set()) & selected_test_ids
        )
        effective["implementation_status"] = (
            "GENERATED_LOCAL"
            if number <= 18
            else "VERIFIED_LOCAL_RECORDED"
            if local_gate_passed
            else "AWAITING_LOCAL_TEST_GATE"
            if number == 34
            else "IMPLEMENTED_LOCAL_PENDING_GATE"
        )
        effective["external_action_status"] = "NOT_EXECUTED"
        backlog_rows.append(effective)

    test_rows: list[dict[str, object]] = []
    for identifier in sorted(selected_test_ids):
        effective = deepcopy(tests[identifier])
        number = int(identifier.rsplit("-", 1)[1])
        effective["requirement_ids"] = sorted(
            t_to_r.get(identifier, set()) & selected_requirement_ids
        )
        effective["backlog_ids"] = sorted(
            backlog_id
            for backlog_id in selected_backlog_ids
            if identifier in b_to_t.get(backlog_id, set())
        )
        effective["effective_phases"] = (
            ["P0", "P1", "P2"]
            if number == 51
            else ["P0"]
            if number in {*range(1, 7), 40}
            else ["P1"]
            if 7 <= number <= 19
            else ["P2"]
        )
        effective["execution_status"] = (
            "PASSED_LOCAL_RECORDED"
            if local_gate_passed
            else "NOT_EXECUTED_RECORDED"
        )
        test_rows.append(effective)

    requirement_rows: list[dict[str, object]] = []
    for identifier in sorted(selected_requirement_ids):
        effective = deepcopy(requirements[identifier])
        effective["decision_ids"] = sorted(
            r_to_d.get(identifier, set()) & selected_decision_ids
        )
        effective["backlog_ids"] = sorted(
            backlog_id
            for backlog_id in selected_backlog_ids
            if identifier in b_to_r.get(backlog_id, set())
        )
        effective["test_ids"] = sorted(
            test_id
            for test_id in selected_test_ids
            if identifier in t_to_r.get(test_id, set())
        )
        requirement_rows.append(effective)

    decision_rows: list[dict[str, object]] = []
    for identifier in sorted(selected_decision_ids):
        effective = deepcopy(decisions[identifier])
        effective["requirement_ids"] = sorted(
            d_to_r.get(identifier, set()) & selected_requirement_ids
        )
        decision_rows.append(effective)

    # Validate the corrected P0-P2 backlog graph before emitting it.
    graph = {
        str(row["id"]): {str(value) for value in row.get("depends_on", [])}
        for row in backlog_rows
    }
    pending = dict(graph)
    while pending:
        ready = {
            identifier
            for identifier, dependencies in pending.items()
            if not (dependencies & pending.keys())
        }
        if not ready:
            fail("RAOS_V2_EFFECTIVE_BACKLOG_CYCLE")
        for identifier in ready:
            pending.pop(identifier)

    d_r_complete = all(
        requirement_id in r_to_d and identifier in r_to_d[requirement_id]
        for identifier in selected_decision_ids
        for requirement_id in d_to_r.get(identifier, set()) & selected_requirement_ids
    )
    r_b_complete = all(
        identifier in b_to_r.get(backlog_id, set())
        for identifier in selected_requirement_ids
        for backlog_id in selected_backlog_ids
        if backlog_id in r_to_b.get(identifier, set())
        or identifier in b_to_r.get(backlog_id, set())
    )
    r_t_complete = all(
        identifier in t_to_r.get(test_id, set())
        for identifier in selected_requirement_ids
        for test_id in selected_test_ids
        if test_id in r_to_t.get(identifier, set())
        or identifier in t_to_r.get(test_id, set())
    )
    b_t_complete = all(
        any(
            str(test_row["id"]) == test_id
            and str(backlog_row["id"]) in test_row.get("backlog_ids", [])
            for test_row in test_rows
        )
        for backlog_row in backlog_rows
        for test_id in backlog_row.get("test_ids", [])
    )
    return {
        "schema": "RAOS_V2_EFFECTIVE_TRACEABILITY_V1",
        "source": "source-package/2.0.0-design/07_DECISION_TRACEABILITY.yaml",
        "source_package_sha256": PACKAGE_SHA256,
        "clarification_overlay": "changes/raos-v2/clarifications.v1.yaml",
        "scope": ["P0", "P1", "P2"],
        "source_counts": {
            "decisions": len(decisions),
            "requirements": len(requirements),
            "backlog": len(backlog),
            "tests": len(tests),
        },
        "decisions": decision_rows,
        "requirements": requirement_rows,
        "backlog": backlog_rows,
        "tests": test_rows,
        "invariants": {
            "D_to_R_and_R_to_D_complete": d_r_complete,
            "R_to_B_and_B_to_R_complete": r_b_complete,
            "R_to_T_and_T_to_R_complete": r_t_complete,
            "B_to_T_and_T_to_B_complete": b_t_complete,
            "backlog_acyclic": not pending,
            "each_backlog_has_requirement": all(
                row.get("requirement_ids") for row in backlog_rows
            ),
            "each_backlog_has_test": all(row.get("test_ids") for row in backlog_rows),
            "B_V2_009_waits_all_phase0": backlog_rows[8].get("depends_on")
            == [f"B-V2-{value:03d}" for value in range(1, 9)],
            "B_V2_034_waits_all_phase2_builders": next(
                row for row in backlog_rows if row["id"] == "B-V2-034"
            ).get("depends_on")
            == [f"B-V2-{value:03d}" for value in range(19, 34)],
        },
    }


def phase1_validation_document(
    product: Mapping[str, object],
    routes: Mapping[str, object],
    schemas: Mapping[Path, object],
) -> dict[str, object]:
    portfolio = product.get("portfolio")
    route_rows = routes.get("routes")
    return {
        "schema": "RAOS_V2_PHASE1_VALIDATION_V1",
        "status": "GENERATED_CONTRACTS_VALIDATED",
        "checks": {
            "one_wedge": product.get("wedge", {}).get("single_wedge") is True
            if isinstance(product.get("wedge"), dict)
            else False,
            "portfolio_count": len(portfolio) if isinstance(portfolio, list) else -1,
            "template_count": len(product.get("templates", []))
            if isinstance(product.get("templates"), list)
            else -1,
            "route_count_including_home": len(route_rows)
            if isinstance(route_rows, list)
            else -1,
            "schema_count": len(schemas),
            "public_mutation_authorized": False,
            "network_used_by_generator": False,
            "external_actions": "NOT_EXECUTED",
        },
        "expected": {
            "portfolio_count": 25,
            "template_count": 7,
            "route_count_including_home": 26,
            "schema_count": 10,
        },
        "test_ids": [f"T-V2-{value:03d}" for value in range(7, 20)] + ["T-V2-051"],
    }


def preview_documents() -> dict[Path, bytes]:
    source_root = ROOT / "packages/web-ui/src/decision-support-v2/preview"
    renderer_path = source_root / "render_preview.py"
    try:
        specification = importlib.util.spec_from_file_location(
            "raos_v2_preview_renderer", renderer_path
        )
        if specification is None or specification.loader is None:
            fail("RAOS_V2_PREVIEW_RENDERER_IMPORT_INVALID")
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        render_pages = getattr(module, "render_pages")
        pages = _read_json(
            Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
        )
        css = (source_root / "styles.css").read_text(encoding="utf-8")
        javascript = (source_root / "checker.js").read_text(encoding="utf-8")
        rendered = render_pages(
            pages=pages,
            css=css,
            javascript=javascript,
        )
    except BuildFailure:
        raise
    except (AttributeError, OSError, TypeError, UnicodeError, ValueError):
        fail("RAOS_V2_PREVIEW_RENDER_FAILED")
    if not isinstance(rendered, dict):
        fail("RAOS_V2_PREVIEW_RENDER_INVALID")
    paths = {
        "/": Path("changes/raos-v2/phase-2/preview/index.html"),
        "/carry-on/": Path("changes/raos-v2/phase-2/preview/carry-on/index.html"),
        "/tools/carry-on-size-checker/": Path(
            "changes/raos-v2/phase-2/preview/tools/carry-on-size-checker/index.html"
        ),
        "/guides/carry-on-baggage-rules/": Path(
            "changes/raos-v2/phase-2/preview/guides/carry-on-baggage-rules/index.html"
        ),
        "/guides/low-cost-carrier-7kg-packing/": Path(
            "changes/raos-v2/phase-2/preview/guides/low-cost-carrier-7kg-packing/index.html"
        ),
        "/carry-on-suitcase-comparison/": Path(
            "changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html"
        ),
        "/guides/carry-on-bag-measurement/": Path(
            "changes/raos-v2/phase-2/preview/guides/carry-on-bag-measurement/index.html"
        ),
        "/policy/how-we-compare-carry-on-products/": Path(
            "changes/raos-v2/phase-2/preview/policy/how-we-compare-carry-on-products/index.html"
        ),
        "/differences/ace-cresta-vs-difference-vs-maxpass4/": Path(
            "changes/raos-v2/phase-2/preview/differences/ace-cresta-vs-difference-vs-maxpass4/index.html"
        ),
    }
    if set(rendered) != set(paths):
        fail("RAOS_V2_PREVIEW_ROUTE_SET_INVALID")
    result: dict[Path, bytes] = {}
    for route, path in paths.items():
        payload = rendered[route]
        if (
            not isinstance(payload, bytes)
            or not payload.startswith(b"<!doctype html>")
            or len(payload) > 1200 * 1024
        ):
            fail("RAOS_V2_PREVIEW_OUTPUT_INVALID")
        result[path] = payload
    return result


def media_binding_state(
    binding: object, expected: Mapping[str, object]
) -> str:
    """Return the closed media gate state for a recorded offer image binding."""

    if binding is None:
        return "NO_IMAGE_INTENTIONAL"
    required = {"source_id", "item_code", "content_sha256", "alt", "checked_at"}
    if not isinstance(binding, dict) or set(binding) != required:
        return "BLOCKED"
    if set(expected) != {"source_id", "item_code", "content_sha256"}:
        return "BLOCKED"
    source_id = binding.get("source_id")
    item_code = binding.get("item_code")
    digest = binding.get("content_sha256")
    alt = binding.get("alt")
    checked_at = binding.get("checked_at")
    if (
        not isinstance(source_id, str)
        or not source_id.startswith("SRC-")
        or not isinstance(item_code, str)
        or not item_code
        or len(item_code) > 160
        or any(character.isspace() for character in item_code)
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or not isinstance(alt, str)
        or not alt.strip()
        or len(alt) > 300
        or "<" in alt
        or not isinstance(checked_at, str)
    ):
        return "BLOCKED"
    try:
        checked = datetime.fromisoformat(checked_at)
    except ValueError:
        return "BLOCKED"
    if checked.tzinfo is None or checked.utcoffset() is None:
        return "BLOCKED"
    if any(binding.get(key) != expected.get(key) for key in expected):
        return "BLOCKED"
    return "BOUND_OFFICIAL_IMAGE"


def validate_media_policy_document(
    media: Mapping[str, object], offers: Mapping[str, object]
) -> None:
    """Validate the no-image safe default and fail-closed image binding gate."""

    binding = media.get("image_binding_contract")
    registry = media.get("product_registry")
    negatives = media.get("negative_fixtures")
    required_fields = {
        "source_id",
        "item_code",
        "content_sha256",
        "alt",
        "checked_at",
    }
    expected_products = {
        "PRD-ACE-CRESTA-06316",
        "PRD-ACE-DIFFERENCE-05721",
        "PRD-ACE-MAXPASS4-01471",
    }
    if (
        not isinstance(binding, dict)
        or set(binding.get("required_when_offer_image_ref_present", []))
        != required_fields
        or binding.get("missing_or_modified_state") != "BLOCKED"
        or binding.get("no_image_state") != "NO_IMAGE_INTENTIONAL"
        or not isinstance(registry, list)
        or not isinstance(negatives, list)
    ):
        fail("RAOS_V2_MEDIA_POLICY_INVALID")
    registry_products: set[str] = set()
    for row in registry:
        if (
            not isinstance(row, dict)
            or set(row) != {"product_id", "state", "image_binding", "render"}
            or row.get("state") != "NO_IMAGE_INTENTIONAL"
            or row.get("image_binding") is not None
            or row.get("render") != "NEUTRAL_PLACEHOLDER"
            or not isinstance(row.get("product_id"), str)
        ):
            fail("RAOS_V2_MEDIA_POLICY_INVALID")
        registry_products.add(str(row["product_id"]))
    if registry_products != expected_products:
        fail("RAOS_V2_MEDIA_POLICY_INVALID")
    negative_ids: set[str] = set()
    for row in negatives:
        if not isinstance(row, dict) or set(row) != {
            "fixture_id",
            "binding",
            "expected",
            "expected_state",
        }:
            fail("RAOS_V2_MEDIA_POLICY_INVALID")
        fixture_id = row.get("fixture_id")
        expected = row.get("expected")
        if (
            fixture_id not in {"MEDIA-MISSING-SOURCE", "MEDIA-MODIFIED-HASH"}
            or not isinstance(expected, dict)
            or media_binding_state(row.get("binding"), expected)
            != row.get("expected_state")
            or row.get("expected_state") != "BLOCKED"
        ):
            fail("RAOS_V2_MEDIA_POLICY_INVALID")
        negative_ids.add(str(fixture_id))
    if negative_ids != {"MEDIA-MISSING-SOURCE", "MEDIA-MODIFIED-HASH"}:
        fail("RAOS_V2_MEDIA_POLICY_INVALID")
    offer_rows = offers.get("offers")
    registry_by_product = {
        str(row["product_id"]): row for row in registry if isinstance(row, dict)
    }
    if not isinstance(offer_rows, list):
        fail("RAOS_V2_MEDIA_BINDING_UNRESOLVED")
    for row in offer_rows:
        observation = row.get("offer_observation") if isinstance(row, dict) else None
        if not isinstance(observation, dict):
            fail("RAOS_V2_MEDIA_BINDING_UNRESOLVED")
        registry_row = registry_by_product.get(str(observation.get("product_id")))
        if not isinstance(registry_row, dict):
            fail("RAOS_V2_MEDIA_BINDING_UNRESOLVED")
        if observation.get("image_ref") is None:
            if media_binding_state(registry_row.get("image_binding"), {}) != (
                "NO_IMAGE_INTENTIONAL"
            ):
                fail("RAOS_V2_MEDIA_BINDING_UNRESOLVED")
        else:
            # Phase 2 deliberately has no recorded image body/hash. An image
            # reference can only be introduced together with a complete exact
            # expected binding in a successor contract.
            fail("RAOS_V2_MEDIA_BINDING_UNRESOLVED")


def validate_event_catalog_document(catalog: Mapping[str, object]) -> None:
    expected = {
        "tool_result_view": ({"result_state"}, {"source_id", "product_id"}),
        "comparison_view": (set(), {"result_state", "source_id", "product_id"}),
        "evidence_link_open": ({"source_id"}, {"result_state", "product_id"}),
        "official_source_open": ({"source_id"}, {"result_state", "product_id"}),
        "affiliate_outbound_activate": (
            {"product_id"},
            {"result_state", "source_id"},
        ),
        "article_complete": (set(), {"result_state", "source_id", "product_id"}),
        "error_state_view": ({"result_state"}, {"source_id", "product_id"}),
    }
    events = catalog.get("events")
    matrix = catalog.get("event_field_matrix")
    if (
        not isinstance(events, list)
        or set(events) != set(expected)
        or not isinstance(matrix, dict)
        or set(matrix) != set(expected)
    ):
        fail("RAOS_V2_EVENT_FIELD_MATRIX_INVALID")
    for event_name, (required, forbidden) in expected.items():
        row = matrix.get(event_name)
        if (
            not isinstance(row, dict)
            or set(row) != {"required_non_null", "must_be_null"}
            or set(row.get("required_non_null", [])) != required
            or set(row.get("must_be_null", [])) != forbidden
            or required & forbidden
        ):
            fail("RAOS_V2_EVENT_FIELD_MATRIX_INVALID")


def validate_phase2_source_inputs() -> dict[Path, object]:
    """Parse every machine input strictly and bound every source file.

    This intentionally runs before any Phase 2 output is composed. JSON/YAML
    duplicate keys, YAML aliases/tags, symlinks, invalid UTF-8 and oversized
    inputs therefore fail closed at the single generator-owner boundary.
    """

    discovered_implementation = {
        path.relative_to(ROOT)
        for base, suffix in (
            (ROOT / "packages/web-ui/src/decision-support-v2", "*.ts"),
            (ROOT / "python/raos/adapters/decision_support_v2", "*.py"),
            (ROOT / "python/raos/application/decision_support_v2", "*.py"),
            (ROOT / "python/raos/domain/decision_support_v2", "*.py"),
            (ROOT / "python/raos/ports/decision_support_v2", "*.py"),
        )
        for path in base.glob(suffix)
        if path.is_file() and not path.is_symlink()
    }
    discovered_tests = {
        path.relative_to(ROOT)
        for pattern in ("*.py", "*.mjs")
        for path in (ROOT / "tests/raos_v2").glob(pattern)
        if path.is_file() and not path.is_symlink()
    }
    discovered_preview_inputs = {
        path.relative_to(ROOT)
        for path in (ROOT / "packages/web-ui/src/decision-support-v2/preview").glob(
            "*"
        )
        if path.is_file() and not path.is_symlink()
    }
    if discovered_implementation != set(PHASE2_IMPLEMENTATION_PATHS):
        fail("RAOS_V2_PHASE2_IMPLEMENTATION_INVENTORY_DRIFT")
    if discovered_preview_inputs != set(PHASE2_PREVIEW_INPUT_PATHS):
        fail("RAOS_V2_PHASE2_PREVIEW_INPUT_INVENTORY_DRIFT")
    if discovered_tests != set(PHASE2_TEST_SOURCE_PATHS):
        fail("RAOS_V2_PHASE2_TEST_INVENTORY_DRIFT")
    if len(PHASE2_SOURCE_PATHS) != len(set(PHASE2_SOURCE_PATHS)):
        fail("RAOS_V2_PHASE2_SOURCE_DUPLICATE")
    parsed: dict[Path, object] = {}
    for relative in PHASE2_SOURCE_PATHS:
        path = ROOT / relative
        try:
            path.lstat()
            payload = path.read_bytes()
        except OSError:
            fail("RAOS_V2_PHASE2_SOURCE_MISSING")
        if path.is_symlink() or not path.is_file() or len(payload) > 2 * 1024 * 1024:
            fail("RAOS_V2_PHASE2_SOURCE_BOUNDARY_INVALID")
        if relative.suffix == ".json":
            parsed[relative] = _read_json(relative)
        elif relative.suffix in {".yaml", ".yml"}:
            parsed[relative] = _read_yaml(relative)
        else:
            try:
                text = payload.decode("utf-8")
            except UnicodeError:
                fail("RAOS_V2_PHASE2_SOURCE_UTF8_INVALID")
            if "\x00" in text:
                fail("RAOS_V2_PHASE2_SOURCE_UTF8_INVALID")
            parsed[relative] = text
    media = parsed.get(Path("changes/raos-v2/phase-2/media/media-policy.v2.yaml"))
    offers = parsed.get(
        Path(
            "changes/raos-v2/phase-2/fixtures/recorded-rakuten-item-search-2026-07-01.json"
        )
    )
    if not isinstance(media, dict) or not isinstance(offers, dict):
        fail("RAOS_V2_MEDIA_POLICY_INVALID")
    validate_media_policy_document(media, offers)
    event_catalog = parsed.get(
        Path("changes/raos-v2/phase-2/events/event-catalog.v2.yaml")
    )
    if not isinstance(event_catalog, dict):
        fail("RAOS_V2_EVENT_FIELD_MATRIX_INVALID")
    validate_event_catalog_document(event_catalog)
    return parsed


def _phase2_input_inventory() -> list[dict[str, object]]:
    roles: dict[Path, str] = {
        **{path: "DATA_OR_CONTENT_INPUT" for path in PHASE2_DATA_PATHS},
        **{
            path: "AUTHORITATIVE_PREVIEW_INPUT"
            for path in PHASE2_PREVIEW_INPUT_PATHS
        },
        **{
            path: "RECORDED_LOCAL_EVIDENCE_INPUT"
            for path in PHASE2_RECORDED_EVIDENCE_PATHS
        },
        **{path: "IMPLEMENTATION_SOURCE" for path in PHASE2_IMPLEMENTATION_PATHS},
        **{path: "TEST_SOURCE" for path in PHASE2_TEST_SOURCE_PATHS},
    }
    # Normal tracked code/tests/content are deliberately not digest-pinned.
    # Hashes below are reserved for runtime data integrity, generated output,
    # package/container provenance and recorded evidence receipts.
    return [
        {"path": path.as_posix(), "role": roles[path]}
        for path in sorted(PHASE2_SOURCE_PATHS)
    ]


def migration_manifest_document(
    capture: Mapping[str, object], preview: Mapping[Path, bytes]
) -> dict[str, object]:
    rows = capture.get("public_urls")
    if not isinstance(rows, list):
        fail("RAOS_V2_MIGRATION_BASELINE_INVALID")
    baseline = next(
        (
            row
            for row in rows
            if isinstance(row, dict)
            and row.get("path") == "/carry-on-suitcase-comparison/"
        ),
        None,
    )
    if not isinstance(baseline, dict):
        fail("RAOS_V2_MIGRATION_BASELINE_INVALID")
    route = str(baseline.get("path"))
    status = baseline.get("status")
    canonical = baseline.get("canonical")
    robots = baseline.get("robots")
    if (
        not isinstance(status, int)
        or not isinstance(canonical, str)
        or not isinstance(robots, str)
    ):
        fail("RAOS_V2_MIGRATION_BASELINE_INVALID")
    round_trip = simulate_route_round_trip(
        (route, status, canonical, robots),
        (route, 200, canonical, "noindex,nofollow"),
    )
    preview_path = Path(
        "changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html"
    )
    preview_payload = preview.get(preview_path)
    if not isinstance(preview_payload, bytes):
        fail("RAOS_V2_MIGRATION_PREVIEW_MISSING")
    document: dict[str, object] = {
        "schema": "RAOS_V2_MIGRATION_MANIFEST_V1",
        "version": "2.0.0",
        "mode": "LOCAL_SIMULATION_ONLY",
        "target_origin": "https://kurashinoshirube.com",
        "target_route": route,
        "legacy_article_aliases": [
            {
                "legacy_article_id": "st1703-first-suitcase-comparison",
                "stable_article_id": "A05",
                "route": route,
                "purpose": "MIGRATION_REFERENCE_ONLY",
            }
        ],
        "public_before": {
            "evidence_class": "PUBLIC_READ_ONLY",
            "observed_at": baseline.get("observed_at"),
            "status": status,
            "canonical": canonical,
            "robots": robots,
            "body_sha256": baseline.get("body_sha256"),
        },
        "local_candidate": {
            "preview_path": preview_path.as_posix(),
            "render_sha256": sha256(preview_payload),
            "preview_robots": "noindex,nofollow",
            "public_write": "NOT_EXECUTED",
        },
        "future_public_intent": {
            "route_preserved": True,
            "canonical": canonical,
            "indexing_change": "REQUIRES_PHASE3_HUMAN_APPROVAL_AND_PUBLIC_VERIFY",
        },
        "rollback": {
            "simulation": round_trip,
            "restore_tuple": [route, status, canonical, robots],
            "plan_scope": "P2_LOCAL_CONTRACT_FOR_P3_HUMAN_GATED_EXECUTION",
            "ordered_restore_steps": [
                {
                    "sequence": 1,
                    "phase_boundary": "P2_LOCAL_PREPARATION",
                    "action": "VERIFY_PRECONDITIONS_AND_EXPORT_RECEIPT",
                    "requires": [
                        "human approval for Phase 3",
                        "recoverable content metadata theme and URL export receipt",
                    ],
                    "production_status": "NOT_EXECUTED",
                },
                {
                    "sequence": 2,
                    "phase_boundary": "P3_HUMAN_GATED",
                    "action": "RESTORE_PRIOR_CONTENT_METADATA_THEME_AND_URL",
                    "requires": ["step 1 verified", "exact restore tuple binding"],
                    "production_status": "NOT_EXECUTED",
                },
                {
                    "sequence": 3,
                    "phase_boundary": "P3_HUMAN_GATED",
                    "action": "PUBLIC_READ_ONLY_VERIFY_STATUS_CANONICAL_ROBOTS_AND_BODY",
                    "requires": ["step 2 completed", "same-origin credential-free capture"],
                    "production_status": "NOT_EXECUTED",
                },
            ],
            "production_backup": "NOT_EXECUTED",
            "production_restore": "NOT_EXECUTED",
        },
        "failure_conditions": [
            "route or canonical differs from captured baseline",
            "critical claim, disclosure, CTA, accessibility or SEO defect",
            "rollback tuple binding or render digest mismatch",
        ],
        "external_actions": "NOT_EXECUTED",
        "backlog_id": "B-V2-031",
        "requirement_ids": ["R-V2-023", "R-V2-025"],
        "test_ids": ["T-V2-025", "T-V2-035", "T-V2-040"],
    }
    validate_migration_restore_plan(document)
    return document


def validate_migration_restore_plan(document: Mapping[str, object]) -> None:
    """Validate the ordered, local-only recovery contract for Phase 3."""

    public_before = document.get("public_before")
    rollback = document.get("rollback")
    if not isinstance(public_before, Mapping) or not isinstance(rollback, Mapping):
        fail("RAOS_V2_MIGRATION_RESTORE_PLAN_INVALID")
    restore_tuple = rollback.get("restore_tuple")
    steps = rollback.get("ordered_restore_steps")
    simulation = rollback.get("simulation")
    expected_tuple = [
        document.get("target_route"),
        public_before.get("status"),
        public_before.get("canonical"),
        public_before.get("robots"),
    ]
    expected_actions = [
        "VERIFY_PRECONDITIONS_AND_EXPORT_RECEIPT",
        "RESTORE_PRIOR_CONTENT_METADATA_THEME_AND_URL",
        "PUBLIC_READ_ONLY_VERIFY_STATUS_CANONICAL_ROBOTS_AND_BODY",
    ]
    expected_boundaries = [
        "P2_LOCAL_PREPARATION",
        "P3_HUMAN_GATED",
        "P3_HUMAN_GATED",
    ]
    if (
        document.get("mode") != "LOCAL_SIMULATION_ONLY"
        or document.get("external_actions") != "NOT_EXECUTED"
        or rollback.get("plan_scope")
        != "P2_LOCAL_CONTRACT_FOR_P3_HUMAN_GATED_EXECUTION"
        or rollback.get("production_backup") != "NOT_EXECUTED"
        or rollback.get("production_restore") != "NOT_EXECUTED"
        or restore_tuple != expected_tuple
        or not isinstance(steps, list)
        or len(steps) != 3
        or not isinstance(simulation, Mapping)
        or simulation.get("status") != "PASSED_LOCAL"
        or simulation.get("exact_tuple_restored") is not True
        or simulation.get("baseline_sha256") != simulation.get("restored_sha256")
        or simulation.get("external_action") != "NOT_EXECUTED"
    ):
        fail("RAOS_V2_MIGRATION_RESTORE_PLAN_INVALID")
    for index, step in enumerate(steps, start=1):
        if (
            not isinstance(step, Mapping)
            or step.get("sequence") != index
            or step.get("action") != expected_actions[index - 1]
            or step.get("phase_boundary") != expected_boundaries[index - 1]
            or step.get("production_status") != "NOT_EXECUTED"
            or not isinstance(step.get("requires"), list)
            or not step["requires"]
            or not all(
                isinstance(value, str) and value for value in step["requires"]
            )
        ):
            fail("RAOS_V2_MIGRATION_RESTORE_PLAN_INVALID")


def claim_ledger_document() -> dict[str, object]:
    products = _read_json(
        Path("changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json")
    )
    airlines = _read_json(
        Path("changes/raos-v2/phase-2/fixtures/recorded-airline-rules.v2.json")
    )
    source_registry = _read_yaml(
        Path("changes/raos-v2/phase-2/sources/source-registry.v2.yaml")
    )
    if not all(isinstance(value, dict) for value in (products, airlines, source_registry)):
        fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
    assert isinstance(products, dict)
    assert isinstance(airlines, dict)
    assert isinstance(source_registry, dict)
    source_rows = source_registry.get("sources")
    if not isinstance(source_rows, list):
        fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
    sources = {
        row["source_id"]: row
        for row in source_rows
        if isinstance(row, dict) and isinstance(row.get("source_id"), str)
    }

    def record(
        *,
        claim_id: str,
        claim_type: str,
        subject_id: str,
        predicate: str,
        value: object,
        unit: str | None,
        source_ids: list[str],
        logic_inputs: list[dict[str, str]],
        checked_at: str,
        next_review_at: str,
        risk_class: str,
        status: str,
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "claim_id": claim_id,
            "claim_type": claim_type,
            "subject_id": subject_id,
            "predicate": predicate,
            "value": value,
            "unit": unit,
            "source_ids": source_ids,
            "logic_inputs": logic_inputs,
            "checked_at": checked_at,
            "next_review_at": next_review_at,
            "risk_class": risk_class,
            "status": status,
        }

    rows: list[dict[str, object]] = []
    product_claim_ids: dict[str, dict[str, str]] = {}
    prefixes = {
        "PRD-ACE-CRESTA-06316": "CRESTA",
        "PRD-ACE-DIFFERENCE-05721": "DIFFERENCE",
        "PRD-ACE-MAXPASS4-01471": "MAXPASS4",
    }
    product_rows = products.get("products")
    if not isinstance(product_rows, list):
        fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
    for product in product_rows:
        if not isinstance(product, dict):
            fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
        product_id = product.get("product_id")
        source_ids = product.get("official_source_ids")
        variants = product.get("variants")
        if (
            not isinstance(product_id, str)
            or product_id not in prefixes
            or not isinstance(source_ids, list)
            or len(source_ids) != 1
            or not isinstance(source_ids[0], str)
            or not isinstance(variants, list)
            or len(variants) != 1
            or not isinstance(variants[0], dict)
        ):
            fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
        source = sources.get(source_ids[0])
        if not isinstance(source, dict):
            fail("RAOS_V2_CLAIM_LEDGER_SOURCE_MISSING")
        checked_at = source.get("checked_at")
        next_review_at = source.get("next_review_at")
        if not isinstance(checked_at, str) or not isinstance(next_review_at, str):
            fail("RAOS_V2_CLAIM_LEDGER_SOURCE_MISSING")
        variant = variants[0]
        prefix = prefixes[product_id]
        identifiers = {
            "identity": f"CLM-A05-{prefix}-IDENTITY",
            "dimensions": f"CLM-A05-{prefix}-DIMENSIONS",
            "capacity": f"CLM-A05-{prefix}-CAPACITY",
            "mass": f"CLM-A05-{prefix}-MASS",
            "features": f"CLM-A05-{prefix}-FEATURES",
            "unknown": f"CLM-A05-{prefix}-USAGE-UNKNOWN",
            "fit": f"CLM-A05-{prefix}-CONDITIONAL-FIT",
        }
        product_claim_ids[product_id] = identifiers
        facts = (
            (
                identifiers["identity"],
                "product_identity",
                {
                    "brand": product.get("brand"),
                    "model_name": product.get("model_name"),
                    "model_number": product.get("model_number"),
                },
                None,
            ),
            (
                identifiers["dimensions"],
                "external_dimensions_cm",
                variant.get("external_dimensions_cm"),
                "cm",
            ),
            (
                identifiers["capacity"],
                "capacity_l",
                variant.get("capacity_l"),
                "L",
            ),
            (identifiers["mass"], "mass_kg", variant.get("mass_kg"), "kg"),
            (
                identifiers["features"],
                "declared_features",
                variant.get("declared_features"),
                None,
            ),
        )
        for claim_id, predicate, fact_value, unit in facts:
            rows.append(
                record(
                    claim_id=claim_id,
                    claim_type="A_OFFICIAL_FACT",
                    subject_id=product_id,
                    predicate=predicate,
                    value=fact_value,
                    unit=unit,
                    source_ids=[source_ids[0]],
                    logic_inputs=[],
                    checked_at=checked_at,
                    next_review_at=next_review_at,
                    risk_class=(
                        "HIGH"
                        if predicate in {"product_identity", "external_dimensions_cm"}
                        else "MEDIUM"
                    ),
                    status="VERIFIED",
                )
            )
        for field, predicate, unit in (
            ("expanded_dimensions_cm", "expanded_dimensions_cm", "cm"),
            ("expanded_capacity_l", "expanded_capacity_l", "L"),
        ):
            if variant.get(field) is not None:
                claim_id = f"CLM-A05-{prefix}-{'EXPANDED-DIMENSIONS' if 'dimensions' in field else 'EXPANDED-CAPACITY'}"
                identifiers[field] = claim_id
                rows.append(
                    record(
                        claim_id=claim_id,
                        claim_type="A_OFFICIAL_FACT",
                        subject_id=product_id,
                        predicate=predicate,
                        value=variant.get(field),
                        unit=unit,
                        source_ids=[source_ids[0]],
                        logic_inputs=[],
                        checked_at=checked_at,
                        next_review_at=next_review_at,
                        risk_class="HIGH",
                        status="VERIFIED",
                    )
                )
        rows.append(
            record(
                claim_id=identifiers["unknown"],
                claim_type="UNKNOWN",
                subject_id=product_id,
                predicate="hands_on_usage",
                value=None,
                unit=None,
                source_ids=[],
                logic_inputs=[],
                checked_at=checked_at,
                next_review_at=next_review_at,
                risk_class="MEDIUM",
                status="BLOCKED",
            )
        )
        decision_inputs = [
            {"input_id": f"IN-{prefix}-DIMENSIONS", "value_ref": identifiers["dimensions"]},
            {"input_id": f"IN-{prefix}-CAPACITY", "value_ref": identifiers["capacity"]},
            {"input_id": f"IN-{prefix}-MASS", "value_ref": identifiers["mass"]},
            {"input_id": f"IN-{prefix}-FEATURES", "value_ref": identifiers["features"]},
        ]
        rows.append(
            record(
                claim_id=identifiers["fit"],
                claim_type="D_EDITORIAL_JUDGEMENT",
                subject_id="A05",
                predicate="conditional_fit",
                value=product_id,
                unit=None,
                source_ids=[source_ids[0]],
                logic_inputs=decision_inputs,
                checked_at=checked_at,
                next_review_at=next_review_at,
                risk_class="MEDIUM",
                status="VERIFIED",
            )
        )

    mass_inputs = [
        {
            "input_id": f"IN-{prefixes[product_id]}-MASS",
            "value_ref": product_claim_ids[product_id]["mass"],
        }
        for product_id in prefixes
    ]
    mass_sources = [sources[source_id] for source_id in (
        "SRC-ACE-CRESTA-06316",
        "SRC-ACE-DIFFERENCE-05721",
        "SRC-ACE-MAXPASS4-01471",
    )]
    if not all(isinstance(row, dict) for row in mass_sources):
        fail("RAOS_V2_CLAIM_LEDGER_SOURCE_MISSING")
    mass_checked_at = max(str(row["checked_at"]) for row in mass_sources)
    mass_next_review_at = min(str(row["next_review_at"]) for row in mass_sources)
    rows.append(
        record(
            claim_id="CLM-A05-CRESTA-LIGHTEST-IN-SCOPE",
            claim_type="D_EDITORIAL_JUDGEMENT",
            subject_id="A05",
            predicate="conditional_lightest_product",
            value="PRD-ACE-CRESTA-06316",
            unit=None,
            source_ids=[
                "SRC-ACE-CRESTA-06316",
                "SRC-ACE-DIFFERENCE-05721",
                "SRC-ACE-MAXPASS4-01471",
            ],
            logic_inputs=mass_inputs,
            checked_at=mass_checked_at,
            next_review_at=mass_next_review_at,
            risk_class="MEDIUM",
            status="VERIFIED",
        )
    )

    displayed_rules = {
        ("AIR-ANA-DOMESTIC-2026", "ANA-100-SEATS-OR-MORE"): "CLM-A02-ANA-LARGE-RULE",
        ("AIR-ANA-DOMESTIC-2026", "ANA-UNDER-100-SEATS"): "CLM-A02-ANA-SMALL-RULE",
        ("AIR-JAL-DOMESTIC-2026", "JAL-100-SEATS-OR-MORE"): "CLM-A02-JAL-LARGE-RULE",
        ("AIR-JAL-DOMESTIC-2026", "JAL-UNDER-100-SEATS"): "CLM-A02-JAL-SMALL-RULE",
        ("AIR-PEACH-2026", "PEACH-STANDARD"): "CLM-A02-PEACH-STANDARD-RULE",
        (
            "AIR-JETSTAR-JAPAN-2026",
            "JETSTAR-JAPAN-STANDARD-7KG",
        ): "CLM-A02-JETSTAR-STANDARD-RULE",
    }
    rule_sets = airlines.get("rule_sets")
    if not isinstance(rule_sets, list):
        fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
    for rule_set in rule_sets:
        if not isinstance(rule_set, dict) or not isinstance(rule_set.get("variants"), list):
            fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
        for variant in rule_set["variants"]:
            if not isinstance(variant, dict):
                fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
            key = (rule_set.get("rule_set_id"), variant.get("variant_id"))
            claim_id = displayed_rules.get(key)
            if claim_id is None:
                continue
            source_id = rule_set.get("source_id")
            next_review_at = rule_set.get("source_next_review_at")
            checked_at = rule_set.get("checked_at")
            if not all(
                isinstance(value, str)
                for value in (source_id, next_review_at, checked_at)
            ):
                fail("RAOS_V2_CLAIM_LEDGER_INPUT_INVALID")
            rows.append(
                record(
                    claim_id=claim_id,
                    claim_type="A_OFFICIAL_FACT",
                    subject_id=str(rule_set["rule_set_id"]),
                    predicate="carry_on_rule_variant",
                    value={
                        "carrier": rule_set.get("carrier"),
                        "effective_from": rule_set.get("effective_from"),
                        "observed_applicable_from": rule_set.get(
                            "observed_applicable_from"
                        ),
                        "effective_to": rule_set.get("effective_to"),
                        "variant": variant,
                    },
                    unit=None,
                    source_ids=[str(source_id)],
                    logic_inputs=[],
                    checked_at=str(checked_at),
                    next_review_at=str(next_review_at),
                    risk_class="HIGH",
                    status="VERIFIED",
                )
            )
    if len(rows) != len({str(row["claim_id"]) for row in rows}):
        fail("RAOS_V2_CLAIM_LEDGER_DUPLICATE")
    return {
        "schema": "RAOS_V2_CLAIM_LEDGER_V1",
        "version": "2.0.0",
        "generation": "NORMALIZED_FROM_RECORDED_PRODUCT_AND_AIRLINE_FACTS",
        "claims": rows,
    }


def publication_claim_evidence(
    *,
    bound_claims: Sequence[Mapping[str, object]],
    all_claims: Mapping[str, Mapping[str, object]],
    source_registry: Mapping[str, object],
    candidate_at: datetime,
) -> list[dict[str, str]]:
    """Resolve evidence freshness instead of trusting a VERIFIED label."""

    if candidate_at.tzinfo is None or candidate_at.utcoffset() is None:
        fail("RAOS_V2_PUBLICATION_TIME_INVALID")
    source_rows = source_registry.get("sources")
    if not isinstance(source_rows, list):
        fail("RAOS_V2_PUBLICATION_SOURCE_REGISTRY_INVALID")
    sources = {
        str(row["source_id"]): row
        for row in source_rows
        if isinstance(row, dict) and isinstance(row.get("source_id"), str)
    }
    allowed_source_classes = {
        "MANUFACTURER_PRIMARY",
        "AIRLINE_PRIMARY",
        "GOVERNMENT_PRIMARY",
        "RAKUTEN_PERMITTED_DATA",
    }
    evidence: list[dict[str, str]] = []
    for claim in sorted(bound_claims, key=lambda row: str(row.get("claim_id"))):
        claim_id = claim.get("claim_id")
        claim_type = claim.get("claim_type")
        risk_class = claim.get("risk_class")
        if not all(isinstance(value, str) for value in (claim_id, claim_type, risk_class)):
            fail("RAOS_V2_PUBLICATION_CLAIM_INVALID")
        assert isinstance(claim_id, str)
        assert isinstance(claim_type, str)
        assert isinstance(risk_class, str)
        if claim_type == "UNKNOWN":
            if (
                claim.get("status") != "BLOCKED"
                or claim.get("value") is not None
                or claim.get("unit") is not None
                or claim.get("source_ids") != []
            ):
                fail("RAOS_V2_PUBLICATION_UNKNOWN_CLAIM_INVALID")
            evidence.append(
                {
                    "claim_id": claim_id,
                    "risk_class": risk_class,
                    "freshness": "UNKNOWN",
                }
            )
            continue
        if claim.get("status") != "VERIFIED":
            fail("RAOS_V2_PUBLICATION_CLAIM_NOT_VERIFIED")
        source_ids = claim.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            fail("RAOS_V2_PUBLICATION_SOURCE_CLOSURE_INVALID")
        resolved_sources: list[Mapping[str, object]] = []
        for source_id in source_ids:
            source = sources.get(str(source_id))
            if (
                not isinstance(source, dict)
                or source.get("source_class") not in allowed_source_classes
                or source.get("status") not in {"FRESH", "DUE"}
                or not isinstance(source.get("content_sha256"), str)
                or len(str(source.get("content_sha256"))) != 64
            ):
                fail("RAOS_V2_PUBLICATION_SOURCE_INELIGIBLE")
            resolved_sources.append(source)
        try:
            source_checked = max(
                datetime.fromisoformat(str(source["checked_at"]).replace("Z", "+00:00"))
                for source in resolved_sources
            )
            source_next_review = min(
                datetime.fromisoformat(
                    str(source["next_review_at"]).replace("Z", "+00:00")
                )
                for source in resolved_sources
            )
            claim_checked = datetime.fromisoformat(
                str(claim["checked_at"]).replace("Z", "+00:00")
            )
            claim_next_review = datetime.fromisoformat(
                str(claim["next_review_at"]).replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            fail("RAOS_V2_PUBLICATION_SOURCE_TIME_INVALID")
        if (
            claim_checked != source_checked
            or claim_next_review != source_next_review
            or candidate_at > claim_next_review
        ):
            fail("RAOS_V2_PUBLICATION_CLAIM_FRESHNESS_INVALID")
        if claim_type == "D_EDITORIAL_JUDGEMENT":
            logic_inputs = claim.get("logic_inputs")
            if not isinstance(logic_inputs, list) or not logic_inputs:
                fail("RAOS_V2_PUBLICATION_LOGIC_CLOSURE_INVALID")
            for logic_input in logic_inputs:
                value_ref = (
                    logic_input.get("value_ref")
                    if isinstance(logic_input, dict)
                    else None
                )
                if not isinstance(value_ref, str) or value_ref not in all_claims:
                    fail("RAOS_V2_PUBLICATION_LOGIC_CLOSURE_INVALID")
        freshness = (
            "DUE"
            if candidate_at == claim_next_review
            or any(source.get("status") == "DUE" for source in resolved_sources)
            else "FRESH"
        )
        evidence.append(
            {
                "claim_id": claim_id,
                "risk_class": risk_class,
                "freshness": freshness,
            }
        )
    return evidence


def validate_publication_hash_closure(document: Mapping[str, object]) -> None:
    hashes = document.get("input_hashes")
    migration = document.get("migration_manifest")
    if (
        not isinstance(hashes, dict)
        or not isinstance(migration, dict)
        or document.get("render_hash") != hashes.get("render")
        or document.get("source_snapshot_hash") != hashes.get("sources")
        or migration.get("sha256") != hashes.get("migration")
    ):
        fail("RAOS_V2_PUBLICATION_HASH_CLOSURE_INVALID")


def publication_candidate_document(
    migration: Mapping[str, object],
    preview: Mapping[Path, bytes],
    claim_ledger: Mapping[str, object],
) -> dict[str, object]:
    content_path = Path("changes/raos-v2/phase-2/content/carry-on-comparison.v2.yaml")
    article_path = Path(
        "changes/raos-v2/phase-2/content/article-definitions.v2.yaml"
    )
    editorial_path = Path(
        "changes/raos-v2/phase-2/editorial/editorial-decisions.v2.yaml"
    )
    product_path = Path("changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json")
    render_model_path = Path(
        "packages/web-ui/src/decision-support-v2/preview/pages.v2.json"
    )
    source_path = Path("changes/raos-v2/phase-2/sources/source-registry.v2.yaml")
    review_path = Path("changes/raos-v2/phase-2/reviews/review-packet.v2.yaml")
    preview_path = Path(
        "changes/raos-v2/phase-2/preview/carry-on-suitcase-comparison/index.html"
    )
    content = _read_yaml(content_path)
    article_definitions = _read_yaml(article_path)
    source_registry = _read_yaml(source_path)
    review = _read_yaml(review_path)
    if not all(
        isinstance(value, dict)
        for value in (content, article_definitions, source_registry, review)
    ):
        fail("RAOS_V2_PUBLICATION_INPUT_INVALID")
    assert isinstance(content, dict)
    assert isinstance(article_definitions, dict)
    assert isinstance(source_registry, dict)
    assert isinstance(review, dict)
    real_review = review.get("real_content")
    article_rows = article_definitions.get("articles")
    claim_rows = claim_ledger.get("claims")
    if not isinstance(article_rows, list) or not isinstance(claim_rows, list):
        fail("RAOS_V2_PUBLICATION_INPUT_INVALID")
    article = next(
        (
            row
            for row in article_rows
            if isinstance(row, dict) and row.get("article_id") == content.get("article_id")
        ),
        None,
    )
    if not isinstance(article, dict) or article.get("route") != content.get("route"):
        fail("RAOS_V2_PUBLICATION_ARTICLE_BINDING_INVALID")
    claims_by_id = {
        row["claim_id"]: row
        for row in claim_rows
        if isinstance(row, dict) and isinstance(row.get("claim_id"), str)
    }
    article_claim_ids = article.get("claim_ids")
    if (
        not isinstance(article_claim_ids, list)
        or not article_claim_ids
        or any(claim_id not in claims_by_id for claim_id in article_claim_ids)
    ):
        fail("RAOS_V2_PUBLICATION_CLAIM_CLOSURE_INVALID")
    bound_claims = [claims_by_id[str(claim_id)] for claim_id in article_claim_ids]
    if any(
        claim.get("status") != (
            "BLOCKED" if claim.get("claim_type") == "UNKNOWN" else "VERIFIED"
        )
        for claim in bound_claims
    ):
        fail("RAOS_V2_PUBLICATION_CLAIM_STATE_INVALID")
    if (
        content.get("review_state") != "EVIDENCE_COMPLETE"
        or not isinstance(real_review, dict)
        or real_review.get("human_review") != "NOT_EXECUTED"
    ):
        fail("RAOS_V2_REAL_CONTENT_REVIEW_BOUNDARY_INVALID")
    preview_payload = preview.get(preview_path)
    if not isinstance(preview_payload, bytes):
        fail("RAOS_V2_PUBLICATION_RENDER_MISSING")
    migration_payload = yaml_bytes(migration)
    input_hashes = {
        "article": exact_file_set_sha256((article_path, content_path)),
        "claims": sha256(yaml_bytes(claim_ledger)),
        "sources": sha256((ROOT / source_path).read_bytes()),
        "render": sha256(preview_payload),
        "migration": sha256(migration_payload),
        "editorial": sha256((ROOT / editorial_path).read_bytes()),
        "products": sha256((ROOT / product_path).read_bytes()),
        "review": sha256((ROOT / review_path).read_bytes()),
        "render_model": sha256((ROOT / render_model_path).read_bytes()),
    }
    route = content.get("route")
    article_id = content.get("article_id")
    source_rows = source_registry.get("sources")
    checked_times = (
        [
            row.get("checked_at")
            for row in source_rows
            if isinstance(row, dict) and isinstance(row.get("checked_at"), str)
        ]
        if isinstance(source_rows, list)
        else []
    )
    try:
        created_at_value = max(
            (
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                for value in checked_times
            ),
            default=None,
        )
    except ValueError:
        fail("RAOS_V2_PUBLICATION_SOURCE_TIME_INVALID")
    created_at = created_at_value.isoformat() if created_at_value is not None else None
    if not all(isinstance(value, str) for value in (route, article_id, created_at)):
        fail("RAOS_V2_PUBLICATION_INPUT_INVALID")
    assert created_at_value is not None
    claim_evidence = publication_claim_evidence(
        bound_claims=bound_claims,
        all_claims=claims_by_id,
        source_registry=source_registry,
        candidate_at=created_at_value,
    )
    document = {
        "schema_version": "1.0.0",
        "package_id": "PKG-V2-CARRY-ON-COMPARISON-CANDIDATE",
        "target_origin": "https://kurashinoshirube.com",
        "target_route": route,
        "article_id": article_id,
        "input_hashes": input_hashes,
        "render_hash": input_hashes["render"],
        "source_snapshot_hash": input_hashes["sources"],
        "claim_evidence": claim_evidence,
        "review_binding": None,
        "migration_manifest": {
            "schema": migration.get("schema"),
            "mode": migration.get("mode"),
            "target_route": migration.get("target_route"),
            "sha256": input_hashes["migration"],
        },
        "created_at": created_at,
        "content_class": "REAL_CONTENT",
        "state": "EVIDENCE_COMPLETE",
        "package_digest": None,
    }
    validate_publication_hash_closure(document)
    return document


def synthetic_seal_receipt_document() -> dict[str, object]:
    python_root = str(ROOT / "python")
    if python_root not in sys.path:
        sys.path.insert(0, python_root)
    try:
        from raos.adapters.decision_support_v2.wordpress_disabled import (
            DisabledWordPressDraft,
        )
        from raos.domain.decision_support_v2.publication import (
            ClaimEvidenceBinding,
            PublicationPackage,
            PublicationState,
            ReviewBinding,
        )
        from raos.domain.decision_support_v2.models import FreshnessState, RiskClass
    except ImportError:
        fail("RAOS_V2_PUBLICATION_RUNTIME_IMPORT_INVALID")
    input_hashes = {
        key: sha256(f"RAOS-V2-SYNTHETIC-{key.upper()}".encode())
        for key in ("article", "claims", "sources", "render", "migration")
    }
    synthetic_migration = {
        "previous": None,
        "next": "synthetic",
        "wordpress_intent": "CREATE_OR_UPDATE",
    }
    input_hashes["migration"] = sha256(canonical_json_bytes(synthetic_migration))
    synthetic_migration["sha256"] = input_hashes["migration"]
    package = PublicationPackage(
        package_id="SYNTHETIC-PACKAGE-V2",
        target_origin="https://kurashinoshirube.com",
        target_route="/synthetic-contract-fixture/",
        article_id="SYNTHETIC-ARTICLE-V2",
        input_hashes=input_hashes,
        render_hash=input_hashes["render"],
        source_snapshot_hash=input_hashes["sources"],
        claim_evidence=(
            ClaimEvidenceBinding(
                claim_id="CLM-SYNTHETIC-FRESH",
                risk_class=RiskClass.LOW,
                freshness=FreshnessState.FRESH,
            ),
        ),
        review_binding=ReviewBinding(
            reviewer_id="SYNTHETIC-REVIEWER-NOT-A-PERSON",
            reviewed_at=datetime.fromisoformat("2026-08-28T12:00:00+09:00"),
            review_version="SYNTHETIC-V1",
            synthetic=True,
        ),
        migration_manifest=synthetic_migration,
        created_at=datetime.fromisoformat("2026-08-28T12:00:00+09:00"),
        state=PublicationState.DRAFT,
        synthetic=True,
    )
    sealed = (
        package.transition(PublicationState.EVIDENCE_COMPLETE)
        .transition(PublicationState.HUMAN_REVIEWED)
        .transition(PublicationState.PACKAGE_SEALED)
    )
    if not sealed.verify_seal() or sealed.package_digest is None:
        fail("RAOS_V2_SYNTHETIC_SEAL_INVALID")
    sealed_record = dict(sealed.to_contract_record())
    validate_publication_hash_closure(sealed_record)
    wordpress_receipt = dict(DisabledWordPressDraft().dry_run(sealed))
    return {
        "schema": "RAOS_V2_SYNTHETIC_SEAL_RECEIPT_V1",
        "purpose": "STATE_MACHINE_AND_DIGEST_TEST_ONLY",
        "state_path": [
            "DRAFT",
            "EVIDENCE_COMPLETE",
            "HUMAN_REVIEWED",
            "PACKAGE_SEALED",
        ],
        "package": sealed_record,
        "package_digest": sealed.package_digest,
        "digest_verified": True,
        "wordpress_dry_run": wordpress_receipt,
        "external_authority": "NONE",
        "publication": "NOT_EXECUTED",
        "test_ids": ["T-V2-031", "T-V2-037", "T-V2-038"],
    }


def validated_browser_evidence(
    parsed: Mapping[Path, object], preview: Mapping[Path, bytes]
) -> dict[str, object]:
    value = parsed.get(BROWSER_EVIDENCE_INPUT_PATH)
    if not isinstance(value, dict) or value.get("schema") != (
        "RAOS_V2_RECORDED_BROWSER_EVIDENCE_V1"
    ):
        fail("RAOS_V2_BROWSER_EVIDENCE_INPUT_INVALID")
    raw_receipt = value.get("raw_receipt")
    assertions = value.get("assertions")
    recorded_digests = value.get("preview_digests")
    browser_data = value.get("browser")
    if not all(
        isinstance(item, dict)
        for item in (raw_receipt, assertions, recorded_digests, browser_data)
    ):
        fail("RAOS_V2_BROWSER_EVIDENCE_INPUT_INVALID")
    assert isinstance(raw_receipt, dict)
    assert isinstance(assertions, dict)
    assert isinstance(recorded_digests, dict)
    assert isinstance(browser_data, dict)
    checker_states = assertions.get("checker_states")
    if not isinstance(checker_states, dict):
        fail("RAOS_V2_BROWSER_EVIDENCE_ASSERTION_FAILED")
    pages = _read_json(
        Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
    )
    page_rows = pages.get("pages") if isinstance(pages, dict) else None
    routes = (
        [row.get("route") for row in page_rows if isinstance(row, dict)]
        if isinstance(page_rows, list)
        else []
    )
    if not routes or not all(isinstance(route, str) for route in routes):
        fail("RAOS_V2_BROWSER_EVIDENCE_ROUTE_INVALID")
    generated_digests: dict[str, str] = {}
    for route in routes:
        assert isinstance(route, str)
        relative = (
            Path("changes/raos-v2/phase-2/preview/index.html")
            if route == "/"
            else Path("changes/raos-v2/phase-2/preview")
            / route.lstrip("/")
            / "index.html"
        )
        payload = preview.get(relative)
        if not isinstance(payload, bytes):
            fail("RAOS_V2_BROWSER_EVIDENCE_ROUTE_INVALID")
        generated_digests[route] = sha256(payload)
    if generated_digests != recorded_digests:
        fail("RAOS_V2_BROWSER_EVIDENCE_PREVIEW_DRIFT")
    required_assertions = {
        "routes": 9,
        "viewports": [320, 360, 390, 768, 1440],
        "axe_runs": 45,
        "axe_violations": 0,
        "axe_incomplete": 0,
        "horizontal_overflow": 0,
        "outbound_requests": 0,
        "persistent_records": 0,
        "keyboard_only": True,
        "zoom_200_percent": True,
        "forced_colors": True,
        "reduced_motion": True,
        "accessibility_tree_routes": 9,
        "screen_reader_smoke": True,
        "unnamed_interactive_count": 0,
        "keyboard_routes": 9,
        "reflow_400_percent": True,
        "javascript_disabled_routes": 2,
        "javascript_disabled_fallback": True,
        "transfer_budget_routes": 9,
        "transfer_budgets": True,
    }
    if any(assertions.get(key) != expected for key, expected in required_assertions.items()):
        fail("RAOS_V2_BROWSER_EVIDENCE_ASSERTION_FAILED")
    raw_path_value = raw_receipt.get("local_path")
    harness_path_value = raw_receipt.get("harness_path")
    if (
        raw_path_value != "output/playwright/raos-v2-local-browser-evidence.json"
        or harness_path_value != "tests/raos_v2/browser-validation.mjs"
        or raw_receipt.get("command_contract")
        != "NODE24_LOCAL_CDP_AXE_WITH_ABSOLUTE_BROWSER_AND_OUTPUT_PLAYWRIGHT_RECEIPT_V1"
        or raw_receipt.get("exit_status") != 0
    ):
        fail("RAOS_V2_BROWSER_EVIDENCE_INPUT_INVALID")
    harness_path = ROOT / str(harness_path_value)
    try:
        harness_payload = _read_local_evidence_file(harness_path, root=ROOT)
    except ValidationFailure:
        fail("RAOS_V2_BROWSER_HARNESS_MISSING")
    if (
        harness_path.is_symlink()
        or not harness_path.is_file()
        or len(harness_payload) != raw_receipt.get("harness_bytes")
        or sha256(harness_payload) != raw_receipt.get("harness_sha256")
    ):
        fail("RAOS_V2_BROWSER_HARNESS_DRIFT")
    raw_path = ROOT / raw_path_value
    raw_verification = "RECORDED_NOT_REVERIFIED"
    if raw_path.exists() or raw_path.is_symlink():
        try:
            payload = _read_local_evidence_file(raw_path, root=ROOT)
        except ValidationFailure:
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_INVALID")
        if (
            len(payload) != raw_receipt.get("bytes")
            or sha256(payload) != raw_receipt.get("sha256")
        ):
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_DRIFT")
        raw = load_json_strict(payload)
        if (
            not isinstance(raw, dict)
            or raw.get("classification") != "PASSED_LOCAL"
            or raw.get("externalActions") != "NOT_EXECUTED"
            or raw.get("previewDigests") != generated_digests
            or raw.get("harnessPath") != harness_path_value
            or raw.get("harnessSha256") != raw_receipt.get("harness_sha256")
            or raw.get("harnessBytes") != raw_receipt.get("harness_bytes")
            or raw.get("commandContract") != raw_receipt.get("command_contract")
            or raw.get("exitStatus") != raw_receipt.get("exit_status")
        ):
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_INVALID")
        raw_routes = raw.get("routes")
        raw_viewports = raw.get("viewports")
        raw_keyboard = raw.get("keyboard")
        raw_media = raw.get("media")
        raw_accessibility = raw.get("accessibility")
        raw_javascript_disabled = raw.get("javascriptDisabled")
        raw_reflow = raw.get("reflow")
        raw_transfer = raw.get("transfer")
        raw_network = raw.get("network")
        raw_persistence = raw.get("persistence")
        raw_runtime = raw.get("runtime")
        raw_browser = raw.get("browser")
        raw_checker = raw.get("checker")
        viewport_names = {
            "reflow-320-equivalent-400pct",
            "mobile-360",
            "mobile-390",
            "tablet-768",
            "desktop-1440",
        }
        checker_field_map = {
            "pass": "pass",
            "fail": "fail",
            "count_fail": "countFail",
            "unknown": "unknown",
            "underseat_unknown": "underseatUnknown",
            "before_observed_boundary_unknown": "beforeObservedBoundaryUnknown",
            "review_deadline_stale": "reviewDeadlineStale",
            "ana_international_no_match": "anaInternationalNoMatch",
            "ana_unknown_scope": "anaUnknownScope",
            "peach_international_pass": "peachInternationalPass",
            "unknown_dominates_no_match": "unknownDominatesNoMatch",
            "all_segment_intersection": "allSegmentIntersection",
        }
        if (
            not isinstance(raw_routes, dict)
            or len(raw_routes) != 9
            or any(
                not isinstance(row, dict)
                or row.get("axeViolations") != 0
                or row.get("axeIncomplete") != []
                or row.get("mobileOverflow") is not False
                or not isinstance(row.get("viewportAudits"), dict)
                or set(row["viewportAudits"]) != viewport_names
                or any(
                    not isinstance(audit, dict)
                    or audit.get("axeViolations") != 0
                    or audit.get("axeIncomplete") != []
                    or audit.get("horizontalOverflow") is not False
                    for audit in row["viewportAudits"].values()
                )
                for row in raw_routes.values()
            )
            or not isinstance(raw_viewports, dict)
            or set(raw_viewports) != viewport_names
            or any(
                not isinstance(row, dict)
                or row.get("axeRuns") != 9
                or row.get("routes") != 9
                or row.get("horizontalOverflow") is not False
                for row in raw_viewports.values()
            )
            or not isinstance(raw_keyboard, dict)
            or raw_keyboard.get("skipLink") is not True
            or raw_keyboard.get("routes") != 9
            or raw_keyboard.get("focusTraversalAllRoutes") is not True
            or raw_keyboard.get("skipLinkAllRoutes") is not True
            or not isinstance(raw_keyboard.get("focusRingPx"), (int, float))
            or raw_keyboard.get("focusRingPx", 0) < 3
            or not isinstance(raw_keyboard.get("routeResults"), dict)
            or set(raw_keyboard["routeResults"]) != set(generated_digests)
            or any(
                not isinstance(row, dict)
                or row.get("focusTraversal") is not True
                or row.get("skipLink") is not True
                or row.get("mainFocused") is not True
                or not isinstance(row.get("focusRingPx"), (int, float))
                or row.get("focusRingPx", 0) < 3
                for row in raw_keyboard["routeResults"].values()
            )
            or not isinstance(raw_media, dict)
            or not isinstance(raw_media.get("zoom"), dict)
            or raw_media["zoom"].get("horizontalOverflow") is not False
            or raw_media["zoom"].get("routes") != 9
            or not isinstance(raw_media.get("media"), dict)
            or raw_media["media"].get("forcedColors") is not True
            or raw_media["media"].get("reducedMotion") is not True
            or raw_media["media"].get("routes") != 9
            or not isinstance(raw_accessibility, dict)
            or raw_accessibility.get("routes") != 9
            or raw_accessibility.get("fullAxTreeAllRoutes") is not True
            or raw_accessibility.get("screenReaderSmokeAllRoutes") is not True
            or raw_accessibility.get("unnamedInteractiveCount") != 0
            or not isinstance(raw_accessibility.get("routeResults"), dict)
            or set(raw_accessibility["routeResults"]) != set(generated_digests)
            or any(
                not isinstance(row, dict)
                or row.get("fullTreeQueried") is not True
                or row.get("screenReaderSmoke") is not True
                or row.get("unnamedInteractiveCount") != 0
                or row.get("levelOneHeadingCount") != 1
                for row in raw_accessibility["routeResults"].values()
            )
            or not isinstance(raw_javascript_disabled, dict)
            or raw_javascript_disabled.get("testedRoutes") != 2
            or not isinstance(raw_javascript_disabled.get("routes"), dict)
            or set(raw_javascript_disabled.get("routes", {}))
            != {"/", "/tools/carry-on-size-checker/"}
            or any(
                not isinstance(row, dict)
                or row.get("fallbackVisible") is not True
                or row.get("formVisible") is not True
                or row.get("initialState") != "UNKNOWN"
                for row in raw_javascript_disabled["routes"].values()
            )
            or not isinstance(raw_reflow, dict)
            or raw_reflow.get("cssViewportWidthPx") != 320
            or raw_reflow.get("equivalentSourceWidthPx") != 1280
            or raw_reflow.get("equivalentZoomPercent") != 400
            or raw_reflow.get("horizontalOverflow") is not False
            or raw_reflow.get("routes") != 9
            or not isinstance(raw_transfer, dict)
            or not isinstance(raw_transfer.get("routes"), dict)
            or set(raw_transfer["routes"]) != set(generated_digests)
            or any(
                not isinstance(row, dict)
                or row.get("withinCeiling") is not True
                or row.get("inlineSingleDocument") is not True
                or row.get("additionalResourceBytes") != 0
                or not isinstance(row.get("bytes"), int)
                or not isinstance(row.get("ceilingBytes"), int)
                or row["bytes"] > row["ceilingBytes"]
                for row in raw_transfer["routes"].values()
            )
            or not isinstance(raw_network, dict)
            or raw_network.get("outboundRequests") != 0
            or not isinstance(raw_persistence, dict)
            or any(value != 0 for value in raw_persistence.values())
            or not isinstance(raw_runtime, dict)
            or raw_runtime.get("nodeMajor") != 24
            or not isinstance(raw_runtime.get("nodeVersion"), str)
            or not isinstance(raw_browser, dict)
            or raw_browser.get("version") != browser_data.get("version")
            or raw_browser.get("executableSha256")
            != browser_data.get("executable_sha256")
            or not isinstance(raw_checker, dict)
            or any(
                raw_checker.get(raw_key) != checker_states.get(recorded_key)
                for recorded_key, raw_key in checker_field_map.items()
            )
        ):
            fail("RAOS_V2_BROWSER_RAW_RECEIPT_ASSERTION_FAILED")
        raw_verification = "RAW_RECEIPT_VERIFIED_LOCAL"
    result = deepcopy(value)
    result["raw_verification"] = raw_verification
    return result


def _preview_evidence_context(
    parsed: Mapping[Path, object], preview: Mapping[Path, bytes]
) -> tuple[dict[str, str], dict[str, str]]:
    pages = parsed.get(
        Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
    )
    page_rows = pages.get("pages") if isinstance(pages, dict) else None
    if not isinstance(page_rows, list) or len(page_rows) != 9:
        fail("RAOS_V2_VISUAL_EVIDENCE_ROUTE_INVALID")
    digests: dict[str, str] = {}
    classifications: dict[str, str] = {}
    state_to_classification = {
        "LOCAL_PREVIEW": "PUBLIC_CANDIDATE",
        "PLANNED_LOCKED": "PLANNED_LOCKED",
        "FIXTURE_ONLY": "FIXTURE_ONLY",
    }
    for row in page_rows:
        if not isinstance(row, dict):
            fail("RAOS_V2_VISUAL_EVIDENCE_ROUTE_INVALID")
        route = row.get("route")
        state = row.get("publication_state")
        if (
            not isinstance(route, str)
            or route in digests
            or state not in state_to_classification
        ):
            fail("RAOS_V2_VISUAL_EVIDENCE_ROUTE_INVALID")
        relative = (
            Path("changes/raos-v2/phase-2/preview/index.html")
            if route == "/"
            else Path("changes/raos-v2/phase-2/preview")
            / route.lstrip("/")
            / "index.html"
        )
        payload = preview.get(relative)
        if not isinstance(payload, bytes):
            fail("RAOS_V2_VISUAL_EVIDENCE_ROUTE_INVALID")
        digests[route] = sha256(payload)
        classifications[route] = state_to_classification[str(state)]
    return digests, classifications


def validated_visual_evidence(
    parsed: Mapping[Path, object], preview: Mapping[Path, bytes]
) -> dict[str, object]:
    value = parsed.get(VISUAL_EVIDENCE_INPUT_PATH)
    if not isinstance(value, dict):
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INPUT_INVALID")
    digests, classifications = _preview_evidence_context(parsed, preview)
    try:
        verification = verify_visual_review_evidence(
            value,
            preview_digests=digests,
            route_classifications=classifications,
            root=ROOT,
        )
    except ValidationFailure:
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INPUT_INVALID")
    result = deepcopy(value)
    result["verification"] = verification
    return result


def phase2_validation_document(
    parsed: Mapping[Path, object],
    preview: Mapping[Path, bytes],
    publication: Mapping[str, object],
    migration: Mapping[str, object],
) -> dict[str, object]:
    airline = parsed.get(
        Path("changes/raos-v2/phase-2/fixtures/recorded-airline-rules.v2.json")
    )
    products = parsed.get(
        Path("changes/raos-v2/phase-2/data/ace-carry-on-models.v2.json")
    )
    sources = parsed.get(
        Path("changes/raos-v2/phase-2/sources/source-registry.v2.yaml")
    )
    if not all(isinstance(value, dict) for value in (airline, products, sources)):
        fail("RAOS_V2_PHASE2_VALIDATION_INPUT_INVALID")
    assert isinstance(airline, dict)
    assert isinstance(products, dict)
    assert isinstance(sources, dict)
    browser = validated_browser_evidence(parsed, preview)
    visual = validated_visual_evidence(parsed, preview)
    local_test = recorded_local_test_evidence()
    browser_assertions = browser.get("assertions")
    raw_receipt = browser.get("raw_receipt")
    browser_data = browser.get("browser")
    assert isinstance(browser_assertions, dict)
    assert isinstance(raw_receipt, dict)
    assert isinstance(browser_data, dict)
    visual_verification = visual.get("verification")
    if not isinstance(visual_verification, dict):
        fail("RAOS_V2_VISUAL_REVIEW_EVIDENCE_INPUT_INVALID")
    recorded_local_test = deepcopy(local_test)
    recorded_local_test["raw_verification"] = "RECORDED_NOT_REVERIFIED"
    recorded_visual_verification = deepcopy(visual_verification)
    recorded_visual_verification["raw_verification"] = (
        "RECORDED_NOT_REVERIFIED"
    )
    tests = [f"T-V2-{value:03d}" for value in range(20, 47)] + ["T-V2-051"]
    gate_passed = (
        local_test.get("status") == "PASSED_LOCAL"
        and browser.get("classification") == "PASSED_LOCAL"
        and browser.get("raw_verification")
        in {"RAW_RECEIPT_VERIFIED_LOCAL", "RECORDED_NOT_REVERIFIED"}
        and visual_verification.get("effective_status")
        == "PASSED_LOCAL_MANUAL_VISUAL_REVIEW"
        and visual_verification.get("raw_verification")
        in {
            "RAW_CAPTURE_AND_27_PNGS_VERIFIED_LOCAL",
            "RECORDED_NOT_REVERIFIED",
        }
    )
    return {
        "schema": "RAOS_V2_PHASE2_VALIDATION_V1",
        "status": (
            "PASSED_LOCAL_RECORDED"
            if gate_passed
            else "READY_FOR_LOCAL_TEST_GATE"
        ),
        "evidence_scope": "LOCAL_ONLY",
        "checks": {
            "strict_source_inputs": len(parsed),
            "recorded_airline_rule_sets": len(airline.get("rule_sets", [])),
            "recorded_official_sources": len(sources.get("sources", [])),
            "product_models": len(products.get("products", [])),
            "preview_routes": len(preview),
            "real_publication_state": publication.get("state"),
            "real_publication_sealed": False,
            "migration_mode": migration.get("mode"),
            "rakuten_adapter": "RECORDED_ONLY",
            "wordpress_adapter": "DISABLED_DRY_RUN",
            "event_collector": "LOCAL_SINK_ONLY",
            "network_default": "DENY",
            "live_write_capability": False,
        },
        "implemented_backlog_ids": [f"B-V2-{value:03d}" for value in range(19, 34)],
        "completed_backlog_ids": (
            [f"B-V2-{value:03d}" for value in range(19, 35)]
            if gate_passed
            else []
        ),
        "pending_exit_backlog_ids": (
            [] if gate_passed else ["B-V2-034"]
        ),
        "local_test_contracts": {
            "ids": tests,
            "status": local_test.get("status"),
            "required_owner": "tests/raos_v2",
            "receipt": recorded_local_test,
            "generator_execution": "NOT_EXECUTED_BY_GENERATOR",
        },
        "browser_evidence": {
            "classification": browser.get("classification"),
            "evidence_basis": "COMMITTED_SANITIZED_RECORDED_RECEIPT",
            "browser": browser_data.get("version"),
            **browser_assertions,
            "receipt_path": raw_receipt.get("local_path"),
            "receipt_sha256": raw_receipt.get("sha256"),
            "receipt_bytes": raw_receipt.get("bytes"),
            "tracked": False,
            "raw_verification": "RECORDED_NOT_REVERIFIED",
            "ci_without_raw": "RECORDED_NOT_REVERIFIED",
        },
        "visual_review_evidence": {
            "classification": visual.get("classification"),
            "reviewer_class": visual.get("reviewer_class"),
            "reviewed_at_jst": visual.get("reviewed_at_jst"),
            "capture_receipt": visual.get("capture_receipt"),
            "aggregate_findings": visual.get("aggregate_findings"),
            "capture_hash_review": visual.get("capture_hash_review"),
            "verification": recorded_visual_verification,
            "evidence_basis": "SEPARATE_MANUAL_REVIEW_BOUND_TO_CAPTURE_AND_27_PNG_HASHES",
            "tracked": True,
            "ci_without_raw": "RECORDED_NOT_REVERIFIED",
        },
        "external_actions": "NOT_EXECUTED",
        "formal_ci": "NOT_CLAIMED_BY_LOCAL_ARTIFACT",
    }


def local_evidence_bundle_document(
    capture: Mapping[str, object],
    generated: Mapping[Path, bytes],
    validation: Mapping[str, object],
) -> dict[str, object]:
    artifact_rows = [
        {
            "path": path.as_posix(),
            "bytes": len(payload),
            "sha256": sha256(payload),
        }
        for path, payload in sorted(generated.items())
    ]
    test_contracts = validation.get("local_test_contracts")
    if not isinstance(test_contracts, dict):
        fail("RAOS_V2_PHASE2_TEST_CONTRACT_INVALID")
    gate_status = validation.get("status")
    gate_passed = gate_status == "PASSED_LOCAL_RECORDED"
    return {
        "schema": "RAOS_V2_LOCAL_EVIDENCE_BUNDLE_V1",
        "phase": "P2",
        "classification": (
            "PASSED_LOCAL_RECORDED_WITH_BROWSER_AND_MANUAL_VISUAL_EVIDENCE"
            if gate_passed
            else "GENERATED_LOCAL_PENDING_COMBINED_EVIDENCE_GATE"
        ),
        "gate_status": gate_status,
        "source_head": capture.get("repository", {}).get("head")
        if isinstance(capture.get("repository"), dict)
        else None,
        "source_inputs": _phase2_input_inventory(),
        "generated_artifacts": artifact_rows,
        "tests": {
            "status": test_contracts.get("status"),
            "ids": test_contracts.get("ids"),
            "owner": "tests/raos_v2",
            "required_command": "uv run --offline pytest -s -q tests/raos_v2",
            "generator_execution": "NOT_EXECUTED_BY_GENERATOR",
            "receipt": test_contracts.get("receipt"),
        },
        "visual_a11y_evidence": [
            validation.get("browser_evidence"),
            validation.get("visual_review_evidence"),
        ],
        "analytics_evidence": {
            "status": "UNAVAILABLE",
            "local_semantic_evidence": "TEST_OWNER_REQUIRED",
            "collector": "LOCAL_SINK_ONLY",
            "production_sender": "DISABLED",
            "note": "production KPI values remain UNAVAILABLE; synthetic QDS semantics are tested locally",
        },
        "security": {
            "credential_required": False,
            "default_network": "DENY",
            "public_internal_isolation": "PRESERVED",
            "publication_capability": False,
        },
        "external_actions": {
            "executed": [],
            "not_executed": [
                "publication",
                "deployment",
                "credential entry",
                "spend",
                "live provider write",
                "WordPress write",
                "production migration",
                "irreversible deletion",
            ],
        },
        "backlog_id": "B-V2-033",
        "test_ids": ["T-V2-023", "T-V2-039", "T-V2-051"],
    }


def phase2_report_document(
    capture: Mapping[str, object], evidence: Mapping[str, object]
) -> str:
    repository = capture.get("repository")
    head = repository.get("head") if isinstance(repository, dict) else "UNAVAILABLE"
    evidence_sha = sha256(canonical_json_bytes(evidence))
    test_receipt = evidence.get("tests")
    test_status = (
        test_receipt.get("status")
        if isinstance(test_receipt, dict)
        else "UNAVAILABLE"
    )
    local_gate_passed = evidence.get("gate_status") == "PASSED_LOCAL_RECORDED"
    backlog_label = (
        ", ".join(f"B-V2-{value:03d}" for value in range(19, 35))
        if local_gate_passed
        else (
            ", ".join(f"B-V2-{value:03d}" for value in range(19, 34))
            + "; B-V2-034 pending local test gate"
        )
    )
    browser_rows = evidence.get("visual_a11y_evidence")
    browser = (
        browser_rows[0]
        if isinstance(browser_rows, list)
        and browser_rows
        and isinstance(browser_rows[0], dict)
        else {}
    )
    browser_status = browser.get("classification", "UNAVAILABLE")
    browser_raw = browser.get("raw_verification", "UNAVAILABLE")
    visual = (
        browser_rows[1]
        if isinstance(browser_rows, list)
        and len(browser_rows) == 2
        and isinstance(browser_rows[1], dict)
        else {}
    )
    visual_verification = visual.get("verification")
    visual_status = visual.get("classification", "UNAVAILABLE")
    visual_raw = (
        visual_verification.get("raw_verification", "UNAVAILABLE")
        if isinstance(visual_verification, dict)
        else "UNAVAILABLE"
    )
    return f"""# RAOS V2 Phase 2 report

## Outcome

The offline carry-on vertical slice is implemented and measurable locally. It
contains recorded official-airline and Rakuten adapters, an exact-decimal
multi-segment checker, three-product identity/selection logic, seven future-route
reader surfaces plus home and one non-public DIFFERENCE fixture, local-only events,
and a disabled WordPress dry-run boundary.

## Exit evidence

- Phase: P2
- Source head: `{head}`
- Worktree before: `CLEAN` at the recorded dedicated-worktree baseline
- Worktree after: `LOCAL_IMPLEMENTATION_CHANGES_PRESENT` (not production state)
- Backlog status: {backlog_label}
- Local test receipt: `{test_status}` for T-V2-020..046 and T-V2-051; generator does not execute tests
- Browser/a11y recorded evidence: `{browser_status}`; raw verification: `{browser_raw}`; required CI must run its own gate
- Manual visual review: `{visual_status}` across 27 route/viewport captures; raw verification: `{visual_raw}`
- Evidence bundle SHA-256: `{evidence_sha}`
- Analytics: production values `UNAVAILABLE`; semantic QDS/local sink evidence only
- Planning ceiling: 80 hours; actual human time `UNAVAILABLE`; external spend: JPY 0
- Rollback: route/canonical/robots exact-tuple simulation `PASSED_LOCAL`; production backup/restore `NOT_EXECUTED`
- Exit gate: `{'PASS_LOCAL_RECORDED' if local_gate_passed else 'PENDING_LOCAL_TEST_GATE'}`

## Publication and migration boundary

The real comparison candidate stops at `EVIDENCE_COMPLETE`: human review is
`NOT_EXECUTED`, it has no seal, and no `PUBLISHED` transition exists. Only the
explicit synthetic contract fixture reaches `PACKAGE_SEALED`. The migration
manifest preserves `/carry-on-suitcase-comparison/` and is
`LOCAL_SIMULATION_ONLY`; public indexing, WordPress write and URL migration await
the separately approved Phase 3 boundary.

## Gaps and external actions

Formal/required CI is not relabelled by this local report. Publication,
deployment, credential entry, spend, provider/WordPress writes, production
migration, policy activation and irreversible deletion are all `NOT_EXECUTED`.
The raw browser receipt remains untracked under `output/playwright`; only its
digest metadata is recorded. Product price, stock, confirmed reward and every
production KPI remain `UNAVAILABLE` rather than zero.
"""


def integration_pr_body_document(evidence: Mapping[str, object]) -> str:
    evidence_sha = sha256(canonical_json_bytes(evidence))
    test_receipt = evidence.get("tests")
    test_status = (
        test_receipt.get("status")
        if isinstance(test_receipt, dict)
        else "UNAVAILABLE"
    )
    browser_rows = evidence.get("visual_a11y_evidence")
    browser_status = (
        browser_rows[0].get("classification", "UNAVAILABLE")
        if isinstance(browser_rows, list)
        and browser_rows
        and isinstance(browser_rows[0], dict)
        else "UNAVAILABLE"
    )
    visual_status = (
        browser_rows[1].get("classification", "UNAVAILABLE")
        if isinstance(browser_rows, list)
        and len(browser_rows) == 2
        and isinstance(browser_rows[1], dict)
        else "UNAVAILABLE"
    )
    return f"""# RAOS V2 Phase 0-2 offline vertical slice

## Design authority

- Successor package SHA-256: `{PACKAGE_SHA256}`
- Immutable source layer: `changes/raos-v2/source-package/2.0.0-design/**`
- The package prompt was excluded and never executed.
- Clarifications are recorded only in `changes/raos-v2/clarifications.v1.yaml`.

## Decision corrections

- `C-V2-002`: the machine contract has seven templates: HOME, HUB, GUIDE,
  COMPARISON, DIFFERENCE, TOOL and POLICY; source prose referring to six is
  superseded.
- `C-V2-003`: Phase 0 owns T-V2-001..006, T-V2-040 and T-V2-051;
  T-V2-007 starts in Phase 1.
- `C-V2-004`: the effective planning ceilings are P0=16h, P1=40h and P2=80h;
  backlog row estimates are reconciliation data, not additive gates.
- `C-V2-005` + `C-V2-010`: B-V2-009 closes over B-V2-001..008, and the
  corrected Phase 2 exit dependencies are closed before B-V2-034.
- `C-V2-007` + `C-V2-008`: real Phase 0-2 content remains unreviewed and
  unsealed; only synthetic fixtures may seal, and the disabled WordPress
  adapter belongs to Phase 2.

## Delivered

- Phase 0: clean dedicated-worktree baseline, public read-only URL inventory,
  metric/deprecation/rollback contracts and nine required artifacts.
- Phase 1: one carry-on wedge, 25-asset portfolio, seven templates, route/design
  contracts, ten entity schemas and disabled-by-default ports.
- Phase 2: recorded official sources/adapters, deterministic checker and product
  selection, local preview, content/review/media/event contracts, publication
  candidate, migration simulation and evidence bundle.

Evidence bundle SHA-256: `{evidence_sha}`. Recorded local test status is
`{test_status}`, browser/a11y evidence is `{browser_status}`, and independent
manual visual review is `{visual_status}`. The generator
does not execute either gate; required repository CI remains the merge gate and
is not claimed by this generated body.

## Safety and rollback

The public site and existing URL are unchanged. The real content package is
`EVIDENCE_COMPLETE`, not sealed or published. WordPress is
`DISABLED_DRY_RUN`, Rakuten is `RECORDED_ONLY`, analytics is `LOCAL_SINK_ONLY`,
and normal runtime/test network is denied. Route/canonical/robots rollback was
round-tripped locally against its captured hash binding.

## External/live actions

Publication, deployment, credentials, spending, live provider/WordPress writes,
production migration, policy activation and irreversible deletion:
`NOT_EXECUTED`.
"""


def phase1_report_document(*, evidence_gate_passed: bool) -> str:
    local_test = recorded_local_test_evidence()
    test_status = local_test.get("status")
    gate = (
        "PASSED_LOCAL_RECORDED"
        if test_status == "PASSED_LOCAL" and evidence_gate_passed
        else "PENDING_LOCAL_TEST_GATE"
    )
    return f"""# RAOS V2 Phase 1 report

The successor product specification fixes one wedge—旅の機内持ち込み条件と荷物選び—
and a locked 25-asset portfolio. The effective machine contract contains seven
templates: HOME, HUB, GUIDE, COMPARISON, DIFFERENCE, TOOL and POLICY.

The route graph, design tokens, component states, ten versioned entity schemas
and disabled-by-default port contracts are deterministic generated outputs. The
existing public comparison route is preserved; every new route remains a local
candidate or `PLANNED_LOCKED`, so Phase 1 changes no public URL.

Source facts, editorial judgement and UNKNOWN are separate. Product/variant facts
are separate from volatile offers. Recommendation inputs cannot include finance.
Real content cannot become human-reviewed or sealed in Phase 0-2; a disabled
WordPress dry-run receipt is not publication evidence.

Validation: T-V2-007..019 and T-V2-051 are `{gate}` (recorded test status:
`{test_status}`); the generator does not execute tests. Publication,
deployment, credentials, spend, live provider writes and production changes are
`NOT_EXECUTED`. Effective planning ceiling: 40 hours; spend ceiling: JPY 0.
"""


def documents() -> dict[Path, bytes]:
    capture = _capture_input()
    phase2_sources = validate_phase2_source_inputs()
    product = product_specification()
    routes = route_registry()
    pages_value = _read_json(
        Path("packages/web-ui/src/decision-support-v2/preview/pages.v2.json")
    )
    if not isinstance(pages_value, dict):
        fail("RAOS_V2_UI_PAGE_SOURCE_INVALID")
    validate_authoritative_ui_parity(pages_value)
    validate_cross_ledger_identity(product, routes, pages=pages_value)
    preview = preview_documents()
    sitemap_candidates = sitemap_candidates_document(pages_value, preview)
    migration = migration_manifest_document(capture, preview)
    claim_ledger = claim_ledger_document()
    publication = publication_candidate_document(migration, preview, claim_ledger)
    synthetic_seal = synthetic_seal_receipt_document()
    phase2_validation = phase2_validation_document(
        phase2_sources, preview, publication, migration
    )
    evidence_gate_passed = (
        phase2_validation.get("status") == "PASSED_LOCAL_RECORDED"
    )
    phase2_generated: dict[Path, bytes] = {
        **preview,
        Path("changes/raos-v2/phase-2/claims/claim-ledger.v2.yaml"): yaml_bytes(
            claim_ledger
        ),
        Path(
            "changes/raos-v2/phase-2/generated/migration-manifest.v2.yaml"
        ): yaml_bytes(migration),
        Path(
            "changes/raos-v2/phase-2/generated/publication-candidate.v2.json"
        ): canonical_json_bytes(publication),
        Path(
            "changes/raos-v2/phase-2/generated/synthetic-seal-receipt.v2.json"
        ): canonical_json_bytes(synthetic_seal),
        Path(
            "changes/raos-v2/phase-2/generated/sitemap-candidates.v2.yaml"
        ): yaml_bytes(sitemap_candidates),
        Path(
            "changes/raos-v2/phase-2/generated/phase-2-validation.v2.json"
        ): canonical_json_bytes(phase2_validation),
    }
    local_evidence = local_evidence_bundle_document(
        capture, phase2_generated, phase2_validation
    )
    schema_documents: dict[Path, object] = {
        Path("contracts/raos-v2/v1/source-record.schema.json"): source_record_schema(),
        Path("contracts/raos-v2/v1/claim.schema.json"): claim_schema(),
        Path("contracts/raos-v2/v1/product-model.schema.json"): product_model_schema(),
        Path(
            "contracts/raos-v2/v1/product-variant.schema.json"
        ): product_variant_schema(),
        Path(
            "contracts/raos-v2/v1/offer-observation.schema.json"
        ): offer_observation_schema(),
        Path(
            "contracts/raos-v2/v1/airline-rule-set.schema.json"
        ): airline_rule_set_schema(),
        Path(
            "contracts/raos-v2/v1/article-definition.schema.json"
        ): article_definition_schema(),
        Path(
            "contracts/raos-v2/v1/editorial-decision.schema.json"
        ): editorial_decision_schema(),
        Path(
            "contracts/raos-v2/v1/publication-package.schema.json"
        ): publication_package_schema(),
        Path(
            "contracts/raos-v2/v1/analytics-event.schema.json"
        ): analytics_event_schema(),
    }
    result: dict[Path, bytes] = {
        Path("changes/raos-v2/source-import.v1.json"): canonical_json_bytes(
            source_import_document(capture)
        ),
        Path("changes/raos-v2/clarifications.v1.yaml"): yaml_bytes(
            clarifications_document()
        ),
        Path("changes/raos-v2/phase-0/preflight-report.json"): canonical_json_bytes(
            preflight_document(capture)
        ),
        Path("changes/raos-v2/phase-0/source-audit-report.json"): canonical_json_bytes(
            source_audit_document()
        ),
        Path("changes/raos-v2/phase-0/public-url-inventory.yaml"): yaml_bytes(
            public_url_inventory(capture)
        ),
        Path(
            "changes/raos-v2/phase-0/production-observation-plan.md"
        ): OBSERVATION_PLAN.encode("utf-8"),
        Path("changes/raos-v2/phase-0/metric-dictionary.yaml"): yaml_bytes(
            metric_dictionary()
        ),
        Path("changes/raos-v2/phase-0/deprecation-ledger.yaml"): yaml_bytes(
            deprecation_ledger()
        ),
        Path("changes/raos-v2/phase-0/pilot-reconciliation.yaml"): yaml_bytes(
            pilot_reconciliation(capture)
        ),
        Path("changes/raos-v2/phase-0/rollback-contract.yaml"): yaml_bytes(
            rollback_contract()
        ),
        # B-V2-009 intentionally follows every B-V2-001..008 output above.
        Path("changes/raos-v2/phase-0/phase-0-report.md"): PHASE0_REPORT.encode(
            "utf-8"
        ),
        Path("changes/raos-v2/product-spec.v2.yaml"): yaml_bytes(product),
        Path("changes/raos-v2/route-registry.v2.yaml"): yaml_bytes(routes),
        Path("changes/raos-v2/design/design-tokens.v2.json"): canonical_json_bytes(
            design_tokens()
        ),
        Path("changes/raos-v2/design/component-states.yaml"): yaml_bytes(
            component_states()
        ),
        Path(
            "changes/raos-v2/generated/decision-traceability.effective.v1.yaml"
        ): yaml_bytes(
            effective_traceability(evidence_gate_passed=evidence_gate_passed)
        ),
        Path(
            "changes/raos-v2/generated/phase-1-validation.v1.json"
        ): canonical_json_bytes(
            phase1_validation_document(product, routes, schema_documents)
        ),
        Path("changes/raos-v2/phase-1-report.md"): phase1_report_document(
            evidence_gate_passed=evidence_gate_passed
        ).encode("utf-8"),
        Path("contracts/raos-v2/v1/ports.v1.yaml"): yaml_bytes(ports_contract()),
        Path(
            "changes/raos-v2/phase-2/generated/local-evidence-bundle.v2.json"
        ): canonical_json_bytes(local_evidence),
        Path("changes/raos-v2/phase-2/phase-2-report.md"): phase2_report_document(
            capture, local_evidence
        ).encode("utf-8"),
        Path(
            "changes/raos-v2/phase-2/integration-pr-body.md"
        ): integration_pr_body_document(local_evidence).encode("utf-8"),
    }
    result.update(
        {
            path: canonical_json_bytes(document)
            for path, document in schema_documents.items()
        }
    )
    result.update(phase2_generated)
    if set(result) != set(OUTPUT_PATHS):
        fail("RAOS_V2_OUTPUT_INVENTORY_MISMATCH")
    return result


def write_generated_output(relative: Path, payload: bytes) -> None:
    """Write an allowlisted output without following target or ancestor links."""

    if (
        relative not in OUTPUT_PATHS
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        fail("RAOS_V2_OUTPUT_PATH_NOT_ALLOWLISTED")
    repository = ROOT.resolve()
    current = ROOT
    for part in relative.parts[:-1]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            fail("RAOS_V2_OUTPUT_ANCESTOR_INVALID")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            fail("RAOS_V2_OUTPUT_ANCESTOR_INVALID")
    target = ROOT / relative
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError:
        fail("RAOS_V2_OUTPUT_TARGET_INVALID")
    if metadata is not None and (
        stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
    ):
        fail("RAOS_V2_OUTPUT_TARGET_INVALID")
    resolved_parent = target.parent.resolve()
    if resolved_parent != repository and repository not in resolved_parent.parents:
        fail("RAOS_V2_OUTPUT_PATH_ESCAPE")
    atomic_write(relative, payload, root=ROOT)


def generate(*, check: bool) -> None:
    expected = documents()
    drift: list[str] = []
    for path in OUTPUT_PATHS:
        payload = expected[path]
        target = ROOT / path
        if check:
            try:
                actual = target.read_bytes()
            except OSError:
                drift.append(path.as_posix())
                continue
            if actual != payload:
                drift.append(path.as_posix())
        else:
            write_generated_output(path, payload)
    if drift:
        print("RAOS_V2_SUCCESSOR_DRIFT " + " ".join(drift), file=sys.stderr)
        raise SystemExit(1)


def generate_preview_only() -> None:
    """Refresh unverified local preview bytes before browser evidence capture."""

    validate_phase2_source_inputs()
    preview = preview_documents()
    expected_preview_paths = {
        path for path in OUTPUT_PATHS if "phase-2/preview" in path.as_posix()
    }
    if set(preview) != expected_preview_paths:
        fail("RAOS_V2_PREVIEW_OUTPUT_INVENTORY_MISMATCH")
    for path, payload in preview.items():
        write_generated_output(path, payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="refresh deterministic unverified preview before a browser evidence run",
    )
    arguments = parser.parse_args(argv)
    if arguments.check and arguments.preview_only:
        parser.error("--check and --preview-only are mutually exclusive")
    try:
        if arguments.preview_only:
            generate_preview_only()
        else:
            generate(check=arguments.check)
    except BuildFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        (
            "RAOS_V2_SUCCESSOR_CHECK_OK"
            if arguments.check
            else "RAOS_V2_PREVIEW_REFRESHED_UNVERIFIED"
            if arguments.preview_only
            else "RAOS_V2_SUCCESSOR_GENERATED"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
