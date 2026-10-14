"""M7: 模型调用记录支持非诊断类调用（AI 助教问答）。

AI 助教（M7）与诊断智能体（M8）共用一张模型调用记录表，以便 NF-14 能够按统一口径
追踪"每一次智能体调用"。因此需要：

1. `diagnosis_id` 允许为空——助教问答不产生诊断记录；
2. 新增 `feature` 区分能力（diagnosis / tutor.ask / tutor.ask.stream）；
3. 新增 `event_id`，把助教调用关联到它写入的学习事件（M6-2 的 asked 事件）；
4. 新增 `details`，存放检索结果、护栏判定与引用校验等结构化过程数据。

SQLite 不支持直接放宽列约束，因此使用 batch 模式重建表。
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    # The historical partner branch also used revision 0002, for a different schema.
    # Refuse to silently stamp/skip tables if that database is supplied here.
    if not sa.inspect(op.get_bind()).has_table("users"):
        raise RuntimeError(
            "This database uses the historical RAG-only 0002 schema. "
            "Do not stamp it as the foundation revision; migrate it separately or use a new database."
        )
    with op.batch_alter_table("model_traces") as batch:
        batch.alter_column("diagnosis_id", existing_type=sa.String(36), nullable=True)
        batch.add_column(sa.Column("feature", sa.String(40), nullable=False, server_default="diagnosis"))
        batch.add_column(sa.Column("event_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("details", sa.JSON, nullable=True))
    op.create_index("ix_model_traces_feature", "model_traces", ["feature"])
    op.create_index("ix_model_traces_event_id", "model_traces", ["event_id"])


def downgrade():
    # 0001 的表结构无法表示助教调用：model_traces.diagnosis_id 必须非空，
    # 而助教问答没有对应的诊断记录。降级时先删除这些行，否则恢复 NOT NULL 会失败。
    # 这是不可逆的信息损失，因此降级只用于开发期回滚，不作为正式数据迁移路径。
    op.execute("DELETE FROM model_traces WHERE diagnosis_id IS NULL")
    op.drop_index("ix_model_traces_event_id", table_name="model_traces")
    op.drop_index("ix_model_traces_feature", table_name="model_traces")
    with op.batch_alter_table("model_traces") as batch:
        batch.drop_column("details")
        batch.drop_column("event_id")
        batch.drop_column("feature")
        batch.alter_column("diagnosis_id", existing_type=sa.String(36), nullable=False)
