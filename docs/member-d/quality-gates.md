# D：CI代码质量与密钥扫描门禁

本模块补齐需求规划中“CI检查、密钥扫描”的公共工程职责。新增统一规范、固定版本扫描器安装、脱敏包装器、自检、单元测试、本地入口与CI任务；不新增或修改其他成员的业务功能。

## 1. 门禁内容

| 检查 | 规则与结果 |
| --- | --- |
| Python规范 | Ruff 0.17.0，根目录 `ruff.toml`，后端pyproject继承同一配置；检查backend/scripts/deploy |
| 规则范围 | E4/E7/E9、F、I：常见语法/风格、未定义/未使用名称及导入排序；不以旧长行作为门禁，不做全仓业务代码重排版 |
| 明确例外 | 6个现有CLI脚本在导入app前需要补sys.path，只对这些路径放宽E402；不全局关闭检查 |
| 敏感文件预拦截 | Git可交付文件中出现 `.env`、非示例 `.env.*`、数据库、私钥等时，先阻断，不读其内容 |
| 当前文件扫描 | 使用Gitleaks默认规则，扫描Git已跟踪与未忽略的新文件快照；包括本轮尚未提交的源码 |
| 历史扫描 | `--history` 扫描本地已获取的全部refs历史；CI使用完整fetch，默认执行此项 |
| 扫描器自检 | 干净输入、无效生成令牌检出、结果脱敏、误跟踪敏感文件预拦截；不使用真实凭据 |
| 故障处理 | 工具丢失、版本不符、超时、无有效报告或异常退出均失败，不默认为通过 |

首次统一规范时，Ruff修复了24项导入排序诊断；没有手工改业务逻辑或批量格式化函数体。所有更早的本地修改保留。历史评测报告仍代表其当时源码，代码摘要可能随导入整理而不同；不为“通过”而改写旧实验结果。

前端继续使用已有TypeScript检查与Vite构建。本模块未新增ESLint或声称已覆盖所有前端格式规则。质量任务失败会使整个工作流失败，并阻止后续Compose部署检查；仓库管理员仍需自行配置受保护分支的必需状态检查，不能仅凭工作流就保证任何人都无法合并。

## 2. 密钥如何保持不输出

本地真实 `.env`、虚拟环境、业务数据库、`.local`等通常被Git忽略，不会复制到扫描快照。如果被误跟踪为待交付文件，包装器会在复制任何文件内容之前阻断。`.env.example`仍要正常扫描，不能因为是示例就放过真凭据。

扫描器使用固定 **Gitleaks 8.30.1**，Windows/Linux x64发行包的SHA256固定在安装脚本中；只从官方发行地址下载，内存校验后仅读取期望的单个可执行文件，不执行压缩包的任意路径解压。工具存放在项目 `.local/tools`，不修改系统PATH，不覆盖内容不一致的已有工具。

调用时强制完全脱敏，捕获而不回显原始stdout/stderr。最终报告只保留文件、行号、规则名和计数，不保留Secret、Match、作者或原始代码。临时快照和扫描器中间报告在项目 `.local`内的独立目录，用完删除；CI仅上传脱敏摘要。默认规则保持启用，没有为了通过而整体排除测试或文档，没有添加任意基线、行内跳过或宽泛白名单。

扫描不是“绝对无泄密”的证明：只覆盖Git可见文本及扫描器默认可识别模式；本地未获取的历史、外部子模块/LFS内容、加密内容、Office/PDF内部或压缩包未展开内容不保证覆盖。工具不验证发现的令牌是否有效，也不会连接服务商试用令牌。

## 3. 本地使用（PowerShell）

首次安装固定扫描器，下载只写入D盘项目工具目录：

```powershell
.\.venv\Scripts\python.exe scripts/install_quality_tools.py
```

完整本地门禁（推荐交付前运行）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\quality.ps1 -History
```

仅检查当前待交付文件可省略 `-History`。这不替代业务回归：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

可单独运行：

```powershell
.\.venv\Scripts\python.exe -m ruff check --config ruff.toml backend scripts deploy
.\.venv\Scripts\python.exe scripts/check_secrets.py --self-test
.\.venv\Scripts\python.exe scripts/check_secrets.py --history
```

报告为 `.local/ci/secret-scan-summary.json`，通过返回0，发现问题返回1，工具无法完成返回2。若命中，只按脱敏报告中的文件/行号在自己电脑查看并修正，不要把密钥贴到聊天或仓库。历史发现不会自动清理提交，也不会自动撤销/轮换密钥；本模块不改写Git历史。

## 4. CI与验证

新增任务 `Quality / Python and secrets`：安装固定Ruff、规范检查、校验扫描器、正反例自检、当前文件与历史扫描、上传脱敏摘要。无需GitHub Secrets或Gitleaks Action授权凭据。CI可执行检查已配置，云端实跑仍需用户决定提交/推送，当前没有推送。

2026-10-20最终验证：完整后端 **308项通过**，耗时144.49秒，本模块新增12项；最终门禁用例额外复核12项通过。覆盖敏感文件先拦截、脱敏、工具故障阻断、SHA256失败阻断、Windows/Linux归档只读取指定成员。保留现有Starlette/httpx弃用警告。

统一Ruff检查、默认继承配置检查、真实扫描器自检、当前工作树/本地历史扫描、一键PowerShell入口及actionlint检查均通过。实际扫描未检出密钥或误跟踪敏感文件。详细结果见 [验证记录](../evaluation/quality-gates-verification.json)；完整临时测试报告为 `.local/ci/quality-gates-tests.xml`，脱敏扫描报告为 `.local/ci/secret-scan-summary.json`。

本轮未改前端，没有重复构建或浏览器人工验收；没有迁移数据库、修改 `.env`、重启服务、提交或推送代码。GitHub托管运行器、Linux实际安装/执行和云端完整历史仍需未来Actions运行确认。

规则与参数参考：[Ruff官方配置](https://docs.astral.sh/ruff/configuration/)、[Gitleaks官方CLI与配置](https://github.com/gitleaks/gitleaks)。
