"""File-backed videos and version-specific click-to-complete flags."""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("resource_versions", sa.Column("storage_path", sa.String(200), nullable=True))
    op.create_table(
        "video_completions",
        sa.Column("student_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("resource_versions.id"), primary_key=True),
    )


def downgrade():
    op.drop_table("video_completions")
    op.drop_column("resource_versions", "storage_path")
