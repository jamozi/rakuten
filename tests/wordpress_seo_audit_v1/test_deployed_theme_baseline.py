"""Review-bound local Git theme bytes; no live reads or authorization."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from scripts import raos_wordpress_runtime_audit as runtime
from scripts import raos_wordpress_scratch_theme_restore as scratch
from raos.application.editorial.local_scratch_theme_restore_v1 import (
    parse_theme_package,
    theme_tree_sha256,
)


DEPLOYED_TREE = "c4dbbe41851a661208645cf5cb81112ced23e886e7f8dd8856760e1e61116ff4"


def test_deployed_reviewed_baseline_resolves_its_exact_file_bytes():
    files = runtime.trusted_theme_files(DEPLOYED_TREE, baseline=True)
    assert len(files) == 31
    assert theme_tree_sha256(files) == DEPLOYED_TREE


def test_default_legacy_baseline_bytes_are_preserved():
    files = parse_theme_package(scratch.baseline_package())
    assert theme_tree_sha256(files) == "086ce67f586701de2be1da5386f6c21f007a758c42245f42961f5cf00be933dc"


def test_unknown_baseline_is_rejected_before_reading_git(monkeypatch):
    def reject_read(*args):
        raise AssertionError("unreviewed baseline must not read a chosen Git revision")
    monkeypatch.setattr(scratch, "git_bytes", reject_read)
    with pytest.raises(ValueError, match="BASELINE"):
        scratch.baseline_package("f" * 64)
