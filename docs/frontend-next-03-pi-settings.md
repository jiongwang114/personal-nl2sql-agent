# Pi 设置与模型配置清单

> 目标：在系统设置中提供真实可用的 Pi Agent 配置窗口：Provider、模型、API Key、Base URL（必要时）和思考等级，并让配置进入下一次 Single/Multi 请求。

## 1. 先定配置契约

- [x] 盘点 Pi CLI 和各 Provider 实际支持的思考等级，依据 Pi 安装包的 `thinkingLevelMap` 隐藏 `null`/不支持项。
- [x] 明确配置作用域：项目默认配置、单次请求覆盖；请求结束事件返回模型/思考等级快照。
- [x] 明确模型标识格式 `provider/model_id` 与内部 Provider metadata 映射；Provider/model 必须来自服务端 allowlist。
- [x] 明确密钥策略：API Key 写入 OS Credential Vault，不进入 URL、项目 YAML、SSE、响应或日志；GET 只返回配置状态。隔离验收服务使用显式文件测试 adapter。

## 2. 后端与 Pi runtime

- [x] 扩展配置请求/响应模型，支持 Provider、模型、Base URL、API Key 写入、保留和二次确认清除。
- [x] 提供 Pi 设置 `GET` 摘要、`PUT` 保存、`POST` 连通性测试；仅返回状态、Provider/model、耗时和脱敏错误。
- [x] `StreamChatInput.thinking_level` 映射到 Pi `--thinking`，删除写死等级。
- [x] Single 与 Multi 使用同一请求配置解析，SSE `end` 包含最终模型和思考等级。
- [x] 以 Pi model catalog 的 `thinkingLevelMap` 验证/隐藏不支持的思考等级；不支持时拒绝请求/保存。
- [x] 增加密钥脱敏、模拟 HTTP 403、并发项目配置写入、缓存驱逐和配置持久化回归测试。

## 3. 前端设置窗口

- [x] Provider 下拉来自服务端 allowlist，显示凭据状态而不显示秘密值。
- [x] 模型下拉按 Provider 显示 allowlist 和可用的上下文/输出上限 metadata；思考等级随模型刷新。
- [x] API Key 密码输入支持显示/隐藏、留空保留、二次确认清除；测试与保存状态分离。
- [x] Base URL 有 Provider 默认值和 HTTP(S)/凭据/端口校验。
- [x] 思考等级选择与项目默认/请求覆盖范围接入真实请求。
- [x] 保存前字段校验并要求当前配置测试成功；失败保留输入且不显示保存成功。
- [x] 保存后刷新配置和聊天选择器；运行中的请求使用已启动的模型快照。
- [x] 浏览器模拟 HTTP 403 失败、思考等级保存与恢复、配置读取及桌面/窄屏视觉回放。
- [ ] 用户取消与真实网络超时的浏览器回放未做。

## 4. 通过标准

- [ ] 浏览器端未输入真实 Key，也未对已保存的真实凭据分别发起 Single/Multi。已在不输入 Key 的情况下保存思考等级，并用模拟 SSE 检查 Single/Multi 请求快照。
- [x] 模拟错 Key HTTP 401、错 Base URL、不支持等级和 HTTP 403 均返回脱敏错误且无假成功；本轮未触发真实配额失败。
- [x] 浏览器 localStorage/截图/控制台审计已回放；未输入或输出密钥，localStorage 为空，预期 403/503/409 日志已区分。
- [ ] 进程重启后的浏览器回放及 Windows Credential Vault 真实 Key 的替换/审计未执行；保存后 GET 读取和 sandbox 配置恢复已验证。

验收证据：[frontend-next-03-04-evidence.md](../reports/frontend-next-03-04-evidence.md)；Playwright 浏览器结构化回放见 `reports/frontend-next-03-04-sandbox/browser-final/acceptance.json`。真实 Key 流程仍未验收。
