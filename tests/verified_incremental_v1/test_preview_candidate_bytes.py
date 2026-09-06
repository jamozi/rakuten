"""Mixed previews seed the already validated final publication bytes."""
from argparse import Namespace
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import raos_wordpress_incremental_preview as preview
import raos_wordpress_incremental_publication as publication


def prepared_fixture(monkeypatch):
    snapshot = {"documents": [{"slug": "example", "status": "publish"}]}
    source = {"example": b"<p>Authored input before reader rendering</p>", "untouched": b"<p>Old</p>"}
    final = b'<p class="raos-research-status">Checked without real-world testing</p>'
    prepared = SimpleNamespace(
        snapshot=deepcopy(snapshot),
        manifest={"articles": [{"slug": "example", "local_artifact": {"key": "local-example"}}]},
        artifacts={"local-example": final},
    )
    calls = []
    monkeypatch.setattr(publication, "prepare_candidate", lambda path, **kwargs: calls.append(path) or prepared)
    return snapshot, source, final, calls


def test_selected_article_uses_validated_final_bytes_and_preserves_other_inputs(monkeypatch):
    snapshot, source, final, calls = prepared_fixture(monkeypatch)
    original = deepcopy(source)
    args = Namespace(candidate="/synthetic/frozen-candidate")
    result = preview.article_bodies_for_preview(
        args, snapshot=snapshot, selected=frozenset({"example"}), source_articles=source
    )
    assert calls == [args.candidate]
    assert result["example"] == final
    assert result["untouched"] == original["untouched"]
    assert source == original


@pytest.mark.parametrize("mismatch", ["snapshot", "selection"])
def test_mismatched_candidate_never_supplies_preview_bytes(monkeypatch, mismatch):
    snapshot, source, _final, _calls = prepared_fixture(monkeypatch)
    selected = frozenset({"example"})
    if mismatch == "snapshot":
        snapshot["documents"][0]["status"] = "draft"
    else:
        selected = frozenset({"untouched"})
    with pytest.raises(ValueError, match="PREVIEW_CANDIDATE_BINDING"):
        preview.article_bodies_for_preview(
            Namespace(candidate="/synthetic/frozen-candidate"), snapshot=snapshot,
            selected=selected, source_articles=source
        )


def test_unbound_legacy_preview_keeps_its_existing_input(monkeypatch):
    snapshot, source, _final, calls = prepared_fixture(monkeypatch)
    assert preview.article_bodies_for_preview(
        Namespace(), snapshot=snapshot, selected=frozenset({"example"}), source_articles=source
    ) == source
    assert calls == []
