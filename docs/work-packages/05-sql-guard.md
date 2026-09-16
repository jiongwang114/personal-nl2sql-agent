# WP-05: SQL Guard

## Status

- state: complete
- depends_on: [WP-03]

## Objective

在任何数据库执行前强制进行确定性 SQL 校验。

## Deliverables

- `dataengineer/tools/func_tool/sql_guard.py`
- MCP 工具 `validate_sql`
- Pi 工具 `execute_readonly_sql`
- `tests/unit_tests/tools/test_sql_guard.py`

## Enforced Rules

- SQL 不得为空。
- 只允许一条语句。
- 只允许查询型 AST。
- 拒绝 DDL、DML、事务和命令节点。
- 返回格式化 SQL、语句类型和引用表。
- 执行工具先 Guard，再调用现有 `read_query`。

## Verification

- Guard 单元测试通过：4 tests passed。
- 现有 adapter 测试继续提供 DML 和多语句执行边界覆盖。
