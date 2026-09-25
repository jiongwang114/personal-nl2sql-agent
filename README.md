# Personal NL2SQL Agent

## 项目说明

Personal NL2SQL Agent 是一个面向数据工程师的自然语言 SQL 分析系统。用户输入业务问题后，系统负责发现数据库结构、生成并校验 SQL、只读执行查询，并根据真实结果生成回答。

项目同时保留三条运行链路，便于对比单 Agent、多 Agent与原有实现：

| 模式 | 模型 | 用途 |
| --- | --- | --- |
| Legacy | `deepseek/deepseek-chat` | 原有 DataEngineer 工作流，作为 baseline 和回滚路径 |
| Pi 单 Agent | `custom/gpt-5.5` | 一个 Agent 独立完成 Schema 分析、SQL 生成、执行和解释 |
| Pi 多 Agent | `custom/gpt-5.5` | 主 Agent按状态调用专业子 Agent，适合复杂 SQL 分析 |

Pi 链路包含以下能力：

- 从真实数据源发现 catalog、schema、表和字段，不默认假设 `public`。
- 使用 SQL Guard 拦截非只读语句，并在执行前格式化和检查 SQL。
- 通过只读数据库快照执行查询，避免修改原始 DuckDB 文件。
- 将 Schema 分析、SQL 生成、异常修复、SQL 审查和结果解释拆分为独立角色。
- 限制 SQL 修复次数，避免无上限重试。
- 通过同一 Web API 切换 Legacy、单 Agent和多 Agent。

## 快速启动

### 1. 安装依赖

项目要求 Python 3.12 和 Node.js。

```powershell
git clone https://github.com/jiongwang114/personal-nl2sql-agent.git
Set-Location personal-nl2sql-agent

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .

Set-Location .pi
npm install --ignore-scripts
Set-Location ..
```

### 2. 配置模型

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

Legacy 使用 `deepseek/deepseek-chat`，在 `.env` 中配置：

```dotenv
DEEPSEEK_API_KEY=your_key
```

Pi 单 Agent和多 Agent使用 `custom/gpt-5.5`。Pi Provider 配置保存在用户目录：

```text
C:\Users\<用户名>\.pi\agent\models.json
```

项目不会把真实 API Key 写入 Git。模型选择分别位于：

- Legacy：`.dataengineer/config.yml`
- Pi：`dataengineer/api/services/pi_runtime_service.py`

### 3. 启动 Web 页面

生产工作台已随 Python 包构建并由 FastAPI 同源托管。直接启动：

```powershell
dataengineer --web --datasource demo --host 127.0.0.1 --port 8512
```

浏览器访问：

```text
http://127.0.0.1:8512
```

页面会调用同一地址下的 `/api/v1/*` 接口，不需要额外代理。验证聊天时，先确认 `.env` 中已配置当前运行模式所需的模型凭据，再选择 Database 和 Runtime 后发送问题。浏览器网络面板中的 `POST /api/v1/chat/stream` 应保持 `text/event-stream`，停止按钮会调用 `/api/v1/chat/stop`，断线后的“重试 / 恢复”会调用 `/api/v1/chat/resume`。

前端源码位于 `frontend/`。仅在修改前端时需要 Node.js：

```powershell
Set-Location frontend
npm install
npm run test
npm run build
Set-Location ..
dataengineer --web --datasource demo --host 127.0.0.1 --port 8512
```

开发模式可先启动上述后端，再运行 `npm run dev` 并访问 `http://127.0.0.1:5173`。Vite 会把 `/api` 代理到 `http://127.0.0.1:8512`。后端不在默认地址时可设置 `VITE_API_BASE_URL`；需要隔离匿名用户会话时可设置只含字母、数字、下划线或连字符的 `VITE_USER_ID`。不要把 API Key 或访问令牌写入 `VITE_*`，它们会出现在浏览器构建产物中。

Web 请求支持三种 `runtime_variant`：

```text
legacy
single
multi
```

默认模式是 `legacy`。Pi 单 Agent或多 Agent请求可以通过 `database` 字段指定数据源，例如 `benchmark_demo`。

### 4. 运行 Benchmark

```powershell
python scripts/run_pi_benchmark.py `
  --cases benchmark/semantic_layer/testing_set.csv `
  --output reports/pi-benchmark.jsonl `
  --base-url http://127.0.0.1:8512 `
  --variants legacy,single,multi `
  --datasource benchmark_demo --timeout 180
```

评测方法、人工判定和限制见 [真实对照评测记录](docs/benchmark-evidence.md)。本次每种模式仅测试 8 题：Legacy 正确 5/8、Single 正确 3/8、Multi 正确 1/8；中位延迟分别为 12.891 秒、142.258 秒和 109.586 秒。该结果不是总体正确率或隔离负载下的性能结论。

非 nightly 单元测试有 10,678 项通过、15 项条件跳过、1 项预期失败；`dataengineer` 在此范围的行覆盖率为 81.85%。确定性验收测试有 153 项通过、9 个模块条件跳过；该验收范围的覆盖率为 29.25%，不是仓库整体覆盖率。命令、跳过原因和证据边界见 [测试与覆盖率证据](docs/test-evidence.md)。

## 架构

```text
Web / API 请求
      |
      v
runtime_variant 路由
      |
      +---------------- Legacy ----------------+
      |                 DeepSeek                |
      |             原有 SQL Workflow           |
      |                                         |
      +--------------- Pi single --------------+
      |              Baseline Agent             |
      |  Schema -> SQL -> Guard -> Execute      |
      |                                         |
      +--------------- Pi multi ---------------+
                        主 Agent
                           |
                    sql_subagent Extension
                           |
          +----------------+----------------+
          |                |                |
    Schema Analyst    SQL Generator    SQL Debugger
          |                |                |
          +--------- SQL Reviewer ----------+
                           |
                  Result Interpreter
                           |
                    SQL Guard / 执行工具
                           |
                     只读数据源快照
```

### Agent 角色

| Agent | 职责 |
| --- | --- |
| Baseline Agent | 单 Agent对照组，独立完成整个 NL2SQL 流程 |
| Schema Analyst | 发现 schema、表、字段和关联关系 |
| SQL Generator | 根据问题和 Schema 上下文生成 SQL |
| SQL Debugger | 根据执行错误修复 SQL，最多重试两次 |
| SQL Reviewer | 审查 SQL 语义、语法、格式和风险 |
| Result Interpreter | 只根据执行结果生成最终业务回答 |

### Extension 与工具

| 组件 | 作用 |
| --- | --- |
| `sql-agents` | 加载 Agent Markdown 定义、启动隔离子进程、校验状态迁移 |
| `sql-tools` | 提供 Schema 查询、SQL 校验和只读执行工具 |
| `sql-observability` | 记录运行过程和必要的观测信息 |

多 Agent只允许一级子 Agent。子 Agent不会继续递归创建子 Agent，主 Agent负责选择下一步，Extension 负责执行、隔离和约束。

## 使用示例

用户输入：

```text
Which country has the highest number of transactions?
```

系统执行过程：

```text
1. 发现 mf_demo schema
2. 读取 transactions、customers 和 countries 的字段
3. 确认 transactions.id_customer 与 customers.id_customer 的关联
4. 生成按 country 聚合交易数量的 SQL
5. SQL Guard 确认语句为只读 SELECT
6. 在 benchmark_demo 快照中执行
7. 根据查询结果生成回答
```

生成的核心 SQL：

```sql
SELECT
  c.country,
  COUNT(*) AS transaction_count
FROM mf_demo.mf_demo_transactions AS t
JOIN mf_demo.mf_demo_customers AS c
  ON t.id_customer = c.id_customer
GROUP BY c.country
ORDER BY transaction_count DESC
LIMIT 1;
```

查询结果：

```text
country: CA
transaction_count: 15
```

最终回答：

```text
Canada (CA) has the highest number of transactions, with 15 transactions.
```
