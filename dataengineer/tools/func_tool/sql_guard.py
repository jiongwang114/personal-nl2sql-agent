from typing import Any, Dict, Optional

import sqlglot
from sqlglot import exp

from dataengineer.configuration.agent_config import AgentConfig
from dataengineer.tools.func_tool.base import FuncToolResult
from dataengineer.utils.mcp_decorators import mcp_tool, mcp_tool_class

READ_ONLY_ROOTS = (exp.Query,)
PROHIBITED_NODES = (
    exp.Alter,
    exp.Command,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Merge,
    exp.Transaction,
    exp.Update,
)


@mcp_tool_class(name="sql_guard_tool", availability_property="has_sql_guard_tools")
class SQLGuardTools:
    @classmethod
    def create_dynamic(cls, agent_config: AgentConfig, sub_agent_name: Optional[str] = None) -> "SQLGuardTools":
        return cls(agent_config)

    @classmethod
    def create_static(
        cls,
        agent_config: AgentConfig,
        sub_agent_name: Optional[str] = None,
        database_name: Optional[str] = None,
    ) -> "SQLGuardTools":
        return cls(agent_config)

    def __init__(self, agent_config: AgentConfig):
        self.agent_config = agent_config
        self.has_sql_guard_tools = True

    @mcp_tool()
    def validate_sql(self, sql: str, dialect: str = "") -> FuncToolResult:
        """Validate and format one read-only SQL query without executing it."""
        result = validate_readonly_sql(sql=sql, dialect=dialect)
        return FuncToolResult(success=1 if result["allowed"] else 0, error=_first_error(result), result=result)


def _diagnostic(code: str, message: str, severity: str = "error") -> Dict[str, str]:
    return {"code": code, "message": message, "severity": severity}


def _first_error(result: Dict[str, Any]) -> Optional[str]:
    diagnostics = result.get("diagnostics", [])
    return diagnostics[0]["message"] if diagnostics else None


def validate_readonly_sql(sql: str, dialect: str = "") -> Dict[str, Any]:
    normalized_dialect = dialect.strip().lower()
    base: Dict[str, Any] = {
        "allowed": False,
        "dialect": normalized_dialect,
        "statement_type": "",
        "formatted_sql": "",
        "tables": [],
        "diagnostics": [],
    }

    if not sql or not sql.strip():
        base["diagnostics"] = [_diagnostic("empty_sql", "SQL must not be empty")]
        return base

    try:
        statements = sqlglot.parse(sql, read=normalized_dialect or None)
    except (sqlglot.errors.ParseError, ValueError) as exc:
        base["diagnostics"] = [_diagnostic("parse_error", str(exc))]
        return base

    if len(statements) != 1:
        base["diagnostics"] = [_diagnostic("multiple_statements", "Exactly one SQL statement is allowed")]
        return base

    statement = statements[0]
    base["statement_type"] = statement.key.upper()

    prohibited = next((node for node in statement.walk() if isinstance(node, PROHIBITED_NODES)), None)
    if prohibited is not None or not isinstance(statement, READ_ONLY_ROOTS):
        base["diagnostics"] = [
            _diagnostic("not_read_only", f"Statement type {base['statement_type'] or 'unknown'} is not allowed")
        ]
        return base

    base["allowed"] = True
    base["formatted_sql"] = statement.sql(dialect=normalized_dialect or None, pretty=True)
    base["tables"] = sorted({table.sql(dialect=normalized_dialect or None) for table in statement.find_all(exp.Table)})
    return base
