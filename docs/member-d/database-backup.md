# D：本地数据库备份与恢复演练

本模块属于公共部署基础设施，用于保护当前原生SQLite环境。提供在线备份、校验和独立恢复演练；不替换运行中的数据库，不包含PostgreSQL、容器文件卷或远程发布。

## 初学者操作

在VS Code中打开“终端 → 新建终端”，确认目录为本项目根目录。网页可保持运行，但备份期间尽量不要编辑课程或提交学习活动，便于核对。

### 1. 生成备份

```powershell
.\.venv\Scripts\python.exe scripts/database_backup.py backup
```

成功时输出 `status: passed`，以及一个类似下面的目录：

```text
.local/backups/20261020T104757-一串随机编号
```

实际目录以终端输出为准，不要原样复制示例。该目录包含 `database.db` 和 `manifest.json`。清单记录SHA256、文件大小、表行数及迁移版本，不包含密码或答案原文。数据库文件本身包含完整账号、会话和学习数据，属于敏感备份。

每次运行创建新目录，不会覆盖旧备份；脚本没有自动清理功能。文件保留在项目D盘 `.local` 中，不写入C盘缓存，不随Git提交，也不上传CI附件。

### 2. 验证备份

把刚才输出的实际目录替换到下面命令中：

```powershell
.\.venv\Scripts\python.exe scripts/database_backup.py verify --backup-dir '.local/backups/替换为实际目录名'
```

成功应输出 `status: passed`。会检查清单版本、文件大小、SHA256、SQLite完整性、外键、表行数及迁移版本。缺少清单、文件被修改或校验不一致时退出非零，不应把失败目录当成可用备份。

SHA256用于发现意外损坏，不是数字签名，不能抵御有人同时篡改数据库和清单。备份未加密，应妥善保管，避免共享项目目录或发送备份文件。

### 3. 恢复演练

```powershell
.\.venv\Scripts\python.exe scripts/database_backup.py restore-drill --backup-dir '.local/backups/替换为实际目录名'
```

先验证原备份，然后复制到新的 `.local/restore-drills/时间-随机编号/database.db`，再次核对SHA256、完整性、外键、表行数及迁移版本，生成 `drill.json`。

成功应输出 `status: passed` 和 `active_database_replaced: false`。这表示备份可以恢复为独立数据库文件，**不会让网页切换到这份副本，也没有覆盖当前数据库**。演练文件没有启动应用、执行迁移、调用模型或恢复旧登录会话。

若真要回滚当前环境，应另行安排停服、最新备份、版本兼容检查和恢复后应用验收，不能直接将旧数据库覆盖到正在运行的服务。本工具有意不提供覆盖当前库的命令。

## 实现保护

- 从已有配置中读取数据库位置，既不改 `.env`，也不显示数据库连接串或密码。仅支持项目内已存在的文件型SQLite库；拒绝内存库、PostgreSQL及工作区外路径。
- 使用SQLite在线backup API，并以只读方式打开源库，纳入已提交WAL数据；不用简单复制活动数据库主文件的方法，避免漏掉WAL记录。未提交事务不被强制提交。
- 备份及演练输出目录均检查解析后的路径，防止符号链接指向指定目录外；新建文件和目录，不复用已有结果。
- 备份工作超过30秒时中止；失败可能留下无有效清单的目录，脚本不自动删除文件。容量和时限适合当前小型本地课程库，不承诺大库备份服务级别。
- 不备份 `.env`、模型密钥、上传目录或检索索引。恢复演练通过不等于全系统灾备通过，也不能据此声称PostgreSQL备份已完成。

## 本机验证（2026-10-20）

11项专项测试覆盖原库保持、恢复快照与后续原库编辑相互独立、在线WAL已提交/未提交事务边界、多次备份和演练互不覆盖、篡改文件/计数/迁移版本/格式、缺失清单、外键损坏、缺失源库及路径越界。完整后端回归341项通过，保留已有Starlette/httpx弃用警告；代码规范和脱敏密钥扫描通过。这些专项测试已随现有后端测试入口纳入CI发现范围，但没有推送或运行云端任务。

当前真实数据库已成功备份并恢复到独立目录：483,328字节（472KiB），23张表，迁移版本0011；原库文件摘要、表行数及 `.env` 摘要保持不变。数据内容不写入公开验证报告。详见 [本轮验证](../evaluation/database-backup-verification.json)。

官方机制参考：[Python SQLite backup API](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup)、[SQLite在线备份](https://www.sqlite.org/backup.html)、[SQLite完整性及外键检查](https://www.sqlite.org/pragma.html)。
