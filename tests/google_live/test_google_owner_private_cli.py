from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Final

import pytest

import raos.adapters.google_live as google_live_adapter
from raos.adapters.google_live import FixedOwnerPrivateAnalyticsSiteBindings
from raos.domain.analytics.google_live import GoogleProviderFailure


ROOT: Final = Path(__file__).resolve().parents[2]
SCRIPT: Final = ROOT / "scripts/raos_google_owner_private_v1.py"
SPEC = importlib.util.spec_from_file_location("raos_google_owner_private_v1", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
cli = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cli
SPEC.loader.exec_module(cli)

SITE_ID: Final = "018f3e90-7b00-7000-8000-000000000805"
PROPERTY_ID: Final = "123456789"
ACCOUNT_ID: Final = "987654321"
PROJECT_ID: Final = "owner-analytics-123"
GSC_EMAIL: Final = f"raos-gsc@{PROJECT_ID}.iam.gserviceaccount.com"
GA4_EMAIL: Final = f"raos-ga4@{PROJECT_ID}.iam.gserviceaccount.com"
PRIVATE_KEY_MARKER: Final = "fixture-private-material-never-print"


@pytest.fixture
def posix_tmp_path() -> Path:
    with tempfile.TemporaryDirectory(
        prefix="raos-google-owner-private-v1-", dir="/tmp"
    ) as temporary:
        yield Path(temporary)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def _write_private(path: Path, value: object) -> None:
    path.write_bytes(_json_bytes(value))
    path.chmod(0o600)


def _credential(*, project_id: str, email: str) -> dict[str, object]:
    return {
        "type": "service_account",
        "project_id": project_id,
        "private_key_id": "fixture-key-id",
        "private_key": (
            "-----BEGIN PRIVATE "
            "KEY-----\n"
            f"{PRIVATE_KEY_MARKER}\n"
            "-----END PRIVATE "
            "KEY-----\n"
        ),
        "client_email": email,
        "client_id": "100000000000000000001",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def _private_tree(
    tmp_path: Path,
    *,
    gsc_project: str = PROJECT_ID,
    ga4_project: str = PROJECT_ID,
    gsc_email: str | None = None,
    ga4_email: str | None = None,
) -> Path:
    root = tmp_path / "owner-private"
    google = root / "google"
    gsc = google / "gsc"
    ga4 = google / "ga4"
    for directory in (root, google, gsc, ga4):
        directory.mkdir(exist_ok=True)
        directory.chmod(0o700)
    _write_private(
        google / cli.LOCAL_SCOPE_FILE_NAME,
        {
            "database_revision": cli.GOOGLE_ANALYTICS_LIVE_REVISION,
            "ga4_ops_job_id": "018f3e90-7b00-7000-8000-000000000807",
            "gsc_ops_job_id": "018f3e90-7b00-7000-8000-000000000806",
            "schema_version": cli.LOCAL_SCOPE_SCHEMA,
            "scope_initialized": True,
            "site_id": SITE_ID,
        },
    )
    resolved_gsc_email = gsc_email or (
        f"raos-gsc@{gsc_project}.iam.gserviceaccount.com"
    )
    resolved_ga4_email = ga4_email or (
        f"raos-ga4@{ga4_project}.iam.gserviceaccount.com"
    )
    _write_private(
        gsc / "service-account.json",
        _credential(project_id=gsc_project, email=resolved_gsc_email),
    )
    _write_private(
        ga4 / "service-account.json",
        _credential(project_id=ga4_project, email=resolved_ga4_email),
    )
    _write_private(
        gsc / "admin-readback.v1.json",
        {
            "captured_at": "2026-08-30T12:34:56.000Z",
            "is_owner": False,
            "permission": "RESTRICTED",
            "resource": cli.GSC_RESOURCE,
            "row_count": 1,
            "schema": cli.GSC_ADMIN_READBACK_SCHEMA,
            "service_account_readback": True,
        },
    )
    _write_private(
        ga4 / "admin-readback.v1.json",
        {
            "account_id": ACCOUNT_ID,
            "captured_at": "2026-08-30T12:35:56.000Z",
            "currency_code": "JPY",
            "custom_dimensions": [
                {
                    "display_name": parameter,
                    "event_scope_readback": True,
                    "parameter_name": parameter,
                    "row_count": 1,
                    "scope": "EVENT",
                }
                for parameter in cli.GA4_EVENT_PARAMETER_NAMES
            ],
            "property_display_name": "Fixture property",
            "property_id": PROPERTY_ID,
            "property_resource": f"properties/{PROPERTY_ID}",
            "schema": cli.GA4_ADMIN_READBACK_SCHEMA,
            "stream_origin": cli.SITE_ORIGIN,
            "viewer_is_administrator": False,
            "viewer_service_account_readback": True,
        },
    )
    return root


def _arguments(root: Path) -> list[str]:
    return ["--private-root", root.as_posix()]


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(cli.canonical_json_bytes(value)).hexdigest()


def _assert_materializing_only(root: Path, *, semantic_valid: bool = True) -> None:
    receipt = json.loads((root / "google/binding-receipt.v1.json").read_text())
    assert receipt["state"] == cli.MATERIALIZING_STATE
    with pytest.raises(GoogleProviderFailure):
        FixedOwnerPrivateAnalyticsSiteBindings(root)
    if semantic_valid:
        materializing = FixedOwnerPrivateAnalyticsSiteBindings._for_generation_state(
            root,
            expected_state=cli.MATERIALIZING_STATE,
        )
        assert str(materializing.gsc().site_id) == SITE_ID
    else:
        with pytest.raises(GoogleProviderFailure):
            FixedOwnerPrivateAnalyticsSiteBindings._for_generation_state(
                root,
                expected_state=cli.MATERIALIZING_STATE,
            )


def test_cli_writes_exact_bindings_and_sanitized_deterministic_receipt(
    posix_tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _private_tree(posix_tmp_path)

    assert cli.main(_arguments(root)) == 0
    captured = capsys.readouterr()
    assert captured.out == "RAOS_GOOGLE_OWNER_PRIVATE_BINDINGS status=PASS\n"
    assert captured.err == ""

    gsc_path = root / "google/gsc/binding.v1.json"
    ga4_path = root / "google/ga4/binding.v1.json"
    receipt_path = root / "google/binding-receipt.v1.json"
    for output in (gsc_path, ga4_path, receipt_path):
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
        assert output.stat().st_nlink == 1

    gsc = json.loads(gsc_path.read_text())
    ga4 = json.loads(ga4_path.read_text())
    assert gsc == {
        "credential_file": "service-account.json",
        "provider": "GSC",
        "resource": "sc-domain:kurashinoshirube.com",
        "schema_version": 1,
        "scopes": [cli.GSC_READONLY_SCOPE],
        "service_account_email_sha256": hashlib.sha256(GSC_EMAIL.encode()).hexdigest(),
        "site_id": SITE_ID,
    }
    assert ga4 == {
        "credential_file": "service-account.json",
        "provider": "GA4",
        "resource": f"properties/{PROPERTY_ID}",
        "schema_version": 1,
        "scopes": [cli.GA4_READONLY_SCOPE],
        "service_account_email_sha256": hashlib.sha256(GA4_EMAIL.encode()).hexdigest(),
        "site_id": SITE_ID,
    }
    loaded = FixedOwnerPrivateAnalyticsSiteBindings(root)
    assert str(loaded.gsc().site_id) == SITE_ID
    assert loaded.ga4().property_id == PROPERTY_ID

    receipt_before = receipt_path.read_bytes()
    receipt = json.loads(receipt_before)
    expected_binding_hashes = {"GA4": _canonical_hash(ga4), "GSC": _canonical_hash(gsc)}
    assert receipt["binding_canonical_sha256s"] == expected_binding_hashes
    assert receipt["binding_set_canonical_sha256"] == _canonical_hash(
        expected_binding_hashes
    )
    readback_hashes = receipt["admin_readback_canonical_sha256s"]
    assert readback_hashes == {
        "GA4": _canonical_hash(
            json.loads((root / "google/ga4/admin-readback.v1.json").read_text())
        ),
        "GSC": _canonical_hash(
            json.loads((root / "google/gsc/admin-readback.v1.json").read_text())
        ),
    }
    assert receipt["admin_readback_set_canonical_sha256"] == _canonical_hash(
        readback_hashes
    )
    email_hashes = {
        "GA4": hashlib.sha256(GA4_EMAIL.encode()).hexdigest(),
        "GSC": hashlib.sha256(GSC_EMAIL.encode()).hexdigest(),
    }
    project_hash = hashlib.sha256(PROJECT_ID.encode()).hexdigest()
    expected_cohashes = {
        provider: _canonical_hash(
            {
                "admin_readback_canonical_sha256": readback_hashes[provider],
                "binding_canonical_sha256": expected_binding_hashes[provider],
                "gcp_project_id_sha256": project_hash,
                "service_account_email_sha256": email_hashes[provider],
            }
        )
        for provider in ("GA4", "GSC")
    }
    assert receipt["credential_readback_binding_canonical_sha256s"] == (
        expected_cohashes
    )
    assert receipt["credential_readback_binding_set_canonical_sha256"] == (
        _canonical_hash(expected_cohashes)
    )
    assert receipt["authority"] == {
        "external_write": False,
        "measurement_gate_enabled": False,
        "provider_configuration_changed": False,
        "publication_authorized": False,
        "separate_admin_approval_asserted": False,
    }

    serialized_receipt = receipt_before.decode()
    for private_value in (
        PROJECT_ID,
        GSC_EMAIL,
        GA4_EMAIL,
        PROPERTY_ID,
        ACCOUNT_ID,
        PRIVATE_KEY_MARKER,
        "Fixture property",
    ):
        assert private_value not in serialized_receipt
        assert private_value not in captured.out
        assert private_value not in captured.err

    assert cli.main(_arguments(root)) == 0
    capsys.readouterr()
    assert receipt_path.read_bytes() == receipt_before


@pytest.mark.parametrize(
    ("relative_path", "insecure_mode"),
    [
        (".", 0o755),
        ("google", 0o755),
        ("google/gsc", 0o755),
        ("google/gsc/service-account.json", 0o644),
        ("google/ga4/admin-readback.v1.json", 0o640),
        ("google/local-scope.v1.json", 0o640),
    ],
)
def test_cli_rejects_insecure_private_modes(
    posix_tmp_path: Path, relative_path: str, insecure_mode: int
) -> None:
    root = _private_tree(posix_tmp_path)
    os.chmod(root / relative_path, insecure_mode)

    assert cli.main(_arguments(root)) == 1
    assert not (root / "google/gsc/binding.v1.json").exists()
    assert not (root / "google/binding-receipt.v1.json").exists()


def test_cli_rejects_symlinked_input(posix_tmp_path: Path) -> None:
    root = _private_tree(posix_tmp_path)
    credential = root / "google/gsc/service-account.json"
    target = posix_tmp_path / "credential-target.json"
    credential.rename(target)
    credential.symlink_to(target)

    assert cli.main(_arguments(root)) == 1
    assert target.read_bytes() == _json_bytes(
        _credential(project_id=PROJECT_ID, email=GSC_EMAIL)
    )
    assert not (root / "google/gsc/binding.v1.json").exists()


def test_cli_refuses_symlinked_output_without_touching_target(
    posix_tmp_path: Path,
) -> None:
    root = _private_tree(posix_tmp_path)
    victim = posix_tmp_path / "victim.json"
    victim.write_text("owner-data-must-survive", encoding="utf-8")
    victim.chmod(0o600)
    output = root / "google/gsc/binding.v1.json"
    output.symlink_to(victim)

    assert cli.main(_arguments(root)) == 1
    assert output.is_symlink()
    assert victim.read_text(encoding="utf-8") == "owner-data-must-survive"
    assert not (root / "google/ga4/binding.v1.json").exists()
    assert not (root / "google/binding-receipt.v1.json").exists()


def test_cli_rejects_hard_linked_input(posix_tmp_path: Path) -> None:
    root = _private_tree(posix_tmp_path)
    credential = root / "google/gsc/service-account.json"
    os.link(credential, posix_tmp_path / "credential-hard-link.json")

    assert cli.main(_arguments(root)) == 1
    assert not (root / "google/gsc/binding.v1.json").exists()


def test_cli_detects_input_path_replacement_during_read(
    posix_tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _private_tree(posix_tmp_path)
    local_scope = root / "google/local-scope.v1.json"
    replacement_value = json.loads(local_scope.read_text())
    original_read = google_live_adapter.os.read
    replaced = False

    def replacing_read(descriptor: int, amount: int) -> bytes:
        nonlocal replaced
        payload = original_read(descriptor, amount)
        if not replaced:
            replaced = True
            local_scope.rename(posix_tmp_path / "local-scope-opened.json")
            _write_private(local_scope, replacement_value)
        return payload

    monkeypatch.setattr(google_live_adapter.os, "read", replacing_read)
    assert cli.main(_arguments(root)) == 1
    assert replaced is True
    assert not (root / "google/gsc/binding.v1.json").exists()


def test_interrupted_generation_leaves_nonloadable_completion_marker(
    posix_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _private_tree(posix_tmp_path)
    assert cli.main(_arguments(root)) == 0
    capsys.readouterr()
    ga4_readback_path = root / "google/ga4/admin-readback.v1.json"
    ga4_readback = json.loads(ga4_readback_path.read_text())
    ga4_readback["property_id"] = "223456789"
    ga4_readback["property_resource"] = "properties/223456789"
    _write_private(ga4_readback_path, ga4_readback)
    original_replace = cli._replace_pinned

    def interrupted_replace(
        tree: object,
        location: str,
        name: str,
        content: bytes,
        *,
        expected: tuple[int, ...] | None,
    ) -> tuple[int, ...]:
        if location == "ga4" and name == cli.BINDING_FILE_NAME:
            raise cli.GoogleOwnerPrivateFailure(
                "RAOS_GOOGLE_OWNER_PRIVATE_TEST_INTERRUPTION"
            )
        return original_replace(
            tree,
            location,
            name,
            content,
            expected=expected,
        )

    monkeypatch.setattr(cli, "_replace_pinned", interrupted_replace)
    assert cli.main(_arguments(root)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "RAOS_GOOGLE_OWNER_PRIVATE_TEST_INTERRUPTION\n"
    _assert_materializing_only(root, semantic_valid=False)


@pytest.mark.parametrize("ancestor", ["root", "google", "provider"])
def test_cli_rejects_ancestor_replacement_after_materializing_marker(
    posix_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ancestor: str,
) -> None:
    root = _private_tree(posix_tmp_path)
    if ancestor == "root":
        original = root
        moved = posix_tmp_path / "owner-private-opened"
    elif ancestor == "google":
        original = root / "google"
        moved = root / "google-opened"
    else:
        original = root / "google/gsc"
        moved = root / "google/gsc-opened"
    original_replace = cli._replace_pinned
    replaced = False

    def replacing_ancestor(
        tree: object,
        location: str,
        name: str,
        content: bytes,
        *,
        expected: tuple[int, ...] | None,
    ) -> tuple[int, ...]:
        nonlocal replaced
        result = original_replace(
            tree,
            location,
            name,
            content,
            expected=expected,
        )
        if (
            not replaced
            and location == "google"
            and name == cli.RECEIPT_FILE_NAME
            and json.loads(content)["state"] == cli.MATERIALIZING_STATE
        ):
            replaced = True
            original.rename(moved)
            original.symlink_to(moved, target_is_directory=True)
        return result

    monkeypatch.setattr(cli, "_replace_pinned", replacing_ancestor)
    assert cli.main(_arguments(root)) == 1
    assert replaced is True
    receipt = json.loads((root / "google/binding-receipt.v1.json").read_text())
    assert receipt["state"] == cli.MATERIALIZING_STATE
    with pytest.raises(GoogleProviderFailure):
        FixedOwnerPrivateAnalyticsSiteBindings(root)


def test_cli_rejects_prefinal_input_tamper_and_keeps_marker_incomplete(
    posix_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _private_tree(posix_tmp_path)
    readback_path = root / "google/gsc/admin-readback.v1.json"
    original_replace = cli._replace_pinned
    tampered = False

    def tampering_replace(
        tree: object,
        location: str,
        name: str,
        content: bytes,
        *,
        expected: tuple[int, ...] | None,
    ) -> tuple[int, ...]:
        nonlocal tampered
        result = original_replace(
            tree,
            location,
            name,
            content,
            expected=expected,
        )
        if not tampered and location == "ga4" and name == cli.BINDING_FILE_NAME:
            tampered = True
            document = json.loads(readback_path.read_text())
            document["captured_at"] = "2026-08-30T12:34:57.000Z"
            _write_private(readback_path, document)
        return result

    monkeypatch.setattr(cli, "_replace_pinned", tampering_replace)
    assert cli.main(_arguments(root)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "RAOS_GOOGLE_OWNER_PRIVATE_INPUT_CHANGED\n"
    assert tampered is True
    _assert_materializing_only(root, semantic_valid=False)


def test_cli_recovers_materializing_marker_after_final_directory_fsync_failure(
    posix_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _private_tree(posix_tmp_path)
    original_replace = cli._replace_pinned
    original_fsync = google_live_adapter.os.fsync
    final_window = False
    injected = False

    def tracking_replace(
        tree: object,
        location: str,
        name: str,
        content: bytes,
        *,
        expected: tuple[int, ...] | None,
    ) -> tuple[int, ...]:
        nonlocal final_window
        final_window = (
            location == "google"
            and name == cli.RECEIPT_FILE_NAME
            and json.loads(content)["state"] == cli.COMPLETED_STATE
        )
        try:
            return original_replace(
                tree,
                location,
                name,
                content,
                expected=expected,
            )
        finally:
            final_window = False

    def failing_fsync(descriptor: int) -> None:
        nonlocal injected
        if final_window and not injected and stat.S_ISDIR(os.fstat(descriptor).st_mode):
            injected = True
            raise OSError("fixture directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(cli, "_replace_pinned", tracking_replace)
    monkeypatch.setattr(google_live_adapter.os, "fsync", failing_fsync)
    assert cli.main(_arguments(root)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "RAOS_GOOGLE_OWNER_PRIVATE_FINAL_RECEIPT_FAILED\n"
    assert injected is True
    _assert_materializing_only(root)


def test_cli_requires_distinct_service_account_identities(
    posix_tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _private_tree(posix_tmp_path, ga4_email=GSC_EMAIL)

    assert cli.main(_arguments(root)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "RAOS_GOOGLE_OWNER_PRIVATE_IDENTITY_REUSED\n"
    for private_value in (PROJECT_ID, GSC_EMAIL, PRIVATE_KEY_MARKER, PROPERTY_ID):
        assert private_value not in captured.err


def test_cli_requires_same_gcp_project(posix_tmp_path: Path) -> None:
    other_project = "owner-analytics-456"
    root = _private_tree(posix_tmp_path, ga4_project=other_project)

    assert cli.main(_arguments(root)) == 1
    assert not (root / "google/binding-receipt.v1.json").exists()


@pytest.mark.parametrize(
    "mutation", ["gsc_resource", "property_id", "site_id", "scope_revision"]
)
def test_cli_derives_and_requires_exact_owner_private_resources(
    posix_tmp_path: Path, mutation: str
) -> None:
    root = _private_tree(posix_tmp_path)
    if mutation == "gsc_resource":
        path = root / "google/gsc/admin-readback.v1.json"
        document = json.loads(path.read_text())
        document["resource"] = "https://kurashinoshirube.com/"
    elif mutation == "property_id":
        path = root / "google/ga4/admin-readback.v1.json"
        document = json.loads(path.read_text())
        document["property_id"] = "0123456789"
        document["property_resource"] = "properties/0123456789"
    elif mutation == "site_id":
        path = root / "google/local-scope.v1.json"
        document = json.loads(path.read_text())
        document["site_id"] = "00000000-0000-0000-0000-000000000000"
    else:
        path = root / "google/local-scope.v1.json"
        document = json.loads(path.read_text())
        document["database_revision"] = "200001010001"
    _write_private(path, document)

    assert cli.main(_arguments(root)) == 1
    assert not (root / "google/gsc/binding.v1.json").exists()


def test_cli_rejects_project_declared_by_only_one_credential(
    posix_tmp_path: Path,
) -> None:
    root = _private_tree(posix_tmp_path)
    credential_path = root / "google/ga4/service-account.json"
    credential = json.loads(credential_path.read_text())
    credential["project_id"] = "owner-analytics-456"
    _write_private(credential_path, credential)

    assert cli.main(_arguments(root)) == 1
    assert not (root / "google/binding-receipt.v1.json").exists()


@pytest.mark.parametrize(
    ("provider", "field", "value"),
    [
        ("gsc", "permission", "FULL"),
        ("gsc", "is_owner", True),
        ("gsc", "service_account_readback", False),
        ("ga4", "currency_code", "USD"),
        ("ga4", "viewer_is_administrator", True),
        ("ga4", "viewer_service_account_readback", False),
        ("ga4", "property_resource", "properties/999999999"),
        ("ga4", "stream_origin", "https://example.invalid"),
    ],
)
def test_cli_rejects_false_admin_readback_semantics(
    posix_tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    provider: str,
    field: str,
    value: object,
) -> None:
    root = _private_tree(posix_tmp_path)
    readback_path = root / f"google/{provider}/admin-readback.v1.json"
    readback = json.loads(readback_path.read_text())
    readback[field] = value
    _write_private(readback_path, readback)

    assert cli.main(_arguments(root)) == 1
    captured = capsys.readouterr()
    assert captured.err == "RAOS_GOOGLE_OWNER_PRIVATE_ADMIN_READBACK_INVALID\n"
    assert not (root / "google/gsc/binding.v1.json").exists()
    assert not (root / "google/binding-receipt.v1.json").exists()


def test_cli_rejects_readback_shape_and_custom_dimension_drift(
    posix_tmp_path: Path,
) -> None:
    mutations = ("extra_key", "missing_dimension", "wrong_scope", "wrong_order")
    for index, mutation in enumerate(mutations):
        case_root = posix_tmp_path / f"case-{index}"
        case_root.mkdir()
        root = _private_tree(case_root)
        readback_path = root / "google/ga4/admin-readback.v1.json"
        readback = json.loads(readback_path.read_text())
        dimensions = readback["custom_dimensions"]
        assert type(dimensions) is list
        if mutation == "extra_key":
            readback["unexpected"] = False
        elif mutation == "missing_dimension":
            dimensions.pop()
        elif mutation == "wrong_scope":
            dimensions[0]["scope"] = "USER"
        else:
            dimensions[0], dimensions[1] = dimensions[1], dimensions[0]
        _write_private(readback_path, readback)

        assert cli.main(_arguments(root)) == 1
        assert not (root / "google/binding-receipt.v1.json").exists()
