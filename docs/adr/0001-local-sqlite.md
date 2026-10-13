# ADR 0001：课堂演示先使用 SQLite

状态：Sprint 0 实施选择，待 RAG 阶段扩展。

背景：本机只有 MySQL，尚无 PostgreSQL / pgvector / Docker，当前目标是尽快在课堂展示。
选择：SQLite 本地文件默认运行；SQLAlchemy 模型和 Alembic 迁移避免绑定数据库专用列类型；保留 PostgreSQL + pgvector Compose 配置。
收益：无额外服务、账号和安装步骤，事件能够真实持久化。
限制：没有向量检索能力；只用于单机低并发演示；切换 PostgreSQL 不会自动迁移旧数据。
不选择 MySQL 的原因：需要额外连接凭据，且仍要另选向量检索方案，对当前最小闭环没有明显收益。
