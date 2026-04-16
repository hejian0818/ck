"""Initial PostgreSQL and pgvector schema.

Revision ID: 202604170001
Revises:
Create Date: 2026-04-17 00:01:00
"""

from __future__ import annotations

from alembic import op

revision = "202604170001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS repos (
            repo_id TEXT PRIMARY KEY,
            repo_path TEXT NOT NULL,
            branch TEXT NOT NULL,
            commit_hash TEXT NOT NULL,
            scan_time TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS modules (
            id TEXT PRIMARY KEY,
            repo_id TEXT NOT NULL REFERENCES repos(repo_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            repo_id TEXT NOT NULL REFERENCES repos(repo_id) ON DELETE CASCADE,
            module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS symbols (
            id TEXT PRIMARY KEY,
            repo_id TEXT NOT NULL REFERENCES repos(repo_id) ON DELETE CASCADE,
            file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            type TEXT NOT NULL,
            signature TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            visibility TEXT NOT NULL,
            doc TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS relations (
            id TEXT PRIMARY KEY,
            repo_id TEXT NOT NULL REFERENCES repos(repo_id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            target_type TEXT NOT NULL,
            source_module_id TEXT NOT NULL,
            target_module_id TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT ''
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS spans (
            repo_id TEXT NOT NULL REFERENCES repos(repo_id) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
            file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            symbol_id TEXT,
            node_type TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            id SERIAL PRIMARY KEY,
            repo_id VARCHAR(255) NOT NULL,
            object_id VARCHAR(255) NOT NULL,
            object_type VARCHAR(50) NOT NULL,
            embedding vector(768) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(repo_id, object_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS embeddings_vector_idx
        ON embeddings
        USING hnsw (embedding vector_cosine_ops)
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS embeddings_type_idx ON embeddings(object_type)")
    op.execute("CREATE INDEX IF NOT EXISTS embeddings_repo_type_idx ON embeddings(repo_id, object_type)")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP TABLE IF EXISTS embeddings")
    op.execute("DROP TABLE IF EXISTS spans")
    op.execute("DROP TABLE IF EXISTS relations")
    op.execute("DROP TABLE IF EXISTS symbols")
    op.execute("DROP TABLE IF EXISTS files")
    op.execute("DROP TABLE IF EXISTS modules")
    op.execute("DROP TABLE IF EXISTS repos")
