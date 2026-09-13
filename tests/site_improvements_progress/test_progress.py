import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "progress",
    Path(__file__).parents[2] / "scripts/site_improvements_progress.py",
)
progress = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(progress)


def test_public_baseline_cannot_be_relabelled_candidate_validation(tmp_path):
    report = tmp_path / "baseline.json"
    report.write_text(
        json.dumps(
            {"schema": "RAOSSiteImprovementsReadOnlyAuditV1", "mode": "public-baseline"}
        )
    )
    with pytest.raises(ValueError, match="Public baseline"):
        progress.apply_validation({}, report)


def test_navigation_failures_remain_visible_in_candidate_progress(tmp_path):
    items = {
        ident: {"validation": {}, "evidence": []}
        for ident in ["Q01", "Q02", "Q05", "Q06", "Q08", "Q12"]
    }
    report = tmp_path / "candidate.json"
    report.write_text(
        json.dumps(
            {
                "schema": "RAOSSiteImprovementsReadOnlyAuditV1",
                "mode": "local-candidate",
                "rows": [{"post_id": 3, "failures": ["NAVIGATION_OR_DOM_FAILURE"]}],
            }
        )
    )
    progress.apply_validation(items, report)
    for item in items.values():
        assert "取得1/34ページ" in item["validation"]["local"]
        assert "[3]" in item["validation"]["local"]
        assert "全受入条件合格を意味しない" in item["validation"]["local"]


def test_unknown_audit_id_does_not_silently_enter_evidence(tmp_path):
    report = tmp_path / "unknown.json"
    report.write_text(json.dumps({"items": {"Q99": {"implementation": "done"}}}))
    with pytest.raises(ValueError, match="Unknown ID"):
        progress.apply_validation({}, report)
