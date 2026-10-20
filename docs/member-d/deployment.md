# D 公共职责：应用部署基础设施

本阶段依据 `docs/implementation-plan.md` 的 P7 部署项，补前端和后端镜像、独立数据库、持久化卷、初始化和部署冒烟检查。不包含视频/课件上传业务、图谱页面或其他成员功能。

## 交付内容

- `deploy/Dockerfile`：Node 22 构建前端；Python 3.13 镜像运行 FastAPI，同源提供网页和 API，单 worker，使用普通用户运行。镜像包含 LibreOffice、Poppler 和中文字体作为规划要求的转换工具；这不代表已实现上传/转换接口。
- `deploy/compose.app.yaml`：应用 + PostgreSQL 16/pgvector；数据库健康后启动应用，应用健康检查包括数据库可访问和基础表存在。
- `deploy/bootstrap.py`：启动前升级迁移、幂等初始化三个演示账号和课程、恢复有效画像投影；不重置数据库，不覆盖已有密码和课程编辑。容器启动时将进程交给 Uvicorn，便于正确停止。
- 数据库、检索索引、日志和预留上传目录分别使用持久化卷。数据库不向宿主机开放端口，网页默认仅绑定本机 `127.0.0.1:8080`。
- `.dockerignore` 排除 `.env`、本地数据库、Git、虚拟环境和缓存，避免把本机密钥及数据带进构建上下文。
- `scripts/smoke_deployment.py`：实际 HTTP 检查健康、前端资源、未登录访问控制、教师/学生登录和课程。除创建/注销自己的登录会话外，不新增或修改课程、作答、画像等业务记录。
- CI 新增 `Deployment / Compose smoke`：前面的回归通过后构建镜像、启动临时独立环境，检查服务，重启应用后再检查。没有上传镜像或向外部服务器发布。

原 `deploy/compose.yaml` 的数据库方案保持不变。新方案的默认 Compose 项目名是 `se-learning-demo`，使用独立数据卷，根目录 `.env`、原 SQLite 和旧数据库卷不会挂载到新容器。这是新的演示环境，不会自动复制你当前已有的学习记录。

## 如何启动（以后有 Docker 时）

本机目前没有可用 Docker，尚未构建或运行容器。本轮没有安装 Docker Desktop、WSL 或下载镜像。这些工具和镜像占用较大；以后安装时先安排好 D 盘存储位置。

以下命令都在项目根目录的 PowerShell 执行。先确认 Docker Desktop 正在运行 Linux 容器，并且 `docker compose version` 可用。

### 1. 创建独立配置

```powershell
if (-not (Test-Path -LiteralPath deploy/.env.deploy)) {
    Copy-Item -LiteralPath deploy/.env.example -Destination deploy/.env.deploy
}
```

打开 `deploy/.env.deploy`，只需先修改两项：

- `DEPLOY_DB_PASSWORD`：给新的容器数据库设置密码。
- `DEPLOY_SEED_PASSWORD`：给新环境的 `teacher`、`student01`、`student02` 设置初始登录密码。

两者至少 8 位，不能保留 `CHANGE_ME...`。密码保留示例中的单引号包裹，尤其是含 `$` 时；不要在聊天中发送密码。不要改根目录已有 `.env`。部署配置文件已被 Git 忽略，并被 Docker 构建排除。

模型项可暂时留空；课程、客观判分和推荐规则可以体验，真实 AI 答疑/诊断/5E 反馈仍需要有效模型配置。容器使用 API，不会借用你的本机 Codex 登录。

### 2. 检查并启动

```powershell
docker compose --env-file deploy/.env.deploy -f deploy/compose.app.yaml config --quiet
docker compose --env-file deploy/.env.deploy -f deploy/compose.app.yaml up --build -d --wait --wait-timeout 180
```

首次下载和构建可能较慢。完成后访问 **http://127.0.0.1:8080**，与原来的本地 **8000** 环境分开。

教师用 `teacher`，学生用 `student01`；密码使用这份部署配置的 `DEPLOY_SEED_PASSWORD`。原数据库不会导入。教师先创建练习、测验、先修关系，学生再完成学习并查看报告和推荐。

### 3. 查看状态、停止和重新启动

```powershell
docker compose --env-file deploy/.env.deploy -f deploy/compose.app.yaml ps
docker compose --env-file deploy/.env.deploy -f deploy/compose.app.yaml logs --tail 50 app
docker compose --env-file deploy/.env.deploy -f deploy/compose.app.yaml down
docker compose --env-file deploy/.env.deploy -f deploy/compose.app.yaml up -d --wait --wait-timeout 180
```

`down` 停容器、保留数据卷。不要加 `-v`，它会删除新环境数据卷。已有账号的密码不会因重启而改变，修改初始化密码也不会替已有用户重设密码。修改数据库密码配置不会自动修改已有 PostgreSQL 卷内的角色密码；保留原配置，不能靠删库解决。

后续更新镜像前先备份容器数据库与文件卷，再执行带 `--build` 的启动命令。容器方案不会自动生成PostgreSQL/文件卷备份或提供一键回滚；不能仅回滚镜像就假定数据库已回滚。原生SQLite环境现有独立的[本地备份与恢复演练工具](database-backup.md)，它不适用于容器PostgreSQL，不能替代此处要求的容器备份。

默认只供本机体验。对外提供访问时，还需确定服务器、域名、HTTPS 与备份策略，并相应设置绑定地址、允许来源及安全 Cookie；本次没有开放公网或执行远程部署。

## 验证边界

2026-10-19 本机实际验证：

- 完整后端隔离回归 **261 项通过**，耗时 132.18 秒；包含本阶段新增的 5 项部署保护测试。报告：`.local/ci/deployment-regression.xml`。保留现有 Starlette/httpx 弃用警告。
- 在临时 SQLite 上实际执行初始化、修改教师课程内容、更换初始化密码后再次初始化，确认账号不重复、原账号密码和课程修改保留、迁移达到 `0010`。数据库密码特殊字符编码和配置占位值拒绝检查通过。
- 新 Python 文件 Ruff 检查、更新后的 CI actionlint 检查通过；Compose YAML 解析和隔离结构检查通过，但未执行 `docker compose config`。
- 冒烟脚本对原本机 `http://127.0.0.1:8000` 实际运行通过，覆盖网页资源、访问控制、教师/学生登录、课程和注销。这验证了脚本和现有服务，不能替代容器端验证。本轮发现原服务已停止后，用原环境重新启动，没有执行本地业务数据库迁移或重置。
- 未修改原 `.env`，未创建含真实密码的部署配置，未推送代码。

容器构建、Linux 镜像内的转换工具、pgvector、容器卷及重启冒烟尚未运行，必须以真正的 Docker/CI 运行结果为准。自动发布/CD 尚未完成，需要先确定发布目标。

实现参考：[Docker 多阶段构建](https://docs.docker.com/build/building/multi-stage/)、[Compose 健康依赖](https://docs.docker.com/compose/how-tos/startup-order/)、[环境变量替换](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)。
