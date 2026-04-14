"""Enhanced retrieval with structured recall, vector recall, ranking, and expansion."""

from __future__ import annotations

from app.core.logging import get_logger
from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Relation, Symbol
from app.models.qa_models import RetrievalResult
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.services.memory.memory_manager import AnchorMemory
from app.services.retrieval.graph_expander import GraphExpander
from app.services.retrieval.ranker import Ranker
from app.storage.repositories import GraphRepository
from app.storage.vector_store import VectorStore

GraphObject = Module | File | Symbol
logger = get_logger(__name__)


class Retriever:
    """Retrieve QA context by fusing graph and semantic evidence."""

    def __init__(
        self,
        repository: GraphRepository,
        embedding_builder: EmbeddingBuilder | None = None,
        vector_store: VectorStore | None = None,
        ranker: Ranker | None = None,
        graph_expander: GraphExpander | None = None,
    ) -> None:
        self.repository = repository
        self.embedding_builder = embedding_builder
        self.vector_store = vector_store
        self.ranker = ranker or Ranker()
        self.graph_expander = graph_expander or GraphExpander(repository)

    def retrieve(
        self,
        anchor: Anchor,
        question: str,
        repo_id: str | None = None,
        memory: AnchorMemory | None = None,
    ) -> RetrievalResult:
        current_object, structured_objects, relations, graph_distances = self._collect_structured(anchor)
        vector_objects, vector_relations, vector_scores = self._collect_vector_hits(
            anchor=anchor,
            question=question,
            repo_id=repo_id,
        )

        related_objects = self._dedupe_objects(structured_objects + vector_objects)
        if current_object is not None:
            related_objects.pop(current_object.id, None)

        all_relations = {relation.id: relation for relation in relations}
        all_relations.update({relation.id: relation for relation in vector_relations})

        ranked_objects, object_scores = self.ranker.rank(
            anchor=anchor,
            question=question,
            current_object=current_object,
            candidates=list(related_objects.values()),
            vector_scores=vector_scores,
            graph_distances=graph_distances,
            memory_object_ids=memory.retrieval_memory.recent_object_ids if memory is not None else [],
        )
        object_scores = self._apply_baseline_scores(
            object_scores=object_scores,
            objects=ranked_objects,
            graph_distances=graph_distances,
        )
        return RetrievalResult(
            anchor=anchor,
            current_object=current_object,
            related_objects=ranked_objects,
            relations=list(all_relations.values()),
            object_scores=object_scores,
        )

    def expand_retrieval(
        self,
        retrieval_result: RetrievalResult,
        question: str,
        memory: AnchorMemory | None = None,
        max_depth: int = 2,
    ) -> RetrievalResult:
        related_objects, relations, expanded_ids, graph_distances = self.graph_expander.expand(
            question=question,
            current_object=retrieval_result.current_object,
            related_objects=retrieval_result.related_objects,
            relations=retrieval_result.relations,
            max_depth=max_depth,
        )
        ranked_objects, object_scores = self.ranker.rank(
            anchor=retrieval_result.anchor,
            question=question,
            current_object=retrieval_result.current_object,
            candidates=related_objects,
            graph_distances=graph_distances,
            memory_object_ids=memory.retrieval_memory.recent_object_ids if memory is not None else [],
        )
        object_scores = self._apply_baseline_scores(
            object_scores=object_scores,
            objects=ranked_objects,
            graph_distances=graph_distances,
        )
        expanded_result = RetrievalResult(
            anchor=retrieval_result.anchor,
            current_object=retrieval_result.current_object,
            related_objects=ranked_objects,
            relations=relations,
            object_scores=object_scores,
        )
        expanded_result.object_scores.update(
            {
                object_id: expanded_result.object_scores.get(object_id, 0.0)
                for object_id in expanded_ids
            }
        )
        return expanded_result

    def _collect_structured(
        self,
        anchor: Anchor,
    ) -> tuple[GraphObject | None, list[GraphObject], list[Relation], dict[str, int]]:
        if anchor.level == "none":
            return None, [], [], {}

        current_object = self._get_current_object(anchor)
        related_objects: list[GraphObject] = []
        relations: list[Relation] = []
        graph_distances: dict[str, int] = {}

        if anchor.level == "symbol" and anchor.symbol_id:
            symbol = self.repository.get_symbol_by_id(anchor.symbol_id)
            if symbol:
                file_obj = self.repository.get_file_by_id(symbol.file_id)
                module = self.repository.get_module_by_id(symbol.module_id)
                related_objects.extend(item for item in [file_obj, module] if item)
                relations.extend(self.repository.get_relations_by_source(symbol.id))
                relations.extend(self.repository.get_relations_by_target(symbol.id))
                related_objects.extend(self._resolve_related_symbols(relations, exclude={symbol.id}))
                graph_distances.update({symbol.id: 0, symbol.file_id: 1, symbol.module_id: 1})

        elif anchor.level == "file" and anchor.file_id:
            file_obj = self.repository.get_file_by_id(anchor.file_id)
            if file_obj:
                module = self.repository.get_module_by_id(file_obj.module_id)
                related_objects.extend(item for item in [module] if item)
                related_objects.extend(self.repository.list_symbols_by_file(file_obj.id))
                graph_distances.update({file_obj.id: 0, file_obj.module_id: 1})
                graph_distances.update({symbol.id: 1 for symbol in self.repository.list_symbols_by_file(file_obj.id)})

        elif anchor.level == "module" and anchor.module_id:
            module = self.repository.get_module_by_id(anchor.module_id)
            if module:
                files = self.repository.list_files_by_module(module.id)
                related_objects.extend(files)
                graph_distances.update({module.id: 0})
                graph_distances.update({file_obj.id: 1 for file_obj in files})

        return current_object, list(self._dedupe_objects(related_objects).values()), relations, graph_distances

    def _collect_vector_hits(
        self,
        *,
        anchor: Anchor,
        question: str,
        repo_id: str | None,
    ) -> tuple[list[GraphObject], list[Relation], dict[str, float]]:
        if repo_id is None or self.embedding_builder is None or self.vector_store is None:
            return [], [], {}

        try:
            query_vector = self.embedding_builder.encode_summary(question)
            search_results = []
            if anchor.level == "symbol":
                search_results.extend(self.vector_store.search_symbols(repo_id=repo_id, query_vector=query_vector))
                search_results.extend(self.vector_store.search_files(repo_id=repo_id, query_vector=query_vector))
            elif anchor.level == "file":
                search_results.extend(self.vector_store.search_files(repo_id=repo_id, query_vector=query_vector))
                search_results.extend(self.vector_store.search_symbols(repo_id=repo_id, query_vector=query_vector))
            elif anchor.level == "module":
                search_results.extend(self.vector_store.search_modules(repo_id=repo_id, query_vector=query_vector))
                search_results.extend(self.vector_store.search_files(repo_id=repo_id, query_vector=query_vector))
            else:
                search_results.extend(self.vector_store.search_modules(repo_id=repo_id, query_vector=query_vector))
                search_results.extend(self.vector_store.search_files(repo_id=repo_id, query_vector=query_vector))
                search_results.extend(self.vector_store.search_symbols(repo_id=repo_id, query_vector=query_vector))
        except Exception as exc:
            logger.warning(
                "vector_retrieval_failed",
                extra={"context": {"repo_id": repo_id, "anchor_level": anchor.level, "error": str(exc)}},
            )
            return [], [], {}

        objects: list[GraphObject] = []
        relations: list[Relation] = []
        scores: dict[str, float] = {}
        for result in search_results:
            object_ = self._resolve_search_result(result.object_id, result.object_type)
            if object_ is not None:
                objects.append(object_)
                scores[object_.id] = max(scores.get(object_.id, 0.0), result.similarity)
                continue

            if result.object_type == "relation":
                relation = self.repository.get_relation_by_id(result.object_id)
                if relation is not None:
                    relations.append(relation)
        return objects, relations, scores

    def _resolve_search_result(self, object_id: str, object_type: str) -> GraphObject | None:
        if object_type == "symbol":
            return self.repository.get_symbol_by_id(object_id)
        if object_type == "file":
            return self.repository.get_file_by_id(object_id)
        if object_type == "module":
            return self.repository.get_module_by_id(object_id)
        return None

    def _get_current_object(self, anchor: Anchor) -> GraphObject | None:
        if anchor.level == "symbol" and anchor.symbol_id:
            return self.repository.get_symbol_by_id(anchor.symbol_id)
        if anchor.level == "file" and anchor.file_id:
            return self.repository.get_file_by_id(anchor.file_id)
        if anchor.level == "module" and anchor.module_id:
            return self.repository.get_module_by_id(anchor.module_id)
        return None

    def _resolve_related_symbols(self, relations: list[Relation], exclude: set[str]) -> list[Symbol]:
        symbols: list[Symbol] = []
        for relation in relations:
            for symbol_id in (relation.source_id, relation.target_id):
                if symbol_id in exclude:
                    continue
                symbol = self.repository.get_symbol_by_id(symbol_id)
                if symbol:
                    symbols.append(symbol)
        return symbols

    @staticmethod
    def _dedupe_objects(objects: list[GraphObject]) -> dict[str, GraphObject]:
        return {object_.id: object_ for object_ in objects}

    def _apply_baseline_scores(
        self,
        *,
        object_scores: dict[str, float],
        objects: list[GraphObject],
        graph_distances: dict[str, int],
    ) -> dict[str, float]:
        boosted_scores = dict(object_scores)
        for object_ in objects:
            boosted_scores[object_.id] = max(
                boosted_scores.get(object_.id, 0.0),
                self._baseline_structured_score(object_, graph_distances.get(object_.id)),
            )
        return boosted_scores

    @staticmethod
    def _baseline_structured_score(object_: GraphObject, graph_distance: int | None) -> float:
        if graph_distance is None:
            return 0.0

        if isinstance(object_, Symbol):
            return 0.85 if graph_distance <= 1 else 0.65
        if isinstance(object_, File):
            return 0.7 if graph_distance <= 1 else 0.55
        return 0.6 if graph_distance <= 1 else 0.45
