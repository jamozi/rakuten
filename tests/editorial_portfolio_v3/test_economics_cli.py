from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/raos_editorial_economics_v3.py"
SPEC = importlib.util.spec_from_file_location("raos_editorial_economics_v3", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
cli = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cli
SPEC.loader.exec_module(cli)


SITE_ID = "0198f8c4-0000-7000-8000-000000000001"
GSC_JOB_ID = "0198f8c4-0000-7000-8000-000000000002"
GA4_JOB_ID = "0198f8c4-0000-7000-8000-000000000003"


def _private_tree(tmp_path: Path) -> Path:
    private_root = tmp_path / "private"
    google_root = private_root / "google"
    database_root = google_root / "database"
    database_root.mkdir(parents=True, mode=0o700)
    for directory in (private_root, google_root, database_root):
        directory.chmod(0o700)
    return private_root


def _scope_document() -> dict[str, object]:
    return {
        "database_revision": cli.GOOGLE_ANALYTICS_LIVE_REVISION,
        "ga4_ops_job_id": GA4_JOB_ID,
        "gsc_ops_job_id": GSC_JOB_ID,
        "schema_version": cli.GOOGLE_SCOPE_RECEIPT_SCHEMA,
        "scope_initialized": True,
        "site_id": SITE_ID,
    }


def _write_0600(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    path.chmod(0o600)


def _write_scope(private_root: Path, document: object | None = None) -> Path:
    path = private_root / cli.DEFAULT_GOOGLE_SCOPE_RECEIPT
    payload = _scope_document() if document is None else document
    _write_0600(
        path,
        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(),
    )
    return path


def test_candidate_query_template_cli_writes_private_independent_input(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)

    assert (
        cli.main(
            [
                "--private-root",
                private_root.as_posix(),
                "candidate-query-template",
                "--output",
                "candidate.json",
            ]
        )
        == 0
    )

    output = private_root / "candidate.json"
    document = json.loads(output.read_text(encoding="utf-8"))
    assert (
        document["aggregation_basis"]
        == "GSC_QUERY_DIMENSION_CANDIDATE_CLUSTER_NOT_ARTICLE_TOTAL"
    )
    assert document["article_totals_reused"] is False
    assert document["raw_queries_included"] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_followup_parser_accepts_private_candidate_query_input() -> None:
    arguments = cli._parser().parse_args(
        [
            "evaluate-followups",
            "--baseline",
            "baseline.json",
            "--candidate-query-demand",
            "candidate.json",
            "--as-of",
            "2026-11-27",
            "--output",
            "followups.json",
        ]
    )
    assert arguments.candidate_query_demand == "candidate.json"


def test_establish_t0_parser_requires_exact_activation_dry_run() -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "establish-t0",
                "--observation",
                "production-readbacks.json",
                "--output",
                "t0.json",
            ]
        )

    arguments = cli._parser().parse_args(
        [
            "establish-t0",
            "--observation",
            "production-readbacks.json",
            "--rakuten-activation-dry-run",
            "rakuten-activation.json",
            "--separate-admin-apply-receipt",
            "publication/separate-admin-apply.json",
            "--publication-receipt",
            "publication/applied-publication.json",
            "--public-readback-receipt",
            "publication/public-readback.json",
            "--output",
            "t0.json",
        ]
    )
    assert arguments.rakuten_activation_dry_run == "rakuten-activation.json"
    assert (
        arguments.separate_admin_apply_receipt
        == "publication/separate-admin-apply.json"
    )
    assert arguments.publication_receipt == "publication/applied-publication.json"
    assert arguments.public_readback_receipt == "publication/public-readback.json"


def test_establish_t0_cli_fails_before_reading_unsigned_candidate_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)

    result = cli.main(
        [
            "--private-root",
            private_root.as_posix(),
            "establish-t0",
            "--observation",
            "missing-observation.json",
            "--rakuten-activation-dry-run",
            "missing-activation.json",
            "--separate-admin-apply-receipt",
            "missing-apply.json",
            "--publication-receipt",
            "missing-publication.json",
            "--public-readback-receipt",
            "missing-readback.json",
            "--output",
            "t0.json",
        ]
    )

    assert result == 1
    assert capsys.readouterr().err.strip() == (cli.TRUSTED_T0_EVIDENCE_REQUIRED)
    assert not (private_root / "t0.json").exists()


def test_baseline_cli_keeps_synthetic_t0_incomplete(tmp_path: Path) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)
    _write_0600(
        private_root / "synthetic-t0.json",
        b'{"schema":"RAOS_EDITORIAL_V3_T0_RECEIPT_V4","t0":"2026-08-01T00:03:00Z"}\n',
    )

    result = cli.main(
        [
            "--private-root",
            private_root.as_posix(),
            "baseline",
            "--t0-receipt",
            "synthetic-t0.json",
            "--json-output",
            "baseline.json",
            "--html-output",
            "baseline.html",
        ]
    )

    assert result == 0
    baseline = json.loads((private_root / "baseline.json").read_bytes())
    assert baseline["state"] == "INCOMPLETE_TRUSTED_T0_EVIDENCE_REQUIRED"
    assert baseline["t0"] == "UNAVAILABLE"
    assert baseline["t0_receipt_sha256"] == "UNAVAILABLE"
    assert baseline["cohort"] == "PRE_T0_BASELINE"
    assert baseline["sources"]["t0_receipt"] == (cli.TRUSTED_T0_EVIDENCE_REQUIRED)


def test_followup_cli_rejects_unsigned_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)
    _write_0600(
        private_root / "unsigned-baseline.json",
        b'{"schema":"RAOS_EDITORIAL_V3_ACTUAL_BASELINE_REPORT_V1",'
        b'"t0":"2026-08-01T00:03:00Z",'
        b'"t0_receipt_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        b'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}\n',
    )

    result = cli.main(
        [
            "--private-root",
            private_root.as_posix(),
            "evaluate-followups",
            "--baseline",
            "unsigned-baseline.json",
            "--as-of",
            "2026-08-29",
            "--output",
            "followups.json",
        ]
    )

    assert result == 1
    assert capsys.readouterr().err.strip() == (cli.TRUSTED_T0_EVIDENCE_REQUIRED)
    assert not (private_root / "followups.json").exists()


def test_refresh_parser_exposes_only_scope_receipt_path_not_internal_ids() -> None:
    arguments = cli._parser().parse_args(
        [
            "refresh-baseline",
            "--date-from",
            "2026-08-01",
            "--date-to",
            "2026-08-30",
            "--database-name",
            "raos",
            "--database-user",
            "raos_google_worker",
            "--database-password",
            "google/database/worker-password.txt",
            "--gsc-output",
            "gsc.json",
            "--ga4-output",
            "ga4.json",
            "--json-output",
            "baseline.json",
            "--html-output",
            "baseline.html",
        ]
    )

    assert arguments.google_scope_receipt == "google/local-scope.v1.json"
    assert not hasattr(arguments, "site_id")
    assert not hasattr(arguments, "gsc_ops_job_id")
    assert not hasattr(arguments, "ga4_ops_job_id")


def test_google_scope_receipt_derives_three_distinct_internal_ids(
    tmp_path: Path,
) -> None:
    private_root = _private_tree(tmp_path)
    _write_scope(private_root)

    site_id, gsc_job_id, ga4_job_id = cli._google_local_scope(
        private_root, "google/local-scope.v1.json"
    )

    assert str(site_id) == SITE_ID
    assert str(gsc_job_id) == GSC_JOB_ID
    assert str(ga4_job_id) == GA4_JOB_ID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "wrong"),
        ("scope_initialized", False),
        ("database_revision", "000000000000"),
        ("site_id", "not-a-uuid"),
        ("gsc_ops_job_id", SITE_ID),
        ("ga4_ops_job_id", "00000000-0000-0000-0000-000000000000"),
    ],
)
def test_google_scope_receipt_rejects_invalid_exact_contract(
    tmp_path: Path, field: str, value: object
) -> None:
    private_root = _private_tree(tmp_path)
    document = _scope_document()
    document[field] = value
    _write_scope(private_root, document)

    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_GOOGLE_SCOPE_INVALID",
    ):
        cli._google_local_scope(private_root, "google/local-scope.v1.json")


def test_google_scope_receipt_rejects_extra_or_duplicate_keys(
    tmp_path: Path,
) -> None:
    private_root = _private_tree(tmp_path)
    document = _scope_document()
    document["unexpected"] = True
    _write_scope(private_root, document)
    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_GOOGLE_SCOPE_INVALID",
    ):
        cli._google_local_scope(private_root, "google/local-scope.v1.json")

    duplicate = json.dumps(_scope_document()).removesuffix("}") + ',"site_id":"x"}'
    _write_0600(private_root / "google/local-scope.v1.json", duplicate.encode("utf-8"))
    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_GOOGLE_SCOPE_INVALID",
    ):
        cli._google_local_scope(private_root, "google/local-scope.v1.json")


@pytest.mark.parametrize(
    "unsafe_name",
    (
        "../local-scope.v1.json",
        "google/../local-scope.v1.json",
        "/tmp/local-scope.v1.json",
        "google//local-scope.v1.json",
        "google\\local-scope.v1.json",
    ),
)
def test_google_scope_receipt_rejects_path_traversal(
    tmp_path: Path, unsafe_name: str
) -> None:
    private_root = _private_tree(tmp_path)
    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_NAME_INVALID",
    ):
        cli._google_local_scope(private_root, unsafe_name)


@pytest.mark.parametrize("link_kind", ("symlink", "hardlink"))
def test_google_scope_receipt_rejects_links(tmp_path: Path, link_kind: str) -> None:
    private_root = _private_tree(tmp_path)
    target = private_root / "google/scope-target.json"
    _write_0600(
        target,
        (json.dumps(_scope_document(), sort_keys=True) + "\n").encode("utf-8"),
    )
    receipt = private_root / "google/local-scope.v1.json"
    if link_kind == "symlink":
        receipt.symlink_to(target.name)
    else:
        os.link(target, receipt)

    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID",
    ):
        cli._google_local_scope(private_root, "google/local-scope.v1.json")


def test_google_scope_receipt_rejects_symlinked_parent(tmp_path: Path) -> None:
    private_root = _private_tree(tmp_path)
    _write_scope(private_root)
    (private_root / "linked-google").symlink_to("google", target_is_directory=True)

    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID",
    ):
        cli._google_local_scope(private_root, "linked-google/local-scope.v1.json")


def test_google_scope_receipt_rejects_symlinked_private_root(tmp_path: Path) -> None:
    private_root = _private_tree(tmp_path)
    _write_scope(private_root)
    linked_root = tmp_path / "linked-private"
    linked_root.symlink_to(private_root, target_is_directory=True)

    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID",
    ):
        cli._google_local_scope(linked_root, "google/local-scope.v1.json")


def test_google_scope_receipt_rejects_symlinked_private_root_ancestor(
    tmp_path: Path,
) -> None:
    real_parent = tmp_path / "real-parent"
    private_root = _private_tree(real_parent)
    _write_scope(private_root)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_ROOT_INVALID",
    ):
        cli._google_local_scope(linked_parent / "private", "google/local-scope.v1.json")


def test_database_snapshot_rejects_absolute_ancestor_replacement_between_stat_and_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    owner_boundary = tmp_path / "owner-boundary"
    private_root = _private_tree(owner_boundary)
    local_file = private_root / "google/database/worker-password.txt"
    _write_0600(local_file, b"fixture-value\n")

    replacement_boundary = tmp_path / "replacement-boundary"
    replacement_private = _private_tree(replacement_boundary)
    _write_0600(
        replacement_private / "google/database/worker-password.txt",
        b"changed-fixture\n",
    )
    original_boundary = tmp_path / "original-boundary"
    original_stat = cli.os.stat
    replaced = False

    def replacing_stat(
        path: object,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal replaced
        metadata = original_stat(
            path,
            dir_fd=dir_fd,
            follow_symlinks=follow_symlinks,
        )
        if path == owner_boundary.name and dir_fd is not None and not replaced:
            owner_boundary.rename(original_boundary)
            replacement_boundary.rename(owner_boundary)
            replaced = True
        return metadata

    monkeypatch.setattr(cli.os, "stat", replacing_stat)

    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED",
    ):
        cli._database_credential_snapshot(
            private_root, "google/database/worker-password.txt"
        )
    assert replaced is True


def test_google_scope_receipt_requires_mode_0600(tmp_path: Path) -> None:
    private_root = _private_tree(tmp_path)
    receipt = _write_scope(private_root)
    receipt.chmod(0o640)

    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID",
    ):
        cli._google_local_scope(private_root, "google/local-scope.v1.json")


def test_nested_database_credential_is_sealed_without_exposing_its_value(
    tmp_path: Path,
) -> None:
    private_root = _private_tree(tmp_path)
    local_file = private_root / "google/database/worker-password.txt"
    _write_0600(local_file, b"fixture-value\n")

    snapshot = cli._database_credential_snapshot(
        private_root, "google/database/worker-password.txt"
    )

    assert type(snapshot) is cli.OwnerPrivateDatabaseCredentialSnapshot
    assert "fixture-value" not in repr(snapshot)


@pytest.mark.parametrize("replacement_scope", ("leaf", "ancestor"))
def test_nested_database_credential_rejects_rename_replacement_during_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    replacement_scope: str,
) -> None:
    private_root = _private_tree(tmp_path)
    database_root = private_root / "google/database"
    local_file = database_root / "worker-password.txt"
    _write_0600(local_file, b"fixture-value\n")
    original_read = cli.os.read
    replaced = False

    def replacing_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        content = original_read(descriptor, size)
        if not replaced:
            replaced = True
            if replacement_scope == "leaf":
                local_file.rename(database_root / "original-password.txt")
                _write_0600(local_file, b"changed-fixture\n")
            else:
                database_root.rename(private_root / "google/original-database")
                database_root.mkdir(mode=0o700)
                _write_0600(database_root / "worker-password.txt", b"changed-fixture\n")
        return content

    monkeypatch.setattr(cli.os, "read", replacing_read)

    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_FILE_CHANGED",
    ):
        cli._database_credential_snapshot(
            private_root, "google/database/worker-password.txt"
        )
    assert replaced is True


def test_nested_database_password_requires_mode_0700_ancestors(
    tmp_path: Path,
) -> None:
    private_root = _private_tree(tmp_path)
    local_file = private_root / "google/database/worker-password.txt"
    _write_0600(local_file, b"fixture-value\n")
    local_file.parent.chmod(0o750)

    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID",
    ):
        cli._database_credential_snapshot(
            private_root, "google/database/worker-password.txt"
        )


@pytest.mark.parametrize("link_kind", ("symlink", "hardlink"))
def test_nested_database_password_rejects_links(tmp_path: Path, link_kind: str) -> None:
    private_root = _private_tree(tmp_path)
    target = private_root / "google/database/target-password.txt"
    _write_0600(target, b"fixture-value\n")
    local_file = private_root / "google/database/worker-password.txt"
    if link_kind == "symlink":
        local_file.symlink_to(target.name)
    else:
        os.link(target, local_file)

    with pytest.raises(
        cli.EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID",
    ):
        cli._database_credential_snapshot(
            private_root, "google/database/worker-password.txt"
        )
