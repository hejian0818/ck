"""Persistence layer for graph objects."""

from __future__ import annotations

import json
import time
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.models.graph_objects import File, GraphCode, Module, Relation, Span, Symbol


class _TTLCache:
    """Simple dict-backed TTL cache."""

    def __init__(self, ttl: int = 60, time_fn: object | None = None) -> None:
        self._store: dict[str, tuple[float, object]] = {}
        self._ttl = ttl
        self._time_fn = time_fn or time.monotonic

    def get(self, key: str) -> object | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._time_fn() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: object) -> None:
        self._store[key] = (self._time_fn() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()


class GraphRepository:
    """CRUD access for GraphCode storage."""

    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url)
        self._object_cache = _TTLCache(ttl=settings.CACHE_GRAPH_TTL)

    def initialize_schema(self) -> None:
        statements = self._load_schema_statements()
        with self.engine.begin() as connection:
            for statement in statements.split(";"):
                sql = statement.strip()
                if sql:
                    connection.execute(text(sql))
            self._ensure_summary_columns(connection)

    def init_vector_tables(self) -> None:
        statements = self._load_vector_schema_statements()
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
                        "summary": module.summary,
                        "metadata": json.dumps(module.metadata),
                    },
                )

            for file_obj in graphcode.files:
                connection.execute(
                    text(
                        """
                        INSERT INTO files (
                            id, repo_id, module_id, name, path, summary, language, start_line, end_line
                        )
                        VALUES (
                            :id, :repo_id, :module_id, :name, :path, :summary, :language, :start_line, :end_line
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            module_id = EXCLUDED.module_id,
                            name = EXCLUDED.name,
                            path = EXCLUDED.path,
                            summary = EXCLUDED.summary,
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
                            signature, summary, start_line, end_line, visibility, doc
                        )
                        VALUES (
                            :id, :repo_id, :file_id, :module_id, :name, :qualified_name, :type,
                            :signature, :summary, :start_line, :end_line, :visibility, :doc
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            file_id = EXCLUDED.file_id,
                            module_id = EXCLUDED.module_id,
                            name = EXCLUDED.name,
                            qualified_name = EXCLUDED.qualified_name,
                            type = EXCLUDED.type,
                            signature = EXCLUDED.signature,
                            summary = EXCLUDED.summary,
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
                            target_type, source_module_id, target_module_id, summary
                        )
                        VALUES (
                            :id, :repo_id, :relation_type, :source_id, :target_id, :source_type,
                            :target_type, :source_module_id, :target_module_id, :summary
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            relation_type = EXCLUDED.relation_type,
                            source_id = EXCLUDED.source_id,
                            target_id = EXCLUDED.target_id,
                            source_type = EXCLUDED.source_type,
                            target_type = EXCLUDED.target_type,
                            source_module_id = EXCLUDED.source_module_id,
                            target_module_id = EXCLUDED.target_module_id,
                            summary = EXCLUDED.summary
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
        self.clear_cache()

    def get_module_by_id(self, module_id: str) -> Module | None:
        cache_key = f"get_module_by_id:{module_id}"
        cached = self._object_cache.get(cache_key)
        if cached is not None:
            return cached
        row = self._fetch_one(
            "SELECT id, name, path, summary, metadata FROM modules WHERE id = :id",
            {"id": module_id},
        )
        if not row:
            return None
        metadata = row.metadata or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        module = Module(id=row.id, name=row.name, path=row.path, summary=row.summary, metadata=metadata)
        self._object_cache.set(cache_key, module)
        return module

    def get_file_by_id(self, file_id: str) -> File | None:
        cache_key = f"get_file_by_id:{file_id}"
        cached = self._object_cache.get(cache_key)
        if cached is not None:
            return cached
        row = self._fetch_one(
            """
            SELECT id, name, path, module_id, summary, language, start_line, end_line
            FROM files WHERE id = :id
            """,
            {"id": file_id},
        )
        if not row:
            return None
        file_obj = File(**row._mapping)
        self._object_cache.set(cache_key, file_obj)
        return file_obj

    def get_symbol_by_id(self, symbol_id: str) -> Symbol | None:
        cache_key = f"get_symbol_by_id:{symbol_id}"
        cached = self._object_cache.get(cache_key)
        if cached is not None:
            return cached
        row = self._fetch_one(
            """
            SELECT id, name, qualified_name, type, signature, file_id, module_id,
                   summary, start_line, end_line, visibility, doc
            FROM symbols WHERE id = :id
            """,
            {"id": symbol_id},
        )
        if not row:
            return None
        symbol = Symbol(**row._mapping)
        self._object_cache.set(cache_key, symbol)
        return symbol

    def get_relations_by_source(self, source_id: str) -> list[Relation]:
        rows = self._fetch_all(
            """
            SELECT id, relation_type, source_id, target_id, source_type, target_type,
                   source_module_id, target_module_id, summary
            FROM relations WHERE source_id = :source_id
            """,
            {"source_id": source_id},
        )
        return [Relation(**row._mapping) for row in rows]

    def get_relations_by_target(self, target_id: str) -> list[Relation]:
        rows = self._fetch_all(
            """
            SELECT id, relation_type, source_id, target_id, source_type, target_type,
                   source_module_id, target_module_id, summary
            FROM relations WHERE target_id = :target_id
            """,
            {"target_id": target_id},
        )
        return [Relation(**row._mapping) for row in rows]

    def get_relation_by_id(self, relation_id: str) -> Relation | None:
        row = self._fetch_one(
            """
            SELECT id, relation_type, source_id, target_id, source_type, target_type,
                   source_module_id, target_module_id, summary
            FROM relations WHERE id = :id
            """,
            {"id": relation_id},
        )
        if not row:
            return None
        return Relation(**row._mapping)

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
            SELECT id, name, path, module_id, summary, language, start_line, end_line
            FROM files WHERE module_id = :module_id
            ORDER BY path ASC
            """,
            {"module_id": module_id},
        )
        return [File(**row._mapping) for row in rows]

    def list_modules(self, repo_id: str) -> list[Module]:
        rows = self._fetch_all(
            """
            SELECT id, name, path, summary, metadata
            FROM modules WHERE repo_id = :repo_id
            ORDER BY path ASC
            """,
            {"repo_id": repo_id},
        )

        modules: list[Module] = []
        for row in rows:
            metadata = row.metadata or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            modules.append(
                Module(
                    id=row.id,
                    name=row.name,
                    path=row.path,
                    summary=row.summary,
                    metadata=metadata,
                )
            )
        return modules

    def list_files(self, repo_id: str) -> list[File]:
        rows = self._fetch_all(
            """
            SELECT id, name, path, module_id, summary, language, start_line, end_line
            FROM files WHERE repo_id = :repo_id
            ORDER BY path ASC
            """,
            {"repo_id": repo_id},
        )
        return [File(**row._mapping) for row in rows]

    def list_symbols_by_file(self, file_id: str) -> list[Symbol]:
        rows = self._fetch_all(
            """
            SELECT id, name, qualified_name, type, signature, file_id, module_id,
                   summary, start_line, end_line, visibility, doc
            FROM symbols WHERE file_id = :file_id
            ORDER BY start_line ASC, qualified_name ASC
            """,
            {"file_id": file_id},
        )
        return [Symbol(**row._mapping) for row in rows]

    def list_symbols_by_module(self, module_id: str) -> list[Symbol]:
        rows = self._fetch_all(
            """
            SELECT id, name, qualified_name, type, signature, file_id, module_id,
                   summary, start_line, end_line, visibility, doc
            FROM symbols WHERE module_id = :module_id
            ORDER BY qualified_name ASC
            """,
            {"module_id": module_id},
        )
        return [Symbol(**row._mapping) for row in rows]

    def list_relations(self, repo_id: str) -> list[Relation]:
        rows = self._fetch_all(
            """
            SELECT id, relation_type, source_id, target_id, source_type, target_type,
                   source_module_id, target_module_id, summary
            FROM relations WHERE repo_id = :repo_id
            ORDER BY id ASC
            """,
            {"repo_id": repo_id},
        )
        return [Relation(**row._mapping) for row in rows]

    def find_modules_by_name(self, name: str, limit: int = 10) -> list[Module]:
        normalized = name.strip().lower()
        if not normalized:
            return []

        rows = self._fetch_all(
            """
            SELECT id, name, path, summary, metadata
            FROM modules
            WHERE lower(name) = :name
               OR lower(path) = :name
               OR lower(name) LIKE :partial
               OR lower(path) LIKE :partial
            ORDER BY
                CASE
                    WHEN lower(name) = :name THEN 0
                    WHEN lower(path) = :name THEN 1
                    ELSE 2
                END,
                length(path) ASC
            LIMIT :limit
            """,
            {"name": normalized, "partial": f"%{normalized}%", "limit": limit},
        )

        modules: list[Module] = []
        for row in rows:
            metadata = row.metadata or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            modules.append(
                Module(
                    id=row.id,
                    name=row.name,
                    path=row.path,
                    summary=row.summary,
                    metadata=metadata,
                )
            )
        return modules

    def find_files_by_name(self, name: str, limit: int = 10) -> list[File]:
        normalized = name.strip().lower()
        if not normalized:
            return []

        rows = self._fetch_all(
            """
            SELECT id, name, path, module_id, summary, language, start_line, end_line
            FROM files
            WHERE lower(name) = :name
               OR lower(path) = :name
               OR lower(name) LIKE :partial
               OR lower(path) LIKE :partial
            ORDER BY
                CASE
                    WHEN lower(name) = :name THEN 0
                    WHEN lower(path) = :name THEN 1
                    ELSE 2
                END,
                length(path) ASC
            LIMIT :limit
            """,
            {"name": normalized, "partial": f"%{normalized}%", "limit": limit},
        )
        return [File(**row._mapping) for row in rows]

    def find_symbols_by_name(self, name: str, limit: int = 10) -> list[Symbol]:
        normalized = name.strip().lower()
        if not normalized:
            return []

        rows = self._fetch_all(
            """
            SELECT id, name, qualified_name, type, signature, file_id, module_id,
                   summary, start_line, end_line, visibility, doc
            FROM symbols
            WHERE lower(name) = :name
               OR lower(qualified_name) = :name
               OR lower(name) LIKE :partial
               OR lower(qualified_name) LIKE :partial
            ORDER BY
                CASE
                    WHEN lower(qualified_name) = :name THEN 0
                    WHEN lower(name) = :name THEN 1
                    ELSE 2
                END,
                length(qualified_name) ASC
            LIMIT :limit
            """,
            {"name": normalized, "partial": f"%{normalized}%", "limit": limit},
        )
        return [Symbol(**row._mapping) for row in rows]

    def get_summary(self, object_type: str, object_id: str) -> str | None:
        table_name = self._resolve_summary_table(object_type)
        row = self._fetch_one(f"SELECT summary FROM {table_name} WHERE id = :id", {"id": object_id})
        return row.summary if row else None

    def update_summary(self, object_type: str, object_id: str, summary: str) -> None:
        table_name = self._resolve_summary_table(object_type)
        with self.engine.begin() as connection:
            connection.execute(
                text(f"UPDATE {table_name} SET summary = :summary WHERE id = :id"),
                {"id": object_id, "summary": summary},
            )
        self.clear_cache()

    def get_repo_path(self, repo_id: str) -> str | None:
        row = self._fetch_one("SELECT repo_path FROM repos WHERE repo_id = :repo_id", {"repo_id": repo_id})
        return row.repo_path if row else None

    def clear_cache(self) -> None:
        """Clear cached graph object lookups."""

        self._object_cache.clear()

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
                summary TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                module_id TEXT NOT NULL,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
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
                summary TEXT NOT NULL DEFAULT '',
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
                target_module_id TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT ''
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

    def _load_vector_schema_statements(self) -> str:
        if self.engine.dialect.name == "sqlite":
            return """
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id TEXT NOT NULL,
                object_id TEXT NOT NULL,
                object_type TEXT NOT NULL,
                embedding TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(repo_id, object_id)
            );
            CREATE INDEX IF NOT EXISTS embeddings_repo_type_idx ON embeddings(repo_id, object_type);
            """
        schema_path = Path(__file__).with_name("schema_vector.sql")
        return schema_path.read_text(encoding="utf-8")

    def _module_upsert_sql(self) -> str:
        if self.engine.dialect.name == "sqlite":
            return """
                INSERT INTO modules (id, repo_id, name, path, summary, metadata)
                VALUES (:id, :repo_id, :name, :path, :summary, :metadata)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    path = EXCLUDED.path,
                    summary = EXCLUDED.summary,
                    metadata = EXCLUDED.metadata
            """
        return """
            INSERT INTO modules (id, repo_id, name, path, summary, metadata)
            VALUES (:id, :repo_id, :name, :path, :summary, CAST(:metadata AS JSONB))
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                path = EXCLUDED.path,
                summary = EXCLUDED.summary,
                metadata = EXCLUDED.metadata
        """

    def _ensure_summary_columns(self, connection) -> None:
        for table_name in ("modules", "files", "symbols", "relations"):
            columns = self._list_columns(connection, table_name)
            if "summary" not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN summary TEXT NOT NULL DEFAULT ''")
                )

    def _list_columns(self, connection, table_name: str) -> set[str]:
        if self.engine.dialect.name == "sqlite":
            rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            return {row[1] for row in rows}

        rows = connection.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).fetchall()
        return {row[0] for row in rows}

    @staticmethod
    def _resolve_summary_table(object_type: str) -> str:
        table_map = {
            "module": "modules",
            "file": "files",
            "symbol": "symbols",
            "relation": "relations",
        }
        try:
            return table_map[object_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported summary object type: {object_type}") from exc
