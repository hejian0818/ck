"""Persistence layer for graph objects."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.models.graph_objects import File, GraphCode, Module, Relation, Span, Symbol


class GraphRepository:
    """CRUD access for GraphCode storage."""

    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url)

    def initialize_schema(self) -> None:
        statements = self._load_schema_statements()
        with self.engine.begin() as connection:
            for statement in statements.split(";"):
                sql = statement.strip()
                if sql:
                    connection.execute(text(sql))

    def save_graphcode(self, graphcode: GraphCode) -> None:
        repo_id = graphcode.repo_meta.repo_id
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO repos (repo_id, repo_path, branch, commit_hash, scan_time)
                    VALUES (:repo_id, :repo_path, :branch, :commit_hash, :scan_time)
                    ON CONFLICT (repo_id) DO UPDATE SET
                        repo_path = EXCLUDED.repo_path,
                        branch = EXCLUDED.branch,
                        commit_hash = EXCLUDED.commit_hash,
                        scan_time = EXCLUDED.scan_time
                    """
                ),
                graphcode.repo_meta.model_dump(),
            )

            for module in graphcode.modules:
                connection.execute(
                    text(self._module_upsert_sql()),
                    {
                        "id": module.id,
                        "repo_id": repo_id,
                        "name": module.name,
                        "path": module.path,
                        "metadata": json.dumps(module.metadata),
                    },
                )

            for file_obj in graphcode.files:
                connection.execute(
                    text(
                        """
                        INSERT INTO files (id, repo_id, module_id, name, path, language, start_line, end_line)
                        VALUES (:id, :repo_id, :module_id, :name, :path, :language, :start_line, :end_line)
                        ON CONFLICT (id) DO UPDATE SET
                            module_id = EXCLUDED.module_id,
                            name = EXCLUDED.name,
                            path = EXCLUDED.path,
                            language = EXCLUDED.language,
                            start_line = EXCLUDED.start_line,
                            end_line = EXCLUDED.end_line
                        """
                    ),
                    {"repo_id": repo_id, **file_obj.model_dump()},
                )

            for symbol in graphcode.symbols:
                connection.execute(
                    text(
                        """
                        INSERT INTO symbols (
                            id, repo_id, file_id, module_id, name, qualified_name, type,
                            signature, start_line, end_line, visibility, doc
                        )
                        VALUES (
                            :id, :repo_id, :file_id, :module_id, :name, :qualified_name, :type,
                            :signature, :start_line, :end_line, :visibility, :doc
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            file_id = EXCLUDED.file_id,
                            module_id = EXCLUDED.module_id,
                            name = EXCLUDED.name,
                            qualified_name = EXCLUDED.qualified_name,
                            type = EXCLUDED.type,
                            signature = EXCLUDED.signature,
                            start_line = EXCLUDED.start_line,
                            end_line = EXCLUDED.end_line,
                            visibility = EXCLUDED.visibility,
                            doc = EXCLUDED.doc
                        """
                    ),
                    {"repo_id": repo_id, **symbol.model_dump()},
                )

            for relation in graphcode.relations:
                connection.execute(
                    text(
                        """
                        INSERT INTO relations (
                            id, repo_id, relation_type, source_id, target_id, source_type,
                            target_type, source_module_id, target_module_id
                        )
                        VALUES (
                            :id, :repo_id, :relation_type, :source_id, :target_id, :source_type,
                            :target_type, :source_module_id, :target_module_id
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            relation_type = EXCLUDED.relation_type,
                            source_id = EXCLUDED.source_id,
                            target_id = EXCLUDED.target_id,
                            source_type = EXCLUDED.source_type,
                            target_type = EXCLUDED.target_type,
                            source_module_id = EXCLUDED.source_module_id,
                            target_module_id = EXCLUDED.target_module_id
                        """
                    ),
                    {"repo_id": repo_id, **relation.model_dump()},
                )

            connection.execute(text("DELETE FROM spans WHERE repo_id = :repo_id"), {"repo_id": repo_id})
            for span in graphcode.spans:
                connection.execute(
                    text(
                        """
                        INSERT INTO spans (repo_id, file_path, line_start, line_end, module_id, file_id, symbol_id, node_type)
                        VALUES (:repo_id, :file_path, :line_start, :line_end, :module_id, :file_id, :symbol_id, :node_type)
                        """
                    ),
                    {"repo_id": repo_id, **span.model_dump()},
                )

    def get_module_by_id(self, module_id: str) -> Module | None:
        row = self._fetch_one("SELECT id, name, path, metadata FROM modules WHERE id = :id", {"id": module_id})
        if not row:
            return None
        metadata = row.metadata or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return Module(id=row.id, name=row.name, path=row.path, metadata=metadata)

    def get_file_by_id(self, file_id: str) -> File | None:
        row = self._fetch_one(
            """
            SELECT id, name, path, module_id, language, start_line, end_line
            FROM files WHERE id = :id
            """,
            {"id": file_id},
        )
        if not row:
            return None
        return File(**row._mapping)

    def get_symbol_by_id(self, symbol_id: str) -> Symbol | None:
        row = self._fetch_one(
            """
            SELECT id, name, qualified_name, type, signature, file_id, module_id,
                   start_line, end_line, visibility, doc
            FROM symbols WHERE id = :id
            """,
            {"id": symbol_id},
        )
        if not row:
            return None
        return Symbol(**row._mapping)

    def get_relations_by_source(self, source_id: str) -> list[Relation]:
        rows = self._fetch_all(
            """
            SELECT id, relation_type, source_id, target_id, source_type, target_type,
                   source_module_id, target_module_id
            FROM relations WHERE source_id = :source_id
            """,
            {"source_id": source_id},
        )
        return [Relation(**row._mapping) for row in rows]

    def get_relations_by_target(self, target_id: str) -> list[Relation]:
        rows = self._fetch_all(
            """
            SELECT id, relation_type, source_id, target_id, source_type, target_type,
                   source_module_id, target_module_id
            FROM relations WHERE target_id = :target_id
            """,
            {"target_id": target_id},
        )
        return [Relation(**row._mapping) for row in rows]

    def find_span(self, file_path: str, line_start: int, line_end: int) -> list[Span]:
        rows = self._fetch_all(
            """
            SELECT file_path, line_start, line_end, module_id, file_id, symbol_id, node_type
            FROM spans
            WHERE file_path = :file_path
              AND line_start <= :line_start
              AND line_end >= :line_end
            ORDER BY (line_end - line_start) ASC
            """,
            {"file_path": file_path, "line_start": line_start, "line_end": line_end},
        )
        return [Span(**row._mapping) for row in rows]

    def list_files_by_module(self, module_id: str) -> list[File]:
        rows = self._fetch_all(
            """
            SELECT id, name, path, module_id, language, start_line, end_line
            FROM files WHERE module_id = :module_id
            """,
            {"module_id": module_id},
        )
        return [File(**row._mapping) for row in rows]

    def list_symbols_by_file(self, file_id: str) -> list[Symbol]:
        rows = self._fetch_all(
            """
            SELECT id, name, qualified_name, type, signature, file_id, module_id,
                   start_line, end_line, visibility, doc
            FROM symbols WHERE file_id = :file_id
            """,
            {"file_id": file_id},
        )
        return [Symbol(**row._mapping) for row in rows]

    def get_repo_path(self, repo_id: str) -> str | None:
        row = self._fetch_one("SELECT repo_path FROM repos WHERE repo_id = :repo_id", {"repo_id": repo_id})
        return row.repo_path if row else None

    def _fetch_one(self, sql: str, params: dict[str, object]):
        with self.engine.begin() as connection:
            return connection.execute(text(sql), params).fetchone()

    def _fetch_all(self, sql: str, params: dict[str, object]):
        with self.engine.begin() as connection:
            return connection.execute(text(sql), params).fetchall()

    def _load_schema_statements(self) -> str:
        if self.engine.dialect.name == "sqlite":
            return """
            CREATE TABLE IF NOT EXISTS repos (
                repo_id TEXT PRIMARY KEY,
                repo_path TEXT NOT NULL,
                branch TEXT NOT NULL,
                commit_hash TEXT NOT NULL,
                scan_time TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS modules (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                module_id TEXT NOT NULL,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                language TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS symbols (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                module_id TEXT NOT NULL,
                name TEXT NOT NULL,
                qualified_name TEXT NOT NULL,
                type TEXT NOT NULL,
                signature TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                visibility TEXT NOT NULL,
                doc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                target_type TEXT NOT NULL,
                source_module_id TEXT NOT NULL,
                target_module_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS spans (
                repo_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                module_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                symbol_id TEXT,
                node_type TEXT NOT NULL
            );
            """
        schema_path = Path(__file__).with_name("schema.sql")
        return schema_path.read_text(encoding="utf-8")

    def _module_upsert_sql(self) -> str:
        if self.engine.dialect.name == "sqlite":
            return """
                INSERT INTO modules (id, repo_id, name, path, metadata)
                VALUES (:id, :repo_id, :name, :path, :metadata)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    path = EXCLUDED.path,
                    metadata = EXCLUDED.metadata
            """
        return """
            INSERT INTO modules (id, repo_id, name, path, metadata)
            VALUES (:id, :repo_id, :name, :path, CAST(:metadata AS JSONB))
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                path = EXCLUDED.path,
                metadata = EXCLUDED.metadata
        """
