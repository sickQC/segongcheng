"""Persistent mastery and idempotent diagnosis application; existing data retained."""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "profile_applications",
        sa.Column("report_id", sa.String(36), sa.ForeignKey("diagnosis_reports.id"), primary_key=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mastery_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("knowledge_point_id", sa.String(36), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("mastery", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("diagnosis_reports.id"), nullable=False),
        sa.Column("evidence_ids", sa.JSON, nullable=False),
        sa.Column("input_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_order", sa.String(120), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("course_id", "student_id", "knowledge_point_id", name="uq_mastery_scope"),
    )
    for column in ("course_id", "student_id"):
        op.create_index(f"ix_mastery_profiles_{column}", "mastery_profiles", [column])


def downgrade():
    op.drop_table("mastery_profiles")
    op.drop_table("profile_applications")
