from dataengineer.configuration.agent_config import _parse_single_file_db


def test_parse_single_file_db_preserves_connector_options():
    config = _parse_single_file_db(
        {
            "type": "duckdb",
            "uri": "duckdb:///test.duckdb",
            "read_only": True,
            "enable_external_access": False,
        },
        "duckdb",
    )

    assert config.extra == {"read_only": True, "enable_external_access": False}
