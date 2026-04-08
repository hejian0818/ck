"""pgvector persistence and similarity search."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.models.vector_models import Embedding, SearchResult

_METRIC_OPERATORS = {
    "cosine": "<=>",
    "l2": "<->",
    "inner_product": "<#>",
}


class VectorStore:
    """CRUD and search access for embedding storage."""

    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url)

    def save_embeddings(self, embeddings: list[Embedding]) -> None:
        """Persist embeddings using bulk upserts."""

        if not embeddings:
            return

        statement = text(
            """
            INSERT INTO embeddings (repo_id, object_id, object_type, embedding)
            VALUES (:repo_id, :object_id, :object_type, CAST(:embedding AS vector))
            ON CONFLICT (repo_id, object_id) DO UPDATE SET
                object_type = EXCLUDED.object_type,
                embedding = EXCLUDED.embedding
            """
        )
        params = [
            {
                "repo_id": embedding.repo_id,
                "object_id": embedding.object_id,
                "object_type": embedding.object_type,
                "embedding": _format_vector(embedding.embedding),
            }
            for embedding in embeddings
        ]
        with self.engine.begin() as connection:
            connection.execute(statement, params)

    def get_embedding(self, repo_id: str, object_id: str) -> list[float] | None:
        """Fetch a stored embedding by object id."""

        statement = text(
            """
            SELECT embedding
            FROM embeddings
            WHERE repo_id = :repo_id AND object_id = :object_id
            """
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement, {"repo_id": repo_id, "object_id": object_id}).fetchone()
        if not row:
            return None
        return _parse_vector(row[0])

    def delete_embeddings(self, repo_id: str, object_ids: list[str] | None = None) -> None:
        """Delete embeddings for a repository or a subset of object ids."""

        if object_ids:
            statement = text(
                """
                DELETE FROM embeddings
                WHERE repo_id = :repo_id AND object_id IN :object_ids
                """
            ).bindparams(bindparam("object_ids", expanding=True))
            params: dict[str, Any] = {"repo_id": repo_id, "object_ids": object_ids}
        else:
            statement = text("DELETE FROM embeddings WHERE repo_id = :repo_id")
            params = {"repo_id": repo_id}

        with self.engine.begin() as connection:
            connection.execute(statement, params)

    def search_similar(
        self,
        repo_id: str,
        query_vector: list[float],
        object_type: str | None = None,
        top_k: int = 10,
        min_similarity: float = 0.5,
        metric: str = "cosine",
    ) -> list[SearchResult]:
        """Run a similarity search for a query vector."""

        operator = _METRIC_OPERATORS.get(metric)
        if operator is None:
            raise ValueError(f"Unsupported distance metric: {metric}")

        formatted_vector = _format_vector(query_vector)
        distance_expr = f"embedding {operator} CAST(:query_vector AS vector)"
        similarity_expr = _similarity_expression(distance_expr=distance_expr, metric=metric)

        filters = ["repo_id = :repo_id", f"{similarity_expr} >= :min_similarity"]
        params: dict[str, Any] = {
            "repo_id": repo_id,
            "query_vector": formatted_vector,
            "min_similarity": min_similarity,
            "top_k": top_k,
        }
        if object_type is not None:
            filters.append("object_type = :object_type")
            params["object_type"] = object_type

        statement = text(
            f"""
            SELECT object_id, object_type, {similarity_expr} AS similarity
            FROM embeddings
            WHERE {' AND '.join(filters)}
            ORDER BY {distance_expr}
            LIMIT :top_k
            """
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement, params).fetchall()
        return [SearchResult(**row._mapping) for row in rows]

    def search_modules(
        self,
        repo_id: str,
        query_vector: list[float],
        top_k: int | None = None,
        min_similarity: float = 0.5,
        metric: str = "cosine",
    ) -> list[SearchResult]:
        return self.search_similar(
            repo_id=repo_id,
            query_vector=query_vector,
            object_type="module",
            top_k=top_k or settings.VECTOR_TOP_K_MODULES,
            min_similarity=min_similarity,
            metric=metric,
        )

    def search_files(
        self,
        repo_id: str,
        query_vector: list[float],
        top_k: int | None = None,
        min_similarity: float = 0.5,
        metric: str = "cosine",
    ) -> list[SearchResult]:
        return self.search_similar(
            repo_id=repo_id,
            query_vector=query_vector,
            object_type="file",
            top_k=top_k or settings.VECTOR_TOP_K_FILES,
            min_similarity=min_similarity,
            metric=metric,
        )

    def search_symbols(
        self,
        repo_id: str,
        query_vector: list[float],
        top_k: int | None = None,
        min_similarity: float = 0.5,
        metric: str = "cosine",
    ) -> list[SearchResult]:
        return self.search_similar(
            repo_id=repo_id,
            query_vector=query_vector,
            object_type="symbol",
            top_k=top_k or settings.VECTOR_TOP_K_SYMBOLS,
            min_similarity=min_similarity,
            metric=metric,
        )

    def search_relations(
        self,
        repo_id: str,
        query_vector: list[float],
        top_k: int | None = None,
        min_similarity: float = 0.5,
        metric: str = "cosine",
    ) -> list[SearchResult]:
        return self.search_similar(
            repo_id=repo_id,
            query_vector=query_vector,
            object_type="relation",
            top_k=top_k or settings.VECTOR_TOP_K_RELATIONS,
            min_similarity=min_similarity,
            metric=metric,
        )


def _similarity_expression(*, distance_expr: str, metric: str) -> str:
    if metric == "cosine":
        return f"1 - ({distance_expr})"
    if metric == "l2":
        return f"1 / (1 + ({distance_expr}))"
    if metric == "inner_product":
        return f"-({distance_expr})"
    raise ValueError(f"Unsupported distance metric: {metric}")


def _format_vector(vector: list[float]) -> str:
    return json.dumps([float(component) for component in vector])


def _parse_vector(raw_value: Any) -> list[float]:
    if isinstance(raw_value, str):
        return [float(component) for component in raw_value.strip("[]").split(",") if component]
    if hasattr(raw_value, "tolist"):
        raw_value = raw_value.tolist()
    return [float(component) for component in raw_value]
