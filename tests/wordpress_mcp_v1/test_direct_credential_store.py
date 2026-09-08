import json
import sys

import pytest

from scripts import store_wordpress_mcp_credential as store


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTORY", tmp_path / ".secrets/wordpress-mcp")
    monkeypatch.setattr("builtins.input", lambda *_: "synthetic-publisher")
    monkeypatch.setattr(
        store.getpass, "getpass", lambda *_: "abcd efgh ijkl mnop qrst uvwx"
    )
    return store.DIRECTORY


def test_owner_direct_credential_uses_private_purpose_and_never_prints_value(
    isolated_store, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", ["store", "--purpose", "owner_direct_publisher"])
    assert store.main() == 0
    path = isolated_store / "owner-direct-application-password.v1.json"
    result = json.loads(path.read_text())
    assert result["purpose"] == "owner_direct_publisher"
    assert path.stat().st_mode & 0o777 == 0o600
    assert isolated_store.stat().st_mode & 0o777 == 0o700
    assert capsys.readouterr().out == "WORDPRESS_MCP_CREDENTIAL_STORED\n"


@pytest.mark.parametrize(
    "existing,purpose",
    [
        (a, b)
        for a in ["editor_mcp", "deployment_operator", "owner_direct_publisher"]
        for b in ["editor_mcp", "deployment_operator", "owner_direct_publisher"]
        if a != b
    ],
)
def test_reuse_is_rejected_between_every_principal_even_with_spacing(
    isolated_store, monkeypatch, capsys, existing, purpose
):
    store.ensure_directory()
    path = isolated_store / store.PURPOSES[existing]
    path.write_text(json.dumps({"application_password": "abcdefghijklmnopqrstuvwx"}))
    path.chmod(0o600)
    monkeypatch.setattr(sys, "argv", ["store", "--purpose", purpose])
    assert store.main() == 69
    assert not (isolated_store / store.PURPOSES[purpose]).exists()
    assert "REUSE_FORBIDDEN" in capsys.readouterr().err
