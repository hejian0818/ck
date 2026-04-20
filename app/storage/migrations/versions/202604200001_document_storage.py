"""Add document skeleton and result storage.

Revision ID: 202604200001
Revises: 202604170001
Create Date: 2026-04-20 00:01:00
"""

from __future__ import annotations

from alembic import op

revision = "202604200001"
down_revision = "202604170001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_skeletons (
            repo_id TEXT PRIMARY KEY REFERENCES repos(repo_id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            skeleton_json JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_results (
            document_id TEXT PRIMARY KEY,
            repo_id TEXT NOT NULL REFERENCES repos(repo_id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            document_json JSONB NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS document_results_repo_generated_idx
        ON document_results(repo_id, generated_at DESC)
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP TABLE IF EXISTS document_results")
    op.execute("DROP TABLE IF EXISTS document_skeletons")
