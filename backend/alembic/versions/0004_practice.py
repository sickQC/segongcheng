"""Member C: course exercise/answer storage, including follow-up ancestry."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "practice_exercises",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("chapter_id", sa.String(36), sa.ForeignKey("chapters.id"), nullable=False),
        sa.Column("knowledge_point_id", sa.String(36), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("knowledge_point_id", name="uq_practice_kp"),
    )
    op.create_index("ix_practice_exercises_course_id", "practice_exercises", ["course_id"])
    op.create_table(
        "practice_submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("exercise_id", sa.String(36), sa.ForeignKey("practice_exercises.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_answer", sa.Text, nullable=False),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("learning_events.event_id"), nullable=False),
        sa.Column("diagnosis_id", sa.String(36), sa.ForeignKey("diagnoses.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("parent_submission_id", sa.String(36), sa.ForeignKey("practice_submissions.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id"),
        sa.UniqueConstraint("diagnosis_id"),
        sa.UniqueConstraint("exercise_id", "student_id", "request_id", name="uq_practice_request"),
    )
    for column in ("exercise_id", "student_id", "parent_submission_id"):
        op.create_index(f"ix_practice_submissions_{column}", "practice_submissions", [column])


def downgrade():
    op.drop_table("practice_submissions")
    op.drop_table("practice_exercises")
