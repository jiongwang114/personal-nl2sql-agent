import sqlite3

from dataengineer.tools.db_tools.config import SQLiteConfig
from dataengineer.tools.db_tools.sqlite_connector import SQLiteConnector


def test_sqlite_read_only_configuration_rejects_writes(tmp_path):
    database = tmp_path / "readonly.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE sample (value INTEGER)")
    connection.execute("INSERT INTO sample VALUES (1)")
    connection.commit()
    connection.close()

    connector = SQLiteConnector(SQLiteConfig(db_path=str(database), read_only=True))
    read = connector.execute_query("SELECT value FROM sample", result_format="list")
    write = connector.execute_insert("INSERT INTO sample VALUES (2)")

    assert read.success is True
    assert write.success is False
    connector.close()
