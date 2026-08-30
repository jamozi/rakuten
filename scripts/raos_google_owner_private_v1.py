#!/usr/bin/env python3
"""Create fixed owner-private GSC/GA4 bindings and a sanitized receipt."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
from pathlib import Path
import re
import sys
from typing import Final, NoReturn, cast
from uuid import UUID


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.google_live import (  # noqa: E402
    FixedOwnerPrivateAnalyticsSiteBindings,
    _PinnedOwnerPrivateGoogleTree,
)
from raos.domain.analytics.google_live import (  # noqa: E402
    AnalyticsSiteBinding,
    GA4_EVENT_PARAMETER_NAMES,
    GA4_READONLY_SCOPE,
    GSC_READONLY_SCOPE,
    GoogleProviderFailure,
    canonical_json_bytes,
    is_google_utc_timestamp,
)
from raos.migrations.catalog import GOOGLE_ANALYTICS_LIVE_REVISION  # noqa: E402


DEFAULT_PRIVATE_ROOT: Final = REPOSITORY_ROOT / ".secrets/editorial-portfolio-v3"
GSC_RESOURCE: Final = "sc-domain:kurashinoshirube.com"
GOOGLE_ROOT_NAME: Final = "google"
PROVIDERS: Final = ("gsc", "ga4")
CREDENTIAL_FILE_NAME: Final = "service-account.json"
BINDING_FILE_NAME: Final = "binding.v1.json"
ADMIN_READBACK_FILE_NAME: Final = "admin-readback.v1.json"
RECEIPT_FILE_NAME: Final = "binding-receipt.v1.json"
LOCAL_SCOPE_FILE_NAME: Final = "local-scope.v1.json"
RECEIPT_SCHEMA: Final = "RAOS_GOOGLE_OWNER_PRIVATE_BINDING_RECEIPT_V1"
LOCAL_SCOPE_SCHEMA: Final = "raos.owner-private.google-local-scope.v1"
COMPLETED_STATE: Final = "OWNER_PRIVATE_BINDINGS_BOUND"
MATERIALIZING_STATE: Final = "OWNER_PRIVATE_BINDINGS_MATERIALIZING"
GSC_ADMIN_READBACK_SCHEMA: Final = "RAOS_GSC_ADMIN_READBACK_V1"
GA4_ADMIN_READBACK_SCHEMA: Final = "RAOS_GA4_ADMIN_READBACK_V1"
SITE_ORIGIN: Final = "https://kurashinoshirube.com"
MAX_PRIVATE_FILE_BYTES: Final = 1024 * 1024

_PROJECT_ID: Final = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]\Z", re.ASCII)
_SERVICE_ACCOUNT_LOCAL_PART: Final = re.compile(
    r"[a-z0-9][a-z0-9._+-]{0,126}\Z", re.ASCII
)
_PROPERTY_ID: Final = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
_PRIVATE_KEY_BEGIN: Final = "-----BEGIN PRIVATE " + "KEY-----\n"
_PRIVATE_KEY_END: Final = "-----END PRIVATE " + "KEY-----"
_GSC_READBACK_KEYS: Final = frozenset(
    {
        "captured_at",
        "is_owner",
        "permission",
        "resource",
        "row_count",
        "schema",
        "service_account_readback",
    }
)
_GA4_READBACK_KEYS: Final = frozenset(
    {
        "account_id",
        "captured_at",
        "currency_code",
        "custom_dimensions",
        "property_display_name",
        "property_id",
        "property_resource",
        "schema",
        "stream_origin",
        "viewer_is_administrator",
        "viewer_service_account_readback",
    }
)
_GA4_CUSTOM_DIMENSION_KEYS: Final = frozenset(
    {
        "display_name",
        "event_scope_readback",
        "parameter_name",
        "row_count",
        "scope",
    }
)
_LOCAL_SCOPE_KEYS: Final = frozenset(
    {
        "database_revision",
        "ga4_ops_job_id",
        "gsc_ops_job_id",
        "schema_version",
        "scope_initialized",
        "site_id",
    }
)


class GoogleOwnerPrivateFailure(RuntimeError):
    """Stable failure that never contains an owner-private value or path."""


def _fail(code: str) -> NoReturn:
    raise GoogleOwnerPrivateFailure(code) from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-root",
        type=Path,
        default=DEFAULT_PRIVATE_ROOT,
        help="existing absolute owner-private directory; mode must be 0700",
    )
    return parser


def _text(document: Mapping[str, object], key: str, *, maximum: int) -> str:
    value = document.get(key)
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or "\x00" in value
    ):
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_CREDENTIAL_INVALID")
    return value


def _credential_identity(document: Mapping[str, object]) -> tuple[str, str]:
    project_id = _text(document, "project_id", maximum=30)
    client_email = _text(document, "client_email", maximum=254)
    private_key_value = document.get("private_key")
    if (
        document.get("type") != "service_account"
        or document.get("token_uri") != "https://oauth2.googleapis.com/token"
        or _PROJECT_ID.fullmatch(project_id) is None
        or type(private_key_value) is not str
        or not 1 <= len(private_key_value) <= 64 * 1024
        or "\x00" in private_key_value
    ):
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_CREDENTIAL_INVALID")
    private_key = private_key_value
    if not private_key.startswith(
        _PRIVATE_KEY_BEGIN
    ) or not private_key.rstrip().endswith(_PRIVATE_KEY_END):
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_CREDENTIAL_INVALID")
    suffix = f"@{project_id}.iam.gserviceaccount.com"
    if not client_email.endswith(suffix):
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_CREDENTIAL_INVALID")
    local_part = client_email.removesuffix(suffix)
    if _SERVICE_ACCOUNT_LOCAL_PART.fullmatch(local_part) is None:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_CREDENTIAL_INVALID")
    return project_id, client_email


def _site_uuid(value: object) -> UUID:
    if type(value) is not str:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_SITE_INVALID")
    try:
        site_id = UUID(value)
    except AttributeError, TypeError, ValueError:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_SITE_INVALID")
    if site_id.int == 0:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_SITE_INVALID")
    return site_id


def _site_uuid_from_local_scope(document: Mapping[str, object]) -> UUID:
    if (
        set(document) != _LOCAL_SCOPE_KEYS
        or document.get("schema_version") != LOCAL_SCOPE_SCHEMA
        or document.get("scope_initialized") is not True
        or document.get("database_revision") != GOOGLE_ANALYTICS_LIVE_REVISION
    ):
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_LOCAL_SCOPE_INVALID")
    site_id = _site_uuid(document.get("site_id"))
    gsc_job_id = _site_uuid(document.get("gsc_ops_job_id"))
    ga4_job_id = _site_uuid(document.get("ga4_ops_job_id"))
    if len({site_id, gsc_job_id, ga4_job_id}) != 3:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_LOCAL_SCOPE_INVALID")
    return site_id


def _property_id(value: object) -> str:
    if type(value) is not str or _PROPERTY_ID.fullmatch(value) is None:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_PROPERTY_INVALID")
    return value


def _valid_readback_text(value: object, *, maximum: int) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= maximum
        and value == value.strip()
        and "\x00" not in value
    )


def _validate_gsc_admin_readback(document: Mapping[str, object]) -> None:
    if (
        set(document) != _GSC_READBACK_KEYS
        or document.get("schema") != GSC_ADMIN_READBACK_SCHEMA
        or not is_google_utc_timestamp(document.get("captured_at"))
        or document.get("resource") != GSC_RESOURCE
        or document.get("permission") != "RESTRICTED"
        or type(document.get("row_count")) is not int
        or document.get("row_count") != 1
        or document.get("service_account_readback") is not True
        or document.get("is_owner") is not False
    ):
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_ADMIN_READBACK_INVALID")


def _validate_ga4_admin_readback(
    document: Mapping[str, object], *, property_id: str
) -> None:
    custom_dimensions = document.get("custom_dimensions")
    if (
        set(document) != _GA4_READBACK_KEYS
        or document.get("schema") != GA4_ADMIN_READBACK_SCHEMA
        or not is_google_utc_timestamp(document.get("captured_at"))
        or not _valid_readback_text(document.get("account_id"), maximum=20)
        or _PROPERTY_ID.fullmatch(cast(str, document.get("account_id"))) is None
        or document.get("property_id") != property_id
        or document.get("property_resource") != f"properties/{property_id}"
        or not _valid_readback_text(document.get("property_display_name"), maximum=100)
        or document.get("stream_origin") != SITE_ORIGIN
        or document.get("currency_code") != "JPY"
        or document.get("viewer_service_account_readback") is not True
        or document.get("viewer_is_administrator") is not False
        or type(custom_dimensions) is not list
        or len(custom_dimensions) != len(GA4_EVENT_PARAMETER_NAMES)
    ):
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_ADMIN_READBACK_INVALID")
    observed_parameters: list[str] = []
    for value in cast(list[object], custom_dimensions):
        if type(value) is not dict:
            _fail("RAOS_GOOGLE_OWNER_PRIVATE_ADMIN_READBACK_INVALID")
        row = cast(dict[str, object], value)
        parameter = row.get("parameter_name")
        if (
            set(row) != _GA4_CUSTOM_DIMENSION_KEYS
            or type(parameter) is not str
            or row.get("display_name") != parameter
            or row.get("scope") != "EVENT"
            or type(row.get("row_count")) is not int
            or row.get("row_count") != 1
            or row.get("event_scope_readback") is not True
        ):
            _fail("RAOS_GOOGLE_OWNER_PRIVATE_ADMIN_READBACK_INVALID")
        observed_parameters.append(parameter)
    if tuple(observed_parameters) != GA4_EVENT_PARAMETER_NAMES:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_ADMIN_READBACK_INVALID")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _binding_document(
    *, provider: str, site_id: UUID, resource: str, client_email: str
) -> dict[str, object]:
    scope = {"GSC": GSC_READONLY_SCOPE, "GA4": GA4_READONLY_SCOPE}[provider]
    document: dict[str, object] = {
        "schema_version": 1,
        "provider": provider,
        "site_id": str(site_id),
        "resource": resource,
        "credential_file": CREDENTIAL_FILE_NAME,
        "service_account_email_sha256": _sha256(client_email.encode("utf-8")),
        "scopes": [scope],
    }
    try:
        AnalyticsSiteBinding(
            provider=provider,
            site_id=site_id,
            resource=resource,
            credential_path=f"/owner-private/google/{provider.lower()}/"
            f"{CREDENTIAL_FILE_NAME}",
            service_account_email_sha256=cast(
                str, document["service_account_email_sha256"]
            ),
            scopes=(scope,),
        )
    except GoogleProviderFailure:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_BINDING_INVALID")
    return document


def _receipt_document(
    *,
    site_id: UUID,
    binding_hashes: Mapping[str, str],
    admin_readback_hashes: Mapping[str, str],
    credential_readback_cohashes: Mapping[str, str],
    state: str = COMPLETED_STATE,
) -> dict[str, object]:
    if state not in {COMPLETED_STATE, MATERIALIZING_STATE}:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_RECEIPT_INVALID")
    binding_set_hash = _sha256(canonical_json_bytes(dict(binding_hashes)))
    readback_set_hash = _sha256(canonical_json_bytes(dict(admin_readback_hashes)))
    cohash_set_hash = _sha256(canonical_json_bytes(dict(credential_readback_cohashes)))
    return {
        "schema": RECEIPT_SCHEMA,
        "version": 1,
        "site_id": str(site_id),
        "state": state,
        "binding_canonical_sha256s": dict(binding_hashes),
        "binding_set_canonical_sha256": binding_set_hash,
        "admin_readback_canonical_sha256s": dict(admin_readback_hashes),
        "admin_readback_set_canonical_sha256": readback_set_hash,
        "credential_readback_binding_canonical_sha256s": dict(
            credential_readback_cohashes
        ),
        "credential_readback_binding_set_canonical_sha256": cohash_set_hash,
        "verification": {
            "distinct_service_accounts": True,
            "same_gcp_project": True,
            "exact_gsc_resource": True,
            "numeric_ga4_property": True,
            "read_only_scopes": True,
            "gsc_restricted_not_owner_readback": True,
            "ga4_viewer_not_administrator_readback": True,
            "ga4_jpy_configuration_readback": True,
            "ga4_event_custom_dimensions_readback": True,
            "credential_readback_cohash_created": True,
            "readback_cryptographically_names_service_account": False,
        },
        "authority": {
            "external_write": False,
            "measurement_gate_enabled": False,
            "provider_configuration_changed": False,
            "publication_authorized": False,
            "separate_admin_approval_asserted": False,
        },
    }


def _replace_pinned(
    tree: _PinnedOwnerPrivateGoogleTree,
    location: str,
    name: str,
    content: bytes,
    *,
    expected: tuple[int, ...] | None,
) -> tuple[int, ...]:
    return tree.atomic_replace(
        location,
        name,
        content,
        expected=expected,
    )


def _assert_inputs_unchanged(
    tree: _PinnedOwnerPrivateGoogleTree,
    snapshots: Mapping[tuple[str, str], bytes],
) -> None:
    for (location, name), expected in snapshots.items():
        _, observed = tree.read_json(location, name, maximum=MAX_PRIVATE_FILE_BYTES)
        if observed != expected:
            _fail("RAOS_GOOGLE_OWNER_PRIVATE_INPUT_CHANGED")
    tree.verify()


def _restore_materializing_marker(
    tree: _PinnedOwnerPrivateGoogleTree,
    materializing_receipt_bytes: bytes,
) -> None:
    for _ in range(2):
        try:
            current = tree.entry_identity("google", RECEIPT_FILE_NAME)
            _replace_pinned(
                tree,
                "google",
                RECEIPT_FILE_NAME,
                materializing_receipt_bytes,
                expected=current,
            )
            return
        except GoogleOwnerPrivateFailure, GoogleProviderFailure:
            try:
                document, _ = tree.read_json(
                    "google",
                    RECEIPT_FILE_NAME,
                    maximum=MAX_PRIVATE_FILE_BYTES,
                )
            except GoogleProviderFailure:
                continue
            if document.get("state") == MATERIALIZING_STATE:
                return
    _fail("RAOS_GOOGLE_OWNER_PRIVATE_COMMIT_MARKER_RECOVERY_FAILED")


def _materialize_pinned(
    *, private_root: Path, tree: _PinnedOwnerPrivateGoogleTree
) -> dict[str, object]:
    local_scope, local_scope_canonical = tree.read_json(
        "google", LOCAL_SCOPE_FILE_NAME, maximum=MAX_PRIVATE_FILE_BYTES
    )
    site_id = _site_uuid_from_local_scope(local_scope)

    identities: dict[str, tuple[str, str]] = {}
    admin_readbacks: dict[str, dict[str, object]] = {}
    admin_readback_hashes: dict[str, str] = {}
    input_snapshots: dict[tuple[str, str], bytes] = {
        ("google", LOCAL_SCOPE_FILE_NAME): local_scope_canonical
    }
    for provider in PROVIDERS:
        credential, credential_canonical = tree.read_json(
            provider,
            CREDENTIAL_FILE_NAME,
            maximum=MAX_PRIVATE_FILE_BYTES,
        )
        identities[provider] = _credential_identity(credential)
        input_snapshots[(provider, CREDENTIAL_FILE_NAME)] = credential_canonical
        readback, readback_canonical = tree.read_json(
            provider,
            ADMIN_READBACK_FILE_NAME,
            maximum=MAX_PRIVATE_FILE_BYTES,
        )
        admin_readbacks[provider] = readback
        admin_readback_hashes[provider.upper()] = _sha256(readback_canonical)
        input_snapshots[(provider, ADMIN_READBACK_FILE_NAME)] = readback_canonical

    _validate_gsc_admin_readback(admin_readbacks["gsc"])
    property_id = _property_id(admin_readbacks["ga4"].get("property_id"))
    _validate_ga4_admin_readback(admin_readbacks["ga4"], property_id=property_id)

    gsc_project, gsc_email = identities["gsc"]
    ga4_project, ga4_email = identities["ga4"]
    if gsc_project != ga4_project:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_PROJECT_MISMATCH")
    if gsc_email == ga4_email:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_IDENTITY_REUSED")

    bindings = {
        "GSC": _binding_document(
            provider="GSC",
            site_id=site_id,
            resource=GSC_RESOURCE,
            client_email=gsc_email,
        ),
        "GA4": _binding_document(
            provider="GA4",
            site_id=site_id,
            resource=f"properties/{property_id}",
            client_email=ga4_email,
        ),
    }
    binding_bytes = {
        provider: canonical_json_bytes(document)
        for provider, document in bindings.items()
    }
    binding_hashes = {
        provider: _sha256(content) for provider, content in binding_bytes.items()
    }
    project_sha256 = _sha256(gsc_project.encode("utf-8"))
    credential_readback_cohashes = {
        provider: _sha256(
            canonical_json_bytes(
                {
                    "admin_readback_canonical_sha256": admin_readback_hashes[provider],
                    "binding_canonical_sha256": binding_hashes[provider],
                    "gcp_project_id_sha256": project_sha256,
                    "service_account_email_sha256": bindings[provider][
                        "service_account_email_sha256"
                    ],
                }
            )
        )
        for provider in ("GSC", "GA4")
    }
    receipt = _receipt_document(
        site_id=site_id,
        binding_hashes=binding_hashes,
        admin_readback_hashes=admin_readback_hashes,
        credential_readback_cohashes=credential_readback_cohashes,
    )
    receipt_bytes = canonical_json_bytes(receipt)
    materializing_receipt = _receipt_document(
        site_id=site_id,
        binding_hashes=binding_hashes,
        admin_readback_hashes=admin_readback_hashes,
        credential_readback_cohashes=credential_readback_cohashes,
        state=MATERIALIZING_STATE,
    )
    materializing_receipt_bytes = canonical_json_bytes(materializing_receipt)

    output_locations = {
        "GSC": "gsc",
        "GA4": "ga4",
        "RECEIPT": "google",
    }
    expected_outputs = {
        key: tree.entry_identity(location, BINDING_FILE_NAME)
        if key != "RECEIPT"
        else tree.entry_identity(location, RECEIPT_FILE_NAME)
        for key, location in output_locations.items()
    }
    # The receipt is the commit marker.  Invalidate any earlier completed
    # generation before replacing either binding so a crash can only leave a
    # fail-closed MATERIALIZING generation behind.
    materializing_identity = _replace_pinned(
        tree,
        "google",
        RECEIPT_FILE_NAME,
        materializing_receipt_bytes,
        expected=expected_outputs["RECEIPT"],
    )
    _replace_pinned(
        tree,
        "gsc",
        BINDING_FILE_NAME,
        binding_bytes["GSC"],
        expected=expected_outputs["GSC"],
    )
    _replace_pinned(
        tree,
        "ga4",
        BINDING_FILE_NAME,
        binding_bytes["GA4"],
        expected=expected_outputs["GA4"],
    )
    _assert_inputs_unchanged(tree, input_snapshots)
    try:
        loaded = FixedOwnerPrivateAnalyticsSiteBindings._for_generation_state(
            private_root,
            expected_state=MATERIALIZING_STATE,
        )
    except GoogleProviderFailure:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_COMPLETION_INVALID")
    if loaded.gsc().site_id != site_id or loaded.ga4().site_id != site_id:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_COMPLETION_INVALID")
    _assert_inputs_unchanged(tree, input_snapshots)
    try:
        _replace_pinned(
            tree,
            "google",
            RECEIPT_FILE_NAME,
            receipt_bytes,
            expected=materializing_identity,
        )
    except GoogleOwnerPrivateFailure:
        _restore_materializing_marker(tree, materializing_receipt_bytes)
        raise
    except GoogleProviderFailure:
        _restore_materializing_marker(tree, materializing_receipt_bytes)
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_FINAL_RECEIPT_FAILED")
    return receipt


def materialize_bindings(*, private_root: Path) -> dict[str, object]:
    try:
        with _PinnedOwnerPrivateGoogleTree(private_root) as tree:
            return _materialize_pinned(private_root=private_root, tree=tree)
    except GoogleOwnerPrivateFailure:
        raise
    except GoogleProviderFailure:
        _fail("RAOS_GOOGLE_OWNER_PRIVATE_PINNED_IO_INVALID")


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        materialize_bindings(private_root=arguments.private_root)
    except GoogleOwnerPrivateFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("RAOS_GOOGLE_OWNER_PRIVATE_BINDINGS status=PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
