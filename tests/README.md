# 测试入口

核心接口和迁移测试位于 backend/tests，覆盖 Sprint 0 与 P1。根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Postgres
```

默认使用临时 SQLite；-Postgres 额外连接本地配置的 PostgreSQL 并创建独立随机 schema，测试后清理，不能改成在应用 schema 上 drop_all。P1 两种数据库均跑权限/课程/迁移检查，总计 48 项。

可选浏览器测试见 browser-foundation.cjs，需要已安装的 Playwright 包、Edge 和运行中的本地应用。使用本地 SEED_PASSWORD 演示账号；新建的测试课程按唯一 ID 自动清理，异常中断时运行 cleanup_browser_fixture.py。详见 docs/sprint/p1-foundation.md。

资源、RAG、正式测验与画像尚未实现；不能把这些基础测试当作完整平台验收。


本轮新增 workspace 占位/权限测试，默认总计 37 项；历史 48 项为 P1 当时含 PostgreSQL 的结果。新增 browser-workspace.cjs 检查四页面、501、预览无业务 POST、手机布局与教师路由守卫；运行前配置 PLAYWRIGHT_MODULE（或安装 playwright），可设 TEST_BASE_URL，默认 http://127.0.0.1:8000。读取本地 SEED_PASSWORD 登录，不输出密码，不写课程业务数据。
