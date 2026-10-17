"""Reconcile databases that used the earlier, local practice revision 0004.

Both versions of 0004 have the same Alembic revision id. A database created by
the earlier version has no request/follow-up columns, although the version
table reports 0004. Fresh databases already have the current schema.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "practice_submissions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("practice_submissions")}
    if "request_id" not in columns:
        op.add_column("practice_submissions", sa.Column("request_id", sa.String(36), nullable=True))
        # Existing submission ids are UUIDs. Reusing them provides a distinct,
        # stable idempotency key without modifying any saved answers or events.
        op.execute(sa.text("UPDATE practice_submissions SET request_id = id WHERE request_id IS NULL"))
        with op.batch_alter_table("practice_submissions") as batch:
            batch.alter_column("request_id", existing_type=sa.String(36), nullable=False)

    if "parent_submission_id" not in columns:
        with op.batch_alter_table("practice_submissions") as batch:
            batch.add_column(sa.Column("parent_submission_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_practice_parent_submission", "practice_submissions", ["parent_submission_id"], ["id"]
            )
            batch.create_index("ix_practice_submissions_parent_submission_id", ["parent_submission_id"])

    constraints = {constraint["name"] for constraint in sa.inspect(bind).get_unique_constraints("practice_submissions")}
    if "uq_practice_request" not in constraints:
        with op.batch_alter_table("practice_submissions") as batch:
            batch.create_unique_constraint("uq_practice_request", ["exercise_id", "student_id", "request_id"])

    exercise_columns = {column["name"]: column for column in sa.inspect(bind).get_columns("practice_exercises")}
    if "created_by" in exercise_columns and not exercise_columns["created_by"]["nullable"]:
        # Keep the historical teacher id; new code does not set this column.
        with op.batch_alter_table("practice_exercises") as batch:
            batch.alter_column("created_by", existing_type=sa.String(36), nullable=True)


def downgrade():
    # A fresh database needs no changes. On a legacy database the added fields
    # contain user data, so leave them intact rather than discarding answers.
    pass
