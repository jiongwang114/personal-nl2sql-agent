
"""Configuration classes for built-in database adapters."""

from pydantic import BaseModel, ConfigDict, Field


class SQLiteConfig(BaseModel):
    """SQLite-specific configuration."""

    model_config = ConfigDict(extra="forbid")

    uri: str = Field(
        ...,
        description="SQLite database URI (e.g., sqlite:////path/to/db.sqlite)",
        json_schema_extra={"input_type": "file_path"},
    )


class DuckDBConfig(BaseModel):
    """DuckDB-specific configuration."""

    model_config = ConfigDict(extra="forbid")

    uri: str = Field(
        ...,
        description="DuckDB database URI (e.g., duckdb:////path/to/db.duckdb)",
        json_schema_extra={
            "input_type": "file_path",
            "default_sample": "duckdb-demo.duckdb",
        },
    )
