"""A loaded but contradictory status cannot satisfy OFF or legacy gates."""

import pytest

from scripts import raos_wordpress_publication_request as publication
from tests.wordpress_mcp_v1.test_reader_measurement_status import (
    legacy_site_status_fixture,
    run_status,
    site_status_fixture,
    status,
)


@pytest.mark.parametrize("version", [None, "1.0.0"])
@pytest.mark.parametrize("legacy", [False, True])
def test_loaded_provider_reporting_absent_is_unknown_and_blocks_publication(
    version, legacy
):
    provider = status()
    provider.update(plugin_active=False, plugin_version=version)
    projected = run_status([provider])["statuses"][0]["reader_measurement"]
    candidate = legacy_site_status_fixture() if legacy else site_status_fixture()
    candidate["reader_measurement"] = projected
    with pytest.raises(publication.PublicationFailure, match="SITE_NOT_READY"):
        publication.validate_site_status(
            candidate,
            require_measurement_off=True,
            allow_legacy_runtime=legacy,
        )
    assert projected["plugin_active"] is True
    assert projected["collection_enabled"] is None
    assert projected["plugin_version"] is None
