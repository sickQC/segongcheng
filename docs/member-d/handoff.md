# 成员 D：验收与交接总入口

核查日期：2026-10-20。本页记录当前本地工作区，不能当作 GitHub 已发布版本。分工依据用户确认：**学习事件、画像推荐、基础算法/E7；公共职责为自动测试、CI/CD、部署与评测基础设施**。D 已保存为本地提交 `2b11042`，本次继续整合远程 main 的 `34df21a`；云端交付以实际推送记录为准。

## 1. 范围与完成状态

本轮新增：[真实事件CSV/JSONL导出](event-export.md)、[只读性能与课程核查](acceptance-tools.md)。这两份文档及下方最新证据优先于旧阶段记录；不扩大D到其他成员的资源制作、问答或测验业务。

“已实现”表示当前代码已有这项行为，并列出验证证据；不表示所有数据库、浏览器、真实模型和部署环境均已验收。“部分实现”表示明确存在未接入或未验证的验收项。

| D 工作项 | 状态 | 当前已有 | 缺口与验证边界 |
| --- | --- | --- | --- |
| 本地数据库备份与恢复演练 | 已实现 | 在线SQLite备份、SHA256/完整性/外键/行数/版本校验、隔离恢复、路径及不覆盖保护 | 当前真实库备份与独立恢复已通过；不含PostgreSQL、文件卷、生产回滚和异地灾备，见[模块说明](database-backup.md) |
| 真实事件导出 | 已实现 | CSV/JSONL、时间/知识点/动作筛选、严格排除模拟数据、教师/学生入口、容量保护 | 本机HTTP与自动测试通过；浏览器实际下载仍待人工验收，见[导出说明](event-export.md) |
| 只读性能采样 | 已实现 | 10并发、六类非AI接口、P50/P95/错误与吞吐报告、CI归档配置 | 本机小数据已测；正式规模、PostgreSQL容器及云端未测，见[验收工具](acceptance-tools.md) |
| 课程规模核查 | 已实现 | 数量门槛、先修图/归属检查、题库去重、资源未知状态、可选严格退出码 | 工具已实测；正式内容尚不足，补内容依赖组内负责成员 |
| 真实学习事件查询 | 已实现 | 课程/学生/知识点/时间/动作筛选、分页、身份隔离，正式画像排除模拟记录 | SQLite 自动测试和先前 HTTP 检查；播放/阅读生产端仍需资源成员对接 |
| 四维画像 | 部分实现 | 有效诊断掌握度投影、独立客观正确率、活跃与问答/练习偏好、可解释风险；未知明确显示；已新增四维快照及历史对比 | 完整四类偏好和时长仍依赖真实资源采集 |
| 画像历史 | 已实现 | [历史模块](profile-history.md)：诊断后自动保存、手动保存、不可变详情、分页、四维对比、幂等与权限 | SQLite/HTTP和构建已验证；不回填旧时点，不把数值差当学习效果 |
| 先修关系 | 已实现 | 教师增删、跨课程拒绝、环路路径、拓扑顺序 | 测试证明约束；正式教学关系由教师/内容负责人录入，不凭空生成 |
| 基础路径推荐 | 已实现 | 目标先修闭包、跳已掌握、未知待测、来源解释、定义/已有练习入口、请求幂等与历史 | 不包含尚未建成的视频/PDF资源入口；历史记录保留生成时快照 |
| E7 时间预算推荐 | 已实现 | 可学节点按既定规则排序、1–240分钟预算、估时来源、剩余步骤、策略切换 | 学习耗时为估计，不是实测；“包含目标”不是“已学会” |
| 推荐反馈与统计 | 已实现 | 一份计划一次接受/拒绝反馈、幂等、权限、接受率分母明确 | 意愿不等于实际学习；没有代真实学生提交接受反馈 |
| 本地自动测试 | 已实现 | 业务、权限、迁移、并发/幂等、调度约束与初始化保护测试，前端类型检查/构建 | 最新统一结果见下方证据；真实模型与浏览器逐页验收另算 |
| GitHub CI | 部分实现 | Windows/Linux 后端、PostgreSQL任务、前端、E7评测、Compose冒烟、[代码规范与密钥门禁](quality-gates.md)及脱敏报告 | 本地门禁与工作流静态检查通过；未推送，云端任务未跑，分支保护未设置 |
| 部署基础设施 | 部分实现 | 应用镜像、独立Compose、初始化、卷、健康检查、冒烟脚本 | 本机无Docker，镜像构建、容器/pgvector、卷和重启尚未实际验证 |
| 自动发布/CD | 未实现 | 无自动发布到外部环境 | 需先确定发布目标；本轮没有公网地址、服务器操作或镜像发布 |
| E7 离线评测设施 | 已实现 | 12个手工边界用例、100个多种子场景、开发/测试分开、重复计时与成对区间、可复跑报告 | 合成场景不能替代真实接受率、真实学习耗时或教学效果 |
| 正式规模事件模拟设施 | 已实现 | [独立模块](simulator.md)生成四类100人×50事件，单独真值、100段模板对话/34段初始误解、结构校验、测试与CI | 离线合成结构已验；不代表真实学生、正式课程内容、资源采集或M8评测已完成 |

本轮没有承担视频/课件上传解析、RAG业务、测验业务、5E业务或图谱可视化的新增开发。已有这些流程的事件和诊断是 D 的输入，D 负责按约定接入与计算。真实课程知识点、视频、课件和题目等内容规模需内容负责人贡献，不能把整个平台内容制作都算作 D 一个人的欠项；事件模拟设施已在独立模块完成，仍需相关成员确认评测对接，当前E7的100场景与学习事件模拟包是两套不同数据。

## 2. 验证证据怎样读

最新 main 整合阶段：**360项完整后端回归通过**，前端4项Markdown测试及类型检查/构建通过，规范、脱敏扫描和工作流检查通过。保留组员讲义及定向5E与D画像推荐，新增跨模块闭环验证；旧本机索引已保留并重建。见[整合说明](../updates/2026-10-20-member-d-main-integration.md)及[验证摘要](../evaluation/main-integration-verification.json)。本轮不包含真实模型、容器、云端和浏览器人工复验，未推送。

最新本地备份恢复阶段：**341项完整回归通过**（本轮新增11项），代码规范及脱敏密钥扫描通过。当前真实SQLite已在线备份、校验并恢复到独立副本，23张表及迁移0011核对通过；原库文件和 `.env` 保持不变。见[备份模块](database-backup.md)及[验证记录](../evaluation/database-backup-verification.json)。本轮没有修改页面、数据库结构或运行服务，因此未重复前端构建。

最新事件导出与公共验收阶段：**330项完整回归通过**，前端类型检查/构建通过；本机HTTP导出9条、身份隔离和数据保留通过；10并发180个只读请求0错误、各接口P95为51–183毫秒。证据见 [本轮验证](../evaluation/d-acceptance-tools-verification.json)、[性能报告](../evaluation/read-api-benchmark.json)、[课程规模清单](../evaluation/course-inventory.json)。当前课程只有2章/4知识点/3先修边，视频/课件缺少权威记录，正式规模尚未达标。没有把小数据性能、API检查或构建冒充正式规模或浏览器验收。

统一记录：[交接阶段验证摘要](../evaluation/member-d-verification.json)。这是新增模拟模块之前的269项测试快照及对应代码摘要，并非后续修改后的实时状态。模拟阶段最新证据见 [模拟模块](simulator.md) 与 [校验报告](../evaluation/learning-simulator-validation.json)。完整临时测试报告存放 `.local/ci`，不随 Git 提交。

最新画像历史阶段：**296项完整回归通过**，前端构建及实际HTTP快照检查通过，见 [画像历史验证](../evaluation/profile-history-verification.json)。不同阶段数字不可相加；云端、真实模型和浏览器人工验收仍独立待验。

最新质量门禁阶段：**308项完整回归通过**；规范、固定扫描器自检、工作树/本地历史脱敏扫描与本地一键入口通过，见 [质量门禁验证](../evaluation/quality-gates-verification.json)。这次只修正导入排序、补基础设施；没有重复前端构建或修改数据库。

| 证据 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| 当前后端全量回归、前端构建 | 本机安装依赖下当前代码可回归、前端类型检查可构建 | 全新安装、Linux/PostgreSQL、真实模型或实际浏览器点击 |
| HTTP冒烟 | 当前网页资源、身份校验、教师/学生登录和课程可读 | 浏览器交互布局、模型质量或容器实际运行 |
| [基础/E7固定报告](../evaluation/e7-baseline-budgeted.json) | 手工边界案例结果与预算/先修约束 | 真实教学收益 |
| [多种子报告](../evaluation/e7-multiseed.json) | 同输入两策略、100合成场景、重复计时和区间 | 100个真实学生或实际学习时间 |
| actionlint与Compose静态检查 | 工作流语法、表达式及配置结构 | GitHub任务或容器已跑通 |

旧记录按阶段保留：基础推荐237项、E7阶段256项、部署阶段261项；它们不是当前全量测试数量，也不能相加。此前其他成员的PostgreSQL或浏览器记录不能替代本轮验证。

## 3. 教师、学生怎样演示

2026-10-20 用户反馈：“检验完成”。记录为用户反馈的浏览器验收完成；未收到逐项表格或截图，不将每个边界场景标记为独立已验证，也不据此声称真实模型、容器或云端验收通过。

按 [演示与人工验收步骤](demo-checklist.md) 操作。现有本机入口：**http://127.0.0.1:8000**。原生环境账号为 `teacher`、`student01`、`student02`，初始密码在本机根目录 `.env` 的 `SEED_PASSWORD`，不要复制到交接材料或聊天。

容器方案将来启动后默认用 **8080**，账号密码来自独立部署配置，不是同一个数据库。不要把配置中的8080当成当前已启动网页。

## 4. 代码定位与接口入口

| 内容 | 主要文件 |
| --- | --- |
| 事件/画像 API与计算 | `backend/app/api/routes/profile.py`、`backend/app/services/learning_events.py`、`backend/app/services/profile.py` |
| 综合诊断到掌握度 | `backend/app/services/evidence_diagnosis.py`、`backend/app/models/profile.py` |
| 先修图、推荐、预算调度 | `backend/app/services/prerequisites.py`、`recommendation.py`、`budgeted_recommendation.py` |
| 推荐/反馈/统计 API | `backend/app/api/routes/recommendation.py` |
| 数据库增量迁移 | `backend/alembic/versions/0008_profiles.py`、`0009_recommendations.py`、`0010_budgeted_recommendation.py` |
| 页面 | `frontend/src/components/LearningProfilePanel.vue`、`PrerequisiteEditor.vue`、`StudyTimeEditor.vue`、`RecommendationPanel.vue` |
| 自动化与部署 | `.github/workflows/ci.yml`、`scripts/test.ps1`、`deploy/Dockerfile`、`deploy/compose.app.yaml`、`deploy/bootstrap.py` |
| E7评测 | `scripts/eval_recommendation.py`、`scripts/eval_e7_experiment.py`、`data/eval/recommendation/` |

正式接口前缀 `/api/v1`；完整请求字段看 [OpenAPI](../api.yaml) 或运行服务的 `/docs`。学生有自己的画像/事件/推荐接口，教师通过带学生ID的课程接口查询。教师的原有班级看板不自动等于新增四维画像的专用UI。旧 `/report?algorithm=enhanced` 仍是501占位，当前 E7 应从推荐面板或专用推荐接口进入。

## 5. 复跑与交付

在项目根目录 PowerShell 执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
.\.venv\Scripts\python.exe scripts/eval_recommendation.py --output .local/ci/e7-evaluation.json
.\.venv\Scripts\python.exe scripts/eval_e7_experiment.py
```

首次环境安装与启动见根目录 README；[画像规则](profile-milestone.md)、[基础推荐](baseline-recommendation.md)、[E7](e7-budgeted-recommendation.md)、[多种子实验](e7-experiment.md)、[CI](ci.md)、[部署](deployment.md)保留详细说明。

交接时源码、迁移、前端、测试、评测配置和文档需一起交付，不能只复制工作流。根目录 `.env`、`deploy/.env.deploy`、数据库、`.venv`、`.local`、`node_modules` 不提交。现有修改未经用户要求不推送；不能把当前本地功能描述成远程仓库已经具备。

## 6. 后续事项按依赖推进

1. 用户已反馈完成浏览器验收；后续出现具体界面问题再记录复查。未提供逐项明细，真实模型未配置的项目及未说明的边界场景仍保持待验。
2. 资源成员完成采集后，由 D 对接可信事件与四类偏好，不代做资源业务。接口约定以现有 `learning_events.py`、画像文档与 OpenAPI 为准。
3. 有Docker环境后跑部署文档的检查与启动，验证数据卷、重启和干净环境，补实测证据。
4. 用户决定提交/推送后，检查Actions记录，处理Linux/PostgreSQL/容器实测失败，并由管理员设置必需状态检查。代码规范与密钥门禁已接入，无需重复开发。
5. 组内明确部署目标、公共数据/内容与真实评测安排后，补CD及对应验收。没有外部条件时不新增无关功能来凑完成度。
