"""Course document ownership, immutable versions and searchable parsed chunks."""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "course_resources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("chapter_id", sa.String(36), sa.ForeignKey("chapters.id"), nullable=True),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("builtin_key", sa.String(40), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("knowledge_point_ids", sa.JSON, nullable=False),
        sa.Column("current_version", sa.Integer, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("course_id", "builtin_key", name="uq_resource_builtin"),
    )
    op.create_index("ix_course_resources_course_id", "course_resources", ["course_id"])
    op.create_table(
        "resource_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("resource_id", sa.String(36), sa.ForeignKey("course_resources.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("original", sa.LargeBinary, nullable=False),
        sa.Column("markdown", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resource_id", "version", name="uq_resource_version"),
    )
    op.create_index("ix_resource_versions_resource_id", "resource_versions", ["resource_id"])
    op.create_table(
        "resource_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("resource_versions.id"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("section", sa.String(400), nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("text", sa.Text, nullable=False),
    )
    op.create_index("ix_resource_chunks_version_id", "resource_chunks", ["version_id"])


def downgrade():
    op.drop_table("resource_chunks")
    op.drop_table("resource_versions")
    op.drop_table("course_resources")
