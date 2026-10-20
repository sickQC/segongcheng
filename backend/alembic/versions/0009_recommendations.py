"""Add prerequisites and saved baseline paths without modifying existing records."""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_edges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("from_kp_id", sa.String(36), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("to_kp_id", sa.String(36), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.UniqueConstraint("course_id", "from_kp_id", "to_kp_id", name="uq_prerequisite_edge"),
        sa.CheckConstraint("from_kp_id <> to_kp_id", name="ck_prerequisite_not_self"),
    )
    for column in ("course_id", "from_kp_id", "to_kp_id"):
        op.create_index(f"ix_knowledge_edges_{column}", "knowledge_edges", [column])
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("target_kp_id", sa.String(36), nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("course_id", "student_id", "request_id", name="uq_recommendation_request"),
    )
    for column in ("course_id", "student_id"):
        op.create_index(f"ix_recommendations_{column}", "recommendations", [column])


def downgrade():
    op.drop_table("recommendations")
    op.drop_table("knowledge_edges")
