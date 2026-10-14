# P1 账号与课程框架完成记录

日期：2026-10-14。范围：步骤 1 前后端框架、PostgreSQL、账号角色和课程基础；不是完整学习平台。

## 实现

- FastAPI /api/v1，auth/courses/knowledge 路由，通用依赖、错误响应与请求 ID；旧演示拆为显式开发路由。
- Argon2id 密码哈希、数据库会话、HttpOnly Cookie、过期和退出、来源和 CSRF 校验、角色及课程成员权限。
- 课程创建/目录，章节新增/修改，知识点新增/修改/删除、编号冲突检查，课程成员列出及按用户名加入。
- Vue 登录、课程列表、教师课程编辑、学生只读目录、成员表单、空态/错误/刷新、角色路由守卫；保留旧诊断演示。
- 原生 PostgreSQL 18.6，独立数据库和非超级用户应用账号；Alembic 0002，三账号/一课程/两章/四知识点的幂等种子。
- 更新运行说明、依赖锁、测试入口、OpenAPI 和需求追溯。

## 实际验证

| 检查 | 结果 |
|---|---|
| 本机 PostgreSQL 连接 | 成功；未修改其他数据库；管理员凭据未写入代码仓库 |
| migration upgrade head + seed | 成功；重复 seed 不改密码/编辑内容 |
| pytest（含 RUN_POSTGRES_TESTS=1） | 48 passed，1 条 Starlette/httpx 弃用警告 |
| 原 Sprint 0 回归 | 保留 24 项，通过；health 阶段改为 1，fixture 显式启用 dev |
| 新 P1 验证 | SQLite 12 项 + PostgreSQL 12 项；临时 schema 清理 |
| 权限 | 未登录 401、学生写入 403、跨课程教师/学生 403、CSRF/来源校验、会话过期/轮换 |
| 迁移 | 0001 写入旧事件 → 0002 → 回退 0001 → 升级，旧事件保留 |
| Alembic check | No new upgrade operations detected |
| Ruff | 通过 |
| npm run build | vue-tsc + Vite 通过；Element Plus 全量包约 1 MB，有非阻断体积提示 |
| 浏览器端到端 | 教师登录、新课程/章节/知识点、加入学生；学生登录看到更新、刷新保持会话；无 JS 错误 |
| UI 权限/移动端 | 学生无编辑按钮，教师页面跳回课程，成员接口 403；390px 无横向溢出 |

浏览器在隔离无头 Edge 中运行，未读取个人浏览器资料。Codex 内置浏览器入口初始化失败，改用 Playwright 测试。截图位于 .local/p1-courses.png、p1-teacher.png、p1-student.png、p1-mobile.png；截图是验证中间文件，不纳入源码。浏览器临时课程按唯一 ID 清理，保留原种子课程。

## 复跑

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Postgres
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
```

可选浏览器检查：需 Playwright 包及 Edge，本地服务先启动；在仓库根目录运行 `node tests/browser-foundation.cjs`。Playwright 未在当前 Node 查找路径时，用 PLAYWRIGHT_MODULE 指向已安装的包。脚本读取本地 SEED_PASSWORD 登录演示账号，新建专用测试课程并在 finally 调用 cleanup_browser_fixture.py 清理；如果异常中断，手动运行 `.\.venv\Scripts\python.exe tests/cleanup_browser_fixture.py`。清理会校验课程名称和演示教师归属，不匹配则拒绝删除。

## 尚未完成

pgvector 未安装（P4 检索前准备）；未验证真实模型；未实现资源/图谱关系/测验/RAG/画像/推荐/学情看板。知识点当前只关联章节，没有资源或题目，因此删除尚不涉及后续依赖；后续加关系时需保留外键约束并按草案返回 409。P1 仅为课程演示的基础框架，未做生产级登录限流或密码找回。
