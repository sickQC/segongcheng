"""Immutable four-dimensional profile snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "profile_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.String(80), nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("diagnosis_reports.id"), nullable=True),
        sa.Column("days", sa.Integer, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("course_id", "student_id", "request_id", name="uq_profile_snapshot_request"),
    )
    op.create_index("ix_profile_snapshots_course_id", "profile_snapshots", ["course_id"])
    op.create_index("ix_profile_snapshots_student_id", "profile_snapshots", ["student_id"])


def downgrade():
    op.drop_table("profile_snapshots")
