"""Synthetic path separation: no real credentials, provider data or live calls."""

from pathlib import Path

import pytest

from scripts import raos_wordpress_deployment_operator as owner
from scripts import build_wordpress_mcp_v1 as generator


@pytest.fixture
def private_owner(tmp_path, monkeypatch):
    root = tmp_path / "saved-checkout"
    (root / ".secrets/wordpress-mcp").mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(owner, "OWNER_CHECKOUT", root)
    return root


def test_default_private_location_preserves_legacy_paths():
    assert (
        owner.private_location(owner.CREDENTIAL_PATH, "ignored.json")
        == owner.CREDENTIAL_PATH
    )
    assert owner.parser().parse_args(["deployment-status"]).owner_checkout is None


def test_explicit_owner_changes_only_private_storage(private_owner):
    theme, registry, root = owner.THEME_ROOT, owner.ARTIFACT_REGISTRY, owner.ROOT
    private_context_reset = owner._private_owner.set(owner.validated_owner_checkout(private_owner))
    try:
        assert (
            owner.private_location(
                owner.CREDENTIAL_PATH, "operator-application-password.v1.json"
            )
            == private_owner
            / ".secrets/wordpress-mcp/operator-application-password.v1.json"
        )
        assert (
            owner.private_location(
                owner.REPO_ARTIFACT_DIRECTORY, "repo-plugin-artifacts"
            )
            == private_owner / ".secrets/wordpress-mcp/repo-plugin-artifacts"
        )
        assert (owner.THEME_ROOT, owner.ARTIFACT_REGISTRY, owner.ROOT) == (
            theme,
            registry,
            root,
        )
    finally:
        owner._private_owner.reset(private_context_reset)
    assert owner._private_owner.get() is None


@pytest.mark.parametrize("path", [Path("/tmp/other"), Path("relative"), Path("/")])
def test_arbitrary_owner_is_rejected_before_private_reads(path):
    with pytest.raises(owner.OperatorFailure, match="OWNER_CHECKOUT_INVALID"):
        owner.validated_owner_checkout(path)


def test_private_parent_symlink_is_rejected(private_owner, tmp_path):
    directory = private_owner / ".secrets/wordpress-mcp"
    directory.rmdir()
    other = tmp_path / "other-private"
    other.mkdir(mode=0o700)
    directory.symlink_to(other, target_is_directory=True)
    with pytest.raises(owner.OperatorFailure, match="OWNER_CHECKOUT_INVALID"):
        owner.validated_owner_checkout(private_owner)


def test_cli_rejects_owner_before_reading_operation_input(monkeypatch):
    monkeypatch.setattr(
        owner, "read_stdin", lambda: pytest.fail("stdin must not be read")
    )
    assert (
        owner.main(["--owner-checkout", "/tmp/not-allowed", "deployment-status"]) == 69
    )
    assert owner._private_owner.get() is None


def test_cli_restores_private_context_on_failed_request(private_owner, monkeypatch):
    monkeypatch.setattr(owner, "read_stdin", lambda: {})

    def refuse(command, inputs):
        assert command == "deployment-status" and inputs == {}
        assert owner._private_owner.get() == private_owner
        owner.fail("RECORDED_REQUEST_REFUSED")

    monkeypatch.setattr(owner, "run", refuse)
    assert (
        owner.main(["--owner-checkout", str(private_owner), "deployment-status"]) == 69
    )
    assert owner._private_owner.get() is None


def test_bridge_owner_configuration_is_not_an_mcp_tool_argument():
    source = (owner.ROOT / "packages/wordpress-mcp-bridge/src/index.ts").read_text()
    assert "const ownerCheckoutArgs = process.argv.slice(2);" in source
    assert "ownerCheckoutArgs[1] !== '/home/minami/rakuten'" in source
    assert "['-B', operator, ...ownerCheckoutArgs, command]" in source
    assert "process.env" not in source
    for tool_body in source.split("server.registerTool(")[1:]:
        assert "ownerCheckout" not in tool_body


def test_rebuilt_measurement_package_cannot_inherit_migration_review():
    package = generator.REVIEWED_MEASUREMENT_PACKAGE_SHA256
    files = generator.REVIEWED_MEASUREMENT_FILE_MANIFEST_SHA256
    assert generator.measurement_migration_review(package, files) is not None
    for actual_package, actual_files in (("f" * 64, files), (package, "f" * 64)):
        review = generator.measurement_migration_review(actual_package, actual_files)
        assert review is None
        binding = {
            "artifact_id": "raos-editorial-measurement-v1",
            "slug": "raos-editorial-measurement",
            "version": "1.0.0",
            "package_sha256": actual_package,
            "migration_review": review,
        }
        assert not owner._reviewed_migration_eligible(
            binding,
            artifact_id=binding["artifact_id"],
            slug=binding["slug"],
            version=binding["version"],
            activation_intent="activate",
            package_sha256=actual_package,
            file_manifest_sha256=actual_files,
        )
