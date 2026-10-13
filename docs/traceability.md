# 需求追溯

## Sprint 0（M8 诊断）

| 需求 | 实现 | 验证 | 当前边界 |
|---|---|---|---|
| M6-1 统一事件 | LearningEvent、提交接口 | 正常提交/字段/持久化测试 | 只有 answered 与 asked 两种 verb |
| M8-2 结构化诊断 | DiagnosisOutput | 正常、结构错误、证据不足测试 | 尚无正式语义效果评测 |
| M8-5 测验后触发 | 提交事务后 BackgroundTasks | 独立连接验证先提交 | 仅模拟学生固定练习 |
| NF-5 失败处理 | 诊断错误状态、重试接口 | 密钥/HTTP/连接/超时测试 | 无自动服务商切换 |
| NF-7 配置保密 | SecretStr、.env、.gitignore | 响应不包含测试密钥 | 尚未接入 CI 密钥扫描 |
| NF-11 输出校验 | Pydantic + 当前 event_id 校验 | 伪造事件/知识点/引用测试 | 不等同语义真实性验证 |
| NF-14 trace | ModelTrace | ID、状态、usage、重试历史 | 不编造 token 与费用 |
| MS2 骨架 | 两页前端、API、数据库、迁移 | mock 测试与本机演示 | 真实模型调用未验收 |

## M7 检索增强（本次增量）

| 需求 | 实现 | 验证 | 当前边界 |
|---|---|---|---|
| M7-1 问答带出处 | `rag/tutor.py` 引用对象 + `POST /api/tutor/ask` | `test_demo_ask_writes_asked_event_and_trace` | 出处可定位到文档/小节/片段 ID |
| M7-2 无依据不编造 | `retrieve.is_supporting` 双闸门 | `test_out_of_scope_is_not_supporting`、`test_out_of_scope_abstains_with_suggestions` | 判据基于词面重合，同义改写仍可能失效 |
| M7-3 拒绝作弊诱导 | `guardrails.CHEATING_PATTERNS` | `test_cheating_is_refused`（参数化） | 中文两种语序已覆盖，其他语言未覆盖 |
| M7-4 流式首字符 | `GET /api/tutor/ask/stream`（SSE） | `test_stream_records_event_and_trace` | 首字符延迟未在真实模型下实测 |
| M3-3 课件入库可检索 | `data/kb/` + `chunker.py` + `scripts/build_rag_index.py` | `test_index_covers_curriculum` | 尚未接入 PDF/视频字幕导入流水线 |
| M4-5 知识点挂资源 | 字面挂接 + 语义兜底 | `test_every_knowledge_point_has_resource` | 兜底挂接未经人工复核 |
| M4 知识图谱 | `GET /api/tutor/graph` | `test_kb_endpoints`、`test_knowledge_graph_edges_are_valid` | 39 节点 / 49 边，未做环检测 |
| M6-2 对话产生事件 | `services/tutor._persist` 写 asked 事件 | `test_three_turns_produce_three_asked_events` | 事件里不含会话分组 ID |
| NF-10 提示注入 | 输入正则 + 检索资料逐行净化 | `test_injection_is_blocked`、`test_sanitize_evidence_strips_embedded_instructions` | 未做跨组红队演练 |
| NF-11 引用编号校验 | `guardrails.validate_citations` | `test_validate_citations_detects_invalid_reference` | 越界编号被删除并计入准确率 |
| NF-14 调用可追溯 | `model_traces.details` + `GET /api/traces/{id}` | `test_trace_endpoint_replays_one_call` | 诊断与助教共用一张 trace 表 |
| NF-4 成本统计 | `GET /api/cost-report` | `test_cost_report_counts_calls` | 费用仅在价格表命中时估算，否则标 unpriced |
| NF-2 首字符 <5s | SSE 流式接口 | 接口行为已验证 | 真实模型下的延迟待实测 |
| 评测集与消融 | `data/eval/`、`scripts/eval_rag.py` | `test_eval_set_is_split_deterministically` | 56 题，未达课程 ≥60 题要求 |

检索主表（test 子集 28 题）：doc_hit@3 = 1.000、term_hit@6 = 1.000、MRR = 0.944、
引用准确率 = 1.000、超范围拒答率 = 1.000、注入拦截率 = 1.000、作弊拒绝率 = 1.000。
消融实验在 8 种检索配置下均达检索上限，未产生区分度，需在语料扩展后复跑。

M1–M5、M9、M10、E1–E7 及正式评测尚未实现，不能由本表推定完成。
