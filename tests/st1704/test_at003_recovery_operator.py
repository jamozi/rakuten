from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = (
    ROOT
    / "changes/st-1704/at003-recovery-operator-v1/wordpress-plugin"
    / "raos-at003-recovery-operator/raos-at003-recovery-operator.php"
)
BUILD = ROOT / "scripts/build_st1704_at003_recovery_operator.py"


def source() -> str:
    return PLUGIN.read_text(encoding="utf-8")


def test_surface_is_one_fixed_human_action() -> None:
    text = source()
    for required in (
        "const SOURCE_POST_ID = 26;",
        "const TARGET_POST_ID = 19;",
        "const ARTICLE_ID = 'st1703-first-suitcase-comparison';",
        "const CATEGORY_NAME = '暮らしの道具';",
        "RAOS_AT003_RECOVERY_WRITES_ENABLED === true",
        "current_user_can('manage_options')",
        "current_user_can('publish_posts')",
        "check_admin_referer(",
        "wp_check_password(",
        "Final 12 operation-hash characters",
        "add_option(self::LOCK_KEY",
        "Diagnostic: <code>",
    ):
        assert required in text
    for forbidden in (
        "register_rest_route",
        "wp_ajax_",
        "admin_post_nopriv_",
        "wp_insert_post(",
        "wp_delete_post(",
        "wp_create_category(",
        "wp_insert_term(",
        "delete_option(",
    ):
        assert forbidden not in text


def test_mutation_is_bounded_and_rollback_precedes_failure() -> None:
    text = source()
    assert text.count("wp_update_post(") == 2
    assert text.count("update_post_meta(") == 4
    assert "'post_status' => 'publish'" in text
    assert "'post_status' => $pre['post_status']" in text
    assert "self::restore_taxonomies(" in text
    handler = text.split("public function handle()", 1)[1]
    assert handler.index("add_option(self::LOCK_KEY") < handler.index(
        "'post_status' => 'publish'"
    )
    assert handler.count("self::rollback($context)") == 3
    assert "source_snapshot_repair_sha256" in text


def test_fixed_hashes_are_lowercase_sha256() -> None:
    text = source()
    values = dict(
        re.findall(
            r"const (PACKET_SHA256|REQUEST_SHA256|PAYLOAD_SHA256) = '([0-9a-f]{64})';",
            text,
        )
    )
    assert values == {
        "PACKET_SHA256": "570708758b22b2af06e663d1e89dbb39bcd2bb4536e039a6c486e6d47405687c",
        "REQUEST_SHA256": "9ead64fcc0bedb35718d9e62c8f073cf89482d97a182243e5852feb4b272b516",
        "PAYLOAD_SHA256": "f743a2944f1adca0a8fef2cdd850567767f2257836bb807c47901b25c04fc942",
    }


def test_deterministic_package_and_manifest() -> None:
    spec = importlib.util.spec_from_file_location("at003_recovery_build", BUILD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first = module.package_bytes()
    second = module.package_bytes()
    assert first == second
    assert module.MANIFEST.read_bytes() == module.manifest_bytes()


def test_builder_accepts_standard_and_legacy_check_commands() -> None:
    for arguments in (["--check"], ["check"]):
        completed = subprocess.run(
            [sys.executable, str(BUILD), *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert '"command": "check"' in completed.stdout
        assert '"status": "PASS"' in completed.stdout
