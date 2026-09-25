# 下载数据库与本地导入清单

> 目标：用户可以下载或准备一个本地数据库文件，在设置页导入为受控数据源，并立即在聊天、SQL 控制台和 Catalog 中使用。第一版优先支持 SQLite 与 DuckDB。

## 1. 产品流程

```text
选择数据库文件 -> 填写数据源名称 -> 上传/复制到受控目录 -> 校验文件 -> 只读连接测试
-> 保存数据源配置 -> 刷新数据源与 Catalog -> Single/Multi 查询验证
```

- [x] 设置页提供 SQLite/DuckDB 文件选择、文件名/大小、数据源名和只读状态。
- [x] 明确不由服务器下载任意 URL；限制扩展名、文件大小与命名。
- [x] 数据源 ID 进入聊天、SQL、Catalog 和表详情请求；切换时按数据源 ID 重载目录。
- [x] 实现上传/校验/成功/失败/取消/重复名状态，支持确认解绑配置与同文件重新注册。

## 2. 后端接口与存储

- [x] 实现 multipart `POST /api/v1/config/datasources/import`，字段为文件、名称和是否设为默认；数据库类型由扩展名确定。
- [x] 文件落盘到项目 `.dataengineer/imported-databases`；防目录穿越、软链接逃逸和覆盖不同内容的既有文件。
- [x] 以临时文件流式接收，限制 512 MiB 和扩展名；验证后原子移动/注册，失败清理。
- [x] 用 SQLite `quick_check`/DuckDB 只读连接验证；返回 schema/table 数、字节数和 SHA-256。
- [x] 配置强制 `read_only`，SQLite 使用 `mode=ro`，DuckDB connector 使用 `read_only=True`；服务缓存失效后返回数据源 ID/类型，不返回落盘路径。
- [x] 增加默认数据源切换、managed import 解绑与 Catalog 刷新工作流；解绑保留文件并支持同内容重新注册。

## 3. 前端交互

- [x] 选择文件后显示名称/大小并允许编辑数据源名。
- [x] XHR 上传进度与取消状态可观察；拒绝时保留文件和表单输入。
- [x] 成功后刷新设置、数据源选择器和 Catalog，并选中新数据源。
- [x] 默认来源切换和设默认导入均二次确认；只影响后续请求。
- [x] UI 不展示绝对落盘路径，长错误/名称允许换行。

## 4. 验证数据

- [x] 导入有效 DuckDB；Catalog 的 `events` 表与独立 DuckDB 查询一致。
- [x] 导入有效 SQLite；Single/Multi 在同一来源均返回 2 行、金额合计 37.5。
- [x] 拒绝错误扩展名、空文件、损坏文件、超限文件、重复名称、目录穿越及不同内容文件覆盖。
- [x] 导入后 Single/Multi 使用同一数据源；服务重启后注册信息仍可加载。
- [x] SQLite/DuckDB 写操作均被只读拒绝；失败不留下部分配置/文件，取消测试也未注册数据源。

## 通过标准

- [x] 设置页文件选择 -> Catalog -> SQL 已在浏览器分别回放 SQLite 与 DuckDB；浏览器聊天请求载荷确认携带新导入 datasource ID，真实 Single/Multi 数据结果见 API 证据。
- [x] 数据源注册、缓存失效、Catalog 读取和 SQL 结果分开展示，不以单一导入状态代表后续步骤成功。
- [x] 安全/API/真实 DuckDB 与 SQLite 验证以及浏览器视觉、重复点击、重复名失败和窄屏宽表回放通过。

验收证据：[frontend-next-03-04-evidence.md](../reports/frontend-next-03-04-evidence.md)。
