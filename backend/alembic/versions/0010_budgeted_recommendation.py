"""Optional teacher time estimates and explicit recommendation feedback."""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("knowledge_points", sa.Column("estimated_minutes", sa.Integer, nullable=True))
    op.create_table(
        "recommendation_feedback",
        sa.Column("recommendation_id", sa.String(36), sa.ForeignKey("recommendations.id"), primary_key=True),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("choice", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("choice IN ('accepted', 'declined')", name="ck_feedback_choice"),
    )
    op.create_index("ix_recommendation_feedback_student_id", "recommendation_feedback", ["student_id"])


def downgrade():
    op.drop_table("recommendation_feedback")
    op.drop_column("knowledge_points", "estimated_minutes")
