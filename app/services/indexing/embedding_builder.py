"""Embedding generation for graph summaries."""

from __future__ import annotations

import math
from time import perf_counter
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.models.graph_objects import GraphCode
from app.models.vector_models import Embedding

logger = get_logger(__name__)

_SUPPORTED_PROVIDERS = {"sentence-transformer", "sentence-transformers", "openai"}


class EmbeddingBuilder:
    """Build embeddings for graph object summaries."""

    def __init__(
        self,
        provider: str | None = None,
        model_name: str | None = None,
        batch_size: int | None = None,
        dimension: int | None = None,
        sentence_transformer_model: Any | None = None,
        openai_client: Any | None = None,
    ) -> None:
        self.provider = (provider or settings.EMBEDDING_PROVIDER).strip().lower()
        if self.provider not in _SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported embedding provider: {self.provider}")

        default_model = settings.EMBEDDING_MODEL
        if self.provider == "openai":
            default_model = settings.EMBEDDING_OPENAI_MODEL

        self.model_name = model_name or default_model
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self.dimension = dimension or settings.VECTOR_DIMENSION
        self._sentence_transformer_model = sentence_transformer_model
        self._openai_client = openai_client

    def encode_summary(self, summary: str) -> list[float]:
        """Encode a single summary into a normalized vector."""

        vectors = self.encode_summaries([summary])
        if not vectors:
            raise ValueError("Unable to encode summary")
        return vectors[0]

    def encode_summaries(self, summaries: list[str]) -> list[list[float]]:
        """Encode summaries in batches."""

        if not summaries:
            return []

        vectors: list[list[float]] = []
        for batch in _chunked(summaries, self.batch_size):
            if self.provider in {"sentence-transformer", "sentence-transformers"}:
                raw_vectors = self._encode_sentence_transformer_batch(batch)
            else:
                raw_vectors = self._encode_openai_batch(batch)
            vectors.extend(self._normalize_vector(vector) for vector in raw_vectors)
        return vectors

    def build_embeddings(self, graphcode: GraphCode) -> list[Embedding]:
        """Build embeddings for all graph objects with summaries."""

        candidates = self._collect_embedding_candidates(graphcode)
        if not candidates:
            return []

        repo_id = graphcode.repo_meta.repo_id
        embeddings: list[Embedding] = []
        start = perf_counter()
        logger.info(
            "embedding_generation_started",
            extra={
                "context": {
                    "repo_id": repo_id,
                    "provider": self.provider,
                    "model_name": self.model_name,
                    "objects": len(candidates),
                    "batch_size": self.batch_size,
                }
            },
        )

        for batch in _chunked(candidates, self.batch_size):
            try:
                batch_vectors = self.encode_summaries([summary for _, _, summary in batch])
                embeddings.extend(
                    Embedding(
                        repo_id=repo_id,
                        object_id=object_id,
                        object_type=object_type,
                        embedding=vector,
                    )
                    for (object_id, object_type, _), vector in zip(batch, batch_vectors, strict=True)
                )
            except Exception as exc:
                logger.warning(
                    "embedding_batch_failed",
                    extra={
                        "context": {
                            "repo_id": repo_id,
                            "provider": self.provider,
                            "batch_size": len(batch),
                            "error": str(exc),
                        }
                    },
                )
                self._encode_batch_individually(
                    repo_id=repo_id,
                    batch=batch,
                    embeddings=embeddings,
                )

        duration_ms = round((perf_counter() - start) * 1000, 3)
        logger.info(
            "embedding_generation_completed",
            extra={
                "context": {
                    "repo_id": repo_id,
                    "provider": self.provider,
                    "generated_embeddings": len(embeddings),
                    "requested_embeddings": len(candidates),
                    "duration_ms": duration_ms,
                }
            },
        )
        return embeddings

    def _encode_batch_individually(
        self,
        *,
        repo_id: str,
        batch: list[tuple[str, str, str]],
        embeddings: list[Embedding],
    ) -> None:
        for object_id, object_type, summary in batch:
            try:
                vector = self.encode_summary(summary)
            except Exception as exc:
                logger.warning(
                    "embedding_object_skipped",
                    extra={
                        "context": {
                            "repo_id": repo_id,
                            "object_id": object_id,
                            "object_type": object_type,
                            "error": str(exc),
                        }
                    },
                )
                continue

            embeddings.append(
                Embedding(
                    repo_id=repo_id,
                    object_id=object_id,
                    object_type=object_type,
                    embedding=vector,
                )
            )

    def _encode_sentence_transformer_batch(self, summaries: list[str]) -> list[list[float]]:
        model = self._get_sentence_transformer_model()
        raw_vectors = model.encode(
            summaries,
            batch_size=self.batch_size,
            convert_to_numpy=False,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return [_coerce_vector(vector) for vector in raw_vectors]

    def _encode_openai_batch(self, summaries: list[str]) -> list[list[float]]:
        client = self._get_openai_client()
        response = client.embeddings.create(model=self.model_name, input=summaries)
        return [_coerce_vector(item.embedding) for item in response.data]

    def _get_sentence_transformer_model(self) -> Any:
        if self._sentence_transformer_model is None:
            from sentence_transformers import SentenceTransformer

            self._sentence_transformer_model = SentenceTransformer(self.model_name)
        return self._sentence_transformer_model

    def _get_openai_client(self) -> Any:
        if self._openai_client is None:
            from openai import OpenAI

            self._openai_client = OpenAI(
                api_key=settings.EMBEDDING_OPENAI_API_KEY or settings.LLM_API_KEY,
                base_url=settings.EMBEDDING_OPENAI_BASE_URL or settings.LLM_API_BASE,
            )
        return self._openai_client

    def _collect_embedding_candidates(self, graphcode: GraphCode) -> list[tuple[str, str, str]]:
        candidates: list[tuple[str, str, str]] = []
        for object_type, objects in (
            ("module", graphcode.modules),
            ("file", graphcode.files),
            ("symbol", graphcode.symbols),
            ("relation", graphcode.relations),
        ):
            for item in objects:
                summary = item.summary.strip()
                if not summary:
                    logger.warning(
                        "embedding_summary_missing",
                        extra={
                            "context": {
                                "repo_id": graphcode.repo_meta.repo_id,
                                "object_id": item.id,
                                "object_type": object_type,
                            }
                        },
                    )
                    continue
                candidates.append((item.id, object_type, summary))
        return candidates

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        if self.dimension and len(vector) != self.dimension:
            logger.warning(
                "embedding_dimension_mismatch",
                extra={
                    "context": {
                        "provider": self.provider,
                        "model_name": self.model_name,
                        "expected_dimension": self.dimension,
                        "actual_dimension": len(vector),
                    }
                },
            )

        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0:
            return vector
        return [component / norm for component in vector]


def _chunked(items: list[Any], chunk_size: int) -> list[list[Any]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _coerce_vector(vector: Any) -> list[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(component) for component in vector]
