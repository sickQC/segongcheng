# D：学习事件离线模拟与校验模块

本模块对应需求规划 US-16/M6-4 与 P7 的合成数据设施。提供生成器、独立结构校验、测试、CI及交接说明。仅使用标准库生成文件，不读取 `.env`，不连接数据库、模型或网络，没有数据库导入操作。

## 1. 本轮交付

| 内容 | 路径 |
| --- | --- |
| 固定参数 | `data/simulator/config.json` |
| 自编概念/误解模板 | `data/simulator/topics.json` |
| 生成器 | `scripts/simulate_learning.py` |
| 校验器 | `scripts/validate_simulator.py` |
| 模块回归 | `backend/tests/test_simulator_d.py` |
| 本轮实际校验报告 | [learning-simulator-validation.json](../evaluation/learning-simulator-validation.json) |

实际产物保存在本机 D 盘项目 `.local/ci/learning-simulator-final-v1/`；早期试跑的目录也保留，没有覆盖或删除。完整数据不提交Git。CI在临时运行器生成相同数据，并随 `.local/ci` 的报告产物上传；这些文件是虚构数据，不包含真实用户账号或密钥。

## 2. 数据规模与内容

固定种子 `20261019`，固定UTC起点，所有UUID可重复生成。四类各25人，共100人，每人正好50事件，总计5,000条。每类前5人进入开发集，因此开发20人、测试80人，按学生划分而非拆散同一人的事件。

| 类型 | 潜在掌握度先验 | 观测行为假设 |
| --- | --- | --- |
| strong_active | Beta(8,2) | 较多活跃日、正常时长 |
| weak_active | Beta(2,6) | 较多活跃日、较多提问/练习 |
| low_engagement | Beta(5,3) | 活跃日较少、有长间隔、资源观测时长短；低投入不自动等于低掌握 |
| uneven | 交替Beta(8,2)/Beta(2,7) | 不同知识点的潜在掌握不均衡 |

先用独立随机流抽样每人每知识点的潜在掌握度，再使用另一个随机流生成观测。客观作答概率为 `m*(1-slip)+(1-m)*guess`，默认slip=0.12、guess=0.20。没有调用画像风险阈值或诊断规则来反推真值。这里的“真值”只是模拟器设定的潜变量，不是真实学生的已知能力，也没有假装发生学习提升。

所有学生的事件包含问答、客观作答、未判分练习、视频和阅读样例。本轮共问答1,086条、视频1,060条、阅读928条、客观作答1,115条、练习811条。资源观测是按“学生+资源”累计的快照，不能把累计时长逐条相加。

每人提供一段3轮对话（3次学生提问、3次模板助教回复，共6条消息），共100段；其中按固定序号安排34段初始误解。误解标注只在单独真值文件中。它们复用6类人工模板，**不是100段真实对话，也不是34种不同误解**；标注针对初始误解，不能当作之后仍持续误解的证明。回复来自模板，不是模型实测。

## 3. 文件与隔离约定

| 文件 | 内容与用途 |
| --- | --- |
| `students.jsonl` | 虚构学生UUID、课程UUID、数据划分、模拟标记；不含类型或掌握度标签 |
| `knowledge_points.jsonl` | 6个带SIM编号的概念样例，供离线引用，不映射现有课程 |
| `events.jsonl` | `event_id/actor/verb/object/result/context/timestamp` 标准外形的观测 |
| `dialogues.jsonl` | 对话文本、学生、知识点和3个事件关联 |
| `truth/students.jsonl` | 类型及每知识点潜在掌握度，仅供离线评测 |
| `truth/dialogues.jsonl` | 是否有初始误解、模板标签及事件关联，仅供离线评测 |
| `manifest.json` | 来源、参数、生成器/模板摘要、各文件SHA256、数量和限制 |

所有事件保留 `context.synthetic=true`、`source=learning_simulator`、`measurement=simulated`。资源样例还明确 `resource_available=false`，没有假装真实视频/PDF或服务端采集已经存在。练习 `correct=null`，不冒充已有AI评分。

不能把整份目录、`truth/`、学生类型或manifest中的分布参数送给待评模型。未来评测器只应选择观测文件/字段，标签在模型输出后用于离线打分。本模块没有调用模型，因此目前不会把这些内容发送出去。

正式画像读取器只接纳明确 `synthetic=false` 的记录。新增测试把同一虚构学生的50条生成事件放入内存临时SQLite，确认真实事件读取结果为空；这不是向本机业务数据库导入数据。模拟包也不能证明真实播放/阅读采集和完整四类偏好已经实现。

## 4. 初学者复跑

在项目根目录的PowerShell执行，指定一个**尚不存在**的目录：

```powershell
.\.venv\Scripts\python.exe scripts/simulate_learning.py --output .local/simulator/my-first-run
.\.venv\Scripts\python.exe scripts/validate_simulator.py .local/simulator/my-first-run --report .local/simulator/my-first-validation.json
```

再次检查已有包，使用新的报告文件名即可：

```powershell
.\.venv\Scripts\python.exe scripts/validate_simulator.py .local/simulator/my-first-run --report .local/simulator/my-second-validation.json
```

生成器拒绝已存在的目录，校验器拒绝覆盖已有报告，不会替你清理文件。重新生成时改目录名；相同配置、模板和代码生成的文件摘要一致。更改配置应记录新的实验批次，不能悄悄把原数据当成同一批。

校验器检查哈希、人数/四类平衡、每人事件数量、开发集分配、UUID与引用、UTC顺序、累计资源计数、客观判分字段、对话和事件一致、真值泄漏、模拟标记，以及至少100人×50事件与30段误解对话。任一检查失败以非零状态退出。仅“生成成功”不等于通过校验，两条命令都需要运行。

## 5. 验证与限制

2026-10-19最终完整后端回归 **282项通过**，耗时128.29秒，其中本模块新增13项。覆盖完整规模与可复现性、不覆盖旧文件、规模/哈希错误、重新计算哈希后仍能发现语义篡改、非整除事件数的时间顺序、真实读取器排除模拟记录。JUnit报告保存在 `.local/ci/simulator-final-regression.xml`；仍有现有Starlette/httpx弃用警告。新增Python文件Ruff、CI工作流actionlint检查通过，云端执行尚待推送。本轮未改前端，没有重复前端构建或浏览器人工验收。

数据生成与结构要求已跑通，但没有人工评审全部模板、真实资源、真实学生行为验证或真实教学效果。六个概念样例不替代平台正式内容规模；本模块也没有替其他成员完成M7/M8评测器或模型验证。需要M8等模块使用时，应先由相关成员确认字段映射与标签使用方式。
