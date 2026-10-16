# master 合并修复与 RAG 可用性检查

日期：2026-10-14。工作分支：codex/integrate-rag，基于本地 master 的 3de5e72；原 main/master 指针保持不变。

## 发现的合并问题

1. 两条开发线都增加了 revision=0002 的迁移，Alembic 无法确定 head。
2. master 保留了伙伴的 tutor 文件，但 main.py 使用新的路由组织，漏了注册 tutor_router。
3. 模型重构到 models/legacy.py 后，没有带回伙伴的可空 diagnosis_id、feature、event_id、details。
4. requirements-lock.txt 有 RAG 依赖，但 pyproject.toml 没有；本机虚拟环境也尚未安装。
5. 伙伴的接口测试假设助教路由默认开放，与当前 ENABLE_DEV_ROUTES 的演示隔离约定冲突。

## 修复方案

- 保留已用于 P1 的 0002_foundation；将尚未在本机执行的 RAG 迁移改为 0003，依赖 0002。
- 补齐 ModelTrace 字段，迁移和 ORM 的列类型、可空性、索引保持一致。
- 在 ENABLE_DEV_ROUTES=true 时注册原 /api/tutor/*、/api/traces/*、/api/cost-report。关闭时这些接口返回 404。
- 这些是固定模拟学生、共享文件知识库的本地演示接口，不接入 /api/v1/courses/{id}/chat，不把它们冒充正式多用户业务。
- 同步依赖声明，调整测试的演示开关，增加旧 P1 升级保留账号、历史错误迁移拒绝和关闭路由测试。
- ENABLE_DEMO=false 时禁止离线 demo 模式；live 缺少 key/model 仍返回错误，不降级伪造成功。

## 数据库注意事项

当前迁移链为 0001 → 0002（账号课程）→ 0003（RAG trace）。运行 scripts/start.ps1 会先升级数据库。

如果伙伴的数据库已在旧代码下执行“RAG 版 0002”，该版本号与 P1 的 0002 含义不同：不能直接 stamp 到 0003。本轮新增检测，在没有 users 表时拒绝继续。课程演示数据可在新的独立数据库重新迁移；需要保留伙伴原数据时应先备份并单独编写迁移转换，不能盲目改版本号。降级 RAG 迁移会删除无 diagnosis_id 的助教 trace，不作为常规操作。

## 可复用内容与边界

可复用：Markdown 讲义切分、领域分词/同义词、BM25 与本地 hashing TF-IDF 混合检索、先修图数据、引用/拒答与提示注入护栏、离线抽取式回答、问答事件与模型 trace、SSE 演示、检索消融脚本。

仍需开发或验证：

- 正式课程和登录用户隔离；当前 actor 为固定 sim-student-001、课程为 SE。
- 学习页面的 chat 契约适配、真实资源 ID/页码/时间戳、会话历史和多轮上下文。
- 教师上传文件、PPT/Word/PDF 解析、数据库知识点与文件元数据同步。
- 真实模型联网质量、成本与首字延迟；本轮仅离线验证，不能视为 M7 最终验收。
- 流式中断/配置失败的持久化与重试仍需完善；当前成功路径可测，不代表失败路径全部完备。
- 正式服务不能沿用演示接口的 GET 流式写入与全局 trace/cost 查询，需要鉴权、CSRF、资源归属和接口调整。
- 文件知识库和现有数据库课程是两套数据，不能将文件中的知识点数量当作数据库课程已完成。

## 接手入口

开发演示接口与正式四页面占位接口并存。正式接口状态仍以 handoff-api.md 为准。运行本轮整合代码前需重新安装 requirements-lock.txt，然后执行迁移。不要只复制 tutor.py 而漏掉迁移、模型与依赖。

## 实测结果

- `scripts/test.ps1 -Postgres`：96 项通过，覆盖旧诊断、P1、SQLite/PostgreSQL、RAG 与迁移。前端 vue-tsc/Vite 构建通过。
- Ruff、pip check 通过。前端仍有既有大 chunk 提示；Starlette 测试客户端有弃用提示，不阻断测试。
- 本机确认原库是带 users 表的 P1 0002 后，已执行增量升级至 0003；Alembic check 无结构漂移。没有导入或删除业务数据。
- 知识库构建：5 文档、100 chunk、39 知识点、49 关系；索引位于忽略的 data/index。
- 显式 offline + hashing 模式运行 test split：28 题（18 课程内、4 超范围、3 注入、3 作弊）。doc_hit@3=1.0、MRR=0.9444；该小样本集上的引用编号有效率、拒答与护栏指标为 1.0。这是自带离线评测，不证明真实模型质量或完整验收达标。
- 本轮完整评测输出在本机 `.local/rag-integration-eval.json`，未覆盖伙伴提交的历史 data/eval/report.json。
- 额外修复 Windows 下构建/评测脚本因 GBK 控制台无法输出符号而崩溃的问题。

重现：在项目环境安装 requirements-lock.txt，执行 scripts/test.ps1 -Postgres；离线评测设置 SE_RAG_LLM_PROVIDER=offline、SE_RAG_EMBED_BACKEND=hashing，先运行 scripts/build_rag_index.py，再运行 scripts/eval_rag.py --mode all --split test --out .local/rag-integration-eval.json。运行应用请重启后端，旧进程不会自动注册新增路由。

## 2026-10-14 后续：课程答疑接入 RAG

原整合方案把 `/api/v1/courses/{id}/chat` 留作 501 占位。现按 M7 需求将其接入检索内核：

- `services/tutor.course_chat` 复用同一套检索、护栏与拒答逻辑，改用**登录用户**作为事件 actor，
  并把 `course_id`、`resource_id` 记入 `LearningEvent.context`，可按课程回溯。
- 复用请求自身的数据库会话；仅"模型不可用"的失败记录改用独立事务，
  否则会被错误响应的事务回滚，学生的问题丢失。
- 事件里保存的是**学生可见的引用结构**（resource_id/title/section），
  片段 ID 与检索分数保留在 `model_traces.details.retrieved`，供误差分析。
- 讲义类来源没有页码与视频时间点，引用改由 `section` 定位；前端标签优先显示小节路径。
- `mode=5e` 仍返回 501：不把普通答疑静默降级冒充 5E 引导。
- 未配置密钥且 `ENABLE_DEMO=false` 时返回 503 `MISSING_API_KEY`，并保留学生的问题，不写入伪造回答。
