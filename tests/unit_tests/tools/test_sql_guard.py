from dataengineer.tools.func_tool.sql_guard import validate_readonly_sql


def test_allows_single_select_and_returns_tables():
    result = validate_readonly_sql("select c.id from customer c", "sqlite")

    assert result["allowed"] is True
    assert result["statement_type"] == "SELECT"
    assert result["tables"] == ["customer AS c"]
    assert "SELECT" in result["formatted_sql"]


def test_rejects_multiple_statements():
    result = validate_readonly_sql("SELECT 1; DELETE FROM customer", "sqlite")

    assert result["allowed"] is False
    assert result["diagnostics"][0]["code"] == "multiple_statements"


def test_rejects_write_statement():
    result = validate_readonly_sql("UPDATE customer SET name = 'x'", "sqlite")

    assert result["allowed"] is False
    assert result["diagnostics"][0]["code"] == "not_read_only"


def test_reports_parse_error():
    result = validate_readonly_sql("SELECT FROM", "sqlite")

    assert result["allowed"] is False
    assert result["diagnostics"][0]["code"] == "parse_error"
