from unittest.mock import MagicMock, patch

from dataengineer.tools.db_tools.config import DuckDBConfig
from dataengineer.tools.db_tools.duckdb_connector import DuckdbConnector


def test_connect_passes_read_only_to_duckdb():
    connection = MagicMock()
    config = DuckDBConfig(db_path="test.duckdb", read_only=True)

    with patch("dataengineer.tools.db_tools.duckdb_connector.duckdb.connect", return_value=connection) as connect:
        connector = DuckdbConnector(config)
        connector.connect()

    connect.assert_called_once_with("test.duckdb", read_only=True)
