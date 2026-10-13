# 测试入口

后端单元、接口和迁移测试在 `backend/tests/`，使用临时 SQLite 数据库及 HTTP mock。
从根目录执行 `powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1`。
课堂手动检查脚本见 `docs/classroom-demo.md`。不需要真实密钥即可运行自动化测试。
