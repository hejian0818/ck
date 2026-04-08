"""Structured retrieval around an anchor."""

from __future__ import annotations

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Symbol
from app.models.qa_models import RetrievalResult
from app.storage.repositories import GraphRepository


class Retriever:
    """Retrieve local graph context for QA."""

    def __init__(self, repository: GraphRepository) -> None:
        self.repository = repository

    def retrieve(self, anchor: Anchor, question: str) -> RetrievalResult:
        _ = question
        if anchor.level == "none":
            return RetrievalResult(anchor=anchor)

        current_object = self._get_current_object(anchor)
        related_objects: list[Module | File | Symbol] = []
        relations = []

        if anchor.level == "symbol" and anchor.symbol_id:
            symbol = self.repository.get_symbol_by_id(anchor.symbol_id)
            if symbol:
                file_obj = self.repository.get_file_by_id(symbol.file_id)
                module = self.repository.get_module_by_id(symbol.module_id)
                related_objects.extend(item for item in [file_obj, module] if item)
                relations.extend(self.repository.get_relations_by_source(symbol.id))
                relations.extend(self.repository.get_relations_by_target(symbol.id))
                related_objects.extend(self._resolve_related_symbols(relations, exclude={symbol.id}))

        elif anchor.level == "file" and anchor.file_id:
            file_obj = self.repository.get_file_by_id(anchor.file_id)
            if file_obj:
                module = self.repository.get_module_by_id(file_obj.module_id)
                related_objects.extend(item for item in [module] if item)
                related_objects.extend(self.repository.list_symbols_by_file(file_obj.id))

        elif anchor.level == "module" and anchor.module_id:
            module = self.repository.get_module_by_id(anchor.module_id)
            if module:
                related_objects.extend(self.repository.list_files_by_module(module.id))

        deduped_objects = self._dedupe_objects(related_objects)
        deduped_relations = {relation.id: relation for relation in relations}
        object_scores = self._score_objects(
            current_object=current_object,
            related_objects=list(deduped_objects.values()),
        )
        return RetrievalResult(
            anchor=anchor,
            current_object=current_object,
            related_objects=list(deduped_objects.values()),
            relations=list(deduped_relations.values()),
            object_scores=object_scores,
        )

    def expand_retrieval(self, retrieval_result: RetrievalResult, max_depth: int = 2) -> RetrievalResult:
        """Expand retrieval by following nearby graph edges and containers."""

        if retrieval_result.anchor.level == "none":
            return retrieval_result

        related_objects = {object_.id: object_ for object_ in retrieval_result.related_objects}
        if retrieval_result.current_object is not None:
            related_objects[retrieval_result.current_object.id] = retrieval_result.current_object
        relations = {relation.id: relation for relation in retrieval_result.relations}

        frontier = [object_ for object_ in related_objects.values() if isinstance(object_, Symbol)]
        seen_symbols = {symbol.id for symbol in frontier}
        depth = 1
        while frontier and depth < max_depth:
            next_frontier: list[Symbol] = []
            for symbol in frontier:
                symbol_relations = self.repository.get_relations_by_source(symbol.id)
                symbol_relations.extend(self.repository.get_relations_by_target(symbol.id))
                for relation in symbol_relations:
                    relations[relation.id] = relation
                    for related_symbol in self._resolve_related_symbols([relation], exclude=seen_symbols):
                        related_objects[related_symbol.id] = related_symbol
                        seen_symbols.add(related_symbol.id)
                        next_frontier.append(related_symbol)
                        self._attach_symbol_containers(related_objects, related_symbol)
            frontier = next_frontier
            depth += 1

        expanded_related_objects = list(related_objects.values())
        current_object = retrieval_result.current_object
        if current_object is not None:
            expanded_related_objects = [
                object_ for object_ in expanded_related_objects if object_.id != current_object.id
            ]

        return RetrievalResult(
            anchor=retrieval_result.anchor,
            current_object=current_object,
            related_objects=list(self._dedupe_objects(expanded_related_objects).values()),
            relations=list(relations.values()),
            object_scores=self._score_objects(
                current_object=current_object,
                related_objects=expanded_related_objects,
            ),
        )

    def _get_current_object(self, anchor: Anchor) -> Module | File | Symbol | None:
        if anchor.level == "symbol" and anchor.symbol_id:
            return self.repository.get_symbol_by_id(anchor.symbol_id)
        if anchor.level == "file" and anchor.file_id:
            return self.repository.get_file_by_id(anchor.file_id)
        if anchor.level == "module" and anchor.module_id:
            return self.repository.get_module_by_id(anchor.module_id)
        return None

    def _resolve_related_symbols(self, relations: list, exclude: set[str]) -> list[Symbol]:
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
    def _dedupe_objects(objects: list[Module | File | Symbol]) -> dict[str, Module | File | Symbol]:
        return {object_.id: object_ for object_ in objects}

    def _attach_symbol_containers(self, related_objects: dict[str, Module | File | Symbol], symbol: Symbol) -> None:
        file_obj = self.repository.get_file_by_id(symbol.file_id)
        module = self.repository.get_module_by_id(symbol.module_id)
        for object_ in (file_obj, module):
            if object_ is not None:
                related_objects[object_.id] = object_

    @staticmethod
    def _score_objects(
        current_object: Module | File | Symbol | None,
        related_objects: list[Module | File | Symbol],
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        if current_object is not None:
            scores[current_object.id] = 1.0

        for object_ in related_objects:
            if isinstance(object_, Symbol):
                scores[object_.id] = max(scores.get(object_.id, 0.0), 0.85)
            elif isinstance(object_, File):
                scores[object_.id] = max(scores.get(object_.id, 0.0), 0.7)
            else:
                scores[object_.id] = max(scores.get(object_.id, 0.0), 0.6)
        return scores
