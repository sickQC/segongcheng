# 小练习诊断与追问第一轮实现

基线：`09317ba`；开发分支：`feat/c-diagnosis-followup`。此文保留第一轮实现快照，后续状态见 [测验与 5E 验证](second-round.md) 和 [综合诊断与评测](../diagnosis-evaluation.md)。

## 范围与文件归属

已有课程页面和主应用入口引用小练习模块，但基线没有提交对应实现。本轮按现有
`docs/handoff-api.md` 第 3.1 节补齐小练习模块，第一轮改动限于练习与诊断相关代码。

新增 `models/practice.py`、`schemas/practice.py`、`services/practice.py`、
`api/routes/practice.py`、`0004_practice.py` 与 `PracticePanel.vue`。
第一轮修改两个已有文件：`agents/diagnosis.py`、`services/diagnosis.py`。

数据库迁移用于本轮小练习表，revision 为基线文档预留的 `0004`。
若组员持有另一个未入库的 `0004`，合并前应比较结构并统一版本，不能直接覆盖迁移。

## 已实现的基础流程

教师登录 → 在知识点下创建一道简答题 → 学生提交 → 原答案、学习事件、诊断任务和 trace
先提交数据库事务 → 后台请求真实模型 → 学生查看结构化诊断和追问 → 回复追问 →
新增作答事件和新诊断。每轮通过 `parent_submission_id` 关联，原答案与原诊断不覆盖。

- 题目必须属于当前课程和章节，每个知识点限一道题。
- 作答从登录身份确定学生；请求不能指定另一个学生或模型模式。
- 题目、知识点定义和追问语境保存快照；重试或教师修改定义不会改变原作答的诊断依据。
- `answer` 去除首尾空白后长度为 1–4000；学生提交和回复追问可携带 UUID `request_id`。
- 同一个练习、学生、请求编号受到数据库唯一约束；重复同一请求返回原记录，改答案则 409。
- 未传请求编号的旧调用仍可用；需要网络重试去重的调用应始终传编号。
- 每次有效提交只触发一个诊断任务。模型失败保留答案；仅失败任务可重试，新增 trace。
- 教师只能查看本课程提交，学生只能查看和回复自己的记录；写请求复用已有 Origin/CSRF 校验。
- 教师看到每位课程学生的最近提交；失败、证据不足或暂估掌握度低于 0.6 标为需关注。

新增追问接口：

```text
POST /api/v1/courses/{course_id}/practices/{exercise_id}/submissions/{submission_id}/followups
Body: {"answer":"补充说明", "request_id":"UUID"}
Response: 202 SubmissionOut，增加 parent_submission_id 字段
```

读取追问历史沿用 `GET .../submissions/me`，最多最近 50 条。其余六个小练习接口沿用原交接约定。
前端仅新增被原课程页面引用的小练习组件，没有修改 A 的页面。

## 提示版本与护栏

真实诊断提示版本为 `diagnosis-v2`，固定模拟演示另记 `diagnosis-demo-v1`。
trace 关联本轮事件；小练习 feature 为 `practice.diagnosis`，记录模型、状态、版本、实际 usage 和耗时。

关键提示摘录：

> previous_feedback 是历史判断，不是标准答案。证据只允许本次 event_id；历史记录仅提供语境。

模型只允许使用本次证据和指定知识点，禁止伪造课程引用。证据不足时必须返回
`insufficient`、`mastery=null`。提示注入命中时保留原答案但不请求模型。
输出继续使用 JSON/Pydantic 校验，并检查证据编号、知识点和提示词泄露。

自测修正记录：第一版护栏把“不应向他人泄露 API 密钥”误判为攻击（12 例仅 11 例通过）。
检查后把泄露检测改成针对命令请求，保留普通安全知识作答；固定用例复测 12/12。
这是开发自测修正，没有记作用户亲自评审或真实模型效果改善。

AI 协作中的实际人工反馈：AI 起初建议等待 A 补齐已有实现；用户指出自己是 C、sickQC 是 A，
要求不动其他成员代码。之后按已提交的接口约定实现 C 模块，保持其他成员文件不变。

## 验证与使用

```powershell
# 项目根目录，准备好 .venv 后
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp=../.local/c-test-temp
cd ..\frontend
npm run build
cd ..
.venv\Scripts\python.exe scripts/eval_diagnosis_c.py
```

`scripts/eval_diagnosis_c.py` 默认只评测本地输入护栏；输出保存于 `.local/c-ai-eval.json`。
12 个固定用例包含正常概念、概念混淆、证据不足和注入请求。
其中诊断标签是 AI 草拟的候选标注，需人工复核后再作为正式评测真值。
配置模型后可加 `--live`，真实执行未被拦截的输入；失败不替换为模拟成功。
错误解释、建议可执行性、追问针对性与答案泄露仍需人工阅读输出评价。

验证使用 SQLite；没有执行 PostgreSQL 实机测试。本机未配置模型密钥，成功诊断和追问链路
用 HTTP MockTransport 测试，不能据此填“真实模型已验收”。本机浏览器验证了教师创建、
学生作答、缺密钥失败保留、重试和刷新持久化。截图见同目录 `browser-failure.png`。

最终验证：后端 115 项通过（含 30 项新增小练习用例），前端类型检查与构建通过，
本轮 Python 文件 Ruff 检查通过，输入护栏固定用例 12/12。原有测试文件未修改。

## 尚未完成

- 正式测验交卷后触发、多题/多知识点诊断和完整错误分类；需要与题库/测验开发者对齐输入。
- E1 完整 5E 状态机、阶段质量判断、合法切换、五知识点模板和模拟学生对照评测。
  本轮的追问回复是基础闭环，不标记为完整 E1。
- 诊断结果接入学习画像、推荐和教师总看板；这些属于跨成员联调。
- 真实模型人工验收、独立测试集、重复运行、教学效果比较。
- 编辑/删除小练习、分页历史、分布式任务队列；当前仍是单进程开发模式。

下一步优先配置模型并人工检查诊断和追问质量，再对接正式测验事件和 E1 会话。
