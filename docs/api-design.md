# 平台接口设计草案

> 本轮新增四页面接口框架。当前可调用契约、501 占位状态及与本文差异见 [接口交接文档](handoff-api.md)。本文保留完整目标设计，不能将尚未注册的接口视为已实现。

版本：v0.2；日期：2026-10-14；状态：P1 部分实现，其余待开发。覆盖 M1–M10、FR-04 追问、暂定 E1/E7。本文约定目标契约，供按阶段开发；当前真实接口仍以 [api.yaml](api.yaml) 和后端代码为准，不将草案混入自动生成文件。

## P1 实施状态

已实现第 4 节登录/me/退出、课程列表/创建/目录、章节新建/修改、知识点新建/修改/删除。CSV 导入未实现。补充两个最小成员接口：GET /api/v1/courses/{course_id}/members（教师、分页 MemberOut），POST 同路径（教师，{username}，201 MemberOut）；用于把已有学生加入新课程。MemberOut={user,role}。登录和 me 都返回 user/csrf_token/expires_at/courses。

第 5–10 节完整学习业务未实现。旧诊断接口保留为显式开发模式；当前实际导出见 api.yaml（包括启用时的旧演示接口）。默认 ENABLE_DEV_ROUTES=false，本机课堂配置显式开启。

## 1 当前与目标接口的区别

现有接口：`GET /health`、`GET /api/dev/question`、`POST /api/dev/submissions`、`GET /api/diagnoses`、`GET /api/diagnoses/{diagnosis_id}`、`POST /api/diagnoses/{diagnosis_id}/retry`。以上旧接口属于开发演示，固定模拟学生；新 /api/v1 账号课程接口已实现会话鉴权。

正式接口前缀 `/api/v1`，避免改变旧响应格式导致当前页面失效。现有诊断列表返回数组，目标返回分页对象；旧诊断单知识点，目标为多知识点列表。旧接口在开发模式继续回归，在正式部署关闭，不把 `ENABLE_DEMO=false` 误当成禁用全部开发接口（当前它只禁用 demo 模式）。

## 2 通用约定

- JSON 字段 snake_case；ID 为字符串 UUID，示例的 course-1/kp-1 等仅为易读占位符。时间 ISO 8601 带时区，持久化 UTC。
- 登录采用数据库会话，Cookie `se_session` 为 HttpOnly、SameSite=Lax、生产 Secure；会话 token 仅服务端保存哈希。登录/写请求校验 Origin，登录后写请求携带 `X-CSRF-Token`（由登录或 me 获取）。同源部署，前端 fetch 使用会话 Cookie。
- `S` 学生、`T` 本课程教师、`U` 已登录用户。所有资源均须校验课程成员；学生仅操作本人对象。请求中的 student_id 不能覆盖登录身份。不同课程/用户资源访问返回 403，真正不存在返回 404。
- 对象读写直接返回对象，不包多层 code/data；列表统一 `{items: [], total: 0, page: 1, page_size: 20}`。page≥1，page_size 为 1–100。
- 创建一般 201，异步启动 202，查询/修改 200，删除/退出 204 无正文。模型处理失败通过任务状态返回；提交已成功后不得返回“作答丢失”。
- 错误统一 `{detail: {code, message, fields?}, request_id}`；422 请求校验，401 未登录，403 越权，404 不存在，409 状态/重复冲突，413 文件超限，415 格式不支持，429 超出调用限额，503 依赖不可用。实现时同时统一 FastAPI 默认 validation error。
- GET 只查询业务结果，不新触发模型/推荐；到期测验由定时结算器处理。所有可重试写入用客户端 request_id 或 client_event_id 去重，唯一键必须包含用户及业务范围，不能只在前端禁用按钮。
- 未写“可选”的请求字段均必填；PATCH 仅发送允许修改的字段，至少一个字段。列表筛选均可选，教师请求本课程对象时仍验证归属。

错误示例：

```json
{"detail":{"code":"PREREQUISITE_CYCLE","message":"先修关系形成环","fields":{"cycle":["kp-1","kp-2","kp-1"]}},"request_id":"req-1"}
```

## 3 公共对象

| 对象 | 字段与约束 |
|---|---|
| User | id, username, display_name, role(student/teacher)；不返回密码/哈希 |
| Course | id, title, description, teacher_id |
| Chapter | id, course_id, title, sort_order（非负整数） |
| KnowledgePoint | id, code, chapter_id, name, definition, difficulty(1–5), bloom_level, resource_ids, question_ids |
| Edge | id, course_id, from_kp_id, to_kp_id, relation_type(prerequisite/related/confusable)；章节包含关系由 outline 表达 |
| Resource | id, course_id, chapter_id, title, type(video/slide/doc), knowledge_point_ids, status(pending/processing/ready/failed), preview_url, download_url, error_code/message, duration_seconds? |
| Citation | resource_id, chunk_id, title, page_no(int≥1或null), start_s/end_s(≥0或null), url；页码和时间至少一种有效 |
| Question | id, course_id, type(single/multiple/boolean/fill), stem, options, knowledge_point_ids, difficulty, answer, explanation；学生未交卷响应剔除最后两项 |
| Attempt | id, quiz_id, student_id, status(in_progress/submitted), started_at, deadline_at, submitted_at, score, max_score, diagnosis_id；提交前 score/diagnosis_id 为 null |
| Event | event_id, actor, verb, object{type,id,kp[]}, result, context{course,session?,synthetic,source}, timestamp |
| Trace | trace_id, feature, business_id, model, prompt_version, status, retrieval_chunk_ids, latency_ms, usage, estimated_cost, currency, error_code；未知用 null |

普通字符串默认非空；标题≤200，定义/解析≤8000，答案/用户消息≤4000，名称/用户名≤100。题型、模型枚举和范围通过 Pydantic 校验；引用不能由客户端直接写入系统答案。

## 4 登录和课程

下文方法与路径均省略 `/api/v1`。

| 方法与路径 | 权限 | 请求 | 返回 |
|---|---|---|---|
| POST /auth/login | 匿名 | username, password | 200：user, csrf_token, expires_at；Set-Cookie |
| GET /auth/me | U | 无 | user, csrf_token, courses[] |
| POST /auth/logout | U | 空 | 204；使会话失效 |
| GET /courses | U | 分页 | Course 列表，只返回本人课程 |
| POST /courses | T | title, description | 201 Course；创建者为教师 |
| GET /courses/{course_id}/outline | U | 无 | course, chapters[{id,title,sort_order,knowledge_points[]}] |
| POST /courses/{course_id}/chapters | T | title, sort_order | 201 Chapter |
| PATCH /chapters/{chapter_id} | T | title/sort_order | Chapter |
| POST /chapters/{chapter_id}/knowledge-points | T | code,name,definition,difficulty,bloom_level | 201 KnowledgePoint |
| PATCH /knowledge-points/{kp_id} | T | name/definition/difficulty/bloom_level | KnowledgePoint |
| DELETE /knowledge-points/{kp_id} | T | 无 | 204；有依赖对象时 409，不级联删除历史 |
| POST /courses/{course_id}/students/import | T | multipart CSV file | created_count, skipped_count, errors[{row,code,message}]；P1 后补 |

课程成员先由种子脚本创建，导入功能后补；不做开放注册。导入仅使用模拟账号，初始密码通过本地配置给出，不能在日志输出。bloom_level 枚举 remember/understand/apply/analyze/evaluate/create。

## 5 图谱、资源和学习事件

| 方法与路径 | 权限 | 请求/筛选 | 返回 |
|---|---|---|---|
| GET /courses/{course_id}/graph | U | student_id（仅 T 可指定） | nodes[{KnowledgePoint,mastery,confidence}], edges[], contains[] |
| POST /courses/{course_id}/knowledge-edges | T | from_kp_id,to_kp_id,relation_type | 201 Edge；成环 409 并附 cycle |
| DELETE /knowledge-edges/{edge_id} | T | 无 | 204 |
| GET /courses/{course_id}/resources | U | type,kp_id,分页 | Resource 列表 |
| POST /courses/{course_id}/resources | T | multipart 见下 | 202 Resource，status=pending |
| GET /resources/{resource_id} | U | 无 | Resource，处理进度状态 |
| POST /resources/{resource_id}/retry | T | 空 | 202；仅 failed 可重试，其余 409 |
| GET /resources/{resource_id}/content | U | variant=original/preview | 文件流，video 支持 Range，正确 Content-Type |
| GET /resources/{resource_id}/progress | S | 无 | position_s, watched_seconds, covered_seconds, completion_rate, updated_at |
| POST /learning-events | S | 允许的客户端行为事件，见下 | 201 Event；重复相同 client_event_id 返回已有 200 |
| GET /learning-events | U | course_id 必填；student_id,kp_id,from,to,verb,分页 | Event 列表；学生自动本人 |
| GET /learning-events/export | U | 同上，format=json/csv | 下载文件，权限范围同查询；后补 |

上传 multipart：`title,chapter_id,type,knowledge_point_ids`（JSON 数组字符串），`file` 与 `external_url` 二选一；仅 video 允许 external_url，file 支持 PDF/PPT/PPTX/DOC/DOCX/MP4，默认文档≤20MB、视频≤200MB，可配置。关联知识点必须同课程。正文解析、PDF 转换及 embedding 不在上传事务里执行。embedding 接入前资源可预览，检索状态另设 `index_status=pending/ready/failed`，只有索引 ready 才可参与 RAG。

外链只登记可播放的 HTTP(S) URL，不通过后端任意抓取内网地址；课件都以文件上传。查询的预览/下载链接指向鉴权文件接口。浏览器发起下载/打开预览时显式记录事件，避免 Range 请求反复记录 viewed。开发时可用 Cookie 让 video/iframe 同源鉴权。

客户端事件请求示例：

```json
{"client_event_id":"client-1","course_id":"course-1","verb":"seeked","object":{"type":"video","id":"res-1"},"result":{"from_s":60,"to_s":240},"session_id":"play-1"}
```

允许 played/paused/seeked/rate_changed/completed/left/heartbeat/viewed/downloaded；按类型限制 result（position_s、from_s/to_s、rate、page、duration_s）。heartbeat 另含 last_position_s、position_s、elapsed_s、visible、playback_rate；服务器校验非负、合理上限和视频长度，结合 event 去重更新进度。课程和知识点从资源记录回填，timestamp 由服务器生成。completed 只是行为声明，完成率由服务端区间计算，不相信客户端百分比。

answered/submitted/asked/rated/diagnosed/recommended 由对应业务服务写入，不允许通用客户端接口提交。

## 6 题库与测验

| 方法与路径 | 权限 | 请求/筛选 | 返回 |
|---|---|---|---|
| GET /courses/{course_id}/questions | T | kp_id,type,分页 | 教师 Question 列表（含答案） |
| POST /courses/{course_id}/questions | T | type,stem,options,knowledge_point_ids,difficulty,answer,explanation | 201 Question |
| PATCH /questions/{question_id} | T | 题目可编辑字段 | Question；不改已发布试卷快照 |
| GET /courses/{course_id}/quizzes | U | 分页 | 测验摘要含开放时间、时限、剩余次数 |
| POST /courses/{course_id}/quizzes | T | title,question_ids,points[],opens_at,closes_at,time_limit_seconds,max_attempts | 201 Quiz，status=draft；points 与题目同长度 |
| POST /quizzes/{quiz_id}/publish | T | 空 | Quiz，status=published；校验题目/分值/时间 |
| GET /quizzes/{quiz_id} | U | 无 | 测验摘要及规则；不提前返回答案 |
| POST /quizzes/{quiz_id}/attempts | S | request_id | 201 Attempt + 不含答案的题目快照；已有进行中返回 200 |
| PATCH /attempts/{attempt_id}/answers/{question_id} | S | answer,elapsed_seconds,revision | 200：saved_at,revision；旧 revision 409 |
| POST /attempts/{attempt_id}/submit | S | request_id,answers[] | 202：提交结果，见下 |
| GET /attempts/{attempt_id} | S/T | 无 | Attempt + answers；交卷后含判分与解析 |
| GET /students/me/attempts | S | course_id,分页 | 本人 Attempt 列表 |
| POST /attempts/{attempt_id}/answers/{question_id}/explanation-view | S | client_event_id | 保存 viewed 事件及 viewed_explanation=true；只限已交卷 |
| GET /students/me/mistakes | S | course_id,kp_id,分页 | question,answer,explanation,knowledge_points,resources[] |

题目答案格式：single 为选项 ID 字符串；multiple 为去重选项 ID 数组；boolean 为 JSON 布尔；fill 为按空顺序的字符串数组。教师填空 answer 为每空的可接受字符串数组列表。options 为 `{id,text}[]`，仅选择题使用。多选全匹配计分；填空全部空匹配才计分，详见主规划。

草稿 revision 从 1 递增，服务端按递增版本更新并统计修改次数；同版本同内容重试返回原结果，不重复增加次数；不同内容同版本 409。elapsed_seconds 范围 0–86400，服务端累计值限定在测验有效时长内。服务端超时结算使用最后保存草稿；提交发生在到期后不接收新的答案覆盖。

提交请求及响应（示例分数不是实测）：

```json
{"request_id":"submit-1","answers":[{"question_id":"q-1","answer":["A","C"],"elapsed_seconds":38,"revision":3}]}
```

```json
{"attempt_id":"attempt-1","status":"submitted","score":8,"max_score":10,"submitted_at":"2026-10-14T08:00:00Z","submission_event_id":"event-1","diagnosis_id":"diag-1","diagnosis_status":"pending"}
```

事务内锁定 attempt，保存最终答案、判分、answered/submitted 事件、pending 诊断及 trace，再后台调用模型。重复提交返回同一结果（200）且不再建诊断；已开始诊断不能依赖最新题库而丢失题目快照。限时 min(started_at+时限, closes_at)。前端提交只是辅助，后端定时结算器处理关闭页面的到期测验。

## 7 RAG 问答与流式协议

| 方法与路径 | 权限 | 请求 | 返回 |
|---|---|---|---|
| POST /chat/sessions | S | course_id,knowledge_point_id 可选,resource_id 可选 | 201：id,course_id,created_at |
| GET /chat/sessions/{session_id}/messages | S/T | 分页 | message 列表含问题/回答/引用/状态 |
| POST /chat/sessions/{session_id}/messages | S | request_id,question,resource_id 可选,knowledge_point_id 可选 | SSE 流，见下 |
| POST /chat/messages/{message_id}/feedback | S | rating(up/down),reason 可选≤1000 | 201：feedback_id,event_id；再次反馈更新原条 |

当前上下文必须属于会话课程；后端自行查询该学生进行中的测验，不能相信客户端 quiz_in_progress=false。模型只能检索本课程 ready 的片段，不把答案字段喂给正在测验的问答服务。

通过 `fetch(POST)` 读取 `text/event-stream`，不是原生 EventSource GET。顺序为 meta → delta 若干 → citations → done。无依据输出明确说明和空引用。返回 delta 前完成输入与测验护栏；引用 ID 只能来自已检索候选，非法引用不得进入最终消息。不能将一整段已生成答案切成字伪装模型流式。

```text
event: meta
data: {"message_id":"msg-1","trace_id":"trace-1"}

event: delta
data: {"text":"验证关注"}

event: citations
data: {"items":[{"resource_id":"res-1","chunk_id":"chunk-2","title":"课程讲义","page_no":3,"start_s":null,"end_s":null,"url":"/api/v1/resources/res-1/content?variant=preview#page=3"}]}

event: done
data: {"message_id":"msg-1","status":"completed","event_id":"event-2"}
```

SSE 建立前错误返回正常 HTTP JSON。建立后失败发送 `event:error`、`data:{code,message,trace_id}` 并关闭，消息标 failed，部分文字仅为未完成展示，不记作可信答案。保存用户问题和失败状态便于追踪。前端断开要取消上游调用并记 interrupted；用户重试使用新 request_id，重复旧 request_id 返回已完成消息回放或 409 MESSAGE_IN_PROGRESS，不重复计费。trace 和事件只写一次。流式超时单独配置，不能复用现有 15 秒 JSON fetch 封装。

## 8 诊断与追问

| 方法与路径 | 权限 | 请求/筛选 | 返回 |
|---|---|---|---|
| POST /diagnoses | T | course_id,student_id,knowledge_point_ids[],from,to,request_id | 202：id,status=pending,trace_id |
| GET /diagnoses | U | course_id 必填；student_id,status,kp_id,分页 | 诊断摘要列表，学生仅自己 |
| GET /diagnoses/{diagnosis_id} | S/T | 无 | 诊断详情、基线、可授权事件和 trace 摘要 |
| POST /diagnoses/{diagnosis_id}/retry | S/T | request_id | 202：同一 id，新 trace_id；仅 failed 可重试 |
| POST /diagnoses/{diagnosis_id}/followups | S | request_id,knowledge_point_id,answer | 202：followup_id,event_id,new_diagnosis_id,status=pending |
| GET /diagnoses/{diagnosis_id}/followups | S/T | 分页 | 已提出的追问、回复、新诊断引用和状态 |

自动诊断由交卷内部调用 service；学生不能指定别人的 student_id 发诊断。追问仅对本人且 supported/insufficient 的结果、实际存在的追问开放。新回答生成新事件和新诊断，保留旧结果，不覆盖历史。retry 保留原输入快照，重启标 PROCESS_INTERRUPTED 后可重试。

详情响应示例：

```json
{
  "id":"diag-1","student_id":"student-1","course_id":"course-1","attempt_id":"attempt-1",
  "status":"supported","source":"live","schema_version":"diagnosis-v2",
  "input_cutoff_at":"2026-10-14T08:00:00Z",
  "knowledge_states":[{"knowledge_point_id":"kp-1","mastery":0.4,"confidence":0.7,"evidence_event_ids":["event-1","event-2"]}],
  "problems":[{"type":"concept_confusion","knowledge_point_ids":["kp-1"],"description":"可能混淆了验证与确认","evidence_event_ids":["event-1","event-2"]}],
  "citations":[{"resource_id":"res-1","chunk_id":"chunk-2","title":"课程讲义","page_no":3,"start_s":null,"end_s":null,"url":"/api/v1/resources/res-1/content?variant=preview#page=3"}],
  "recommendations":[{"knowledge_point_id":"kp-1","text":"比较符合规格与满足需求两个角度"}],
  "followup_questions":[{"knowledge_point_id":"kp-1","text":"符合规格是否必然满足实际需求？"}],
  "baseline":{"method":"accuracy-v1","knowledge_states":[{"knowledge_point_id":"kp-1","mastery":0.5,"sample_count":2}]},
  "trace_ids":["trace-1"],"error":null,"profile_updated":true
}
```

mastery 为 [0,1] 或 null，confidence 为 [0,1]；问题 type 为 concept_confusion/prerequisite_gap/low_engagement/repeated_error/practice_only。无问题时 problems=[]，不足时掌握度 null 并写说明，不能编造问题。pending/failed 仍返回 id/owner/course/status，尚无结果字段用 null 或空数组，error={code,message}。详情还需 `created_at,updated_at,model,prompt_version,insufficient_reason`（不适用时 null）。本节例子只说明格式，不是模型验证结果。

只有校验通过的有效结果更新掌握度；baseline 不自动覆盖模型结果。非法 ID、引用、越权、JSON 错误将任务置 failed。证据存在性不是语义正确性，后者由评测检验。

## 9 画像、推荐和教师看板

| 方法与路径 | 权限 | 请求/筛选 | 返回 |
|---|---|---|---|
| GET /students/me/profile | S | course_id 必填 | 四维 Profile |
| GET /students/me/recommendations | S | course_id,分页 | 保存的推荐列表 |
| POST /students/me/recommendations | S | request_id,course_id,target_kp_id,strategy(baseline/budgeted),time_budget_minutes 可选(1–240) | 201 Recommendation；budgeted 必填预算 |
| POST /recommendations/{recommendation_id}/feedback | S | kp_id,feedback(mastered/too_hard/not_needed),request_id | 201：event_id,new_recommendation_id |
| GET /teacher/courses/{course_id}/overview | T | from,to 可选 | student_count,active_count,resource_completion_rate,average_score,score_distribution |
| GET /teacher/courses/{course_id}/knowledge-heatmap | T | 无 | items[{kp_id,average_mastery,diagnosed_count,student_count}] |
| GET /teacher/courses/{course_id}/questions/{question_id}/stats | T | from,to 可选 | answered_count,correct_rate,average_seconds,option_distribution |
| GET /teacher/courses/{course_id}/students | T | risk_only,分页 | 学生摘要和风险理由 |
| GET /teacher/courses/{course_id}/students/{student_id} | T | 无 | user,profile,latest_diagnosis,recommendations |
| GET /teacher/courses/{course_id}/students/{student_id}/timeline | T | kp_id,from,to,分页 | Event 列表 |
| GET /teacher/courses/{course_id}/model-usage | T | from,to,feature 可选 | calls,tokens,estimated_cost,unknown_cost_calls,by_feature[] |

Profile：`student_id,course_id,knowledge_states[],engagement{watched_seconds,active_days,completion_rate},preferences{video,document,practice,chat},risk{level,reasons[]},source_event_ids[],source_diagnosis_ids[],updated_at`。偏好为 [0,1] 比例，无样本均 null；统计须带时间窗。风险是规则估计，界面说明依据。

Recommendation：`id,target_kp_id,strategy,algorithm_version,diagnosis_ids[],steps[{order,kp_id,resource_ids[],question_ids[],reason,reason_source,diagnosis_id,estimated_minutes}],remaining_kp_ids[],estimated_minutes,created_at`。baseline 先修拓扑排序，budgeted 只选可学且预算内的步骤。mastered 反馈保存为学生自述并重算路径，可暂跳过，但不直接篡改客观掌握度；冲突时提示复测并保留证据。

统计口径：成绩按测验百分制归一后统计；单题正确率基于已提交作答；多选各选项比例允许总和>100%；平均掌握度只统计有有效诊断的学生，同时返回覆盖人数，未知不填零；资源完成率为课程成员×已发布资源范围内的平均进度（文档按阅读规则记录）；活跃为时间窗内有非 demo 学习事件。所有看板默认排除固定 demo 输出。

## 10 E1 学习会话

| 方法与路径 | 权限 | 请求 | 返回 |
|---|---|---|---|
| POST /learning-sessions | S | course_id,knowledge_point_id,request_id | 201：id,stage=engage,status=active |
| GET /learning-sessions/{session_id} | S/T | 无 | id,stage,status,turns[],evaluation,updated_at |
| POST /learning-sessions/{session_id}/turns | S | answer,request_id | 202：turn_id,status=pending,trace_id |
| GET /learning-sessions/{session_id}/turns/{turn_id} | S/T | 无 | status,reply,stage_before,stage_after,transition_reason,citations[],evaluation,error |

五阶段为 engage/explore/explain/elaborate/evaluate，评价通过才 completed。轮次保存真实模型回复、质量评分、切换理由和事件，失败重试同 request_id 返回已有失败状态；重新请求须新 request_id，且不能并发生成两轮。session_id 限定学习状态，不能让客户端直接指定下一阶段或 passing=true。

## 11 实施契约检查

按阶段为新接口补 Pydantic 请求/响应模型及权限测试，导出 FastAPI OpenAPI 到 `docs/api.yaml`；新增接口在本草案标记实现日期，不能用本文替代实际导出。至少验证：分页/错误模型、四题型、重复提交、CSRF/越权、资源引用、SSE 结束/失败、异步状态、追问和画像一致性。P2 版本管理与导出扩展另写契约，不阻塞主线；本草案尚不涵盖这些未来扩展的全部字段。
