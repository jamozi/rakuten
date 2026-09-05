"""Repository-wide pytest configuration and explicit shared-resource suites.

The entries below preserve the previously audited execution boundaries. New
files do not become serial because of their names. Prefer module/function
pytest.mark.serial/database/storage for new shared-resource tests; remove an
entry after its shared checkout writes have been isolated in tmp_path.
"""

from pathlib import Path
import sys

import pytest

sys.dont_write_bytecode = True
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "python"))

# Read-only checks now parallel: st0102/test_uv_cli.py, st0103/test_node_cli.py,
# st1004_v2/test_generation.py. Their mutations use per-test temporary paths.

DATABASE_MODULES = frozenset(
    {
        "tests/google_live/test_google_live_database.py",
        "tests/google_live/test_google_live_postgresql.py",
        "tests/st0002/test_postgresql_migration.py",
        "tests/st0003/test_database_migration_static.py",
        "tests/st0003/test_postgresql_migration.py",
        "tests/st0004/test_database_migration_static.py",
        "tests/st0004/test_postgresql_migration.py",
        "tests/st0301/test_postgresql.py",
        "tests/st0302/test_postgresql.py",
        "tests/st0303/test_postgresql.py",
        "tests/st0304/test_postgresql.py",
        "tests/st0305/test_postgresql.py",
        "tests/st0306/test_postgresql.py",
        "tests/st0307/test_postgresql.py",
        "tests/st0308_persistence/test_postgresql_runtime.py",
        "tests/st0405/test_sqlite_hardening_v3.py",
        "tests/st0603/test_st0603_fact_conflict_sqlite_v2.py",
        "tests/st0604/test_source_packet_lifecycle_sqlite_v2.py",
        "tests/st1201/test_durable_sqlite_hardening_v3.py",
    }
)

STORAGE_MODULES = frozenset(
    {
        "tests/st0406/test_storage_security_v2.py",
        "tests/st0502/test_item_search_runtime_v2_storage.py",
        "tests/st0503/test_catalog_normalization_runtime_v2_storage.py",
        "tests/st0504/test_product_identity_runtime_v2_storage.py",
        "tests/st0601/test_storage_security_v2.py",
        "tests/st0602/test_fact_extraction_runtime_v2_storage.py",
    }
)

SERIAL_MODULES = frozenset(
    {
        "tests/editorial_portfolio_v3/test_economics_cli.py",
        "tests/editorial_product_safety_manufacturer_capture/test_generation.py",
        "tests/google_live/test_google_owner_private_cli.py",
        "tests/google_live/test_runtime_manifest.py",
        "tests/st0002/test_revision_generation.py",
        "tests/st0003/test_revision_generation.py",
        "tests/st0004/test_revision_generation.py",
        "tests/st0005/test_revision_generation.py",
        "tests/st0006/test_revision_generation.py",
        "tests/st0102/test_commands_and_docs.py",
        "tests/st0102/test_toolchain_contract.py",
        "tests/st0103/test_commands_and_docs.py",
        "tests/st0103/test_toolchain_contract.py",
        "tests/st0104/test_commands_and_docs.py",
        "tests/st0104/test_installer.py",
        "tests/st0105/test_codegen_cli.py",
        "tests/st0105/test_commands_and_docs.py",
        "tests/st0105/test_determinism_and_safety.py",
        "tests/st0105/test_generated_runtime.py",
        "tests/st0105/test_manifest_contract.py",
        "tests/st0106/test_ci_wrapper.py",
        "tests/st0106/test_generated_namespace_ownership.py",
        "tests/st0107/test_generation.py",
        "tests/st0201/test_generation.py",
        "tests/st0201/test_wrapper.py",
        "tests/st0202/test_wrapper.py",
        "tests/st0203/test_generation.py",
        "tests/st0204/test_generation.py",
        "tests/st0205/test_generation.py",
        "tests/st0301/test_cli.py",
        "tests/st0301/test_generation.py",
        "tests/st0302/test_generation.py",
        "tests/st0303/test_generation.py",
        "tests/st0304/test_generation.py",
        "tests/st0306/test_generation.py",
        "tests/st0307/test_generation.py",
        "tests/st0308_reference/test_generation.py",
        "tests/st0401/test_generation_v2.py",
        "tests/st0402/test_generation_v2.py",
        "tests/st0403/test_generation.py",
        "tests/st0406/test_generation_v2.py",
        "tests/st0504/test_generation.py",
        "tests/st0505/test_generation.py",
        "tests/st0601/test_generation_runtime_v2.py",
        "tests/st0602/test_generation.py",
        "tests/st0603/test_generation.py",
        "tests/st0604/test_generation.py",
        "tests/st0605/test_generation.py",
        "tests/st0605_runtime/test_generation.py",
        "tests/st0606_v2/test_generation.py",
        "tests/st0701/test_generation.py",
        "tests/st0702/test_generation.py",
        "tests/st0703/test_generation.py",
        "tests/st0703/test_implementation_manifest.py",
        "tests/st0705/test_generation.py",
        "tests/st0705_runtime/test_generation_security.py",
        "tests/st0706/test_durable_queue_v2_generation.py",
        "tests/st0707_runtime/test_generation_and_bindings.py",
        "tests/st0708/test_generation.py",
        "tests/st0708_v2/test_generation_and_bindings.py",
        "tests/st0709_v2/test_generation.py",
        "tests/st0801/test_generation.py",
        "tests/st0803_runtime/test_generation.py",
        "tests/st0804_runtime/test_generation.py",
        "tests/st0805_runtime/test_generation.py",
        "tests/st0806/test_ai_draft_integration_v2_generation.py",
        "tests/st0807_v2/test_generation.py",
        "tests/st0901_v2/test_generation.py",
        "tests/st0902/test_generation.py",
        "tests/st0902_v2/test_generation.py",
        "tests/st0903/test_generation.py",
        "tests/st0903_v2/test_generation.py",
        "tests/st0904/test_generation.py",
        "tests/st0904_v2/test_generation.py",
        "tests/st0905/test_generation.py",
        "tests/st0905/test_runtime_generation_v2.py",
        "tests/st0906/test_generation_v2.py",
        "tests/st1001_v2/test_generation.py",
        "tests/st1002_v2/test_generation.py",
        "tests/st1006_v2/test_generation.py",
        "tests/st1102/test_generation_v2.py",
        "tests/st1103/test_generation.py",
        "tests/st1104_v2/test_generation.py",
        "tests/st1105_v2/test_generation.py",
        "tests/st1201/test_durable_generation_v2.py",
        "tests/st1202_v2/test_generation.py",
        "tests/st1203/test_generation.py",
        "tests/st1204/test_generation.py",
        "tests/st1205/test_generation.py",
        "tests/st1206/test_generation.py",
        "tests/st1302/test_generation.py",
        "tests/st1302/test_recorded_generation.py",
        "tests/st1303/test_generation.py",
        "tests/st1303_v2/test_generation.py",
        "tests/st1304/test_generation.py",
        "tests/st1304_v2/test_generation.py",
        "tests/st1305/test_generation.py",
        "tests/st1305_v2/test_generation.py",
        "tests/st1403/test_generation.py",
        "tests/st1407/test_generation.py",
        "tests/st1407_v2/test_generation.py",
        "tests/st1501/test_generation.py",
        "tests/st1502/test_generation.py",
        "tests/st1503/test_generation.py",
        "tests/st1504/test_generation.py",
        "tests/st1505/test_generation.py",
        "tests/st1506/test_generation.py",
        "tests/st1506/test_local_canary_generation.py",
        "tests/st1506_operator/test_client_surface.py",
        "tests/st1506_operator/test_package_manifest.py",
        "tests/st1602/test_generation.py",
        "tests/st1602/test_local_generation_v2.py",
        "tests/st1603/test_generation.py",
        "tests/st1604/test_generation.py",
        "tests/st1604_runtime/test_runtime_generation.py",
        "tests/st1605/test_generation.py",
        "tests/st1606/test_generation.py",
        "tests/st1607/test_generation.py",
        "tests/st1701/test_generation.py",
        "tests/st1702/test_generation.py",
        "tests/st1702_v2/test_generation.py",
        "tests/st1703/test_self_hosted_wordpress_cli.py",
        "tests/st1703/test_wordpresscom_mvp_wave3_cli.py",
        "tests/st1703/test_wordpresscom_review_draft_cli.py",
        "tests/st1703_low_cost/test_generation.py",
        "tests/st1704/test_self_hosted_editorial_pilot_cli.py",
        "tests/st1704_publication_operator/test_client_surface.py",
        "tests/st1704_publication_operator/test_package_manifest.py",
        "tests/st1705/test_generation.py",
        "tests/st1801/test_generation.py",
        "tests/st1802/test_generation.py",
        "tests/st1803/test_generation.py",
        "tests/st1804/test_generation.py",
        "tests/st1901/test_generation.py",
        "tests/st1902/test_generation.py",
        "tests/st1903/test_contract_generation.py",
        "tests/st1904/test_generation.py",
        "tests/st1905/test_generation.py",
        "tests/st1906/test_generation.py",
        "tests/st1907/test_generation.py",
        "tests/st1908/test_generation.py",
        "tests/verified_incremental_v1/test_manifest.py",
        "tests/wordpress_local_preview/test_wrapper.py",
    }
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        relative = item.path.relative_to(REPOSITORY_ROOT).as_posix()
        if relative in DATABASE_MODULES:
            item.add_marker(pytest.mark.database)
            item.add_marker(pytest.mark.serial)
        elif relative in STORAGE_MODULES:
            item.add_marker(pytest.mark.storage)
            item.add_marker(pytest.mark.serial)
        elif relative in SERIAL_MODULES:
            item.add_marker(pytest.mark.serial)
