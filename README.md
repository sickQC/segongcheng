# 知序 · 软件工程课程智能学习辅助系统

> 后续整合说明：伙伴的 RAG 演示模块已纳入整合分支，详见 [合并修复与可用性检查](docs/integration-review.md)。正式课程聊天仍为 501 占位；下文“未实现”不代表文件检索内核不存在。
当前为 **P1 真实业务 + 四类业务页面与接口框架版本**。前端 Vue 3 + TypeScript + Vite + Element Plus，后端 FastAPI + SQLAlchemy + Alembic。已连接本机 PostgreSQL 18；数据库账号与密码仅保存在被 Git 忽略的 `.env`。初版规划的 PostgreSQL 16 不再是本机版本限制。

## 已实现

- 学生/教师登录、退出、会话过期，Argon2 密码哈希、HttpOnly Cookie、来源与 CSRF 校验。
- 我的课程、课程目录；教师创建课程、新建/编辑章节、新建/编辑/删除知识点。
- 教师按已存在学生用户名添加课程成员；学生仅可浏览本人课程。
- 知识点包含编号、定义、难度、学习目标，同课程编号唯一。
- 增量数据库迁移 `0002`，可重复初始化的演示数据，保留旧迁移和原诊断回归。
- 独立 `/api/v1` 业务接口；旧无鉴权演示由 `ENABLE_DEV_ROUTES` 显式控制。

新增页面：资源学习（答疑/5E 侧栏）、课程测验（四种题型/结果布局）、个人学习报告（诊断/画像/推荐/记录/错题）、教师看板（热力图/学生详情）。它们有类型化请求层和受权限保护的后端占位接口，但业务尚未实现，真实请求明确返回 501。

**页面已做不等于业务已做。** 视频/课件存储解析、正式题库测验判分、RAG、多用户诊断、画像推荐、统计、5E 和推荐增强均待实现。资源管理、题库组卷和图谱的前端界面也待开发。未执行真实模型调用。pgvector 在本机尚未安装，本阶段没有向量字段，后续检索阶段补齐。

## 本机直接运行

此电脑的数据库、迁移、依赖和前端构建已经准备完成。在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

打开 [课程平台](http://127.0.0.1:8000)。如已有本项目服务占用 8000，直接访问或先结束旧服务再启动。脚本会先迁移数据库，但不会重置账号、删除数据或重跑种子。

演示账号：`teacher`（教师）、`student01` / `student02`（学生）。本机初始密码由根目录 `.env` 中 `SEED_PASSWORD` 配置，初始化后只以 Argon2 哈希存入数据库。修改这个配置不会修改已存在账号的密码。请勿把 PostgreSQL 管理员密码当成平台账号密码。

演示顺序：教师登录 → 打开“软件工程基础” → 新建章节和知识点 → 退出 → student01 登录 → 打开同一课程并刷新查看。新建课程默认只有创建教师，需在课程底部“课程成员”加入 student01 后该学生才可见。

## 查看新页面

登录 → 我的课程 → 打开课程 → 点击“资源学习 / 课程测验 / 学习报告”；教师课程页另有“教师看板”。

- 默认“真实接口”：显示业务尚未实现的提示；不会把模拟内容当成真实结果。
- 手动打开“界面预览（样例）”：可检查资源布局、提问/引用、四题型、结果布局、报告标签页及教师学生详情。
- 样例不入库、不调用模型、不提交真实作答；“查看结果布局样例”与判分区分。切换模式/页面会清空交互。
- 真实视频/文档未导入，所以样例显示媒体占位区域。新页面仍需登录，教师看板有角色守卫。
- 更新代码后先在 frontend 运行 `npm run build`，再重启后端；旧服务不会自动加载新增 Python 路由。

| 页面地址（`/#` 后） | 组件 |
|---|---|
| /courses/:id/learn | LearningView.vue |
| /courses/:id/quiz | QuizView.vue |
| /courses/:id/report | LearningReportView.vue |
| /teacher/courses/:id/dashboard | TeacherDashboardView.vue |

## 新环境初始化

需要 Python 3.11+、Node.js/npm、本地 PostgreSQL（本机验证版本 18）。依赖固定在两个 lock 文件；不用 Docker 也可运行步骤 1。

1. 安装依赖并构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

2. 在 PostgreSQL 中创建独立项目角色和数据库（在 SQL Shell 或 pgAdmin 中执行，替换示例密码，不改已有数据库）：

```sql
CREATE ROLE se_learning_app LOGIN PASSWORD '在本机设置的专用密码' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE se_learning OWNER se_learning_app;
```

3. 只有没有 `.env` 时才复制 `.env.example`，设置 DATABASE_URL 和 SEED_PASSWORD（至少 8 位）。连接密码的 URL 特殊字符需要编码。不要覆盖已有本机配置。
4. 在根目录初始化：

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe scripts/seed_data.py
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

种子创建一名教师、两名学生、一门课程、两章四个知识点。重复执行不重置密码、不覆盖现有编辑；缺失的内置演示记录会补建。遇到同名非种子账号会报冲突，绝不覆盖。

SQLite 旧库保留在原位置，没有自动复制到 PostgreSQL。切换数据库只改变连接目标；迁移会保留目标数据库已有 Sprint 0 数据。

## 开发与验证

后端（根目录）：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

前端另开终端在 `frontend` 下运行 `npm run dev`。Vite 代理 `/api` 与 `/health`；受信任来源在 ALLOWED_ORIGINS 配置，增加端口或域名时同步修改。开发者工具不要向控制台打印 `.env` 或数据库连接密码。

```powershell
# SQLite 回归 + 前端类型检查/构建
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
# 另加本机 PostgreSQL 测试（独立随机 schema，测试后清理）
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Postgres
.\.venv\Scripts\python.exe -m ruff check backend/app backend/tests backend/alembic scripts/seed_data.py
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
```

导出接口（在 backend 目录）：`..\.venv\Scripts\python.exe ..\scripts\export_openapi.py`。
实际契约：[api.yaml](docs/api.yaml)，浏览器 [Swagger](http://127.0.0.1:8000/docs)，JSON [OpenAPI](http://127.0.0.1:8000/openapi.json)。Swagger UI 依赖外部静态资源；Cookie 写接口还需发送正确 Origin 和 X-CSRF-Token，普通页面已处理。

## 旧课堂演示

本机 `.env` 显式启用了 ENABLE_DEV_ROUTES，可从侧栏打开单题诊断和记录；它使用独立模拟学生数据，尚未接入正式账号，不能当作正式学生记录。其他环境默认关闭，关闭后旧接口返回 404。`ENABLE_DEMO` 仅控制固定模拟答案，不能代替开发路由开关。

原版启动和真实模型配置说明保留在 [Sprint 0 历史说明](docs/sprint/sprint-0-readme.md)。真实模型失败不自动变成模拟成功；当前保留了这套回归逻辑。

## 文档与后续

- [需求规划](需求规划.md)：完整功能和技术栈。
- [实施路线](docs/implementation-plan.md)：目录与分步执行。
- [接口草案](docs/api-design.md)：未来模块设计；P1 已实现部分见实际 OpenAPI。
- [P1 验证记录](docs/sprint/p1-foundation.md)：本轮验证与边界。

## 交接入口与目录

请接手者优先阅读：

1. [接口交接文档](docs/handoff-api.md)：真实接口、10 个占位接口、字段定义、权限、与旧草案的差异。
2. [剩余开发清单](docs/handoff-todo.md)：尚未实现的后端业务及前端功能、开发顺序和验证边界。
3. [完整需求规划](需求规划.md)：老师要求与最终验收目标。

```text
frontend/src/
  views/                  登录、课程、四类新页面与旧演示
  components/             WorkspaceHeader、ReportPanels
  api/client.ts           Cookie / CSRF / 错误处理
  api/workspace.ts         新页面的真实请求函数
  api/preview.ts           仅手动预览使用的内存样例
  types/workspace.ts       前端业务契约
backend/app/
  api/routes/workspace.py  新接口占位（501），复用现有权限
  schemas/workspace.py     请求和未来成功响应的字段模型
  services/               当前真实 P1 / 旧演示服务；待增加业务服务
backend/alembic/           现有迁移，本轮无新表
```

本轮验证：37 项后端测试、前端类型检查与构建、Ruff。浏览器检查脚本为 `tests/browser-workspace.cjs`（需要 Playwright 和 Edge）。下一步从资源管理、学习事件和知识图谱开始，再接题库测验。不要把前端样例作为数据库种子或正式接口结果。


浏览器实测通过（Edge）：四页真实模式 501 提示、样例交互、四题型、报告标签页、学生详情、390px 手机无横向溢出、学生教师路由隔离；无 JS 运行错误，预览无业务 POST。
