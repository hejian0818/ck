"""Section-level retrieval for document generation."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.models.anchor import Anchor
from app.models.doc_models import SectionPlan
from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.services.retrieval.graph_expander import GraphExpander
from app.services.retrieval.ranker import Ranker
from app.storage.repositories import GraphRepository
from app.storage.vector_store import VectorStore

GraphObject = Module | File | Symbol
_API_SYMBOL_TYPES = {"route", "controller", "endpoint", "api"}
_CALL_CHAIN_RELATIONS = {"calls", "depends_on"}
logger = get_logger(__name__)


@dataclass(slots=True)
class SectionRetrievalResult:
    """Resolved context bundle for a document section."""

    section: SectionPlan
    objects: list[GraphObject]
    relations: list[Relation]
    object_scores: dict[str, float]


class DocRetriever:
    """Retrieve section-specific graph context for document generation."""

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

    def retrieve(self, repo_id: str, section: SectionPlan) -> SectionRetrievalResult:
        """Retrieve graph objects and relations required by a planned section."""

        objects, relations, graph_distances = self._collect_structured(repo_id=repo_id, section=section)
        vector_objects, vector_relations, vector_scores = self._collect_vector_hits(repo_id=repo_id, section=section)

        object_map = {object_.id: object_ for object_ in objects}
        for object_ in vector_objects:
            object_map[object_.id] = object_

        relation_map = {relation.id: relation for relation in relations}
        for relation in vector_relations:
            relation_map[relation.id] = relation

        ranked_objects, object_scores = self.ranker.rank(
            anchor=Anchor(level="none", source="none", confidence=1.0),
            question=self._build_query(section),
            current_object=None,
            candidates=list(object_map.values()),
            vector_scores=vector_scores,
            graph_distances=graph_distances,
            top_k=settings.DOC_RETRIEVAL_TOP_K,
        )
        return SectionRetrievalResult(
            section=section,
            objects=ranked_objects,
            relations=list(relation_map.values()),
            object_scores=object_scores,
        )

    def _collect_structured(
        self,
        *,
        repo_id: str,
        section: SectionPlan,
    ) -> tuple[list[GraphObject], list[Relation], dict[str, int]]:
        targets = [self._resolve_object(object_id) for object_id in section.target_object_ids]
        target_objects = [object_ for object_ in targets if object_ is not None]

        if section.section_type == "overview":
            return self._collect_overview(repo_id)
        if section.section_type == "architecture":
            return self._collect_architecture(repo_id)
        if section.section_type == "api":
            return self._collect_api(repo_id, target_objects)
        if section.section_type == "dependency":
            return self._collect_dependency(repo_id, target_objects)
        if section.section_type == "data_flow":
            return self._collect_data_flow(target_objects)
        if section.section_type == "summary":
            return self._collect_summary(repo_id)
        return self._collect_module(target_objects)

    def _collect_overview(self, repo_id: str) -> tuple[list[GraphObject], list[Relation], dict[str, int]]:
        modules = self.repository.list_modules(repo_id)
        graph_distances = {module.id: 0 for module in modules}
        return modules, [], graph_distances

    def _collect_architecture(self, repo_id: str) -> tuple[list[GraphObject], list[Relation], dict[str, int]]:
        modules = self.repository.list_modules(repo_id)
        relations = [
            relation
            for relation in self.repository.list_relations(repo_id)
            if relation.source_module_id != relation.target_module_id
        ]
        graph_distances = {module.id: 0 for module in modules}
        return modules, relations, graph_distances

    def _collect_summary(self, repo_id: str) -> tuple[list[GraphObject], list[Relation], dict[str, int]]:
        modules = self.repository.list_modules(repo_id)
        relations = self.repository.list_relations(repo_id)
        graph_distances = {module.id: 0 for module in modules}
        return modules, relations[: settings.DOC_RETRIEVAL_TOP_K], graph_distances

    def _collect_module(
        self,
        target_objects: list[GraphObject],
    ) -> tuple[list[GraphObject], list[Relation], dict[str, int]]:
        objects: list[GraphObject] = []
        relations: list[Relation] = []
        graph_distances: dict[str, int] = {}

        for target in target_objects:
            if isinstance(target, Module):
                objects.append(target)
                graph_distances[target.id] = 0
                files = self.repository.list_files_by_module(target.id)
                objects.extend(files)
                graph_distances.update({file_obj.id: 1 for file_obj in files})
                module_symbols = self.repository.list_symbols_by_module(target.id)
                for symbol in module_symbols[: settings.DOC_MODULE_SYMBOL_LIMIT]:
                    objects.append(symbol)
                    graph_distances[symbol.id] = 2
            elif isinstance(target, File):
                objects.append(target)
                graph_distances[target.id] = 0
                module = self.repository.get_module_by_id(target.module_id)
                if module is not None:
                    objects.append(module)
                    graph_distances[module.id] = 1
                symbols = self.repository.list_symbols_by_file(target.id)
                objects.extend(symbols[: settings.DOC_MODULE_SYMBOL_LIMIT])
                graph_distances.update({symbol.id: 1 for symbol in symbols[: settings.DOC_MODULE_SYMBOL_LIMIT]})

        return self._dedupe_objects(objects), relations, graph_distances

    def _collect_api(
        self,
        repo_id: str,
        target_objects: list[GraphObject],
    ) -> tuple[list[GraphObject], list[Relation], dict[str, int]]:
        symbols = [object_ for object_ in target_objects if isinstance(object_, Symbol)]
        if not symbols:
            symbols = [
                symbol
                for module in self.repository.list_modules(repo_id)
                for symbol in self.repository.list_symbols_by_module(module.id)
                if self._is_api_symbol(symbol)
            ]

        relations: list[Relation] = []
        related_objects: list[GraphObject] = list(symbols)
        graph_distances = {symbol.id: 0 for symbol in symbols}

        for symbol in symbols:
            direct_relations = [
                relation
                for relation in self.repository.get_relations_by_source(symbol.id) + self.repository.get_relations_by_target(symbol.id)
                if relation.relation_type.lower() in _CALL_CHAIN_RELATIONS
            ]
            relations.extend(direct_relations)
            for relation in direct_relations:
                neighbor = self._resolve_object(
                    relation.target_id if relation.source_id == symbol.id else relation.source_id
                )
                if neighbor is not None:
                    related_objects.append(neighbor)
                    graph_distances.setdefault(neighbor.id, 1)

        expanded_objects, expanded_relations, _, expanded_distances = self.graph_expander.expand(
            question=f"{section_title(symbols)} 调用链",
            current_object=symbols[0] if symbols else None,
            related_objects=[object_ for object_ in related_objects if isinstance(object_, Symbol)],
            relations=relations,
            max_depth=2,
        ) if symbols else ([], [], [], {})
        related_objects.extend(expanded_objects)
        relations.extend(expanded_relations)
        graph_distances.update(expanded_distances)
        self._attach_parents(related_objects, graph_distances)
        return self._dedupe_objects(related_objects), self._dedupe_relations(relations), graph_distances

    def _collect_dependency(
        self,
        repo_id: str,
        target_objects: list[GraphObject],
    ) -> tuple[list[GraphObject], list[Relation], dict[str, int]]:
        module_ids = {object_.id for object_ in target_objects if isinstance(object_, Module)}
        relations = [
            relation
            for relation in self.repository.list_relations(repo_id)
            if relation.source_module_id != relation.target_module_id
        ]
        if module_ids:
            relations = [
                relation
                for relation in relations
                if relation.source_module_id in module_ids or relation.target_module_id in module_ids
            ]

        objects: list[GraphObject] = []
        graph_distances: dict[str, int] = {}
        for relation in relations:
            source_module = self.repository.get_module_by_id(relation.source_module_id)
            target_module = self.repository.get_module_by_id(relation.target_module_id)
            for module in (source_module, target_module):
                if module is not None:
                    objects.append(module)
                    graph_distances[module.id] = 0
        return self._dedupe_objects(objects), relations, graph_distances

    def _collect_data_flow(
        self,
        target_objects: list[GraphObject],
    ) -> tuple[list[GraphObject], list[Relation], dict[str, int]]:
        symbols = [object_ for object_ in target_objects if isinstance(object_, Symbol)]
        if not symbols:
            return [], [], {}

        seed = symbols[0]
        related_symbols = symbols[1:] if len(symbols) > 1 else []
        expanded_objects, relations, _, graph_distances = self.graph_expander.expand(
            question="data flow calls depends on",
            current_object=seed,
            related_objects=related_symbols,
            relations=[],
            max_depth=2,
        )
        objects: list[GraphObject] = [seed, *expanded_objects]
        graph_distances[seed.id] = 0
        self._attach_parents(objects, graph_distances)
        return self._dedupe_objects(objects), relations, graph_distances

    def _collect_vector_hits(
        self,
        *,
        repo_id: str,
        section: SectionPlan,
    ) -> tuple[list[GraphObject], list[Relation], dict[str, float]]:
        if self.embedding_builder is None or self.vector_store is None:
            return [], [], {}

        try:
            query_vector = self.embedding_builder.encode_summary(self._build_query(section))
            search_results = []
            if section.section_type == "overview":
                search_results.extend(
                    self.vector_store.search_modules(
                        repo_id=repo_id,
                        query_vector=query_vector,
                        top_k=settings.DOC_VECTOR_TOP_K,
                    )
                )
            elif section.section_type in {"module", "architecture"}:
                search_results.extend(
                    self.vector_store.search_files(
                        repo_id=repo_id,
                        query_vector=query_vector,
                        top_k=settings.DOC_VECTOR_TOP_K,
                    )
                )
                search_results.extend(
                    self.vector_store.search_symbols(
                        repo_id=repo_id,
                        query_vector=query_vector,
                        top_k=settings.DOC_VECTOR_TOP_K,
                    )
                )
            else:
                search_results.extend(
                    self.vector_store.search_symbols(
                        repo_id=repo_id,
                        query_vector=query_vector,
                        top_k=settings.DOC_VECTOR_TOP_K,
                    )
                )
                search_results.extend(
                    self.vector_store.search_relations(
                        repo_id=repo_id,
                        query_vector=query_vector,
                        top_k=settings.DOC_VECTOR_TOP_K,
                    )
                )
        except Exception as exc:
            logger.warning(
                "doc_vector_retrieval_failed",
                extra={"context": {"repo_id": repo_id, "section_id": section.section_id, "error": str(exc)}},
            )
            return [], [], {}

        objects: list[GraphObject] = []
        relations: list[Relation] = []
        scores: dict[str, float] = {}
        for result in search_results:
            object_ = self._resolve_object(result.object_id)
            if object_ is not None:
                objects.append(object_)
                scores[object_.id] = max(scores.get(object_.id, 0.0), result.similarity)
                continue

            relation = self.repository.get_relation_by_id(result.object_id)
            if relation is not None:
                relations.append(relation)
        return self._dedupe_objects(objects), self._dedupe_relations(relations), scores

    def _resolve_object(self, object_id: str) -> GraphObject | None:
        return (
            self.repository.get_module_by_id(object_id)
            or self.repository.get_file_by_id(object_id)
            or self.repository.get_symbol_by_id(object_id)
        )

    @staticmethod
    def _build_query(section: SectionPlan) -> str:
        return f"{section.title}\n{section.description}".strip()

    @staticmethod
    def _dedupe_objects(objects: list[GraphObject]) -> list[GraphObject]:
        return list({object_.id: object_ for object_ in objects}.values())

    @staticmethod
    def _dedupe_relations(relations: list[Relation]) -> list[Relation]:
        return list({relation.id: relation for relation in relations}.values())

    @classmethod
    def _is_api_symbol(cls, symbol: Symbol) -> bool:
        normalized_type = symbol.type.lower()
        normalized_name = symbol.qualified_name.lower()
        return normalized_type in _API_SYMBOL_TYPES or any(
            hint in normalized_name for hint in ("route", "controller", "endpoint", "api")
        )

    def _attach_parents(self, objects: list[GraphObject], graph_distances: dict[str, int]) -> None:
        additional: list[GraphObject] = []
        for object_ in list(objects):
            if not isinstance(object_, Symbol):
                continue
            file_obj = self.repository.get_file_by_id(object_.file_id)
            module = self.repository.get_module_by_id(object_.module_id)
            distance = graph_distances.get(object_.id, 1)
            if file_obj is not None:
                additional.append(file_obj)
                graph_distances[file_obj.id] = min(graph_distances.get(file_obj.id, distance + 1), distance + 1)
            if module is not None:
                additional.append(module)
                graph_distances[module.id] = min(graph_distances.get(module.id, distance + 1), distance + 1)
        objects.extend(additional)


def section_title(symbols: list[Symbol]) -> str:
    """Build a stable API section query title for graph expansion."""

    if not symbols:
        return "api"
    if len(symbols) == 1:
        return symbols[0].qualified_name
    return ", ".join(symbol.qualified_name for symbol in symbols[:3])
