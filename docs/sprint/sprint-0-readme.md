> 历史快照：以下为 P1 改造前的 Sprint 0 说明；当前启动和功能状态以根目录 README 为准。

# 知序 · 软件工程课程智能学习辅助系统

当前版本为 **Sprint 0 本地演示骨架**：前端 Vue 3 + TypeScript + Vite + Element Plus，后端 Python + FastAPI + Pydantic + SQLAlchemy + Alembic。

默认使用 **SQLite**，无需安装 PostgreSQL、Docker 或配置 MySQL。PostgreSQL + pgvector 配置保留在 `deploy/`，下一阶段引入 RAG 时切换。

## 现在能展示什么

- 两个页面：模拟作答、诊断记录/详情。
- 真实写入 `learning_events`，包含 `event_id/actor/verb/object/result/context/timestamp`。
- **真实调用模式**：请求可配置的 OpenAI 风格 `/chat/completions` 接口；没配置密钥时显示明确失败，绝不自动切换固定结果。
- **模拟演示模式**：仅使用固定题目及预置答案，显著标注“模拟数据 / 没有调用大模型”；不会产生模型费用，也不能作为真实模型验收证据。
- Pydantic 校验诊断 JSON；拒绝伪造事件、错误知识点和未导入的课程引用。
- 原答案独立提交；诊断失败可重试，保留所有调用记录；单进程重启后中断任务会标为失败。

**尚未完成**：一次真实模型调用的人工验收、PostgreSQL 实机验证、完整 RAG、登录鉴权、正式题库、追问作答、学生画像、推荐、正式评测。Sprint 0 代码与 mock 测试不能替代真实模型调用验收。

## 本机快速启动

环境：Python 3.11+、Node.js 20.14+（本项目锁定 Vite 6）、npm。当前电脑使用 Python 3.12.4、Node 20.14.0。

在 PowerShell 中运行：

```powershell
cd D:\develope\segongcheng
# 首次使用，或重新安装依赖时执行；需要联网。
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
# 启动前会自动执行数据库迁移；已安装并构建后只需此命令。
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

浏览器访问 **http://127.0.0.1:8000**。保留启动终端；按 Ctrl+C 停止。构建后的前端由后端直接提供，只需一个服务，无需同时启动两个终端。

首次没有 `.env` 也能启动。数据库文件是 `backend/learning.db`，关闭浏览器或重启服务不会丢失已保存的答案。不要把数据库、`.env` 或个人数据提交到 Git。已有原始需求文档保留在根目录。

## 课堂展示（无需 API Key）

1. 进入模拟作答页，选择“模拟演示 · 无模型调用”。预置答案自动填入。
2. 点击“保存并查看模拟演示”，展示固定模拟诊断、追问、事件 JSON 和 trace。
3. 返回作答，切换“真实模型调用”，填入示例后提交。
4. 未配置密钥时，展示“作答已保存 / 诊断未完成 / MISSING_API_KEY”，证明失败不会丢答案。
5. 打开诊断记录，查看两次提交，刷新浏览器验证持久化。

详细讲解顺序见 [课堂演示说明](../classroom-demo.md)。所有掌握度与置信度都是模型暂估值或显式模拟值，不是教师成绩或已验证评测结果。

## 开发模式

终端一：

```powershell
cd D:\develope\segongcheng\backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

终端二：

```powershell
cd D:\develope\segongcheng\frontend
npm run dev
```

前端开发地址为 http://127.0.0.1:5173，Vite 将 API 请求代理到 8000 端口。前端不保存密钥。普通演示优先使用前面的单服务启动方式。

## 配置真实模型并人工验证

```powershell
cd D:\develope\segongcheng
Copy-Item .env.example .env
```

如果已经有 `.env`，直接编辑，**不要覆盖现有配置**。填写：

```dotenv
LLM_API_KEY=在本机填写服务商的密钥
LLM_BASE_URL=https://服务商的兼容接口地址/v1
LLM_MODEL=服务商支持的模型名称
LLM_TIMEOUT_SECONDS=30
```

密钥不用发到聊天里。服务需支持 Chat Completions 及 `response_format: {"type":"json_object"}`；不兼容时会明确返回模型 HTTP 错误，不会静默假装成功。选定服务商后可能需要针对其协议进行适配。

1. 重启后端，选择“真实模型调用”并提交模拟学生答案。请求可能产生该服务商费用。
2. 检查模式为 `live`，trace 状态为 `succeeded`，结果 JSON 通过校验，证据 ID 与原事件相同，`citations=[]`。
3. 核查诊断是否符合答案实际内容；结构合法不等于诊断语义已被证明正确。
4. 记录实际模型、trace ID、耗时，以及服务商真实返回的 token 数；费用未配置计价时不推测。
5. 人工核查后再在 Sprint 记录中补记真实调用证据。目前不声称真实模型验收已通过。

## 自动化检查

```powershell
cd D:\develope\segongcheng
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
cd backend
..\.venv\Scripts\python.exe -m ruff check app tests alembic
..\.venv\Scripts\python.exe ..\scripts\export_openapi.py
```

自动化测试使用临时数据库和 HTTP mock，不读取真实模型结果、不产生 API 费用。覆盖先入库再调用、缺失密钥、超时、HTTP 错误、非法 JSON、错误证据、诊断重试、模拟标识、请求校验和迁移升降级。实际执行记录见 `docs/sprint/sprint-0.md`。

## 后续切换 PostgreSQL + pgvector

当前不要求安装 Docker。准备好 Docker Desktop 后，在根目录 `.env` 设置自己的 `POSTGRES_PASSWORD`：

```powershell
docker compose --env-file .env -f deploy/compose.yaml up -d
```

将 `DATABASE_URL` 改为 `postgresql+psycopg://se_learning:密码@127.0.0.1:5432/se_learning`，密码中的特殊字符需 URL 编码。然后从 `backend/` 执行 `alembic upgrade head` 并重启服务。pgvector 扩展由初始化 SQL 创建，Sprint 0 不创建向量表或执行检索。

这是在新数据库中建表，**不会自动转移 SQLite 中的旧演示数据**。PostgreSQL 启动及迁移尚需在安装环境后实测。

## 目录与边界

```text
backend/app/          配置、数据模型、校验、接口、诊断服务与提示词
backend/alembic/      版本化数据库迁移
backend/tests/        接口、异常与迁移测试
frontend/src/         两个页面及接口客户端
deploy/              PostgreSQL + pgvector 可选环境
scripts/             Windows 安装、启动、测试及契约导出脚本
docs/                架构、接口、开发记录和演示说明
data/                演示数据说明，后续扩展课程数据
tests/               集成检查入口说明
```

本版没有登录鉴权，所有记录属于固定模拟学生，只监听 127.0.0.1，用于本机开发与课堂展示。不要改成公网部署或录入真实学生数据。后台任务是进程内任务，当前只支持一个后端进程；后续正式部署再加入持久任务队列和用户权限。

故障排查：8000 被占用时停止旧的本项目服务或修改启动端口；页面修改后重新 `npm run build` 并重启；模型参数修改后重启；数据库报错先检查迁移和 `DATABASE_URL`。Swagger 文档在 `/docs`（其界面资源可能需要网络），机器可读契约在 `/openapi.json`，导出副本在 `docs/api.yaml`。
