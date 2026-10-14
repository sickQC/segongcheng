> 最新页面框架与交接状态见 [handoff-todo.md](handoff-todo.md)，本文保留原分步实施路线。

# 项目目录与分步实施路线

日期：2026-10-14。P1 已按本方案实施，完成状态和实测见 [P1 记录](sprint/p1-foundation.md)；下文原目录盘点保留为实施前基线。配套 [需求规划](../需求规划.md) 和 [接口草案](api-design.md)。本文是实施方案，原规划轮次仅改文档；随后开发轮次已经完成 P1 代码、依赖和数据库初始化。

## 1 从头开始是否应该重写

不建议清空项目。现有工程已经提供可以验证的提交事务、模型错误处理、结果轮询、失败重试、迁移和测试基础。最合理的“重新开始”是重新确定完整功能的开发顺序，保留这些基础，再接账号、课程和正式题库。

不能直接把固定题目演示复制成完整系统：当前没有用户隔离；诊断只接受 KP-VAL-01、一个事件和空引用；题目写在 Python 常量；简答不判分；前端追问不能回答；Compose 只有数据库。不存在可可靠估计的“完成百分比”，应按模块判定。

## 2 当前实际目录

```text
segongcheng/
├── 需求规划.md                     # v2 主规划
├── 软件工程智能学习平台_*.docx      # 原始课程依据，保留原件
├── README.md                       # 当前 Sprint 0 运行说明
├── .env.example / .gitignore
├── backend/
│   ├── pyproject.toml / requirements-lock.txt
│   ├── app/
│   │   ├── main.py                  # 当前全部路由、应用工厂、生命周期
│   │   ├── core/config.py           # 配置和密钥
│   │   ├── core/database.py         # engine/session、SQLite 设置
│   │   ├── models/__init__.py       # 事件、诊断、trace 三张业务表
│   │   ├── schemas/__init__.py      # Submission、DiagnosisOutput
│   │   ├── services/diagnosis.py    # 固定题目、模型调用、任务、重试 trace
│   │   ├── agents/diagnosis.py      # 固定知识点提示词
│   │   └── api/__init__.py          # 预留目录，尚未拆路由
│   ├── alembic/versions/0001_sprint0.py
│   └── tests/test_flow.py / test_migrations.py
├── frontend/
│   ├── package.json / package-lock.json
│   ├── vite.config.ts / tsconfig.json / index.html
│   └── src/
│       ├── main.ts / App.vue / style.css
│       ├── api.ts                   # 当前仅 GET/POST JSON 与固定类型
│       └── views/SubmitView.vue / DiagnosisView.vue
├── scripts/                        # setup/start/test.ps1、export_openapi.py
├── deploy/compose.yaml / init.sql   # 只有 PostgreSQL + pgvector 数据库
├── data/README.md                   # 尚无正式课程数据集和生成器
├── tests/README.md                  # 集成检查说明，不是完整 E2E 测试
└── docs/                           # 现有架构、OpenAPI、ADR、Sprint、课堂材料
```

`.venv`、`frontend/node_modules`、`frontend/dist`、数据库文件、`.local`、缓存等属于运行产物，不作为源代码结构或功能完成证据。当前没有 `.github/workflows` CI 实现。

## 3 目标目录

下列是目标结构，不代表文件已经存在。按阶段添加实际要用的模块，不提前创建大量空文件。

```text
segongcheng/
├── 需求规划.md
├── README.md / .env.example / .gitignore
├── backend/
│   ├── pyproject.toml / requirements-lock.txt
│   ├── app/
│   │   ├── main.py                  # 应用工厂、注册 router、启动恢复、静态文件
│   │   ├── api/
│   │   │   ├── deps.py              # 当前用户、课程权限、DB session、CSRF
│   │   │   └── routes/
│   │   │       ├── auth.py / courses.py / knowledge.py
│   │   │       ├── resources.py / events.py
│   │   │       ├── quizzes.py / chat.py / diagnoses.py
│   │   │       ├── profiles.py / recommendations.py / teacher.py
│   │   │       └── learning.py / dev.py
│   │   ├── core/
│   │   │   ├── config.py / database.py / security.py
│   │   │   └── errors.py / logging.py
│   │   ├── models/                  # 按业务拆文件，__init__ 导出兼容名
│   │   │   ├── users.py / courses.py / knowledge.py / resources.py
│   │   │   └── quizzes.py / events.py / conversations.py / diagnoses.py
│   │   │       profiles.py / recommendations.py / traces.py / learning.py
│   │   ├── schemas/                 # 与业务模块同名，区分教师/学生输出
│   │   ├── services/
│   │   │   ├── auth.py / courses.py / knowledge.py
│   │   │   ├── resources.py / parsing.py / progress.py / events.py
│   │   │   ├── quizzes.py / grading.py / expiry.py
│   │   │   ├── retrieval.py / diagnosis.py / profiles.py
│   │   │   └── recommendations.py / teacher.py / learning.py
│   │   └── agents/
│   │       ├── client.py            # 通用模型/embedding 客户端、限额和 trace
│   │       ├── tutor.py / diagnosis.py / learning.py
│   │       └── prompts/             # 版本化提示词
│   ├── alembic/versions/            # 保留 0001，逐阶段加迁移
│   └── tests/                      # 按模块拆，保留原回归
├── frontend/src/
│   ├── main.ts / App.vue / style.css
│   ├── router/index.ts
│   ├── api/                        # client.ts、auth.ts、courses.ts 等
│   ├── types/                      # 明确类型，和 API schema 一致
│   ├── composables/                # useSession、usePolling 等共享逻辑
│   ├── layouts/StudentLayout.vue / TeacherLayout.vue
│   ├── components/                 # ChatPanel、VideoPlayer、CitationLink、Graph
│   └── views/
│       ├── LoginView.vue / CourseView.vue / StudyView.vue / GraphView.vue
│       ├── QuizView.vue / QuizResultView.vue / MistakesView.vue
│       ├── DiagnosisView.vue / ProfileView.vue / RecommendationView.vue
│       ├── LearningView.vue
│       ├── teacher/CourseManageView.vue / DashboardView.vue / StudentView.vue
│       └── dev/SubmitView.vue        # 旧演示保留为开发入口
├── data/
│   ├── seed/                       # 课程/账号化名/资源元数据/知识点/题目 JSON
│   ├── kg/ / questions/             # 图谱和题库可交换数据
│   ├── simulator/                  # 生成器配置、随机种子和真值格式
│   └── eval/                       # 固定开发/测试样例及人工标注
├── storage/                        # 上传原件、PDF 副本；持久卷，Git 忽略
├── scripts/
│   ├── setup.ps1 / start.ps1 / test.ps1 / export_openapi.py
│   ├── seed_data.py / import_data.py / export_data.py
│   ├── generate_students.py / check_dataset.py
│   └── eval_tutor.py / eval_diagnosis.py / eval_extensions.py / cost_report.py
├── tests/                          # 完整闭环脚本、部署冒烟、性能检查
├── deploy/
│   ├── compose.yaml / init.sql
│   └── Dockerfile                  # 前端构建 + Python/转换工具运行镜像
├── .github/workflows/ci.yml
└── docs/
    ├── requirements-plan.md        # 主规划链接
    ├── api-design.md / api.yaml    # 目标草案 / 已实现导出，分开维护
    ├── implementation-plan.md / architecture.md / traceability.md
    ├── changes.md / guardrails.md / eval-plan.md / eval-report.md
    └── adr/ / sprint/ / ai-log.md / classroom-demo.md
```

不必再建立顶层 agents/，使用已有 backend/app/agents 即可；没有外部调用需求不拆微服务。最终部署让应用同源提供前端静态文件和 API，保留现有 hash 路由避免 SPA 刷新回退的额外配置。

## 4 现有代码逐项复用

| 现有位置 | 复用方式 | 必须修改之处 |
|---|---|---|
| backend/app/core/config.py | 保留 Pydantic Settings、环境读取、SecretStr | 增加会话/上传/embedding/模型选择/预算配置，不能输出密钥 |
| core/database.py | 保留 engine/session 工厂和 Base | 正式库验证 PostgreSQL；向量字段及迁移不能只用 SQLite 测试代替 |
| models/__init__.py | 三个现有模型保留并拆文件 | Diagnosis 加学生/课程/输入范围；Trace 泛化关联；拆分后保持导出，Alembic 可发现所有模型 |
| schemas/__init__.py | 保留 extra=forbid、数值范围和不足证据校验思路 | Literal 固定 KP、单证据数量、citations 为空都须替换；旧 schema 留给 dev |
| services/diagnosis.py | 保留先提交后调用、错误分类、事务边界、重试 trace | QUESTION 移到种子数据；模型客户端抽出；接收多证据快照和检索片段 |
| agents/diagnosis.py | 保留把学生输入当数据、结构化输出约束 | 固定题知识说明改为检索上下文；提示版本升级并评测 |
| app/main.py | 保留 create_app、health、静态托管和单进程重启恢复思路 | 路由移到 APIRouter；用户隔离；只有一个 worker 时使用全量 pending 恢复 |
| SubmitView.vue | 保留为本机 dev 演示和提交状态参考 | 正式测验重写为多题/草稿/计时，不强行改固定 textarea 承担所有题型 |
| DiagnosisView.vue | 复用列表、轮询、错误/重试、事件及 trace 展示 | 多知识点、引用跳转、基线比较、回复表单、历史对比 |
| frontend/src/api.ts | 保留基本 fetch 与错误提示思路 | 支持 PATCH/DELETE、204、Cookie/CSRF、分页错误；另做 multipart 和 SSE |
| App.vue/style.css | 保留已有布局和视觉样式 | 固定学生/知识点替换真实会话，添加角色导航，不大规模重设计 |
| backend/tests | 保留 24 项回归 | 通用化时更新合理契约，新增权限/判分/引用/去重测试，不能仅删除失败测试 |
| alembic/0001 | 保留历史迁移 | 新迁移逐步加列回填、建表/索引；不要直接改 0001 让旧库无法升级 |
| scripts 与 deploy | 保留启动/测试/锁文件/OpenAPI 导出和数据库配置 | 补应用镜像、卷、初始化、CI，验证干净机器启动 |

保留 0001 不表示强行迁移所有旧演示数据。先备份，旧记录可以留在 SQLite 归档，正式 PostgreSQL 从 0001 升级到 head 后导入新种子。若迁移旧记录，将 sim-student-001 显式映射到新模拟账号，保留旧事件 ID/来源和 demo 标记；禁止猜测归属。

## 5 从零搭建和接着开发的共同顺序

如果是完全空目录：先建 Vue/FastAPI 工程及依赖、配置、健康接口、数据库会话、初始迁移和一条测试，再进入 P1；诊断骨架在 P5 接入。对当前仓库，这一步已经存在，P0 核实后直接继续。不要同时维护两个仓库或复制所有历史缓存。

### P0 固定现有基线

输入：现有代码、依赖锁、配置示例。核对当前 Git 修改；保留已有 README 编辑。运行测试/类型检查，配置模型后做一次真实调用，检查 trace、失败重试和持久化。此次已核实后端 24 项测试，不代表真实 AI 已通。

现有命令在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

setup 在依赖未安装时才需要；不会替你配置真实服务商、密钥或部署 PostgreSQL。先在本机环境配置 LLM_BASE_URL/LLM_MODEL/LLM_API_KEY，模型成功以 trace 为准。

退出条件：旧演示和异常路径稳定，真实调用是否成功有明确记录。如果暂缺模型配置，可继续 P1–P3，不假称 P0 的真实调用验收完成。

### P1 用户和课程基础

1. main.py 拆出 dev 路由但保持旧接口兼容，增加 `/api/v1` 和错误/响应规范。
2. 准备 PostgreSQL + pgvector，保留现有 0001，加 users/sessions/courses/chapters/knowledge_points/course_members 迁移；种子脚本可重复运行而不重复建账号。
3. 登录、退出、CSRF、用户/课程权限、课程目录；前端 Login 和课程列表。
4. 教师建课程/章节/知识点表单，学生成员看到更新；管理员职责由教师兼任。

涉及 api/auth/courses、models/users/courses、core/security、router 和两个布局。验收：教师操作成功，学生调用教师接口 403，A 无法读 B，迁移在空库和旧版本库均可升级。

### P2 图谱和学习资源

1. 建资源/片段/关联/图谱/进度表，统一事件 service；为客户端事件加去重键。
2. 从 PDF 开始做上传、抽取、分页预览和下载，再补 PPTX/DOCX/旧格式转换；失败状态与重试一起完成。embedding 留给 P4。
3. MP4 或外链播放器；暂停/拖动/倍速/离开事件、心跳、续播、区间统计。
4. 图谱缩放和点击资源，教师加边校验环路；未有掌握度时用未知颜色。

验收：一个学生学习视频与课件，能查询事件；重复心跳不加倍，跳尾不算完成；文件白名单/超限拒绝；PDF 引用定位真实。PPT/Word 转换必须实测，不能仅说明“支持”。

### P3 正式题库和测验

1. 题库四题型和多知识点关联、教师组卷/发布、不可变题目快照。
2. 学生建立 attempt，服务端设 deadline/次数；前端逐题草稿、用时/修改次数和倒计时。
3. 规则判分、事务式交卷、重复提交保护、后台到期结算与重启补扫。
4. 结果页/解析已查看事件/错题本；诊断任务暂可标尚未接入，不能使用固定题伪造所有测验结果。

验收：20 道明确标准答案含多选部分正确；成绩、记录、事件一致；重复交卷无重复记录，关闭页面仍到期结算，未交卷接口不返回答案。

### P4 RAG 问答

1. 配置 embedding，片段保存文本/定位/模型/维度；新模型维度不一致需重建索引，不能混算。
2. 先在 1 份课件验证检索，再加本课程过滤、相似度阈值及无依据逻辑。
3. 抽通用模型客户端/trace，开发共享聊天侧栏、真实流式响应和引用定位。
4. 接入当前资源上下文、多轮历史、问答事件、反馈；实现注入隔离和服务端测验状态检查。
5. 建 10–15 个开发样例先调试，再扩为正式评测集；开发样例不能冒充独立测试结果。

验收：有依据问题能点开正确页，无依据问题拒答，正在测验不直接答题；流式错误有状态且无伪成功；断开连接终止/标记请求。

### P5 诊断和完整主线

1. 固定题诊断变为指定学生/课程/时间/知识点的事件摘要；保留输入快照；汇总行为、作答和对话。
2. 新 schema 支持多知识点、五类问题和多证据/资料引用；严格校验归属/存在性/范围，抽查相关性。
3. 交卷自动触发、教师手动触发，失败重试；正确率基线、历史对比、追问回复和新诊断。
4. 知识掌握更新、其他三维统计、M9 先修拓扑路径；旧诊断不可覆盖新画像。
5. 教师汇总/热力图/单题分析/个人详情；把旧 DiagnosisView 迁入正式角色布局。

验收：新学生完成一次学习活动，问答、测验、诊断、追问、画像、图谱颜色、推荐、教师看板全可查；超时/伪造证据不污染成绩画像。**这是第一次完整平台演示里程碑。**

### P6 两个选做模块

E1：将追问扩成五阶段状态机、模板和真实模型评价，切换有理由并记录；至少五知识点，三类学生完整会话，对照直接讲解。

E7：增加薄弱程度/时长预算的可学节点排序，保持先修约束，输出剩余路径；前端切换策略，比较步数、时长、接受率。不要用另一个随机排序冒充增强方法。

验收：两个选做能力在同一课程闭环内操作，保存过程与结果，有可复现对照数据。

### P7 数据、评测、部署和材料

1. 数据校验脚本统计两章/30 节点/40 先修/10 视频/10 课件/100 题，检查孤立节点及题型覆盖。
2. 模拟器固定 seed 生成四类100人、每人50事件和独立真值；每批输出来源/参数说明。
3. M7/M8 和 E1/E7 评测、基线/消融、重复运行统计、成本延迟。固定测试集不参与提示调参。
4. 补 app Dockerfile（含前端静态文件和文档转换工具）、Compose app 服务/文件卷/迁移/种子初始化，应用一个 worker；部署可访问地址和演示账号。
5. CI 风格/测试/密钥扫描/构建；完善正式 README、OpenAPI、架构、追溯、护栏、评测报告、变更与协作记录。

验收：干净环境按 README 30 分钟内启动；真实模型演示可复现；测量10并发、问答首字符和诊断时长；关键数据与结果无编造。上线前必须关闭旧无鉴权 dev 接口，不能只隐藏菜单。

## 6 每个阶段的交付顺序

先补请求/响应与验收样例 → 增量数据库迁移 → service 和核心测试 → API 权限/错误 → 页面 → 演示检查 → 更新 OpenAPI 与追溯。每阶段只引入对应依赖。保持旧演示可回归，但正式业务数据隔离。

本轮修改的是规划和设计材料，没有修改 README 原有工作区改动、业务代码、数据库或原始 Word 文件。2026-10-14 后端复跑命令：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=short -p no:cacheprovider --basetemp=.local/pytest-plan-verified-20261014
```

结果 24 passed，1 条 Starlette/httpx 弃用警告。普通权限尝试被 Windows 临时目录权限阻断；在授权运行后通过。本轮没有新跑前端构建或浏览器完整流程；历史构建结果见 Sprint 0 记录，不能当成本轮新验证。
