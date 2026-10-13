# Sprint 0 记录

日期：2026-10-13。

范围：最小事件入库 → 模型诊断接口 → 页面展示；提供无密钥的显式模拟演示。
实际数据库采用 SQLite；PostgreSQL/pgvector 配置已提供但本机未运行。

## 实现

- 后端：FastAPI、学习事件/诊断/trace 模型、Alembic 初始迁移、提交/列表/详情/重试接口。
- 诊断：真实兼容接口、结构与证据校验、错误分类、trace、显式模拟数据。
- 前端：作答与诊断两页、记录列表、轮询、重试、模拟提示、事件 JSON。
- 工程：本机安装/启动/测试脚本、环境示例、部署配置、架构/ADR/需求追溯/课堂说明。

## 验证记录

2026-10-13 在本机实际执行：

| 检查 | 结果 |
|---|---|
| Python 3.12.4 虚拟环境与依赖安装 | 成功，冻结依赖至 backend/requirements-lock.txt |
| pytest -q --tb=short | **24 passed, 1 warning in 1.81s** |
| Ruff（app/tests/alembic/契约导出脚本） | All checks passed |
| Alembic upgrade head | 成功，在本机创建 SQLite 数据库及三张业务表 |
| 迁移 upgrade/downgrade | 自动化测试通过 |
| npm run build | vue-tsc 类型检查和 Vite 6.4.4 构建成功 |
| 前端依赖安装检查 | Element Plus 2.11.8，0 项已知漏洞；兼容当前 Node 20.14.0 |
| scripts/start.ps1 | 实际启动成功，127.0.0.1:8000 可访问 |
| GET /health | HTTP 200，status=ok，database=sqlite |
| 浏览器模拟提交 | 模拟诊断、模拟数值、事件编号与 trace 可查看 |
| 浏览器真实模式（缺密钥） | MISSING_API_KEY，原作答保留 |
| 浏览器重试 | 同一作答保留，新增第二条 trace |
| 后端重启后刷新记录 | 两条演示提交仍可查询 |

浏览器检查留下两条明确使用模拟学生数据的作答，可在课堂直接查看。
模拟模式实际诊断 ID：`d3eb8ae6-e3f7-42f6-9849-7c7f93a270a5`。
缺密钥失败诊断 ID：`46be296e-67c1-4231-ad5b-cada0c47873e`。
截图：`docs/screenshots/sprint0-demo.png`。

已知非阻断警告：Starlette TestClient 提示未来将迁移 httpx 接口；当前测试通过。
Element Plus 全量引入使 JS 约 1 MB（gzip 约 333 KB），构建有包体积提示；本机演示可用，后续按需引入优化。
沙箱曾阻止 Python 临时目录写入及 esbuild 子进程启动；授权后实际安装、测试和构建成功，不将受阻运行记作业务测试通过。

没有执行真实收费模型调用，也没有安装或运行 PostgreSQL/Docker。真实模型验收、RAG 和 PostgreSQL 实机验证仍为未完成项。

## 下一步

提供服务商、模型名及 API 地址，在本机 `.env` 填写密钥后人工执行一次真实模型调用；核对结果和 trace。
随后安装 PostgreSQL + pgvector 环境，补课程资源、鉴权和 RAG。没有实际证据前不标记这些项目完成。
