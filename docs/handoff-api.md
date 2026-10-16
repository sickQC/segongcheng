# 前后端接口交接文档

> 2026-10-16 状态更新：下文保留最初的接口设计。演示课程中，`GET /resources` 已返回内置 Markdown 讲义目录；学生 `POST /chat` 的 `mode=rag` 已接真实模型和按相关性筛选的模拟学习历史；`GET /report?algorithm=baseline` 已返回分章节模拟历史；`POST /report/followup` 已接同一问答服务。这四条仅覆盖预置课程及 `student01`、`student02`，数据来源在响应和页面标为 `synthetic`。`mode=5e`、`algorithm=enhanced`、正式测验、教师看板等仍返回 501。新增字段和演示步骤见 [个性化演示说明](personalized-demo.md)，运行时契约以 `/openapi.json` 为准。

> 后续整合说明：伙伴的 RAG 演示模块已纳入整合分支，详见 [合并修复与可用性检查](integration-review.md)。正式课程聊天仍为 501 占位；下文“未实现”不代表文件检索内核不存在。
日期：2026-10-14。交付范围：P1 真实业务 + 四类页面及接口框架，未完成课程全功能验收。

## 1. 先看状态

- **已实现**：登录/会话、课程、章节、知识点、课程成员。实际读写 PostgreSQL。
- **仅契约与权限骨架**：第 4 节除上方更新说明中的演示分支外，其余业务仍返回 HTTP 501 `NOT_IMPLEMENTED`。
- **尚无路由**：上传与解析、题库维护和发布、图谱、行为采集、推荐反馈等。目标设计仍见 `api-design.md`，不能按已上线接口调用。
- **旧演示**：`/api/dev/*`、`/api/diagnoses*` 由 ENABLE_DEV_ROUTES 开关控制，固定模拟用户，不是正式账号的学习报告。

实际机器可读契约见 [api.yaml](api.yaml)，运行后见 `/docs` 或 `/openapi.json`。OpenAPI 中新接口声明的 200/201/202 是未来成功结构，**现在只返回鉴权/参数错误或 501**。前端预览不会访问这些新接口，也不会回退成假成功。

## 2. 通用约定

- 基础路径 `/api/v1`，JSON snake_case；ID 是不透明字符串，时间按 ISO 8601 UTC 交付。百分比字段为 0–100。
- Cookie `se_session`；登录需可信 `Origin`，其他写请求还需 `X-CSRF-Token`，token 从 login/me 响应获取。同源 fetch，统一调用 `frontend/src/api/client.ts`。
- `401` 未登录/过期；`403` CSRF、来源或权限不符；`404` 课程/学生不存在；`409` 数据冲突；`422` 参数错误；`501` 已声明但未实现。
- 错误形状：`{"detail":{"code":"NOT_IMPLEMENTED","message":"此业务尚未实现；可手动开启界面预览查看布局。"},"request_id":"..."}`，响应头含 X-Request-ID。
- P1 列表采用分页 `{items,total,page,page_size}`；本轮 resources/quizzes 是完整数组，报告和看板为聚合对象。与旧草案中的统一分页不同；后续改分页须同步前端。
- 所有新接口先检查登录和课程成员；dashboard 和 students 子路由要求本课程教师。学生个人报告取登录用户身份，不能从查询参数指定他人。
- 未实现的实体归属检查：resource/quiz/attempt 尚无模型，所以目前只有课程权限和基本参数校验。落地时必须补充实体所属课程、作答所属用户及状态校验。

## 3. 已完成的 P1 接口

以下路径均相对 `/api/v1`；字段全部定义见后端 `schemas/foundation.py` 和 api.yaml。

| 方法 | 路径 | 请求 | 成功响应 / 权限 |
|---|---|---|---|
| POST | /auth/login | username,password | 200 AuthOut；无需已有会话，需 Origin |
| GET | /auth/me | 无 | 200 AuthOut；登录 |
| POST | /auth/logout | 无 | 204；登录 + CSRF |
| GET | /courses | page=1,page_size=20 | 200 Page[CourseOut]；本人的课程 |
| POST | /courses | title,description? | 201 CourseOut；教师 |
| GET | /courses/{course_id}/outline | 无 | 200 Outline；课程成员 |
| POST | /courses/{course_id}/chapters | title,sort_order? | 201 ChapterOut；课程教师 |
| PATCH | /chapters/{chapter_id} | title/sort_order，至少一个 | 200 ChapterOut；课程教师 |
| POST | /chapters/{chapter_id}/knowledge-points | code,name,definition,difficulty,bloom_level | 201 KpOut；课程教师 |
| PATCH | /knowledge-points/{kp_id} | name/definition/difficulty/bloom_level，至少一个 | 200 KpOut；课程教师 |
| DELETE | /knowledge-points/{kp_id} | 无 | 204；课程教师 |
| GET | /courses/{course_id}/members | page,page_size | 200 Page[MemberOut]；课程教师 |
| POST | /courses/{course_id}/members | username | 201 MemberOut；课程教师；学生账号须已存在 |

AuthOut 为 `{user,csrf_token,expires_at,courses}`，user 为 `{id,username,display_name,role}`。Outline 为 `{course,chapters}`，每个 chapter 含 knowledge_points。知识点难度 1–5，bloom_level 为 remember/understand/apply/analyze/evaluate/create。当前没有注册、重置密码、批量导入学生功能。

## 4. 原预留接口（部分已有受限演示实现）

公共前缀 `B=/api/v1/courses/{course_id}`。成功结构在第 5 节；实际状态按本文开头的 2026-10-16 更新说明区分。

| 方法与路径 | 请求参数 | 未来成功结构 | 页面 |
|---|---|---|---|
| GET B/resources | 无 | 200 ResourceOut[] | 资源学习 |
| POST B/chat | ChatIn | 200 ChatOut | 资源学习 |
| GET B/quizzes | 无 | 200 QuizOut[] | 课程测验 |
| POST B/attempts | StartAttemptIn | 201 AttemptOut | 开始测验 |
| POST B/attempts/{attempt_id}/submit | SubmitIn | 200 ResultOut | 提交测验 |
| GET B/report | algorithm=baseline 或 enhanced，默认 baseline | 200 ReportOut | 本人学习报告 |
| POST B/report/followup | FollowupIn | 200 ChatOut | 诊断追问 |
| GET B/dashboard | 无 | 200 DashboardOut | 教师看板 |
| GET B/students/{student_id}/report | 无 | 200 ReportOut | 教师学生详情 |
| POST B/students/{student_id}/diagnoses | 无请求体 | 202 JobOut | 教师手动诊断 |

### 调用示例

```ts
// 会话与 CSRF 由已有 client.ts 处理。当前预期 ApiError.status === 501。
await workspaceApi.chat(courseId, {
  resource_id: resourceId,
  message: '功能需求与质量要求有什么区别？',
  mode: 'rag', // 或 '5e'
})
await workspaceApi.submit(courseId, attemptId, [
  {question_id: questionId, value: ['用户可以导出报告']},
])
```

### 对接语义和必须补齐的约束

- ResourceOut.url：已授权的 http(s) 媒体或浏览器可预览文档地址，可为 null；前端拒绝其他协议。视频用原生 video，文档用 iframe。PPT/Word 须由后端转 PDF 或提供可预览地址；当前没有转换器。媒体授权不能只保护列表接口。
- CitationOut：page 为从 1 开始的页码，seconds 为视频秒数，至少一个非 null（业务层待校验）。resource_id 必须属于课程且可访问。前端支持列表内引用定位；跨分页/外部资源引用解析待扩展。
- ChatIn 当前按 JSON 单次请求，**没有会话 ID、历史上下文或 SSE**。接入真实多轮/5E/流式服务前必须增加会话与流协议，同步客户端；当前 15 秒请求超时不适合长模型任务。
- QuestionOut 不含正确答案；options 当前是唯一选项文本数组。value 对单选/判断为一个选项文本，多选为多个文本，填空为一个字符串。正式题库若改稳定选项 ID，需同时修改前后端。题目版本应冻结在 attempt。
- expires_at 由服务器计算；浏览器倒计时仅提示。服务端须校验开放时间、限时、次数、归属、重复提交、题目 ID 和合法答案；完成幂等写入、判分、错题和诊断触发。目前 UI 不自动交卷、不保存草稿，刷新会清空未提交答案。
- ReportOut 的 evidence_ids 当前仅展示标识，尚无证据详情接口；记录/时间线为聚合只读数据。画像中的 value 是展示归一化值，正式四维含义和计算公式需在业务阶段定义。
- recommendations 数组顺序就是建议学习顺序；算法选择仅向后端传参，没有前端算法。预算输入、接受/拒绝反馈和对比指标未实现。
- DashboardOut.students.mastery 按 knowledge_points 顺序一一对应；分布人数与学生数口径须一致。活跃、完成率和平均分统计窗口尚需业务方约定；当前无日期筛选。
- JobOut 返回 job_id 后，后续需要任务状态/失败/重试接口。本轮仅预留触发入口，没有任务执行或轮询。

## 5. 数据结构（从当前 Python 模型自动整理）

以下是未来成功响应/当前输入的字段定义，不是已有数据库内容。必填为“是”的 nullable 字段必须显式返回 null。详细长度、数值范围和 extra=forbid 约束以 api.yaml 为准。

### ResourceOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| id | `{"type": "string"}` | 是 |
| title | `{"type": "string"}` | 是 |
| type | `{"enum": ["video", "doc"], "type": "string"}` | 是 |
| url | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` | 是 |
| description | `{"type": "string"}` | 是 |
| knowledge_point_ids | `{"items": {"type": "string"}, "type": "array"}` | 是 |

### CitationOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| resource_id | `{"type": "string"}` | 是 |
| title | `{"type": "string"}` | 是 |
| page | `{"anyOf": [{"minimum": 1, "type": "integer"}, {"type": "null"}]}` | 是 |
| seconds | `{"anyOf": [{"minimum": 0, "type": "number"}, {"type": "null"}]}` | 是 |

### ChatIn

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| resource_id | `{"maxLength": 100, "minLength": 1, "type": "string"}` | 是 |
| message | `{"maxLength": 2000, "minLength": 1, "type": "string"}` | 是 |
| mode | `{"enum": ["rag", "5e"], "type": "string"}` | 是 |

### FollowupIn

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| message | `{"maxLength": 2000, "minLength": 1, "type": "string"}` | 是 |

### ChatOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| message | `{"type": "string"}` | 是 |
| citations | `{"items": {"$ref": "#/$defs/CitationOut"}, "type": "array"}` | 是 |
| phase | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` | 是 |

### QuizOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| id | `{"type": "string"}` | 是 |
| title | `{"type": "string"}` | 是 |
| duration_minutes | `{"minimum": 1, "type": "integer"}` | 是 |
| attempts_remaining | `{"minimum": 0, "type": "integer"}` | 是 |

### QuestionOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| id | `{"type": "string"}` | 是 |
| type | `{"enum": ["single", "multiple", "boolean", "fill"], "type": "string"}` | 是 |
| stem | `{"type": "string"}` | 是 |
| options | `{"items": {"type": "string"}, "type": "array"}` | 是 |
| points | `{"minimum": 0, "type": "number"}` | 是 |

### StartAttemptIn

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| quiz_id | `{"maxLength": 100, "minLength": 1, "type": "string"}` | 是 |

### AttemptOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| id | `{"type": "string"}` | 是 |
| quiz_id | `{"type": "string"}` | 是 |
| expires_at | `{"type": "string"}` | 是 |
| questions | `{"items": {"$ref": "#/$defs/QuestionOut"}, "type": "array"}` | 是 |

### AnswerIn

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| question_id | `{"maxLength": 100, "minLength": 1, "type": "string"}` | 是 |
| value | `{"items": {"type": "string"}, "maxItems": 100, "type": "array"}` | 是 |

### SubmitIn

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| answers | `{"items": {"$ref": "#/$defs/AnswerIn"}, "maxItems": 500, "type": "array"}` | 是 |

### AnswerResultOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| question_id | `{"type": "string"}` | 是 |
| correct | `{"type": "boolean"}` | 是 |
| explanation | `{"type": "string"}` | 是 |

### ResultOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| score | `{"type": "number"}` | 是 |
| total | `{"type": "number"}` | 是 |
| answers | `{"items": {"$ref": "#/$defs/AnswerResultOut"}, "type": "array"}` | 是 |

### DiagnosisItem

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| knowledge_point | `{"type": "string"}` | 是 |
| mastery | `{"maximum": 100, "minimum": 0, "type": "number"}` | 是 |
| confidence | `{"maximum": 100, "minimum": 0, "type": "number"}` | 是 |
| issue | `{"type": "string"}` | 是 |
| evidence_ids | `{"items": {"type": "string"}, "type": "array"}` | 是 |

### ProfileItem

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| label | `{"type": "string"}` | 是 |
| value | `{"maximum": 100, "minimum": 0, "type": "number"}` | 是 |

### RecommendationItem

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| title | `{"type": "string"}` | 是 |
| reason | `{"type": "string"}` | 是 |
| minutes | `{"minimum": 0, "type": "integer"}` | 是 |
| resource_id | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` | 是 |

### RecordItem

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| title | `{"type": "string"}` | 是 |
| score | `{"type": "number"}` | 是 |
| at | `{"type": "string"}` | 是 |

### MistakeItem

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| stem | `{"type": "string"}` | 是 |
| explanation | `{"type": "string"}` | 是 |

### TimelineItem

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| at | `{"type": "string"}` | 是 |
| description | `{"type": "string"}` | 是 |

### ReportOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| diagnosis | `{"items": {"$ref": "#/$defs/DiagnosisItem"}, "type": "array"}` | 是 |
| profile | `{"items": {"$ref": "#/$defs/ProfileItem"}, "type": "array"}` | 是 |
| recommendations | `{"items": {"$ref": "#/$defs/RecommendationItem"}, "type": "array"}` | 是 |
| records | `{"items": {"$ref": "#/$defs/RecordItem"}, "type": "array"}` | 是 |
| mistakes | `{"items": {"$ref": "#/$defs/MistakeItem"}, "type": "array"}` | 是 |
| timeline | `{"items": {"$ref": "#/$defs/TimelineItem"}, "type": "array"}` | 是 |

### StudentMetric

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| id | `{"type": "string"}` | 是 |
| name | `{"type": "string"}` | 是 |
| mastery | `{"items": {"type": "number"}, "type": "array"}` | 是 |
| risk | `{"type": "string"}` | 是 |

### QuestionMetric

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| stem | `{"type": "string"}` | 是 |
| correct_rate | `{"maximum": 100, "minimum": 0, "type": "number"}` | 是 |
| average_seconds | `{"minimum": 0, "type": "number"}` | 是 |
| option_counts | `{"additionalProperties": {"type": "integer"}, "type": "object"}` | 是 |

### ScoreBucket

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| label | `{"type": "string"}` | 是 |
| count | `{"minimum": 0, "type": "integer"}` | 是 |

### DashboardOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| student_count | `{"minimum": 0, "type": "integer"}` | 是 |
| active_count | `{"minimum": 0, "type": "integer"}` | 是 |
| completion | `{"maximum": 100, "minimum": 0, "type": "number"}` | 是 |
| average_score | `{"type": "number"}` | 是 |
| knowledge_points | `{"items": {"type": "string"}, "type": "array"}` | 是 |
| students | `{"items": {"$ref": "#/$defs/StudentMetric"}, "type": "array"}` | 是 |
| questions | `{"items": {"$ref": "#/$defs/QuestionMetric"}, "type": "array"}` | 是 |
| score_distribution | `{"items": {"$ref": "#/$defs/ScoreBucket"}, "type": "array"}` | 是 |

### JobOut

| 字段 | 类型 / 约束 | 必填 |
|---|---|---|
| job_id | `{"type": "string"}` | 是 |

## 6. 交接位置与修改流程

- 页面：frontend/src/views/{LearningView,QuizView,LearningReportView,TeacherDashboardView}.vue。
- 共享：components/WorkspaceHeader.vue、ReportPanels.vue；types/workspace.ts；api/workspace.ts。
- 样例：api/preview.ts，只在用户明确开启预览后使用；默认真实接口报 501，不自动用样例兜底。
- 后端：api/routes/workspace.py、schemas/workspace.py。把 pending() 替换为业务服务调用，继续复用 deps.py 的权限检查。
- 建议新增 services/resources.py、quizzes.py 等和增量 Alembic 迁移，不修改已运行的 0001/0002。
- 修改契约顺序：Python 模型 → TS 类型 → 页面和请求函数 → 测试 → 导出 api.yaml → 更新本文。旧 api-design.md 是完整目标草案，差异应显式评审，不能混用。
- 开发完成后，把测试中对应接口的 501 断言替换为真正业务和隔离断言；不得只删除权限测试。

剩余任务与建议顺序见 [handoff-todo.md](handoff-todo.md)。
