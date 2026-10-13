"""Sprint 0: 学习事件、诊断与模型调用记录。"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("verb", sa.String(40), nullable=False),
        sa.Column("object", sa.JSON, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("context", sa.JSON, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_learning_events_actor", "learning_events", ["actor"])
    op.create_table(
        "diagnoses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("learning_events.event_id"), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("output", sa.JSON, nullable=True),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_diagnoses_event_id", "diagnoses", ["event_id"])
    op.create_table(
        "model_traces",
        sa.Column("trace_id", sa.String(36), primary_key=True),
        sa.Column("diagnosis_id", sa.String(36), sa.ForeignKey("diagnoses.id"), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_summary", sa.JSON, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("usage", sa.JSON, nullable=True),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_traces_diagnosis_id", "model_traces", ["diagnosis_id"])


def downgrade():
    op.drop_table("model_traces")
    op.drop_table("diagnoses")
    op.drop_table("learning_events")
