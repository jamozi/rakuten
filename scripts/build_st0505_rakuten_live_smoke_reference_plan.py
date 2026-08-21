#!/usr/bin/env python3
"""Build the explicit-but-disabled-by-default ST-0505 live-smoke plan."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st1505_staging_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-0505/contracts/rakuten-live-smoke-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0505/generated/rakuten-live-smoke-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0505/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0505_rakuten_live_smoke_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0505/README.md")
DESIGN_HANDOFF_PATH: Final = Path("changes/st-0505/DESIGN_HANDOFF_V1.yaml")
TEST_PATHS: Final = (
    Path("tests/st0505/conftest.py"),
    Path("tests/st0505/test_contract.py"),
    Path("tests/st0505/test_generation.py"),
    Path("tests/st0505/test_negative_cases.py"),
    Path("tests/st0505/test_rakuten_live_smoke_installed_runtime.py"),
    Path("tests/st0505/test_rakuten_live_smoke_runtime.py"),
    Path("tests/st0505/test_rakuten_owner_local_core.py"),
    Path("tests/st0505/test_rakuten_owner_local_adapter.py"),
    Path("tests/st0505/test_rakuten_owner_local_installed_runtime.py"),
)
RUNTIME_PATHS: Final = (
    Path("python/raos/__init__.py"),
    Path("python/raos/domain/catalog/rakuten_live_smoke.py"),
    Path("python/raos/application/catalog/rakuten_live_smoke.py"),
    Path("python/raos/ports/rakuten_live_smoke.py"),
    Path("python/raos/adapters/rakuten_live_smoke.py"),
    Path("scripts/install_rakuten_live_smoke_runtime.py"),
    Path("scripts/rakuten_live_smoke_runtime_install.sh"),
    Path("scripts/rakuten_live_smoke.py"),
    Path("scripts/rakuten_live_smoke_launcher.sh"),
    Path("python/raos/domain/catalog/rakuten_owner_local.py"),
    Path("python/raos/application/catalog/rakuten_owner_local.py"),
    Path("python/raos/ports/rakuten_owner_local.py"),
    Path("python/raos/adapters/rakuten_owner_local.py"),
    Path("scripts/install_rakuten_owner_local_runtime.py"),
    Path("scripts/rakuten_owner_local_runtime_install.sh"),
    Path("scripts/rakuten_owner_local.py"),
    Path("scripts/rakuten_owner_local_launcher.sh"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    DESIGN_HANDOFF_PATH,
    README_PATH,
    GENERATOR_PATH,
    *RUNTIME_PATHS,
    *TEST_PATHS,
)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "python3 scripts/build_st0505_rakuten_live_smoke_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9e8a89c0faac140af6a0bdee7eceb68a90ccd885f3d9ea318372187560528aff"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
EXPECTED_INSTALLED_BUNDLE_SHA256: Final = (
    "94c256d8832167c6df89327fc2840bc6db6fc82af4c912286b95ee6e8084148d"
)
EXPECTED_INSTALLED_LAUNCHER_SHA256: Final = (
    "9deabbf7dff82e43b87a793a27b0c7f0d7371e97559755484f0c5cba9ddeabed"
)
EXPECTED_RUNTIME_INSTALLER_SHA256: Final = (
    "e59ba05bfd97b56e9a59b1ceac9ee54a16ef461af43ae5f01ace5322319bf3da"
)
EXPECTED_RUNTIME_INSTALL_STAGE_SHA256: Final = (
    "9effd085052570cf943f311b012c6dcf7ac26c2514182513c1f52d33ca88d549"
)
EXPECTED_OWNER_LOCAL_BUNDLE_SHA256: Final = (
    "af69bc9b7153d14ea00739b9479001dca20652844b105f75fc88a3187ac372b8"
)
EXPECTED_OWNER_LOCAL_LAUNCHER_SHA256: Final = (
    "27aa51a680eac393c304da443a82b6930a956c21913a53827ccf6584a2c1c47d"
)
EXPECTED_OWNER_LOCAL_INSTALLER_SHA256: Final = (
    "90d40c86af676cc0d2c959ca5aaa1615cc95a52102b64d54332c507599e84931"
)
EXPECTED_OWNER_LOCAL_INSTALL_STAGE_SHA256: Final = (
    "18af67a14afc33a014733d1d7e79e1bc8a217b57c93b0c3411f38e54c8c4c8d5"
)
OWNER_LOCAL_CREDENTIAL_REFLECTION_METHOD_AST_SHA256: Final = (
    "129f7f01fb5bafc13ddd54d39bacdc0d28975478ebff8a84bf1b57c37f90c0e5"
)
EXPECTED_OWNER_LOCAL_RESULT_OBJECT_KEYS: Final = (
    "schema",
    "version",
    "run_id",
    "started_at",
    "finished_at",
    "api",
    "endpoint_id",
    "api_version",
    "outcome",
    "diagnostic_code",
    "request_fingerprint",
    "request_disposition",
    "request_count",
    "retry_count",
    "pagination_count",
    "http_status",
    "body_byte_count",
    "response_sha256",
    "count",
    "page",
    "first",
    "last",
    "hits",
    "pageCount",
    "items",
    "products",
    "provider_data_classification",
    "evidence_authority",
    "formal_tst_016",
    "staging",
    "production",
    "od_015",
)
INSTALLED_LAUNCHER_PATH: Final = (
    "/home/minami/.local/share/raos/rakuten-live-smoke/runtime/"
    f"{EXPECTED_INSTALLED_BUNDLE_SHA256}/bin/rakuten-live-smoke"
)
OWNER_LOCAL_INSTALLED_LAUNCHER_PATH: Final = (
    "/home/minami/.local/share/raos/rakuten-owner-local/runtime/"
    f"{EXPECTED_OWNER_LOCAL_BUNDLE_SHA256}/bin/rakuten-owner-local"
)
REVIEWED_RUNTIME_INSTALL_STAGE: Final = (
    "/home/minami/rakuten/scripts/rakuten_live_smoke_runtime_install.sh"
)
OWNER_LOCAL_REVIEWED_RUNTIME_INSTALL_STAGE: Final = (
    "/home/minami/rakuten/scripts/rakuten_owner_local_runtime_install.sh"
)
INSTALLED_PAYLOADS: Final = (
    (Path("scripts/rakuten_live_smoke_launcher.sh"), "bin/rakuten-live-smoke", 0o500),
    (Path("scripts/rakuten_live_smoke.py"), "scripts/rakuten_live_smoke.py", 0o400),
    (Path("python/raos/__init__.py"), "python/raos/__init__.py", 0o400),
    (
        Path("python/raos/domain/catalog/rakuten_item_search.py"),
        "python/raos/domain/catalog/rakuten_item_search.py",
        0o400,
    ),
    (
        Path("python/raos/domain/catalog/rakuten_item_search_live_request_v1.py"),
        "python/raos/domain/catalog/rakuten_item_search_live_request_v1.py",
        0o400,
    ),
    (
        Path("python/raos/domain/catalog/rakuten_live_smoke.py"),
        "python/raos/domain/catalog/rakuten_live_smoke.py",
        0o400,
    ),
    (
        Path("python/raos/application/catalog/rakuten_live_smoke.py"),
        "python/raos/application/catalog/rakuten_live_smoke.py",
        0o400,
    ),
    (
        Path("python/raos/ports/rakuten_live_smoke.py"),
        "python/raos/ports/rakuten_live_smoke.py",
        0o400,
    ),
    (
        Path("python/raos/adapters/rakuten_live_smoke.py"),
        "python/raos/adapters/rakuten_live_smoke.py",
        0o400,
    ),
)
OWNER_LOCAL_INSTALLED_PAYLOADS: Final = (
    (Path("scripts/rakuten_owner_local_launcher.sh"), "bin/rakuten-owner-local", 0o500),
    (Path("scripts/rakuten_owner_local.py"), "scripts/rakuten_owner_local.py", 0o400),
    (Path("python/raos/__init__.py"), "python/raos/__init__.py", 0o400),
    (
        Path("python/raos/domain/catalog/rakuten_item_search.py"),
        "python/raos/domain/catalog/rakuten_item_search.py",
        0o400,
    ),
    (
        Path("python/raos/domain/catalog/rakuten_item_search_live_request_v1.py"),
        "python/raos/domain/catalog/rakuten_item_search_live_request_v1.py",
        0o400,
    ),
    (
        Path("python/raos/domain/catalog/rakuten_owner_local.py"),
        "python/raos/domain/catalog/rakuten_owner_local.py",
        0o400,
    ),
    (
        Path("python/raos/application/catalog/rakuten_owner_local.py"),
        "python/raos/application/catalog/rakuten_owner_local.py",
        0o400,
    ),
    (
        Path("python/raos/ports/rakuten_owner_local.py"),
        "python/raos/ports/rakuten_owner_local.py",
        0o400,
    ),
    (
        Path("python/raos/adapters/rakuten_owner_local.py"),
        "python/raos/adapters/rakuten_owner_local.py",
        0o400,
    ),
)


def _authoritative_runtime_install_command() -> str:
    return (
        "/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 "
        "TZ=UTC /usr/bin/busybox sh -c 'umask 077; "
        f"p={REVIEWED_RUNTIME_INSTALL_STAGE}; "
        'exec 4<"$p" || { /usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; "
        "u=$(/usr/bin/busybox id -u 2>/dev/null) || { "
        '/usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; "
        'case "$u" in ""|*[!0-9]*) /usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2;; esac; "
        'fm=$(/usr/bin/busybox stat -Lc "%d %i %f %u %a %h %s" '
        "/proc/self/fd/4 2>/dev/null) || { "
        '/usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; "
        'nm=$(/usr/bin/busybox stat -c "%d %i %f %u %a %h %s" -- '
        '"$p" 2>/dev/null) || { /usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; "
        '[ "$fm" = "$nm" ] || { /usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; "
        'set -- $fm; [ "$#" -eq 7 ] || { '
        '/usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; "
        'case "$1:$2:$3:$4:$5:$6:$7" in *[!0-9a-f:]*) '
        '/usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2;; esac; "
        "v=$((0x$3)); [ $((v & 0xf000)) -eq 32768 ] "
        '&& [ "$4" -eq "$u" ] && [ $((v & 18)) -eq 0 ] '
        '&& [ "$6" -eq 1 ] && [ "$7" -ge 1 ] && [ "$7" -le 2097152 ] '
        '|| { /usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; "
        "h=$(/usr/bin/busybox sha256sum /proc/self/fd/4 2>/dev/null) || { "
        '/usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; "
        f'[ "$h" = "{EXPECTED_RUNTIME_INSTALL_STAGE_SHA256}  '
        '/proc/self/fd/4" ] || { /usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED; exit 2; }; "
        "exec /usr/bin/busybox sh /proc/self/fd/4'"
    )


def _authoritative_installed_command(command: str) -> str:
    if command not in {"doctor", "run"}:
        raise ValueError("closed installed command")
    failure = (
        "RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY"
        if command == "doctor"
        else "RAKUTEN_LIVE_SMOKE_FAIL"
    )
    return (
        "/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 "
        "TZ=UTC /usr/bin/busybox sh -c 'umask 077; "
        f"p={INSTALLED_LAUNCHER_PATH}; "
        'exec 4<"$p" || { '
        f'/usr/bin/busybox printf "%s\\n" {failure}; exit 2; '
        "}; "
        "h=$(/usr/bin/busybox sha256sum /proc/self/fd/4 2>/dev/null) || { "
        f'/usr/bin/busybox printf "%s\\n" {failure}; exit 2; '
        "}; "
        f'[ "$h" = "{EXPECTED_INSTALLED_LAUNCHER_SHA256}  '
        '/proc/self/fd/4" ] || { '
        f'/usr/bin/busybox printf "%s\\n" {failure}; exit 2; '
        "}; "
        f'exec "$p" {command}\''
    )


def _owner_local_authoritative_runtime_install_command() -> str:
    return (
        _authoritative_runtime_install_command()
        .replace(
            REVIEWED_RUNTIME_INSTALL_STAGE,
            OWNER_LOCAL_REVIEWED_RUNTIME_INSTALL_STAGE,
        )
        .replace(
            EXPECTED_RUNTIME_INSTALL_STAGE_SHA256,
            EXPECTED_OWNER_LOCAL_INSTALL_STAGE_SHA256,
        )
        .replace(
            "RAKUTEN_LIVE_SMOKE_RUNTIME_INSTALL_FAILED",
            "RAKUTEN_OWNER_LOCAL_RUNTIME_INSTALL_FAILED",
        )
    )


def _owner_local_authoritative_installed_command(arguments: tuple[str, ...]) -> str:
    allowed = {
        ("setup",),
        ("rotate",),
        ("doctor",),
        ("list-apis",),
        ("smoke", "--api", "item-search"),
        ("smoke", "--api", "product-search"),
    }
    if arguments not in allowed:
        raise ValueError("closed owner-local installed command")
    old_command = "doctor" if arguments == ("doctor",) else "run"
    command = _authoritative_installed_command(old_command)
    command = command.replace(
        INSTALLED_LAUNCHER_PATH, OWNER_LOCAL_INSTALLED_LAUNCHER_PATH
    )
    command = command.replace(
        EXPECTED_INSTALLED_LAUNCHER_SHA256,
        EXPECTED_OWNER_LOCAL_LAUNCHER_SHA256,
    )
    command = command.replace(
        "RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY",
        "RAKUTEN_OWNER_LOCAL_DOCTOR_NOT_READY",
    ).replace("RAKUTEN_LIVE_SMOKE_FAIL", "RAKUTEN_OWNER_LOCAL_FAIL")
    rendered_arguments = " ".join(arguments)
    return command.replace(
        f'exec "$p" {old_command}\'',
        f'exec "$p" {rendered_arguments}\'',
    )


def _owner_local_authoritative_request_argv_template() -> list[str]:
    command = _owner_local_authoritative_installed_command(("list-apis",))
    prefix = (
        "/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 "
        "TZ=UTC /usr/bin/busybox sh -c '"
    )
    if not command.startswith(prefix) or not command.endswith("'"):
        raise ValueError("owner-local installed gate shape")
    script = command[len(prefix) : -1]
    fixed_dispatch = 'exec "$p" list-apis'
    positional_dispatch = (
        '[ "$#" -eq 2 ] || { /usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_OWNER_LOCAL_FAIL; exit 2; }; "
        'case "$1" in item-search|product-search) ;; *) '
        '/usr/bin/busybox printf "%s\\n" RAKUTEN_OWNER_LOCAL_FAIL; exit 2;; esac; '
        'case "$2" in /*) ;; *) /usr/bin/busybox printf "%s\\n" '
        "RAKUTEN_OWNER_LOCAL_FAIL; exit 2;; esac; "
        'exec "$p" request --api "$1" --request-file "$2"'
    )
    if script.count(fixed_dispatch) != 1:
        raise ValueError("owner-local installed dispatch shape")
    script = script.replace(fixed_dispatch, positional_dispatch)
    return [
        "/usr/bin/busybox",
        "env",
        "-i",
        "PATH=/usr/bin:/bin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "TZ=UTC",
        "/usr/bin/busybox",
        "sh",
        "-c",
        script,
        "rakuten-owner-local-request",
        "<item-search|product-search>",
        "<absolute-json>",
    ]


def _owner_local_reference_binding(value: object) -> dict[str, object]:
    owner = dict(_mapping(value, "owner_local_read_integration"))
    owner["authoritative_fixed_commands"] = {
        "runtime_install": _owner_local_authoritative_runtime_install_command(),
        "setup": _owner_local_authoritative_installed_command(("setup",)),
        "rotate": _owner_local_authoritative_installed_command(("rotate",)),
        "doctor": _owner_local_authoritative_installed_command(("doctor",)),
        "list_apis": _owner_local_authoritative_installed_command(("list-apis",)),
        "smoke_item_search": _owner_local_authoritative_installed_command(
            ("smoke", "--api", "item-search")
        ),
        "smoke_product_search": _owner_local_authoritative_installed_command(
            ("smoke", "--api", "product-search")
        ),
    }
    owner["authoritative_request_gate"] = {
        "launcher_path": OWNER_LOCAL_INSTALLED_LAUNCHER_PATH,
        "launcher_sha256": EXPECTED_OWNER_LOCAL_LAUNCHER_SHA256,
        "authentication": "STATIC_BUSYBOX_FD4_SHA256_BEFORE_LAUNCHER_BODY",
        "argument_contract": (
            "request --api <item-search|product-search> --request-file <absolute-json>"
        ),
        "shell_interpolation": "FORBIDDEN_USE_POSITIONAL_ARGUMENTS",
    }
    owner["authoritative_request_template"] = {
        "argv": _owner_local_authoritative_request_argv_template(),
        "api_argv_index": 12,
        "request_file_argv_index": 13,
        "rendering": "REPLACE_EXACT_TWO_ARRAY_ELEMENTS_THEN_DIRECT_EXECVE_NO_EVAL",
        "unrendered_or_extra_arguments": "FAIL_CLOSED",
    }
    return owner


INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
TEST_ACCEPTANCE_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md"
)
TEST_ENVIRONMENT_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_environment_matrix_v1.0.yaml"
)
STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")

EXPECTED_SOURCES: Final = (
    (
        "integration",
        INTEGRATION_PATH.as_posix(),
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "open_decisions",
        OPEN_DECISIONS_PATH.as_posix(),
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "test_catalog",
        TEST_CATALOG_PATH.as_posix(),
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "test_acceptance",
        TEST_ACCEPTANCE_PATH.as_posix(),
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac",
    ),
    (
        "test_environment",
        TEST_ENVIRONMENT_PATH.as_posix(),
        "3dc59c8c951a39d2079eb82e6a3e5adde3ce1910296abf8e1a3a539107a96b68",
    ),
    (
        "story",
        STORY_PATH.as_posix(),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
)
PREDECESSOR_COMMIT: Final = "3b63ea8b35b25f1c38c53a7fb5e8c0b596ddd0ab"
EXPECTED_PREDECESSOR_ARTIFACTS: Final = (
    (
        Path("changes/st-0502/README.md"),
        "d242024ecb824c36fe45d63709a34af7138f6101deb5c36782f78f8836c7b731",
    ),
    (
        Path("python/raos/domain/catalog/rakuten_item_search.py"),
        "4ea7f33ecee122f7e1e57590c2a972ffe7fb9aa493575a547e3354d0f01570c2",
    ),
    (
        Path("python/raos/ports/rakuten_item_search.py"),
        "63983941eeb4a485a3d169073f44c0e4241bdcad452d124cfce1dd07cf2d29fe",
    ),
    (
        Path("python/raos/application/catalog/rakuten_item_search.py"),
        "454c46f66ad473a81395bc08330e7b62635e78c0d1763424227d2f7ebd84688c",
    ),
    (
        Path("python/raos/adapters/recorded_rakuten_item_search.py"),
        "ffdde9dda64800369ac1d90357a6b9300ff104447547bf8c4bb9bf28e89e7dd7",
    ),
    (
        Path("tests/st0502/conftest.py"),
        "31285176cd193385818f830c15b3a520195f8e5fe819e541fd916aad6bf66718",
    ),
    (
        Path("tests/st0502/test_boundaries.py"),
        "d67b995da35bf31b5fb576ca291a9c16e34ccfa4a672377b83121b576ef8eb78",
    ),
    (
        Path("tests/st0502/test_failure_isolation.py"),
        "964139bc7e81e41d2dab066599cfa434ee186c465f417e51db97c930f0ea5d52",
    ),
    (
        Path("tests/st0502/test_rakuten_item_search.py"),
        "5d6d8767ea11124dc378cc52f18006fbb4eb9cdba3fbfe4bb7d06526ebddd42a",
    ),
    (
        Path("python/raos/domain/catalog/rakuten_item_search_live_request_v1.py"),
        "acd53bc3b12925e09859833ed9fc817e52a14872ae946336cc3dd039e990849e",
    ),
    (
        Path("tests/st0502/test_rakuten_item_search_live_request_v1.py"),
        "710ee36b2cc88d2f14c5a3e726b2fe50d1bd9fbc2bdd9bdb1a05c099bbf4c696",
    ),
)

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "predecessor",
    "open_decision",
    "live_smoke_definition",
    "owner_local_read_integration",
    "observation_defaults",
    "rate_quota_cost_defaults",
    "execution_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_binding",
    "open_decision",
    "test_suite",
    "live_smoke_definition",
    "owner_local_read_integration",
    "observation_boundary",
    "rate_quota_cost_boundary",
    "execution_boundary",
    "verification_boundary",
)
ACTION_COUNT_KEYS: Final = (
    "live_call",
    "network",
    "credential_read",
    "retry",
    "paginate",
    "create",
    "update",
    "delete",
    "store",
    "persist",
    "external",
)
LIVE_POLICY_ALLOWED_IMPORTS: Final = frozenset(
    {
        "__future__",
        "dataclasses",
        "enum",
        "hashlib",
        "json",
        "raos",
        "typing",
    }
)
LIVE_POLICY_ALLOWED_IMPORT_BINDINGS: Final[
    frozenset[tuple[str, str, str, str | None, int]]
] = frozenset(
    {
        ("from", "__future__", "annotations", None, 0),
        ("from", "dataclasses", "dataclass", None, 0),
        ("from", "enum", "Enum", None, 0),
        ("import", "", "hashlib", None, 0),
        ("import", "", "json", None, 0),
        ("from", "typing", "NoReturn", None, 0),
        ("from", "typing", "SupportsIndex", None, 0),
        (
            "from",
            "raos.domain.catalog.rakuten_item_search",
            "fail_item_search",
            None,
            0,
        ),
    }
)
LIVE_POLICY_ALLOWED_NAME_CALLS: Final = frozenset(
    {
        "TypeError",
        "_bounded_text",
        "_exact_int",
        "any",
        "dataclass",
        "dict",
        "fail_item_search",
        "len",
        "ord",
        "sorted",
        "tuple",
        "type",
    }
)
LIVE_POLICY_ALLOWED_ATTRIBUTE_CALLS: Final = frozenset(
    {
        "dumps",
        "encode",
        "hexdigest",
        "items",
        "partition",
        "sha256",
        "strip",
        "update",
    }
)
LIVE_POLICY_EXPECTED_TOP_LEVEL_FUNCTIONS: Final = frozenset(
    {"_bounded_text", "_exact_int"}
)
LIVE_POLICY_EXPECTED_CLASS_METHODS: Final[Mapping[str, frozenset[str]]] = {
    "LiveItemSearchSortV1": frozenset(),
    "LiveItemSearchElementV1": frozenset(),
    "ProviderTextTrustV1": frozenset(),
    "_RedactedValue": frozenset({"__reduce_ex__", "__repr__", "__str__"}),
    "RakutenItemSearchLiveRequestV1": frozenset(
        {
            "__post_init__",
            "canonical_json",
            "canonical_parameters",
            "fingerprint",
            "pagination_followup_limit",
            "provider_derived_recommendation_inputs",
            "provider_text_trust",
            "retry_limit",
        }
    ),
}
LIVE_POLICY_EXPECTED_DEFINITION_AST_SHA256: Final[Mapping[str, str]] = {
    "_bounded_text": (
        "2bfc582b76f363ce8ff4714ca2d95466fd49a6b6ff262b65b3fb0c738aa66a0e"
    ),
    "_exact_int": ("5bc0641d1a1a36488cc7bef4b27e3a84af68f42f69bfe7739b4c697c46b9d104"),
    "_RedactedValue.__repr__": (
        "42234706298cad84560a330232331303f10bca79d121b21047b8527c013342fe"
    ),
    "_RedactedValue.__str__": (
        "e83938cb60d4af60cce2aa0e50cd7c8c467446c90dfc03096f6b70dd8f351b5a"
    ),
    "_RedactedValue.__reduce_ex__": (
        "ab186dc206a94c78126c33f97a540e5d05b07661f3b6210ed8995ba6ac6a929f"
    ),
    "RakutenItemSearchLiveRequestV1.__post_init__": (
        "73ad229594810c26c3ec528b4763f3e1e380ecf48e974f446e84a794847858cc"
    ),
    "RakutenItemSearchLiveRequestV1.canonical_parameters": (
        "2280325aa2398f58b2b2aba39f35db9572e4cef2b1672c1ecbf945200f086a8f"
    ),
    "RakutenItemSearchLiveRequestV1.canonical_json": (
        "fdd0e5ed07d41d0cf3ac31058c9bfe7e71b4fec41cb102caf9c05238a124d853"
    ),
    "RakutenItemSearchLiveRequestV1.fingerprint": (
        "8b47f804f96e82d6ce401addeb12d1ad67dd2e7f0fb767777e48dd56815a229d"
    ),
    "RakutenItemSearchLiveRequestV1.retry_limit": (
        "d076b89c1eb6963ffb44acd1368485899aa98b7d50e6aaad5ac8d11ac6559e8c"
    ),
    "RakutenItemSearchLiveRequestV1.pagination_followup_limit": (
        "169ee0a7d161698acdcde71b55c20370a9e59cd2347d92ba0db3693e4991bd74"
    ),
    "RakutenItemSearchLiveRequestV1.provider_text_trust": (
        "6174281582ea9147c68f877d4750c0f78fc65c99b2738bdd8f4850742cc2b71e"
    ),
    "RakutenItemSearchLiveRequestV1.provider_derived_recommendation_inputs": (
        "a7d21ee1bf2ad262ebbf723c3f6a4988ad18108225299830cd0a7325ceb5f590"
    ),
}
LIVE_POLICY_EXPECTED_MODULE_AST_SHA256: Final = (
    "b24db041cee99db89a1c951973f0a9fe6a5c3ae7e88729fef6ca21d95b04afcb"
)
LIVE_POLICY_FORBIDDEN_IMPORTS: Final = frozenset(
    {
        "builtins",
        "boto3",
        "botocore",
        "http",
        "httpx",
        "importlib",
        "os",
        "pathlib",
        "requests",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "sys",
        "urllib",
    }
)
LIVE_POLICY_FORBIDDEN_CALLS: Final = frozenset(
    {
        "commit",
        "execute",
        "getenv",
        "open",
        "persist",
        "publish",
        "request",
        "save",
        "send",
        "store",
        "unlink",
        "upload",
        "urlopen",
        "write",
    }
)
LIVE_POLICY_FORBIDDEN_DYNAMIC_REFERENCES: Final = frozenset(
    {
        "__builtins__",
        "__dict__",
        "__getattribute__",
        "__globals__",
        "__import__",
        "__mro__",
        "__subclasses__",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "hasattr",
        "import_module",
        "locals",
        "modules",
        "setattr",
        "vars",
    }
)
LIVE_POLICY_FORBIDDEN_IDENTIFIER_PARTS: Final = (
    "affiliate_rate",
    "credential",
    "endpoint",
    "http",
    "network",
    "persistence",
    "review_average",
    "review_count",
    "secret",
    "storage",
)


class RakutenLiveSmokeReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise RakutenLiveSmokeReferenceError(f"ST-0505 build failed: {code} field={field}")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


def _same_exact(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if type(right) is dict:
        left_map = cast(dict[str, object], left)
        right_map = cast(dict[str, object], right)
        return tuple(left_map) == tuple(right_map) and all(
            _same_exact(left_map[key], right_map[key]) for key in right_map
        )
    if type(right) is list:
        left_list = cast(list[object], left)
        right_list = cast(list[object], right)
        return len(left_list) == len(right_list) and all(
            _same_exact(a, b) for a, b in zip(left_list, right_list, strict=True)
        )
    return left == right


def _exact(value: object, expected: object, field: str) -> None:
    if not _same_exact(value, expected):
        _fail("VALUE_MISMATCH", field)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _ast_sha256(node: ast.AST) -> str:
    material = ast.dump(
        node,
        annotate_fields=True,
        include_attributes=False,
    ).encode("utf-8")
    return _sha256(material)


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        content = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(item, field)
        for item in _list(items, field)
        if type(item) is dict and item.get("id") == identity
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _expected_source_rows() -> list[dict[str, str]]:
    return [
        {"role": role, "uri": f"repo://{path}", "sha256": digest}
        for role, path, digest in EXPECTED_SOURCES
    ]


def _expected_predecessor_artifacts() -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path.as_posix()}", "sha256": digest}
        for path, digest in EXPECTED_PREDECESSOR_ARTIFACTS
    ]


def _validate_hashes(root: Path) -> None:
    for _role, source_path, digest in EXPECTED_SOURCES:
        if _sha256(_read(root, Path(source_path), "authority.source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "authority.source")
    for predecessor_path, digest in EXPECTED_PREDECESSOR_ARTIFACTS:
        if _sha256(_read(root, predecessor_path, "predecessor.artifact")) != digest:
            _fail("PREDECESSOR_HASH_DRIFT", "predecessor.artifact")
    if _sha256(_read(root, HELPER_PATH, "implementation.helper")) != HELPER_SHA256:
        _fail("IMPLEMENTATION_HELPER_DRIFT", "implementation.helper")


EXPECTED_STORY: Final = {
    "id": "ST-0505",
    "epic_id": "EPIC-05",
    "title": "Rakuten live bounded smoke",
    "objective": "実Credentialで低影響検証",
    "depends_on": ["ST-0502"],
    "requirement_ids": ["FR-002"],
    "design_refs": [],
    "deliverables": ["live smoke report"],
    "acceptance_criteria": ["auth/schema/rate observed"],
    "test_suites": ["TST-016"],
    "priority": "P0",
    "mvp": True,
    "size": "S",
    "open_decisions": ["OD-015"],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_OPEN_DECISION_ROW: Final = {
    "id": "OD-015",
    "topic": "production_provider_credentials",
    "status": "EXTERNAL_EVIDENCE_REQUIRED",
    "required_by": "Live adapter test",
    "owner": "Operations Owner",
    "decision_needed": "楽天、OpenAI、Google、AWSの専用Account/権限/Secretを設定",
    "default_behavior": "Recorded fixtureのみ",
    "blocking": True,
}
EXPECTED_TEST_SUITE: Final = {
    "id": "TST-016",
    "name": "Rakuten adapter live smoke",
    "layer": "adapter",
    "purpose": "公式Sandbox/低影響Liveでauth/rate/schema",
    "candidate_tools": ["live credential"],
    "release_blocking": True,
    "environments": ["staging"],
    "owner": "Operations",
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "execution_status": "NOT_EXECUTED",
}


def _validate_authority_semantics(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "story")
    _exact(_find(stories.get("stories"), "ST-0505", "story"), EXPECTED_STORY, "story")
    decisions = _load_yaml(root, OPEN_DECISIONS_PATH, "open_decision")
    _exact(
        _find(decisions.get("items"), "OD-015", "open_decision"),
        EXPECTED_OPEN_DECISION_ROW,
        "open_decision",
    )
    suites = _load_yaml(root, TEST_CATALOG_PATH, "test_suite")
    _exact(
        _find(suites.get("suites"), "TST-016", "test_suite"),
        EXPECTED_TEST_SUITE,
        "test_suite",
    )


def _validate_predecessor_semantics(root: Path) -> None:
    readme = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[0][0], "predecessor.readme"
    ).decode("utf-8", errors="strict")
    required_readme = (
        "RECORDED_TEST_ONLY",
        "live_eligible: false",
        "health `NOT_EXECUTED`",
        "executes once",
        "never sleeps",
        "retries",
        "follows another page",
        "storage and\n  persistence are both `NOT_EXECUTED`",
        "URI is `None`",
        "filesystem, network, SDK, credential, or external-action",
    )
    if any(fragment not in readme for fragment in required_readme):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.readme")

    domain = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[1][0], "predecessor.domain"
    ).decode("utf-8", errors="strict")
    required_domain = (
        'RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"',
        'NOT_EXECUTED = "NOT_EXECUTED"',
        'CONTRACT_TEST = "CONTRACT_TEST"',
        'ITEM_SEARCH = "ITEM_SEARCH"',
        "self.purpose is not ItemSearchPurpose.CONTRACT_TEST",
        "self.live_eligible is not False",
        "self.uri is not None",
        "self.storage_status is not StorageExecutionStatus.NOT_EXECUTED",
        "self.persistence_status is not PersistenceExecutionStatus.NOT_EXECUTED",
        "self.page != 1",
    )
    if any(fragment not in domain for fragment in required_domain):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.domain")

    port = _read(root, EXPECTED_PREDECESSOR_ARTIFACTS[2][0], "predecessor.port").decode(
        "utf-8", errors="strict"
    )
    if any(
        fragment in port
        for fragment in (
            "endpoint_url",
            "credential",
            "def save(",
            "def delete(",
            "def list(",
        )
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.port")

    application = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[3][0], "predecessor.application"
    ).decode("utf-8", errors="strict")
    required_application = (
        "command.request.page != 1",
        "raw = self._provider.execute(command)",
        "storage_status=StorageExecutionStatus.NOT_EXECUTED",
        "persistence_status=PersistenceExecutionStatus.NOT_EXECUTED",
        "live_eligible=False",
    )
    if any(fragment not in application for fragment in required_application):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.application")

    live_policy = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[9][0], "predecessor.live_policy"
    ).decode("utf-8", errors="strict")
    required_live_policy = (
        '"""Pure non-executable live-safe Item Search request policy for ST-0502."""',
        "class RakutenItemSearchLiveRequestV1(_RedactedValue):",
        'self.api_version != "2026-07-01"',
        "_exact_int(self.hits, minimum=1, maximum=30)",
        "type(self.page) is not int or self.page != 1",
        "def retry_limit(self) -> int:\n        return 0",
        "def pagination_followup_limit(self) -> int:\n        return 0",
        "return ProviderTextTrustV1.UNTRUSTED_DATA",
        "if self.has_review_only:\n            fail_item_search()",
    )
    if any(fragment not in live_policy for fragment in required_live_policy):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    if any(
        forbidden in live_policy
        for forbidden in ("reviewAverage", "reviewCount", "affiliateRate")
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    live_policy_tree: ast.Module | None = None
    try:
        live_policy_tree = ast.parse(live_policy)
    except SyntaxError:
        pass
    if live_policy_tree is None:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    if _ast_sha256(live_policy_tree) != LIVE_POLICY_EXPECTED_MODULE_AST_SHA256:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    top_level_definitions = [
        node
        for node in live_policy_tree.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    ]
    top_level_definition_names = [node.name for node in top_level_definitions]
    class_definitions = [
        node for node in live_policy_tree.body if isinstance(node, ast.ClassDef)
    ]
    class_definition_names = [node.name for node in class_definitions]
    if (
        len(top_level_definition_names) != len(set(top_level_definition_names))
        or frozenset(top_level_definition_names)
        != LIVE_POLICY_EXPECTED_TOP_LEVEL_FUNCTIONS
        or len(class_definition_names) != len(set(class_definition_names))
        or frozenset(class_definition_names)
        != frozenset(LIVE_POLICY_EXPECTED_CLASS_METHODS)
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    definition_nodes: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {
        node.name: node for node in top_level_definitions
    }
    observed_class_methods: dict[str, frozenset[str]] = {}
    for class_definition in class_definitions:
        methods = [
            node
            for node in class_definition.body
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        ]
        method_names = [node.name for node in methods]
        if len(method_names) != len(set(method_names)):
            _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
        observed_class_methods[class_definition.name] = frozenset(method_names)
        definition_nodes.update(
            {f"{class_definition.name}.{method.name}": method for method in methods}
        )
    observed_definition_fingerprints = {
        name: _ast_sha256(definition) for name, definition in definition_nodes.items()
    }
    if (
        observed_class_methods != LIVE_POLICY_EXPECTED_CLASS_METHODS
        or observed_definition_fingerprints
        != LIVE_POLICY_EXPECTED_DEFINITION_AST_SHA256
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")
    imports: set[str] = set()
    import_bindings: set[tuple[str, str, str, str | None, int]] = set()
    calls: set[str] = set()
    name_calls: set[str] = set()
    attribute_calls: set[str] = set()
    identifiers: set[str] = set()
    string_values: set[str] = set()
    has_indirect_call = False
    for node in ast.walk(live_policy_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.partition(".")[0])
                import_bindings.add(("import", "", alias.name, alias.asname, 0))
                identifiers.add(alias.name)
                if alias.asname:
                    identifiers.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.add(module.partition(".")[0])
            for alias in node.names:
                import_bindings.add(
                    ("from", module, alias.name, alias.asname, node.level)
                )
                identifiers.add(alias.name)
                if alias.asname:
                    identifiers.add(alias.asname)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
                attribute_calls.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                calls.add(node.func.id)
                name_calls.add(node.func.id)
            else:
                has_indirect_call = True
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            identifiers.add(node.name)
        elif isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.Constant) and type(node.value) is str:
            string_values.add(node.value)
    if (
        not imports.issubset(LIVE_POLICY_ALLOWED_IMPORTS)
        or import_bindings != LIVE_POLICY_ALLOWED_IMPORT_BINDINGS
        or not imports.isdisjoint(LIVE_POLICY_FORBIDDEN_IMPORTS)
        or not name_calls.issubset(LIVE_POLICY_ALLOWED_NAME_CALLS)
        or not attribute_calls.issubset(LIVE_POLICY_ALLOWED_ATTRIBUTE_CALLS)
        or not calls.isdisjoint(LIVE_POLICY_FORBIDDEN_CALLS)
        or not identifiers.isdisjoint(LIVE_POLICY_FORBIDDEN_CALLS)
        or not identifiers.isdisjoint(LIVE_POLICY_FORBIDDEN_DYNAMIC_REFERENCES)
        or not string_values.isdisjoint(LIVE_POLICY_FORBIDDEN_DYNAMIC_REFERENCES)
        or not string_values.isdisjoint(LIVE_POLICY_FORBIDDEN_IMPORTS)
        or has_indirect_call
        or any(
            part in identifier.lower()
            for identifier in identifiers
            for part in LIVE_POLICY_FORBIDDEN_IDENTIFIER_PARTS
        )
        or any(
            part in value.lower()
            for value in string_values
            for part in LIVE_POLICY_FORBIDDEN_IDENTIFIER_PARTS
        )
        or '"has_review_only":' in live_policy
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy")

    live_policy_test = _read(
        root, EXPECTED_PREDECESSOR_ARTIFACTS[10][0], "predecessor.live_policy_test"
    ).decode("utf-8", errors="strict")
    required_live_policy_test = (
        "assert request.retry_limit == request.pagination_followup_limit == 0",
        "assert request.provider_text_trust is ProviderTextTrustV1.UNTRUSTED_DATA",
        'assert b"reviewCount" not in request.canonical_json',
        'assert b"reviewAverage" not in request.canonical_json',
        'assert b"affiliateRate" not in request.canonical_json',
        'assert "has_review_only" not in request.canonical_parameters',
        "test_module_has_no_network_environment_filesystem_or_action_surface",
    )
    if any(fragment not in live_policy_test for fragment in required_live_policy_test):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.live_policy_test")


def _installed_bundle_sha256(root: Path) -> str:
    rows = [
        {
            "path": installed,
            "sha256": _sha256(_read(root, source, "runtime.payload")),
            "mode": f"{mode:04o}",
        }
        for source, installed, mode in INSTALLED_PAYLOADS
    ]
    canonical = json.dumps(
        rows,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return _sha256(canonical)


def _owner_local_bundle_sha256(root: Path) -> str:
    rows = [
        {
            "path": installed,
            "sha256": _sha256(_read(root, source, "owner_local.payload")),
            "mode": f"{mode:04o}",
        }
        for source, installed, mode in OWNER_LOCAL_INSTALLED_PAYLOADS
    ]
    canonical = json.dumps(
        rows,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return _sha256(canonical)


def _literal_assignment(source: str, name: str, field: str) -> object:
    tree = ast.parse(source)
    values: list[ast.expr] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            values.append(node.value)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            values.append(node.value)
    if len(values) != 1:
        _fail("RUNTIME_SEMANTIC_DRIFT", field)
    try:
        return ast.literal_eval(values[0])
    except ValueError, TypeError, SyntaxError:
        _fail("RUNTIME_SEMANTIC_DRIFT", field)


def _validate_runtime_semantics(root: Path) -> None:
    required_fragments = {
        Path("python/raos/domain/catalog/rakuten_live_smoke.py"): (
            'RAKUTEN_LIVE_SMOKE_HOST = "openapi.rakuten.co.jp"',
            'RAKUTEN_LIVE_SMOKE_PATH = "/ichibams/api/IchibaItem/Search/20260701"',
            'RAKUTEN_LIVE_SMOKE_ACCEPT = "application/json"',
            'RAKUTEN_LIVE_SMOKE_USER_AGENT = "RAOS-ST-0505-live-smoke/1"',
            'RAKUTEN_LIVE_SMOKE_ACCESS_HEADER = "access" + "Key"',
            'RAKUTEN_LIVE_SMOKE_REPORT_SCHEMA = "RAOS_ST0505_RAKUTEN_LIVE_SMOKE_REPORT_V2"',
            "elements=LIVE_ITEM_SEARCH_ELEMENTS_V1",
            '"access_key_transport": "HEADER_accessKey_ONLY"',
            '"query_credentials": ["affiliateId", "applicationId"]',
            '"retry_count": 0',
            '"pagination_count": 0',
            '"formal_tst_016": "NOT_EXECUTED"',
            '"staging": "NOT_EXECUTED"',
            '"production": "NOT_EXECUTED"',
            '"response_sha256": self.response_sha256',
        ),
        Path("python/raos/application/catalog/rakuten_live_smoke.py"): (
            '_ITEM_KEYS = frozenset({"affiliateUrl"})',
            'not 1 <= root["count"] <= (1 << 63) - 1',
            'not 1 <= root["pageCount"] <= 100',
            "len(items) != 1",
            'affiliate_url = item["affiliateUrl"]',
            "response_sha256 = response.response_sha256",
        ),
        Path("python/raos/adapters/rakuten_live_smoke.py"): (
            "headers[RAKUTEN_LIVE_SMOKE_ACCESS_HEADER] = (",
            "credentials.access_key_header_value()",
            'connection.request("GET", target, headers)',
            "host=RAKUTEN_LIVE_SMOKE_HOST",
            'anonymous_flag = getattr(os, "O_TMPFILE", 0)',
            "_report_store_has_recovery(report_fd)",
            "os.unlink(target, dir_fd=report_fd)",
            "request_count=int(request_started)",
            "_fail_report_store(report)",
            "after.st_mtime_ns != before.st_mtime_ns",
            "after.st_ctime_ns != before.st_ctime_ns",
            "verification != data",
            '_STAGING_BINDING_FILE = "staging-credential-binding.v1.json"',
            "binding_digest != hashlib.sha256(raw).hexdigest()",
            "_resolve_public_rakuten_addresses(host, port)",
            'setattr(connection, "_create_connection", _PinnedSocketConnector(candidate))',
            "_require_exact_peer(self._candidate, self._connection.sock.getpeername())",
            "_CHUNKED.fullmatch(transfer_encoding)",
            "expected_length is not None and len(body) != expected_length",
        ),
        Path("scripts/rakuten_live_smoke.py"): (
            'TRUSTED_RUNTIME_PARENT = TRUSTED_OWNER_ROOT / "rakuten-live-smoke" / "runtime"',
            "runtime_root = _verify_installed_runtime()",
            "_verify_stage_zero_entry()",
            "_validate_runtime_inventory(",
            "transport, writer = _production_dependencies()",
            "writer.doctor_ready()\n        reader.read()",
            "writer.preflight()",
            "request_count=failure.request_count",
            "response_sha256=failure.response_sha256",
        ),
        Path("scripts/rakuten_live_smoke_launcher.sh"): (
            "#!/usr/bin/busybox sh",
            "expected_busybox_sha256=b3c1009e1b5c927e537487c80639cdf404f69e3eb49371d9be5d841672be3ff9",
            "expected_python_sha256=c2afa8cc3c59d32bac482c122633a352c3910bfed85b59efd8ef49511d46bd2b",
            "stdlib_invalid=$(",
            "pyvenv.cfg",
            '[ ! -L "$runtime_cli" ]',
            'require_metadata "$runtime_cli" regular current 400',
            "stat -Lc '%d %i %f %u %a %h' /proc/self/fd/4",
            '[ "$outer_gate_metadata" = "$entry_gate_metadata" ]',
            "exec 4<&-",
            'exec 3<"$entry_path"',
            '"$python" -B -I -S',
            "exec /usr/bin/busybox env -i",
        ),
        Path("scripts/install_rakuten_live_smoke_runtime.py"): (
            "EXPECTED_BUNDLE_SHA256 = (",
            '"94c256d8832167c6df89327fc2840bc6db6fc82af4c912286b95ee6e8084148d"',
            "EXPECTED_SYSTEM_PYTHON_SHA256 = (",
            'REVIEWED_SYSTEM_PYTHON = Path("/usr/bin/python3.10")',
            '_INSTALL_STAGE_PYTHON_ENTRY = f"/proc/self/fd/{_INSTALL_STAGE_PYTHON_FD}"',
            '_INSTALL_STAGE_SOURCE_ENTRY = f"/proc/self/fd/{_INSTALL_STAGE_SOURCE_FD}"',
            "_validate_authenticated_bootstrap()",
            "_RENAME_NOREPLACE = 1",
            "os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW",
        ),
        Path("scripts/rakuten_live_smoke_runtime_install.sh"): (
            "#!/usr/bin/busybox sh",
            "expected_busybox_sha256=b3c1009e1b5c927e537487c80639cdf404f69e3eb49371d9be5d841672be3ff9",
            "expected_python_sha256=7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86",
            f"expected_installer_sha256={EXPECTED_RUNTIME_INSTALLER_SHA256}",
            'require_hash /proc/self/fd/5 "$expected_python_sha256"',
            'require_hash /proc/self/fd/6 "$expected_installer_sha256"',
            "require_absent /etc/ld.so.preload",
            "require_root_tree /usr/lib/python3.10",
            "/proc/self/fd/5 -B -I -S /proc/self/fd/6",
        ),
    }
    for path, fragments in required_fragments.items():
        source = _read(root, path, "runtime.source").decode("utf-8", errors="strict")
        if any(fragment not in source for fragment in fragments):
            _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.source")
    domain_source = _read(
        root,
        Path("python/raos/domain/catalog/rakuten_live_smoke.py"),
        "runtime.domain",
    ).decode("utf-8", errors="strict")
    adapter_source = _read(
        root,
        Path("python/raos/adapters/rakuten_live_smoke.py"),
        "runtime.adapter",
    ).decode("utf-8", errors="strict")
    if adapter_source.count("_report_store_has_recovery(report_fd)") != 3:
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.adapter")
    if _literal_assignment(domain_source, "_REPORT_KEYS", "runtime.report") != tuple(
        EXPECTED_REPORT_FIELDS
    ):
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.report")
    if _literal_assignment(
        domain_source, "RAKUTEN_LIVE_SMOKE_MINIMAL_ELEMENTS", "runtime.elements"
    ) != ("count", "page", "first", "last", "hits", "pageCount", "affiliateUrl"):
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.elements")
    installer_source = _read(
        root,
        Path("scripts/install_rakuten_live_smoke_runtime.py"),
        "runtime.installer",
    ).decode("utf-8", errors="strict")
    install_stage_source = _read(
        root,
        Path("scripts/rakuten_live_smoke_runtime_install.sh"),
        "runtime.install_stage",
    ).decode("utf-8", errors="strict")
    cli_source = _read(
        root, Path("scripts/rakuten_live_smoke.py"), "runtime.cli"
    ).decode("utf-8", errors="strict")
    launcher_source = _read(
        root,
        Path("scripts/rakuten_live_smoke_launcher.sh"),
        "runtime.launcher",
    ).decode("utf-8", errors="strict")
    if (
        hashlib.sha256(launcher_source.encode("utf-8")).hexdigest()
        != EXPECTED_INSTALLED_LAUNCHER_SHA256
    ):
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.launcher")
    if (
        hashlib.sha256(installer_source.encode("utf-8")).hexdigest()
        != EXPECTED_RUNTIME_INSTALLER_SHA256
        or hashlib.sha256(install_stage_source.encode("utf-8")).hexdigest()
        != EXPECTED_RUNTIME_INSTALL_STAGE_SHA256
    ):
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.install_bootstrap")
    expected_installer_payloads = tuple(
        (source.as_posix(), installed, mode)
        for source, installed, mode in INSTALLED_PAYLOADS
    )
    expected_cli_payloads = {
        installed: f"{mode:04o}" for _source, installed, mode in INSTALLED_PAYLOADS
    }
    if _literal_assignment(installer_source, "_PAYLOADS", "runtime.installer") != (
        expected_installer_payloads
    ):
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.installer")
    if (
        _literal_assignment(cli_source, "_INSTALLED_PAYLOAD_MODES", "runtime.cli")
        != expected_cli_payloads
    ):
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.cli")
    cli_sha256 = hashlib.sha256(cli_source.encode("utf-8")).hexdigest()
    required_launcher_hash_fragments = (
        f"expected_cli_sha256={cli_sha256}",
        '/usr/bin/busybox sha256sum "$runtime_cli"',
        '[ "$cli_hash" = "$expected_cli_sha256  $runtime_cli" ]',
        '"$python" -B -I -S "$runtime_cli" "$command"',
    )
    if any(
        fragment not in launcher_source for fragment in required_launcher_hash_fragments
    ):
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.launcher")
    readme_source = _read(root, README_PATH, "runtime.readme").decode(
        "utf-8", errors="strict"
    )
    if (
        _authoritative_runtime_install_command() not in readme_source
        or "make rakuten-live-smoke" in readme_source
    ):
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.readme")
    handoff = _load_yaml(root, DESIGN_HANDOFF_PATH, "runtime.handoff")
    handoff_decision = handoff.get("decision")
    open_decision = handoff.get("open_decision_state")
    handoff_gates = handoff.get("security_and_approval_gates")
    if (
        handoff.get("schema") != "DESIGN_HANDOFF_V1"
        or handoff.get("approved_story") != "ST-0505"
        or type(handoff_decision) is not dict
        or cast(dict[str, object], handoff_decision).get("local_interface")
        != "OWNER_INSTALLED_EXACT_DIGEST_ENTRY_INSTALLABLE_NOT_INSTALLED"
        or cast(dict[str, object], handoff_decision).get("default_activation")
        != "DISABLED"
        or cast(dict[str, object], handoff_decision).get("installed_bundle_sha256")
        != EXPECTED_INSTALLED_BUNDLE_SHA256
        or cast(dict[str, object], handoff_decision).get("runtime_installer_sha256")
        != EXPECTED_RUNTIME_INSTALLER_SHA256
        or cast(dict[str, object], handoff_decision).get("runtime_install_stage_sha256")
        != EXPECTED_RUNTIME_INSTALL_STAGE_SHA256
        or cast(dict[str, object], handoff_decision).get(
            "runtime_install_entry_authentication"
        )
        != "ROOT_OWNED_STATIC_BUSYBOX_FIXED_STAGE_AND_INSTALLER_FD_SHA256_GATE"
        or cast(dict[str, object], handoff_decision).get("runtime_install_python_trust")
        != "EXACT_ROOT_PYTHON_BINARY_WITH_ROOT_OWNED_OS_RUNTIME_METADATA_CLOSURE"
        or cast(dict[str, object], handoff_decision).get(
            "direct_repository_installer_entry"
        )
        != "REFUSE_BEFORE_RUNTIME_MUTATION"
        or cast(dict[str, object], handoff_decision).get("runtime_install_scope")
        != "CREDENTIAL_BLIND_OWNER_LOCAL_MAINTENANCE_ONLY"
        or cast(dict[str, object], handoff_decision).get(
            "credential_tree_during_install"
        )
        != "FORBIDDEN"
        or cast(dict[str, object], handoff_decision).get("reinstall_policy")
        != "VALIDATE_EXACT_VERSIONED_BUNDLE_RETURN_ALREADY_INSTALLED_NO_CREDENTIAL_ACCESS"
        or cast(dict[str, object], handoff_decision).get(
            "automatic_post_install_doctor_or_run"
        )
        != "FORBIDDEN"
        or cast(dict[str, object], handoff_decision).get("runtime_install_execution")
        != "NOT_EXECUTED"
        or cast(dict[str, object], handoff_decision).get(
            "authoritative_runtime_install"
        )
        != _authoritative_runtime_install_command()
        or cast(dict[str, object], handoff_decision).get("authoritative_doctor")
        != _authoritative_installed_command("doctor")
        or cast(dict[str, object], handoff_decision).get("authoritative_live_command")
        != _authoritative_installed_command("run")
        or cast(dict[str, object], handoff_decision).get("repository_make_entrypoints")
        != "NOT_PROVIDED_USE_REVIEWED_DIRECT_COMMANDS"
        or cast(dict[str, object], handoff_decision).get("staging_credential_binding")
        != ".secrets/rakuten-live-smoke/staging-credential-binding.v1.json"
        or cast(dict[str, object], handoff_decision).get("local_diagnostic_authority")
        != "NON_FORMAL_NON_ATTESTING_ONLY"
        or cast(dict[str, object], handoff_decision).get("live_execution_authority")
        != "NOT_GRANTED_BY_THIS_ARTIFACT"
        or cast(dict[str, object], handoff_decision).get("formal_tst_016")
        != "NOT_EXECUTED"
        or cast(dict[str, object], handoff_decision).get("staging") != "NOT_EXECUTED"
        or cast(dict[str, object], handoff_decision).get("production") != "NOT_EXECUTED"
        or type(open_decision) is not dict
        or cast(dict[str, object], open_decision).get("id") != "OD-015"
        or cast(dict[str, object], open_decision).get("status")
        != "EXTERNAL_EVIDENCE_REQUIRED"
        or cast(dict[str, object], open_decision).get("blocking") is not True
        or cast(dict[str, object], open_decision).get("resolved") is not False
        or cast(dict[str, object], open_decision).get("safe_default")
        != "RECORDED_FIXTURE_ONLY"
        or type(handoff_gates) is not list
        or (
            "repository Make entrypoints are not provided; installation, "
            "doctor, and live execution use only the complete reviewed direct "
            "commands" not in cast(list[object], handoff_gates)
        )
        or (
            "direct installed launcher invocation refuses before credential "
            "access without the authenticated outer-gate launcher descriptor "
            "on fd 4" not in cast(list[object], handoff_gates)
        )
        or (
            "every install and reinstall validates stage path/descriptor "
            "identity and safe metadata before authenticating the exact stage, "
            "root Python trust closure, and installer descriptor before Python "
            "parses repository bytes" not in cast(list[object], handoff_gates)
        )
    ):
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.handoff")
    readme = _read(root, README_PATH, "runtime.readme").decode("utf-8", errors="strict")
    required_readme = (
        "Default activation remains\ndisabled.",
        "Repository Make entrypoints are intentionally not provided.",
        "root-owned\nstatic BusyBox entry.",
        "requires the\nopened stage and named path to identify the same current-UID, "
        "regular,\nsingle-link, bounded, non-group/world-writable inode",
        "does not construct a transport",
        "before reading credentials\nor attempting the GET",
        "outer static, root-owned `/usr/bin/busybox` stage zero authenticates the\nlauncher SHA-256 before executing it",
        "bare invocation of the installed launcher refuses before constructing the\ncredential reader",
        "installed-runtime status is\n`NOT_EXECUTED` and `NOT_EVIDENCED`",
        "formal TST-016, live auth/schema/rate, staging, release, and Production all\nremain `NOT_EXECUTED`",
        "non-formal, non-attesting diagnostic\nsurface only",
        "This artifact grants no live-provider execution authority.",
        "staging-credential-binding.v1.json",
        "response_sha256",
        "Content-Length is parsed strictly",
        "truncated, oversized, or otherwise incomplete reads do not\n  claim a response-body digest",
        "first fully validated\n  numeric address is pinned",
        "Every install\nand reinstall first binds the named stage through fd 4",
        "Only after this check does\nit authenticate the exact stage bytes",
        "root-owned OS runtime metadata closure",
        "Direct repository-path execution of the Python installer refuses before",
        "do not open, stat, list, read, write,\nor mutate `.secrets`",
        "never chains doctor or run",
        "`ALREADY_INSTALLED`",
        "Authenticated installation is credential-blind owner-local maintenance",
    )
    if any(fragment not in readme for fragment in required_readme):
        _fail("RUNTIME_SEMANTIC_DRIFT", "runtime.readme")
    if _installed_bundle_sha256(root) != EXPECTED_INSTALLED_BUNDLE_SHA256:
        _fail("RUNTIME_BUNDLE_DRIFT", "runtime.bundle")


def _validate_owner_local_runtime_semantics(root: Path) -> None:
    required_fragments = {
        Path("python/raos/domain/catalog/rakuten_owner_local.py"): (
            'RAKUTEN_OWNER_LOCAL_PROFILE = "OWNER_LOCAL_RAKUTEN_PRODUCTION_API"',
            'RAKUTEN_OWNER_LOCAL_HOST = "openapi.rakuten.co.jp"',
            '"2026-07-01"',
            '"2025-08-01"',
            '"/ichibams/api/IchibaItem/Search/20260701"',
            '"/ichibaproduct/api/Product/Search/20250801"',
            'RAKUTEN_OWNER_LOCAL_EVIDENCE_AUTHORITY = "OWNER_LOCAL_NON_FORMAL_LIVE_EVIDENCE"',
            'RAKUTEN_OWNER_LOCAL_PROVIDER_DATA_CLASSIFICATION = "UNTRUSTED_PROVIDER_DATA"',
            'RAKUTEN_OWNER_LOCAL_FORMAL_TST_016 = "NOT_EXECUTED"',
            'RAKUTEN_OWNER_LOCAL_OD_015 = "UNRESOLVED_EXTERNAL_EVIDENCE_REQUIRED"',
            "_NON_NULL_URL_FIELDS = {",
            'frozenset({"itemUrl"})',
            'frozenset({"productUrlPC"})',
            "_MANDATORY_TEXT_FIELDS = {",
            'frozenset({"itemCode", "itemName"})',
            'frozenset({"productCode", "productId"})',
            "if type(candidate) in {str, tuple}",
            "unquote_to_bytes(text)",
            "mandatory_record_fields(self.api)",
            "validated_response_text(value)",
            '"first": result.first if result is not None else None,',
            '"last": result.last if result is not None else None,',
            "_MALFORMED_PERCENT_ESCAPE =",
            'unicodedata.category(character) == "Cc"',
            "_validate_https_host(parsed.hostname, parsed.netloc)",
        ),
        Path("python/raos/application/catalog/rakuten_owner_local.py"): (
            "self.result_writer.preflight()",
            "self.credential_reader.read()",
            "self.transport.execute(",
            "self.result_writer.write(envelope)",
            "REQUEST_ALREADY_ATTEMPTED",
        ),
        Path("python/raos/adapters/rakuten_owner_local.py"): (
            '".secrets", "rakuten-owner-local"',
            '"credentials.v1.json"',
            '"results"',
            'connection.request("GET"',
            '"applicationId"',
            '"affiliateId"',
            '"access" + "Key"',
            "mandatory_record_fields(api)",
            "validated_response_text(returned_value)",
            "socket.getaddrinfo(",
            "ssl.create_default_context(",
            "O_TMPFILE",
        ),
        Path("scripts/rakuten_owner_local.py"): (
            'TRUSTED_RUNTIME_PARENT = TRUSTED_OWNER_ROOT / "rakuten-owner-local" / "runtime"',
            '"bin/rakuten-owner-local"',
            '"setup"',
            '"rotate"',
            '"doctor"',
            '"list-apis"',
            '"request"',
            '"smoke"',
            'os.open(\n        "/dev/tty"',
            "_verify_stage_zero_entry()",
            "_verify_installed_runtime()",
        ),
        Path("scripts/rakuten_owner_local_launcher.sh"): (
            "#!/usr/bin/busybox sh",
            "/home/minami/.local/share/raos/rakuten-owner-local/runtime/",
            "exec /usr/bin/busybox env -i",
            'exec 3<"$entry_path"',
            '"$python" -B -I -S "$runtime_cli" "$@"',
        ),
        Path("scripts/rakuten_owner_local_runtime_install.sh"): (
            "#!/usr/bin/busybox sh",
            "rakuten_owner_local_runtime_install.sh",
            "install_rakuten_owner_local_runtime.py",
            "/proc/self/fd/5 -B -I -S /proc/self/fd/6",
        ),
        Path("scripts/install_rakuten_owner_local_runtime.py"): (
            'runtime_path = owner_base / "raos" / "rakuten-owner-local" / "runtime"',
            '"RAOS_ST0505_OWNER_LOCAL_INSTALLED_RUNTIME_V1"',
            "_validate_authenticated_bootstrap()",
            "_RENAME_NOREPLACE = 1",
        ),
    }
    for path, fragments in required_fragments.items():
        source = _read(root, path, "owner_local.source").decode(
            "utf-8", errors="strict"
        )
        if any(fragment not in source for fragment in fragments):
            _fail("OWNER_LOCAL_RUNTIME_SEMANTIC_DRIFT", path.as_posix())
    domain_source = _read(
        root,
        Path("python/raos/domain/catalog/rakuten_owner_local.py"),
        "owner_local.domain",
    ).decode("utf-8", errors="strict")
    try:
        domain_tree = ast.parse(domain_source)
    except SyntaxError:
        _fail("OWNER_LOCAL_RUNTIME_SEMANTIC_DRIFT", "owner_local.domain")
    reflection_methods = [
        member
        for node in domain_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "RakutenOwnerLocalCredentials"
        for member in node.body
        if isinstance(member, (ast.AsyncFunctionDef, ast.FunctionDef))
        and member.name == "reject_reflected_result"
    ]
    if (
        len(reflection_methods) != 1
        or _ast_sha256(reflection_methods[0])
        != OWNER_LOCAL_CREDENTIAL_REFLECTION_METHOD_AST_SHA256
    ):
        _fail(
            "OWNER_LOCAL_RUNTIME_SEMANTIC_DRIFT",
            "owner_local.credential_reflection",
        )
    installer_source = _read(
        root,
        Path("scripts/install_rakuten_owner_local_runtime.py"),
        "owner_local.installer",
    ).decode("utf-8", errors="strict")
    cli_source = _read(
        root, Path("scripts/rakuten_owner_local.py"), "owner_local.cli"
    ).decode("utf-8", errors="strict")
    launcher = _read(
        root,
        Path("scripts/rakuten_owner_local_launcher.sh"),
        "owner_local.launcher",
    )
    stage = _read(
        root,
        Path("scripts/rakuten_owner_local_runtime_install.sh"),
        "owner_local.install_stage",
    )
    expected_installer_payloads = tuple(
        (source.as_posix(), installed, mode)
        for source, installed, mode in OWNER_LOCAL_INSTALLED_PAYLOADS
    )
    expected_cli_payloads = {
        installed: f"{mode:04o}"
        for _source, installed, mode in OWNER_LOCAL_INSTALLED_PAYLOADS
    }
    if (
        _literal_assignment(installer_source, "_PAYLOADS", "owner_local.installer")
        != expected_installer_payloads
    ):
        _fail("OWNER_LOCAL_RUNTIME_SEMANTIC_DRIFT", "owner_local.installer")
    if (
        _literal_assignment(cli_source, "_INSTALLED_PAYLOAD_MODES", "owner_local.cli")
        != expected_cli_payloads
    ):
        _fail("OWNER_LOCAL_RUNTIME_SEMANTIC_DRIFT", "owner_local.cli")
    if _sha256(launcher) != EXPECTED_OWNER_LOCAL_LAUNCHER_SHA256:
        _fail("OWNER_LOCAL_RUNTIME_HASH_DRIFT", "owner_local.launcher")
    if (
        _sha256(
            _read(
                root,
                Path("scripts/install_rakuten_owner_local_runtime.py"),
                "owner_local.installer",
            )
        )
        != EXPECTED_OWNER_LOCAL_INSTALLER_SHA256
        or _sha256(stage) != EXPECTED_OWNER_LOCAL_INSTALL_STAGE_SHA256
    ):
        _fail("OWNER_LOCAL_RUNTIME_HASH_DRIFT", "owner_local.install")
    if _owner_local_bundle_sha256(root) != EXPECTED_OWNER_LOCAL_BUNDLE_SHA256:
        _fail("OWNER_LOCAL_RUNTIME_BUNDLE_DRIFT", "owner_local.bundle")


EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST0505-RAKUTEN-LIVE-SMOKE-REFERENCE-PLAN-001",
    "version": "3.0.0",
    "story_id": "ST-0505",
    "classification": "SOURCE_DERIVED_EXPLICIT_LOCAL_RAKUTEN_LIVE_SMOKE_PLAN",
    "status": "OWNER_INSTALLED_ENTRY_INSTALLABLE_NOT_INSTALLED",
    "executable": True,
    "interface_only": False,
    "decision": "EXACT_OWNER_INSTALLED_ENTRY_REQUIRED",
    "story_acceptance": False,
    "production_eligible": False,
    "approval": None,
    "effective_canonical_status": "UNCHANGED",
}
EXPECTED_LIVE_REQUEST_POLICY_SEMANTICS: Final[dict[str, object]] = {
    "policy_name": "RakutenItemSearchLiveRequestV1",
    "policy_version": "V1",
    "provider_api_version": "2026-07-01",
    "non_executable": True,
    "requested_page": 1,
    "hits_minimum": 1,
    "hits_maximum": 30,
    "retry_limit": 0,
    "pagination_followup_limit": 0,
    "review_derived_request_inputs": "EXCLUDED",
    "affiliate_rate_request_inputs": "EXCLUDED",
    "provider_text_trust": "UNTRUSTED_DATA",
}
EXPECTED_PREDECESSOR_SEMANTICS: Final[dict[str, object]] = {
    "provider": "RAKUTEN_ICHIBA",
    "operation": "ITEM_SEARCH",
    "purpose": "CONTRACT_TEST",
    "mode": "RECORDED_TEST_ONLY",
    "live_eligible": False,
    "health": "NOT_EXECUTED",
    "requested_page": 1,
    "page_fetch_count": 1,
    "retry_count": 0,
    "pagination_count": 0,
    "storage": "NOT_EXECUTED",
    "persistence": "NOT_EXECUTED",
    "receipt_uri": None,
    "endpoint_url": None,
    "account": None,
    "credential_access": "FORBIDDEN",
    "network_access": "FORBIDDEN",
    "provider_sdk": "ABSENT",
    "filesystem": "ABSENT",
    "repository": "ABSENT",
    "external_actions": [],
    "live_request_policy": EXPECTED_LIVE_REQUEST_POLICY_SEMANTICS,
}
EXPECTED_PREDECESSOR: Final = {
    "story_id": "ST-0502",
    "commit": PREDECESSOR_COMMIT,
    "status": "RECORDED_ONE_PAGE_CONTRACT_TEST_ONLY",
    "connection_status": "INTERFACE_AVAILABLE_NOT_CONNECTED",
    "artifacts": _expected_predecessor_artifacts(),
    "semantics": EXPECTED_PREDECESSOR_SEMANTICS,
}
EXPECTED_OPEN_DECISION: Final = {
    "id": "OD-015",
    "status": "EXTERNAL_EVIDENCE_REQUIRED",
    "blocking": True,
    "safe_default": "RECORDED_FIXTURE_ONLY",
    "resolved": False,
    "live_credentials_evidenced": False,
    "live_execution_authorized": False,
}
EXPECTED_REPORT_FIELDS: Final = [
    "schema",
    "version",
    "run_id",
    "started_at",
    "finished_at",
    "result",
    "diagnostic_code",
    "api_version",
    "endpoint_id",
    "request_policy_fingerprint",
    "http_status",
    "body_byte_count",
    "response_sha256",
    "auth_classification",
    "schema_classification",
    "rate_classification",
    "affiliate_url_present",
    "request_count",
    "retry_count",
    "pagination_count",
    "formal_tst_016",
    "staging",
    "production",
]
EXPECTED_SMOKE: Final[dict[str, object]] = {
    "status": "INSTALLABLE_NOT_INSTALLED_OR_EXECUTED",
    "runnable": False,
    "technical_entry_invocable_after_install_and_doctor": True,
    "invocation_gate": "FRESH_OWNER_INVOCATION_REQUIRED",
    "live_execution_authority": "NOT_GRANTED_BY_THIS_ARTIFACT",
    "evidence_authority": "NON_FORMAL_DIAGNOSTIC_ONLY",
    "runner": "OWNER_PRIVATE_VERSIONED_INSTALLED_ENTRY",
    "runtime_install_command": _authoritative_runtime_install_command(),
    "runtime_installer_sha256": EXPECTED_RUNTIME_INSTALLER_SHA256,
    "runtime_install_stage_sha256": EXPECTED_RUNTIME_INSTALL_STAGE_SHA256,
    "runtime_install_entry_authentication": (
        "ROOT_OWNED_STATIC_BUSYBOX_FIXED_STAGE_AND_INSTALLER_FD_SHA256_GATE"
    ),
    "runtime_install_python_trust": (
        "EXACT_ROOT_PYTHON_BINARY_WITH_ROOT_OWNED_OS_RUNTIME_METADATA_CLOSURE"
    ),
    "direct_repository_installer_entry": "REFUSE_BEFORE_RUNTIME_MUTATION",
    "runtime_install_scope": "CREDENTIAL_BLIND_OWNER_LOCAL_MAINTENANCE_ONLY",
    "credential_tree_during_install": "FORBIDDEN",
    "reinstall_policy": (
        "VALIDATE_EXACT_VERSIONED_BUNDLE_RETURN_ALREADY_INSTALLED_NO_CREDENTIAL_ACCESS"
    ),
    "automatic_post_install_doctor_or_run": "FORBIDDEN",
    "runtime_install_execution": "NOT_EXECUTED",
    "command": _authoritative_installed_command("run"),
    "doctor_command": _authoritative_installed_command("doctor"),
    "repository_make_entrypoints": "NOT_PROVIDED_USE_REVIEWED_DIRECT_COMMANDS",
    "direct_installed_launcher_entry": "REFUSE_WITHOUT_OUTER_GATE_FD4",
    "direct_python_entry": "REFUSE_WITHOUT_STAGE_ZERO_DESCRIPTOR",
    "installed_bundle_sha256": (
        "94c256d8832167c6df89327fc2840bc6db6fc82af4c912286b95ee6e8084148d"
    ),
    "installed_launcher_sha256": EXPECTED_INSTALLED_LAUNCHER_SHA256,
    "public_entry_authentication": (
        "ROOT_OWNED_STATIC_BUSYBOX_FIXED_LAUNCHER_FD_SHA256_GATE"
    ),
    "selected_environment": (
        "OWNER_LOCAL_NON_FORMAL_DIAGNOSTIC_WITH_STAGING_CREDENTIAL_BINDING"
    ),
    "selected_account": None,
    "selected_endpoint": "RAKUTEN_ICHIBA_ITEM_SEARCH_20260701",
    "credential_selection": (
        "FIXED_OWNER_PRIVATE_JSON_HASH_BOUND_TO_STAGING_ATTESTATION"
    ),
    "credential_record": {
        "path": ".secrets/rakuten-live-smoke/credentials.v1.json",
        "schema_version": 1,
        "exact_keys": [
            "schema_version",
            "application_id",
            "access_key",
            "affiliate_id",
        ],
        "file_mode": "0600",
        "directory_mode": "0700",
        "symlinks": "REJECT",
        "read_stability": (
            "DESCRIPTOR_DOUBLE_READ_EQUAL_IDENTITY_SIZE_MTIME_CTIME_STABLE"
        ),
        "rotation": "ATOMIC_REPLACE_REQUIRED",
    },
    "staging_credential_binding": {
        "path": ".secrets/rakuten-live-smoke/staging-credential-binding.v1.json",
        "schema_version": 1,
        "exact_keys": [
            "schema_version",
            "environment",
            "credential_purpose",
            "credential_record_sha256",
        ],
        "environment": "staging",
        "credential_purpose": ("DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC"),
        "credential_record_sha256": "SHA256_OF_EXACT_CREDENTIAL_RECORD_BYTES",
        "file_mode": "0600",
        "directory_mode": "0700",
        "symlinks": "REJECT",
        "read_stability": (
            "DESCRIPTOR_DOUBLE_READ_EQUAL_IDENTITY_SIZE_MTIME_CTIME_STABLE"
        ),
        "creation": "EXTERNAL_OPERATIONS_PROCESS_NOT_PROVIDED_BY_THIS_ARTIFACT",
        "authority": "DOES_NOT_EXECUTE_OR_SATISFY_TST_016",
    },
    "doctor_scope": (
        "INSTALLED_RUNTIME_STAGING_BINDING_CREDENTIAL_AND_REPORT_METADATA_ONLY_NO_NETWORK"
    ),
    "run_preflight": ("EXACT_ANONYMOUS_PUBLICATION_ROLLBACK_BEFORE_CREDENTIAL_AND_GET"),
    "request": {
        "method": "GET",
        "authority": "openapi.rakuten.co.jp:443",
        "path": "/ichibams/api/IchibaItem/Search/20260701",
        "api_version": "2026-07-01",
        "query": {
            "keyword": "収納",
            "hits": 1,
            "page": 1,
            "format": "json",
            "formatVersion": 2,
            "sort": "standard",
            "elements": "count,page,first,last,hits,pageCount,affiliateUrl",
            "applicationId": "CREDENTIAL_APPLICATION_ID",
            "affiliateId": "CREDENTIAL_AFFILIATE_ID",
        },
        "headers": [
            {"header_name": "Accept", "fixed_value": "application/json"},
            {
                "header_name": "User-Agent",
                "fixed_value": "RAOS-ST-0505-live-smoke/1",
            },
            {
                "header_name": "accessKey",
                "value_source": "OWNER_PRIVATE_CREDENTIAL_RECORD",
            },
        ],
        "access_key_transport": "HEADER_accessKey_ONLY",
        "redirect_limit": 0,
        "request_limit": 1,
        "dns_resolution_count": 1,
        "dns_candidate_policy": ("REJECT_ENTIRE_SET_IF_ANY_NON_PUBLIC_OR_MALFORMED"),
        "tcp_candidate_policy": "FIRST_VALIDATED_CANDIDATE_ONLY_NO_FALLBACK",
        "tls_hostname": "openapi.rakuten.co.jp",
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 20,
    },
    "response": {
        "maximum_bytes": 2_097_152,
        "encoding": "STRICT_UTF_8",
        "media_type": "application/json",
        "duplicate_keys": "REJECT",
        "nonfinite_numbers": "REJECT",
        "maximum_depth": 32,
        "maximum_nodes": 50_000,
        "affiliate_url": "REQUIRED_HTTPS_PRESENCE_ONLY",
        "http_429_classification": "AUTH_NOT_OBSERVED_RATE_THROTTLED",
        "framing_policy": "STRICT_CONTENT_LENGTH_CHUNKED_OR_CLOSE_DELIMITED",
        "incomplete_framing": "REQUEST_AMBIGUOUS_NO_RESPONSE_DIGEST",
        "response_sha256": "REQUIRED_FOR_EACH_COMPLETE_BOUNDED_RESPONSE_BODY",
        "raw_or_reflected_provider_material_persistence": "FORBIDDEN",
    },
    "report": {
        "directory": ".secrets/rakuten-live-smoke/reports",
        "schema": "RAOS_ST0505_RAKUTEN_LIVE_SMOKE_REPORT_V2",
        "file_mode": "0600",
        "publication": "ATOMIC_NO_REPLACE",
        "rollback_failure_evidence": (
            "BEST_EFFORT_FIXED_0600_RECOVERY_REQUIRED_MARKER"
        ),
        "recovery_evidence_gate": (
            "BLOCKS_DOCTOR_PREFLIGHT_AND_ALL_REPORT_PUBLICATION"
        ),
        "failures_persisted_when_store_is_safe": True,
        "raw_body": "FORBIDDEN",
        "product_text_and_urls": "FORBIDDEN",
        "credential_values": "FORBIDDEN",
        "fields": EXPECTED_REPORT_FIELDS,
    },
    "retry_policy": "ZERO_RETRY",
    "pagination_policy": "ZERO_FOLLOWUP",
    "artifacts": [
        "repo://python/raos/domain/catalog/rakuten_live_smoke.py",
        "repo://python/raos/application/catalog/rakuten_live_smoke.py",
        "repo://python/raos/ports/rakuten_live_smoke.py",
        "repo://python/raos/adapters/rakuten_live_smoke.py",
        "repo://scripts/rakuten_live_smoke.py",
        "repo://scripts/rakuten_live_smoke_launcher.sh",
        "repo://scripts/install_rakuten_live_smoke_runtime.py",
        "repo://scripts/rakuten_live_smoke_runtime_install.sh",
    ],
}
EXPECTED_OBSERVATIONS: Final[dict[str, object]] = {
    "status": "NOT_EXECUTED",
    "started_at": None,
    "finished_at": None,
    "auth_observation": None,
    "schema_observation": None,
    "rate_observation": None,
    "provider_request_id": None,
    "http_status": None,
    "latency": None,
    "observations": [],
    "errors": [],
    "evidence": [],
    "empty_interpretation": "NO_LIVE_EXECUTION_EVIDENCE_NOT_ZERO_ERRORS_OR_SUCCESS",
}
EXPECTED_RATE_QUOTA_COST: Final[dict[str, object]] = {
    "rate_limit": None,
    "rate_remaining": None,
    "rate_reset": None,
    "quota_limit": None,
    "quota_remaining": None,
    "cost": None,
    "currency": None,
    "capacity": None,
    "values": [],
}
EXPECTED_ACTION_COUNTS: Final = {name: 0 for name in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION: Final[dict[str, object]] = {
    "enabled": False,
    "status": "DISABLED_BY_DEFAULT_EXPLICIT_COMMAND_ONLY",
    "default_activation": "DISABLED",
    "explicit_invocation_required": True,
    "live_smoke": "NOT_EXECUTED",
    "network": "EXPLICIT_ONE_DIRECT_GET_ONLY",
    "credential": "FIXED_OWNER_PRIVATE_STORE_WITH_STAGING_HASH_BINDING_ONLY",
    "provider": "FIXED_RAKUTEN_ICHIBA_ENDPOINT_ONLY",
    "sdk": "ABSENT",
    "filesystem": "PRIVATE_CREDENTIAL_READ_AND_SANITIZED_REPORT_ONLY",
    "repository": "NO_RAW_PROVIDER_MATERIAL_OR_TRACKED_REPOSITORY_PERSISTENCE",
    "storage": "NOT_EXECUTED",
    "persistence": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "external_actions": ["EXPLICIT_ONE_GET"],
    "action_counts": EXPECTED_ACTION_COUNTS,
}
EXPECTED_VERIFICATION: Final = {
    "formal_tst_016": "NOT_EXECUTED",
    "live_auth": "NOT_EXECUTED",
    "live_schema": "NOT_EXECUTED",
    "live_rate": "NOT_EXECUTED",
    "provider_runtime": "NOT_EXECUTED",
    "network": "NOT_EXECUTED",
    "credentials": "NOT_EXECUTED",
    "storage": "NOT_EXECUTED",
    "persistence": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "decision": "LOCAL_INTERFACE_INSTALLABLE_NOT_INSTALLED",
    "approval": None,
    "story_acceptance": False,
    "production_eligible": False,
    "effective_canonical_status": "UNCHANGED",
}


def _validate_owner_local_read_integration(value: object) -> None:
    owner = _mapping(value, "owner_local_read_integration")
    if tuple(owner) != (
        "status",
        "default_activation",
        "evidence_authority",
        "provider_data_classification",
        "provider_credential_profile",
        "raos_environment",
        "runtime",
        "commands",
        "credential_record",
        "registry",
        "transport",
        "normalized_result",
        "verification",
    ):
        _fail("CONTRACT_SCHEMA_DRIFT", "owner_local_read_integration")
    required = {
        "status": "INSTALLABLE_NOT_INSTALLED_OR_EXECUTED",
        "default_activation": "DISABLED_EXPLICIT_INSTALLED_COMMAND_ONLY",
        "evidence_authority": "OWNER_LOCAL_NON_FORMAL_LIVE_EVIDENCE",
        "provider_data_classification": "UNTRUSTED_PROVIDER_DATA",
        "provider_credential_profile": "OWNER_LOCAL_RAKUTEN_PRODUCTION_API",
        "raos_environment": "OWNER_LOCAL_NOT_ENV_STAGING_NOT_RAOS_PRODUCTION",
    }
    for key, expected in required.items():
        _exact(owner[key], expected, f"owner_local_read_integration.{key}")
    runtime = _mapping(owner["runtime"], "owner_local.runtime")
    if (
        tuple(runtime)
        != (
            "name",
            "root",
            "bundle_sha256",
            "launcher_sha256",
            "installer_sha256",
            "install_stage_sha256",
            "install_entry",
            "installed_entry",
            "installer_credential_access",
            "repository_make_entrypoint",
            "install_execution",
        )
        or runtime.get("name") != "rakuten-owner-local"
        or runtime.get("root")
        != "/home/minami/.local/share/raos/rakuten-owner-local/runtime"
        or runtime.get("bundle_sha256") != EXPECTED_OWNER_LOCAL_BUNDLE_SHA256
        or runtime.get("launcher_sha256") != EXPECTED_OWNER_LOCAL_LAUNCHER_SHA256
        or runtime.get("installer_sha256") != EXPECTED_OWNER_LOCAL_INSTALLER_SHA256
        or runtime.get("install_stage_sha256")
        != EXPECTED_OWNER_LOCAL_INSTALL_STAGE_SHA256
        or runtime.get("installer_credential_access") != "FORBIDDEN"
        or runtime.get("repository_make_entrypoint") != "NOT_PROVIDED"
        or runtime.get("install_execution") != "NOT_EXECUTED"
    ):
        _fail("VALUE_MISMATCH", "owner_local.runtime")
    commands = _mapping(owner["commands"], "owner_local.commands")
    if tuple(commands) != (
        "setup",
        "rotate",
        "doctor",
        "list_apis",
        "request",
        "authenticated_request_entry",
        "smoke",
    ):
        _fail("CONTRACT_SCHEMA_DRIFT", "owner_local.commands")
    _exact(
        commands,
        {
            "setup": "HIDDEN_DEV_TTY_NO_EXISTING_RECORD",
            "rotate": "HIDDEN_DEV_TTY_ATOMIC_REPLACEMENT",
            "doctor": "LOCAL_METADATA_AND_CREDENTIAL_SCHEMA_ONLY_NO_NETWORK",
            "list_apis": "FIXED_CLOSED_REGISTRY_NO_NETWORK",
            "request": (
                "request --api <item-search|product-search> "
                "--request-file <absolute-json>"
            ),
            "authenticated_request_entry": (
                "GENERATED_POSITIONAL_FD4_DIGEST_GATE_ARGV_TEMPLATE"
            ),
            "smoke": "smoke --api <item-search|product-search>",
        },
        "owner_local.commands",
    )
    credentials = _mapping(owner["credential_record"], "owner_local.credential_record")
    if (
        tuple(credentials)
        != (
            "path",
            "schema_version",
            "exact_keys",
            "profile",
            "directory_mode",
            "file_mode",
            "symlinks",
            "hardlinks",
            "stability",
            "argv_environment_output_persistence",
        )
        or credentials.get("path") != ".secrets/rakuten-owner-local/credentials.v1.json"
        or credentials.get("schema_version") != 1
        or credentials.get("exact_keys")
        != [
            "schema_version",
            "profile",
            "application_id",
            "access_key",
            "affiliate_id",
        ]
        or credentials.get("profile") != "OWNER_LOCAL_RAKUTEN_PRODUCTION_API"
        or credentials.get("file_mode") != "0600"
        or credentials.get("directory_mode") != "0700"
        or credentials.get("symlinks") != "REJECT"
        or credentials.get("hardlinks") != "REJECT"
        or credentials.get("stability")
        != "DESCRIPTOR_DOUBLE_READ_IDENTITY_SIZE_MTIME_CTIME"
        or credentials.get("argv_environment_output_persistence") != "FORBIDDEN"
    ):
        _fail("VALUE_MISMATCH", "owner_local.credential_record")
    registry = _mapping(owner["registry"], "owner_local.registry")
    if tuple(registry) != ("extensibility", "item-search", "product-search"):
        _fail("CONTRACT_SCHEMA_DRIFT", "owner_local.registry")
    item = _mapping(registry["item-search"], "owner_local.registry.item")
    product = _mapping(registry["product-search"], "owner_local.registry.product")
    if (
        tuple(item)
        != (
            "api_version",
            "path",
            "request_policy",
            "selectors",
            "exact_selector_response_binding",
            "page",
            "review_and_affiliate_rate_inputs",
        )
        or tuple(product)
        != (
            "api_version",
            "path",
            "request_policy",
            "selectors",
            "exact_selector_response_binding",
            "page",
            "sort",
            "review_derived_inputs",
        )
        or registry.get("extensibility") != "REVIEWED_CODE_ENTRY_ONLY"
        or item.get("api_version") != "2026-07-01"
        or item.get("path") != "/ichibams/api/IchibaItem/Search/20260701"
        or item.get("request_policy")
        != "UNCHANGED_ST0502_RakutenItemSearchLiveRequestV1"
        or item.get("selectors") != "EXACTLY_ONE_KEYWORD_GENRE_ITEM_SHOP"
        or item.get("exact_selector_response_binding")
        != (
            "SELECTED_ITEM_CODE_OR_SHOP_CODE_MUST_MATCH_EVERY_RETURNED_RECORD_OR_"
            "RESULT_MISMATCH"
        )
        or item.get("page") != 1
        or item.get("review_and_affiliate_rate_inputs") != "EXCLUDED"
        or product.get("api_version") != "2025-08-01"
        or product.get("path") != "/ichibaproduct/api/Product/Search/20250801"
        or product.get("request_policy") != "OWNER_LOCAL_PRODUCT_SEARCH_V1"
        or product.get("selectors")
        != "KEYWORD_OPTIONAL_GENRE_OR_GENRE_OR_EXCLUSIVE_PRODUCT_ID_OR_CODE"
        or product.get("exact_selector_response_binding")
        != (
            "SELECTED_PRODUCT_ID_OR_CODE_MUST_MATCH_EVERY_RETURNED_RECORD_OR_"
            "RESULT_MISMATCH"
        )
        or product.get("page") != 1
        or product.get("sort") != "standard"
        or product.get("review_derived_inputs") != "EXCLUDED"
    ):
        _fail("VALUE_MISMATCH", "owner_local.registry")
    transport = _mapping(owner["transport"], "owner_local.transport")
    authentication = _mapping(
        transport.get("authentication"), "owner_local.transport.authentication"
    )
    if (
        tuple(transport)
        != (
            "origin",
            "method",
            "authentication",
            "proxy_discovery",
            "tls_override_environment",
            "dns",
            "redirects",
            "retries",
            "pagination_followups",
            "concurrency",
            "ip_fallback",
            "requests_per_invocation_maximum",
            "response_maximum_bytes",
            "response_json",
            "response_summary_relationships",
        )
        or tuple(authentication)
        != ("applicationId", "affiliateId", "header_name", "access_key")
        or authentication
        != {
            "applicationId": "QUERY_ONLY",
            "affiliateId": "QUERY_ONLY",
            "header_name": "accessKey",
            "access_key": "HEADER_ONLY",
        }
        or transport.get("origin") != "openapi.rakuten.co.jp:443"
        or transport.get("method") != "GET"
        or transport.get("proxy_discovery") != "REJECT"
        or transport.get("tls_override_environment") != "REJECT"
        or transport.get("dns")
        != "VALIDATE_ENTIRE_CANDIDATE_SET_PUBLIC_THEN_PIN_FIRST_ONLY"
        or transport.get("redirects") != 0
        or transport.get("retries") != 0
        or transport.get("pagination_followups") != 0
        or transport.get("concurrency") != 0
        or transport.get("ip_fallback") != 0
        or transport.get("requests_per_invocation_maximum") != 1
        or transport.get("response_maximum_bytes") != 2 * 1024 * 1024
        or transport.get("response_json")
        != "STRICT_UTF8_DUPLICATE_NONFINITE_DEPTH_NODE_SCHEMA"
        or transport.get("response_summary_relationships")
        != (
            "PAGE1_EMPTY_ALL_ZERO_OR_NONEMPTY_COUNT_GTE_CARDINALITY_"
            "PAGECOUNT_1_TO_100_FIRST_1_LAST_CARDINALITY"
        )
    ):
        _fail("VALUE_MISMATCH", "owner_local.transport")
    result = _mapping(owner["normalized_result"], "owner_local.result")
    if (
        tuple(result)
        != (
            "directory",
            "path",
            "publication",
            "response_sha256",
            "envelope",
            "url_validation",
            "mandatory_text",
            "credential_reflection",
            "forbidden",
            "request_disposition",
        )
        or result.get("directory") != ".secrets/rakuten-owner-local/results"
        or result.get("path")
        != ".secrets/rakuten-owner-local/results/<UTC-run-id>.json"
        or result.get("publication") != "ATOMIC_0600_NO_REPLACE"
        or result.get("response_sha256") != "SHA256_COMPLETE_BOUNDED_RAW_BODY_BYTES"
        or result.get("envelope")
        != {
            "schema": "RAOS_ST0505_RAKUTEN_OWNER_LOCAL_RESULT_V1",
            "version": 1,
            "exact_object_keys": list(EXPECTED_OWNER_LOCAL_RESULT_OBJECT_KEYS),
            "summary_fields": ["count", "page", "first", "last", "hits", "pageCount"],
            "success_summary": "VALIDATED_INTEGER_VALUES",
            "failure_summary": "ALL_SIX_KEYS_NULL",
            "canonical_json": "UTF8_SORTED_KEYS_COMPACT_TRAILING_LF",
            "compatibility": (
                "REPOSITORY_V1_COMPLETION_RUNTIME_EVIDENCE_NOT_EXECUTED_NO_"
                "DEPLOYED_MIGRATION"
            ),
        }
        or result.get("url_validation")
        != {
            "syntax": {
                "scheme": "EXACT_LOWERCASE_HTTPS",
                "whitespace_and_controls": ("REJECT_ASCII_WHITESPACE_AND_UNICODE_CC"),
                "raw_backslash": "REJECT",
                "host": "VALID_IDNA_DNS_OR_BRACKETED_IPV6_WITH_OPTIONAL_PORT",
                "percent_escapes": "COMPLETE_HEX_PAIR_REQUIRED",
                "userinfo_and_fragment": "REJECT",
            },
            "non_null_https": {
                "item-search": ["itemUrl"],
                "product-search": ["productUrlPC"],
            },
            "nullable_scalar_url_values": {
                "item-search": ["affiliateUrl"],
                "product-search": [
                    "affiliateUrl",
                    "mediumImageUrl",
                    "smallImageUrl",
                ],
            },
            "url_list_values": "NON_NULL_TUPLE_OF_HTTPS_URLS",
            "precedence": (
                "FIELD_PRESENCE_THEN_EXACT_SELECTOR_THEN_URL_VALUE_SHAPE_BEFORE_"
                "CREDENTIAL_REFLECTION"
            ),
            "refusal": "RESPONSE_SCHEMA_DRIFT_BEFORE_SUCCESS_ENVELOPE_OR_PERSISTENCE",
        }
        or result.get("mandatory_text")
        != {
            "item-search": ["itemCode", "itemName"],
            "product-search": ["productCode", "productId"],
            "maximum_characters": 20_000,
            "shape": "NON_NULL_NONEMPTY_NO_EDGE_WHITESPACE_UTF8_STRING",
            "optional_fields_unchanged": (
                "SHOP_CODE_SHOP_NAME_AND_PRODUCT_NAME_REMAIN_OPTIONAL_NULLABLE"
            ),
            "precedence": (
                "MANDATORY_KEY_PRESENCE_THEN_EXACT_SELECTOR_THEN_MANDATORY_TEXT_"
                "THEN_URL_THEN_CREDENTIAL_REFLECTION"
            ),
            "refusal": "RESPONSE_SCHEMA_DRIFT_BEFORE_SUCCESS_ENVELOPE_OR_PERSISTENCE",
        }
        or result.get("credential_reflection")
        != {
            "inspected_text_values": (
                "ALL_NORMALIZED_RECORD_STRING_VALUES_AND_STRING_LIST_MEMBERS"
            ),
            "excluded_typed_values": {
                "summary_fields": [
                    "count",
                    "page",
                    "first",
                    "last",
                    "hits",
                    "pageCount",
                ],
                "normalized_record_types": ["NULL", "INTEGER"],
                "policy": (
                    "VALIDATE_BY_FIELD_SCHEMA_AND_DO_NOT_COMPARE_AS_CREDENTIAL_TEXT"
                ),
                "rationale": "TYPED_SCALAR_COINCIDENCE_IS_NOT_TEXT_REFLECTION",
            },
            "success_persistence_scope": (
                "ALL_SIX_VALIDATED_SUMMARIES_AND_ALL_NORMALIZED_RECORD_VALUES"
            ),
            "representations": (
                "INSPECTED_TEXT_RAW_UTF8_OR_SINGLE_PERCENT_DECODED_BYTES"
            ),
            "match": (
                "ANY_NONEMPTY_KNOWN_CREDENTIAL_VALUE_SUBSTRING_IN_INSPECTED_TEXT"
            ),
            "refusal": ("RESPONSE_SCHEMA_DRIFT_BEFORE_SUCCESS_ENVELOPE_OR_PERSISTENCE"),
            "failure_evidence": (
                "COMPLETE_RESPONSE_METADATA_REQUEST_COUNT_1_NO_MATCHED_VALUE"
            ),
        }
        or result.get("forbidden")
        != [
            "raw body and provider headers or reflected error material",
            "credentials or credential aliases containing values",
            "captions and review bodies",
            "review aggregates and affiliateRate",
            "EPC RPM revenue or finance material",
        ]
        or result.get("request_disposition")
        != ["NOT_SENT", "RESPONSE_RECEIVED", "OUTCOME_AMBIGUOUS"]
    ):
        _fail("VALUE_MISMATCH", "owner_local.result")
    verification = _mapping(owner["verification"], "owner_local.verification")
    if (
        tuple(verification)
        != (
            "fake_and_recorded_only",
            "real_credentials",
            "provider_call",
            "formal_tst_016",
            "env_staging",
            "od_015",
            "raos_production",
        )
        or verification.get("fake_and_recorded_only") is not True
        or verification.get("real_credentials") != "NOT_READ"
        or verification.get("provider_call") != "NOT_EXECUTED"
        or verification.get("formal_tst_016") != "NOT_EXECUTED"
        or verification.get("env_staging") != "NOT_EXECUTED"
        or verification.get("od_015") != "UNRESOLVED"
        or verification.get("raos_production") != "NOT_EXECUTED"
    ):
        _fail("VALUE_MISMATCH", "owner_local.verification")


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    authority = _mapping(contract["authority"], "authority")
    if tuple(authority) != ("precedence", "sources"):
        _fail("CONTRACT_SCHEMA_DRIFT", "authority")
    _exact(
        authority["precedence"],
        "CANONICAL_INTEGRATION_THEN_STORY_THEN_OPEN_DECISION_AND_TEST_CATALOG",
        "authority.precedence",
    )
    _exact(authority["sources"], _expected_source_rows(), "authority.sources")
    _exact(contract["predecessor"], EXPECTED_PREDECESSOR, "predecessor")
    _exact(contract["open_decision"], EXPECTED_OPEN_DECISION, "open_decision")
    _exact(contract["live_smoke_definition"], EXPECTED_SMOKE, "live_smoke_definition")
    _validate_owner_local_read_integration(contract["owner_local_read_integration"])
    _exact(contract["observation_defaults"], EXPECTED_OBSERVATIONS, "observations")
    _exact(
        contract["rate_quota_cost_defaults"],
        EXPECTED_RATE_QUOTA_COST,
        "rate_quota_cost",
    )
    _exact(contract["execution_boundary"], EXPECTED_EXECUTION, "execution")
    _exact(contract["verification_boundary"], EXPECTED_VERIFICATION, "verification")
    _validate_hashes(root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
    _validate_runtime_semantics(root)
    _validate_owner_local_runtime_semantics(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(contract: Mapping[str, Any]) -> dict[str, Any]:
    verification = _mapping(contract["verification_boundary"], "verification")
    plan: dict[str, Any] = {
        "document": dict(_mapping(contract["document"], "document")),
        "authority": contract["authority"],
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "predecessor_binding": contract["predecessor"],
        "open_decision": contract["open_decision"],
        "test_suite": {
            **EXPECTED_TEST_SUITE,
            "formal_execution": "NOT_EXECUTED",
            "evidence": None,
        },
        "live_smoke_definition": contract["live_smoke_definition"],
        "owner_local_read_integration": _owner_local_reference_binding(
            contract["owner_local_read_integration"]
        ),
        "observation_boundary": contract["observation_defaults"],
        "rate_quota_cost_boundary": contract["rate_quota_cost_defaults"],
        "execution_boundary": contract["execution_boundary"],
        "verification_boundary": {
            "projection_only": True,
            "predecessor_connection": "NOT_EXECUTED",
            **dict(verification),
        },
    }
    if tuple(plan) != PLAN_KEYS:
        _fail("PLAN_SCHEMA_DRIFT", "plan")
    return plan


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST0505-RAKUTEN-LIVE-SMOKE-MANIFEST-001",
            "version": "3.0.0",
            "story_id": "ST-0505",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256(_read(root, CONTRACT_PATH, "contract")),
            "authority_inputs": _expected_source_rows(),
            "predecessor_commit": PREDECESSOR_COMMIT,
            "predecessor_inputs": _expected_predecessor_artifacts(),
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
        "boundary": {
            "classification": EXPECTED_DOCUMENT["classification"],
            "executable": True,
            "interface_only": False,
            "default_activation": "DISABLED",
            "installed_entry": "INSTALLABLE_NOT_INSTALLED",
            "owner_local_read_entry": "INSTALLABLE_NOT_INSTALLED_OR_EXECUTED",
            "owner_local_evidence_authority": ("OWNER_LOCAL_NON_FORMAL_LIVE_EVIDENCE"),
            "owner_local_provider_data": "UNTRUSTED_PROVIDER_DATA",
            "repository_make_entrypoints": (
                "NOT_PROVIDED_USE_REVIEWED_DIRECT_COMMANDS"
            ),
            "od_015": "EXTERNAL_EVIDENCE_REQUIRED",
            "safe_default": "RECORDED_FIXTURE_ONLY",
            "live_smoke": "NOT_EXECUTED",
            "network": "NOT_EXECUTED",
            "credentials": "NOT_EXECUTED",
            "provider_runtime": "NOT_EXECUTED",
            "storage": "NOT_EXECUTED",
            "persistence": "NOT_EXECUTED",
            "formal_tst_016": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
            "production_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    reference_bytes = _json_bytes(reference_plan(contract))
    return {
        REFERENCE_PLAN_PATH: reference_bytes,
        MANIFEST_PATH: _manifest_bytes(root, reference_bytes),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = base._output_file(root, relative)  # noqa: SLF001
        try:
            actual = path.read_bytes()
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative, content in outputs.items():
        base._atomic_write(root, relative, content)  # noqa: SLF001


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(check=args.check)
    except (RakutenLiveSmokeReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0505 Rakuten live-smoke reference plan checked"
        if args.check
        else "ST-0505 Rakuten live-smoke reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
