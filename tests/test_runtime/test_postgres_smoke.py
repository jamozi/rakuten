"""Execute the discovered runtime without running application migrations."""

import pytest

from tests import postgresql18

postgresql_cluster = postgresql18.postgresql_cluster

pytestmark = [pytest.mark.database, pytest.mark.serial]


def test_postgres_is_exact_and_socket_only(postgresql_cluster):
    with postgresql_cluster.connect("postgres") as connection:
        assert connection.execute("SHOW server_version_num").fetchone() == ("180004",)
        assert connection.execute("SHOW listen_addresses").fetchone() == ("",)
    result = postgresql_cluster.run("psql", ["--version"])
    assert "(PostgreSQL) 18.4" in result.stdout
