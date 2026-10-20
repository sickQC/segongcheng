"""Course diagnosis reports with immutable evidence snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "diagnosis_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("output", sa.JSON, nullable=True),
        sa.Column("trace_id", sa.String(36), sa.ForeignKey("model_traces.trace_id"), nullable=False),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("course_id", "student_id", "request_id", name="uq_report_request"),
    )
    for column in ("course_id", "student_id"):
        op.create_index(f"ix_diagnosis_reports_{column}", "diagnosis_reports", [column])


def downgrade():
    op.drop_table("diagnosis_reports")
