# Sprint 0 需求追溯

| 需求 | 实现 | 验证 | 当前边界 |
|---|---|---|---|
| M6-1 统一事件 | LearningEvent、提交接口 | 正常提交/字段/持久化测试 | 只有 answered 类型 |
| M8-2 结构化诊断 | DiagnosisOutput | 正常、结构错误、证据不足测试 | 尚无正式语义效果评测 |
| M8-5 测验后触发 | 提交事务后 BackgroundTasks | 独立连接验证先提交 | 仅模拟学生固定练习 |
| NF-5 失败处理 | 诊断错误状态、重试接口 | 密钥/HTTP/连接/超时测试 | 无自动服务商切换 |
| NF-7 配置保密 | SecretStr、.env、.gitignore | 响应不包含测试密钥 | 尚未接入 CI 密钥扫描 |
| NF-11 输出校验 | Pydantic + 当前 event_id 校验 | 伪造事件/知识点/引用测试 | 不等同语义真实性验证 |
| NF-14 trace | ModelTrace | ID、状态、usage、重试历史 | 不编造 token 与费用 |
| MS2 骨架 | 两页前端、API、数据库、迁移 | mock 测试与本机演示 | 真实模型调用未验收 |

M1–M5、完整 M7–M10、E1/E7 及正式评测尚未实现，不能由本表推定完成。
