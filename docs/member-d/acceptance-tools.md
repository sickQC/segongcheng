# D：只读性能采样与课程规模核查

本模块覆盖公共验收基础设施，依据需求规划8.2的数据规模与非AI接口性能要求。脚本不替其他成员制作课程内容，也不往正式库填充模拟事件。

## 10并发只读接口采样

先按README启动本机项目。打开项目根目录的PowerShell，执行以下命令；输入 `student01` 的登录密码时屏幕不显示，密码不会出现在命令行参数中：

```powershell
$credential = Get-Credential -UserName student01 -Message '输入本机测试学生的登录密码'
try {
    $env:BENCHMARK_PASSWORD = $credential.GetNetworkCredential().Password
    .\.venv\Scripts\python.exe scripts/benchmark_read_api.py --base-url http://127.0.0.1:8000
} finally {
    Remove-Item Env:BENCHMARK_PASSWORD -ErrorAction SilentlyContinue
    $credential = $null
}
```

报告默认在 `.local/ci/read-api-benchmark.json`。只接受显式本机地址，拒绝远程网址及带账号、路径或查询参数的地址，避免误将密码发送到外部。使用现有 `student01` 及其第一门课程；账号需已加入课程。

先对六个接口各预热一次，再用10个工作线程发起总计180次请求：健康、课程大纲、画像、事件列表、画像历史、推荐历史。不调用AI、判分、反馈或生成推荐，不新增学习记录；仅登录/注销产生临时会话变化。不保存响应内容、作答、Cookie或密码。

报告包含每接口请求数、错误数、均值、P50/P95/最大值及整体吞吐。P95采用nearest-rank定义，阈值为严格小于1000毫秒。有请求错误时退出非零；默认记录而不因延迟超标退出，避免CI硬件差异造成不稳定门禁。需严格验收时追加 `--enforce-latency`。并发范围1–20，每接口请求1–100，避免意外无限压测。

本机实测 [性能报告](../evaluation/read-api-benchmark.json)：10并发、180请求、0错误，各接口P95为51.280–182.720毫秒。**这仅是当前少量数据、预热后的本机HTTP采样**，不能代表完整规模、冷启动、浏览器、AI或线上环境的性能结论。CI已增加容器内对应采样及报告归档，但云端尚未运行。

## 课程规模与一致性核查

从课程页面地址或 `/docs` 获取课程ID，替换下面占位文字后执行：

```powershell
.\.venv\Scripts\python.exe scripts/audit_course_data.py --course-id '替换为实际课程ID'
```

默认输出 `.local/ci/course-inventory.json`，不会导出题目答案。SQLite以只读URI打开已有数据库，PostgreSQL使用只读事务；不创建数据库、迁移、种子数据或学习记录。`--strict` 会在未达标时返回非零，适合正式内容备齐后做门禁；普通模式正常生成不足报告。

检查至少2章、30知识点、40先修关系、100道客观题、10视频和10课件，并验证先修图、知识点章节归属、题目知识点归属及练习归属。报告孤立知识点及缺失题型。题目按题型、规范化题干、选项去重，重复发布不重复充数；练习另列数量，不合并冒充客观题库。此题数口径比简单数发布实例更严格，不评价题目质量。

目前没有正式资源表可作为视频/课件统计依据，相关项保持 `null/unknown`，因此整体不能标记ready。当前实测 [课程清单](../evaluation/course-inventory.json)：2章、4知识点、3先修关系、0道已发布客观题、0练习；视频/课件未知。正式内容需要内容负责人提供，D负责核查和对接，不擅自填充虚构资料。

## 验证边界

新增9项自动测试，覆盖百分位/错误统计、地址与负载边界、只读核查、题库去重及损坏先修图。与事件导出合计新增22项，完整后端回归330项通过。真实本机脚本已运行，业务表行数和 `.env` 保持不变；Docker/PostgreSQL/云端任务仍需在对应环境验证。
