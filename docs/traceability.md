# P1 需求追溯

更新：2026-10-14。以下为已实现账号课程范围；未来功能仍以需求规划和接口草案为目标。

2026-10-24 补充：下表保留 P1 历史阶段，不代表当前全平台状态。课程资料模块已实现 M3 的上传校验、文本解析、预览下载、关联编辑及版本管理，当前课程 RAG 答疑已解除固定演示课程和学生限制。实现路径为 `routes/resources`、`services/resources`、`services/document_parser` 与迁移 `0012`；对应 `backend/tests/test_resources.py`、`test_course_documents.py`、`test_learning_curriculum.py`。格式支持和验证边界见[本轮说明](updates/2026-10-24-course-resources.md)。

| 需求 | 用户故事 | 模块/接口 | 测试 | 状态 |
|---|---|---|---|---|
| M1-1 | US-01 登录 | routes/auth、security、deps；/api/v1/auth/* | test_login_logout_and_no_secret_leak、test_expiry_rotation_and_independent_sessions | 已实现/验证 |
| M1-2 | US-02 课程结构 | routes/courses、knowledge；课程/章节/知识点接口 | test_teacher_student_full_flow | 已实现/浏览器验证 |
| M4-1 | US-09 节点信息 | KnowledgePoint、KpCreate、教师编辑与学生目录 | test_invalid_updates_do_not_mutate、完整流程 | 字段基础完成；图谱未做 |
| NF-6 | 角色/课程权限 | course_access、Teacher、数据库会话、Argon2id | test_course_isolation_and_enrollment、test_origin_csrf_and_validation | 本阶段接口已验证 |
| NF-7 | 本地秘密配置 | .env、.gitignore、非超级用户应用账号 | Git 忽略检查，响应不含密码哈希测试 | 已配置，CI 扫描待后续 |
| NF-16 | 迁移及启动 | 0002、seed_data、start/test.ps1 | test_migrations_incremental_preserve_legacy、test_seed_is_idempotent_and_preserves_changes | 本机完成；Docker/CI 后续 |

新增的课程成员接口支持手工加入已存在学生，用于新课程演示；不冒充 M1-3 CSV 批量导入已完成。个人中心 M1-4、M2–M10 完整功能及 E1/E7 尚未完成。

## Sprint 0 保留记录

### 原骨架追溯

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
