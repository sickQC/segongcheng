# 学习事件离线模拟配置

本目录只保存可复现生成所需的配置和人工模板，不包含真实学生或业务数据库。

- `config.json`：固定种子、四类输入分布、人数/事件数、开发集划分及作答噪声。
- `topics.json`：6个自编概念样例、正确/错误表述与误解对话模板；不是教师确认的正式课程内容，也不算完成30个正式知识点要求。
- 生成器：`scripts/simulate_learning.py`；独立结构校验：`scripts/validate_simulator.py`。

默认生成100名模拟学生、每人50条事件、100段模板对话，其中34段带初始误解。潜在掌握度与类型只放在输出的 `truth/` 中，不能作为模型输入。所有观测保留 `synthetic=true`、`source=learning_simulator`、`measurement=simulated`。

完整用法、格式、验证结果和限制见 [D模拟模块说明](../../docs/member-d/simulator.md)。没有提供导入正式数据库的开关。
