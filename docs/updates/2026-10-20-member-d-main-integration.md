# D 与 main 学习流程整合记录

整合输入：本地 D 提交 `2b11042` 与远程 main 提交 `34df21a`。本页记录本地代码整合，不表示已推送或云端 CI 已通过。

## 保留的功能

- 保留组员的讲义原文、章节与讲义绑定、引用定位、错题定向 5E、学习记录、教师专用导航及角色跳转。
- 保留 D 的真实报告、事件筛选与导出、掌握度投影、画像快照对比、先修关系、教师估时、基础及 E7 推荐、历史和反馈。
- 综合诊断既接收 5E 完成后带来的知识点参数，也保留诊断完成后刷新真实画像的通知。
- 课程目录统一知识点定位标记，同时保留练习定位与推荐知识点高亮。
- 重新导出 OpenAPI，包含讲义与 D 接口；CI 补入组员新增的 Markdown 回归命令。

## 已有克隆的本机准备

本次组员更新增加了前端 Markdown 依赖和第六份内置讲义。拉取整合版本后，应按 README 安装依赖、构建前端、重建索引并重启后端。不要复制其他人的 `.env` 或数据库。

```powershell
cd frontend
npm ci
npm run test:markdown
npm run build
cd ..
.\.venv\Scripts\python.exe scripts/build_rag_index.py
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

先停止旧服务再启动，避免8000端口占用。需要支持当前前端的 Node 版本；本机使用项目内 Node 22。D 数据表迁移仍按 README 和启动脚本执行，原库不清空。

## 验证边界

第一轮回归发现旧派生索引只有五份讲义，造成四项讲义相关失败。保留旧索引后离线重建为六份，讲义及跨模块专项11项通过。新增集成测试验证真实测验诊断进入定向5E后，其作答可进入D画像、事件导出、快照和推荐，且不改变原测验成绩、不会被其他学生导出。

重建索引后完整后端回归360项通过，耗时178.41秒，保留已有Starlette/httpx弃用警告。前端4项Markdown测试、类型检查及生产构建通过，保留构建包体积提示；代码规范、脱敏密钥扫描和工作流语法检查通过。摘要见[验证记录](../evaluation/main-integration-verification.json)。尚未新增真实模型、PostgreSQL、Docker、云端或浏览器点击验证。
