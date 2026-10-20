"""C: formal quiz bridge and persistent five-stage learning sessions."""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "course_quizzes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("max_attempts", sa.Integer, nullable=False),
        sa.Column("questions", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_course_quizzes_course_id", "course_quizzes", ["course_id"])
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("quiz_id", sa.String(36), sa.ForeignKey("course_quizzes.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("questions", sa.JSON, nullable=False),
        sa.Column("submitted_answers", sa.JSON, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("quiz_id", "student_id", "ordinal", name="uq_quiz_attempt_slot"),
    )
    for column in ("quiz_id", "student_id"):
        op.create_index(f"ix_quiz_attempts_{column}", "quiz_attempts", [column])
    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("knowledge_point_id", sa.String(36), sa.ForeignKey("knowledge_points.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("pending_turn_id", sa.String(36), nullable=True),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("student_id", "request_id", name="uq_learning_session_request"),
    )
    for column in ("course_id", "student_id"):
        op.create_index(f"ix_learning_sessions_{column}", "learning_sessions", [column])
    op.create_table(
        "learning_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("learning_sessions.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("evaluation_choice", sa.String(20), nullable=True),
        sa.Column("stage_before", sa.String(20), nullable=False),
        sa.Column("stage_after", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("output", sa.JSON, nullable=True),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("learning_events.event_id"), nullable=False),
        sa.Column("trace_id", sa.String(36), sa.ForeignKey("model_traces.trace_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id"),
        sa.UniqueConstraint("trace_id"),
        sa.UniqueConstraint("session_id", "request_id", name="uq_learning_turn_request"),
    )
    op.create_index("ix_learning_turns_session_id", "learning_turns", ["session_id"])


def downgrade():
    for table in ("learning_turns", "learning_sessions", "quiz_attempts", "course_quizzes"):
        op.drop_table(table)
