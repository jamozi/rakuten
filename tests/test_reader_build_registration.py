"""Reader generation inputs stay reproducible without owner-private packages."""
from scripts import build_reader_measurement_v1 as reader
from scripts.raos_build_core import discover_registry


def test_reader_owner_tracks_every_authored_source_and_has_no_private_input():
    spec = discover_registry()["build_reader_measurement_v1"]
    inputs = {row.uri for row in spec.inputs}
    assert {"repo://" + p.as_posix() for p in reader.SOURCE_PATHS} <= inputs
    assert not any(uri.startswith("repo://.secrets/") for uri in inputs)


def test_mcp_owner_orders_reader_generation_and_binds_public_page_code():
    spec = discover_registry()["build_wordpress_mcp_v1"]
    assert "build_reader_measurement_v1" in spec.owner_dependencies
    inputs = {row.uri for row in spec.inputs}
    assert {
        "repo://" + path for path in (
            "scripts/raos_reader_release_pages.py",
            "scripts/raos_wordpress_reader_hubs.py",
            "python/raos/application/editorial/reader_release_applicability_v1.py",
        )
    } <= inputs

def test_reader_generation_command_is_explicit_and_never_packages():
    spec = discover_registry()["build_reader_measurement_v1"]
    assert spec.command()[-1] == "--generate"
    assert spec.command(check=True)[-1] == "--check"
    assert "--package" not in spec.command()
