"""An ON runtime inspection is read-only and preserves the approved OFF release."""
from pathlib import Path

import pytest

from scripts import raos_reader_release_pages as pages
from tests.verified_incremental_v1.test_publication_port import port

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("stage", ["propose", "apply"])
def test_enabled_runtime_cannot_be_used_for_any_write_stage(stage):
    with pytest.raises(port.publication.PublicationFailure, match="READER_READBACK_STAGE"):
        port.execute_incremental(
            Path("/not-read"), stage=stage, implementation_execution_ids=(),
            browser_validator=lambda **kwargs: {}, public_readback_validator=lambda **kwargs: {},
            reader_measurement_readback=True,
        )


def test_on_factory_keeps_the_audited_off_binding_unchanged():
    binding, _ = pages.reader_measurement_projection(ROOT)
    original = dict(binding)
    enabled = port.reader_runtime_for({"reader_measurement": binding}, post_activation=True)
    assert enabled.expected_collection_enabled is True
    assert binding == original
    assert binding["expected_collection_enabled"] is False
    assert port.reader_runtime_for({"reader_measurement": binding}).expected_collection_enabled is False
    with pytest.raises(port.publication.PublicationFailure, match="READER_RUNTIME_BINDING"):
        port.reader_runtime_for({}, post_activation=True)


def test_workflow_only_allows_explicit_on_inspection_in_readback():
    from scripts import raos_wordpress_release_workflow as workflow
    parsed = workflow.parser().parse_args(["readback", "--reader-measurement-readback"])
    assert parsed.reader_measurement_readback is True
    assert workflow.main(["prepare", "--reader-measurement-readback"]) != 0

@pytest.mark.parametrize("stage", ["propose", "apply", "readback"])
def test_explicit_page_mismatch_is_rejected_before_cli_dispatch(stage, tmp_path, monkeypatch, capsys):
    from scripts import raos_wordpress_release_workflow as workflow
    document = {"articles": [], "shared_artifacts": {"categories": {}}}
    raw = port.canonical(document)
    (tmp_path / ".secrets").mkdir(mode=0o700)
    monkeypatch.setattr(port, "OWNER", tmp_path)
    folder = tmp_path / ".secrets" / port.digest(raw)
    folder.mkdir(mode=0o700)
    (folder / "manifest.v1.json").write_bytes(raw)
    (folder / "manifest.v1.json").chmod(0o600)
    monkeypatch.setattr(port, "_candidate_directory", lambda path: None)
    monkeypatch.setattr(workflow, "previous_report", lambda: {})
    called = []
    monkeypatch.setattr(port, "execute_cli", lambda args: called.append(args))
    assert workflow.main([stage, "--candidate", str(folder), "--reader-pages", "guides"]) != 0
    assert "page selection differs" in capsys.readouterr().err
    assert called == []
