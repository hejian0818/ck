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
        return RetrievalResult(
            anchor=anchor,
            current_object=current_object,
            related_objects=list(deduped_objects.values()),
            relations=list(deduped_relations.values()),
        )

    def _get_current_object(self, anchor: Anchor):
        if anchor.level == "symbol" and anchor.symbol_id:
            return self.repository.get_symbol_by_id(anchor.symbol_id)
        if anchor.level == "file" and anchor.file_id:
            return self.repository.get_file_by_id(anchor.file_id)
        if anchor.level == "module" and anchor.module_id:
            return self.repository.get_module_by_id(anchor.module_id)
        return None

    def _resolve_related_symbols(self, relations, exclude: set[str]) -> list[Symbol]:
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
    def _dedupe_objects(objects):
        return {object_.id: object_ for object_ in objects}
