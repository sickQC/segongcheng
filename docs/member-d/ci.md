# D 公共职责：自动化 CI

CI 的作用是：每次提交代码到 GitHub 或发起 Pull Request，自动检查现有功能有没有被改坏。工作流位于 [ci.yml](../../.github/workflows/ci.yml)。本阶段只配置自动检查与构建产物，不会发布网站、修改线上数据库或自动部署。

## 检查内容

| GitHub 任务 | 内容 |
| --- | --- |
| Backend / ubuntu-latest | Python 3.13、锁定依赖检查、全部默认 SQLite 回归、迁移测试、E7 固定样例评测 |
| Backend / windows-latest | 与 Linux 相同，用于发现 Windows 路径和编码差异 |
| Backend / PostgreSQL 16 | GitHub 临时 PostgreSQL 服务、迁移升级/降级/再升级、开启 PostgreSQL 参数后的完整回归 |
| Frontend / Node 22 | `npm ci` 安装锁定版本，TypeScript 检查和 Vite 正式构建 |
| Deployment / Compose smoke | 前述任务通过后构建应用镜像，启动独立应用和数据库，检查网页/登录，重启应用后再次检查 |

PostgreSQL 回归中的 `foundation` 及引用它的业务测试会同时使用 SQLite 与 PostgreSQL；其余测试仍按自身设计使用 SQLite，不能将此任务理解成每个测试都在两种数据库运行。迁移往返只针对 GitHub 新建的空服务库；测试夹具使用随机测试 schema。

后端按 `backend/requirements-lock.txt` 安装，再以 `--no-deps` 安装本仓库 backend 包，执行 `pip check`。前端使用 `frontend/package-lock.json`。安装缓存用于加速，不替代版本锁。

模型响应使用测试替身，不需要真实 API Key，不测真实模型质量。CI 环境明确清空模型密钥，模型地址指向本机不可用端口，避免缺失替身时意外连接真实服务。CI 不读取你的本机 `.env` 或数据库。服务容器密码仅用于一次性 CI 容器，属于公开测试配置。

工作流使用只读仓库权限，不保留 checkout 凭据，不使用 `pull_request_target`，不需要添加 GitHub Secrets。同一分支的新运行会取消旧运行，每项任务有超时限制。

2026-10-20补齐 [质量与密钥扫描门禁](quality-gates.md)：新增独立quality任务，统一Python规范、固定版本/校验值的Gitleaks、自检、Git可见工作树和历史扫描，并仅上传脱敏摘要。Compose检查增加对quality的依赖；云端执行仍待推送，分支保护未自动设置。

## 怎样查看结果（初学者）

1. 本次没有提交或推送代码，所以 GitHub 暂时不会出现这份新工作流的运行记录。
2. 将来你决定提交时，需包含本轮 CI 文件和前几阶段依赖的源码、迁移、评测样例等相关文件；仅上传 CI 文件不能验证尚未上传的功能。不要添加 `.env`、数据库或 `.local`。
3. 推送后进入仓库网页，点击顶部 **Actions → Project CI**，打开对应提交的运行记录。
4. 绿色对勾表示该任务通过；红色叉号表示失败。点击失败任务，再点展开失败步骤，可查看错误位置。
5. 在运行详情底部 **Artifacts** 下载报告或前端构建产物。后端有 JUnit XML 与 E7 JSON，前端有 `frontend-dist`，保留 7 天。构建产物本身不是已经部署的网站。
6. 也可以在工作流进入默认分支后，从 **Run workflow** 手动运行。工作流被禁用时需要仓库有权限的成员启用 Actions。

分支保护和“测试通过才能合并”需要仓库管理员之后单独设置，本次没有改远程仓库设置。

## 本地复现

原有完整入口继续可用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

仅运行 E7 固定合成样例评测：

```powershell
.\.venv\Scripts\python.exe scripts/eval_recommendation.py --output .local/ci/e7-evaluation.json
```

本地输出位于 D 盘项目 `.local`。真实模型、真实学习效果、浏览器逐页操作、完整部署/CD 仍需分别验证。

## 验证状态（2026-10-19）

本轮实际验证：

- 官方 actionlint 1.7.12 校验工作流 YAML、任务结构和表达式通过；工具位于 D 盘 `.local/tools`，下载包已与官方 SHA256 清单核对。未安装 ShellCheck/Pyflakes，本轮 actionlint 显式禁用了这两项外部检查。
- 本机 Windows / Python 3.13：**256 项后端测试通过**，耗时 135.72 秒，JUnit 报告位于 `.local/ci/backend.xml`。存在一条现有 Starlette/httpx 弃用警告。
- `pip check` 通过；前端 `vue-tsc --noEmit && vite build` 通过，存在现有构建包体积提示。
- E7 的 4 个开发 / 8 个测试合成案例，两策略共 24 次调度无预算或先修违规，JSON 位于 `.local/ci/e7-evaluation.json`。
- 现有 `http://127.0.0.1:8000/health` 返回正常，本轮没有迁移或重置本地业务数据库，没有修改 `.env`，没有提交或推送代码。

本机没有可用 Docker 命令，本轮没有运行 PostgreSQL 服务容器。Linux、全新环境依赖安装、GitHub 托管运行器和 PostgreSQL 服务任务尚未运行，必须以未来 Actions 记录为准，不能把本地通过当作云端已通过。

后续部署阶段已追加容器构建与冒烟任务，见 [部署说明](deployment.md)。这里的“部署检查”运行在临时 CI 环境，没有向外部服务器自动发布，不能当作 CD 已完成。

后续 E7 评测阶段已追加 [多种子合成实验](e7-experiment.md)，输入、逐场景结果和区间报告写入 `.local/ci` 随报告上传；不会连接业务数据库或调用模型。

后续追加 [学习事件模拟模块](simulator.md)：CI独立生成100名虚构学生、5000条事件，验证真值隔离、完整性与数量。完整合成包及报告随 `.local/ci` 上传；其中 `truth/` 仅供离线打分，不应作为模型输入。

配置参考：[GitHub Python CI](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)、[Node.js CI](https://docs.github.com/en/actions/tutorials/build-and-test-code/nodejs)、[PostgreSQL 服务容器](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers)。
