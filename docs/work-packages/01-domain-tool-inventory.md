# WP-01: Domain Tool Inventory

## Status

- state: complete
- owner: pi-agent
- depends_on: []
- scope: read-only analysis

## Objective

建立现有 Data Engineer Agent 的领域能力清单，为 Pi Runtime 重构提供事实依据。

## Product Context

目标产品是面向数据工程师的 SQL 分析助手，第一阶段覆盖：

- 自然语言生成 SQL（NL2SQL）
- SQL 异常定位与修复
- SQL 语法、方言和安全校验
- 查询结果解释

Pi 负责 Agent Runtime 和多 Agent 编排；现有 Python 项目继续负责数据库、Schema、RAG、权限、评测和 API。

## Inputs To Read

- `dataengineer/agent/`
- `dataengineer/tools/`
- `dataengineer/storage/`
- `dataengineer/api/`
- `dataengineer/gateway/`
- `dataengineer/mcp_server.py`
- `conf/agent.yml.example`
- `conf/providers.yml`
- 现有项目介绍和 SQL 流程文档

## Inventory Requirements

对每项能力记录：

1. 文件位置和公开入口
2. 当前调用方
3. 输入和输出结构
4. 是否有副作用
5. 是否适合暴露为 MCP 工具
6. 是否需要 Pi Extension 适配
7. 当前测试和 benchmark 覆盖

重点识别以下领域工具：

- `search_schema`
- `describe_table`
- `find_join_paths`
- `search_metrics`
- `search_reference_sql`
- `validate_sql`
- `explain_sql`
- `execute_readonly_sql`
- `classify_sql_error`

## Deliverables

- 工具清单
- 现有 SQL 请求调用链
- MCP/API 可复用接口清单
- 工具输入输出契约草案
- 权限和安全风险清单
- 迁移到 Pi 的阻塞项

## Non-goals

- 不修改现有 Python 业务代码
- 不删除或替换旧 workflow
- 不创建 Pi Extension
- 不接入生产 API 或 Feishu

## Acceptance Criteria

- 所有候选领域工具都有文件位置和调用链证据
- 明确区分确定性工具和 Agent 能力
- 明确列出读写权限、超时和结果限制风险
- 输出可以直接作为 WP-02 的输入

## Verification

- test command: none; read-only inventory
- benchmark command: none
- result: complete; see `01-domain-tool-inventory-result.md`
