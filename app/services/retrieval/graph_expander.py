"""Graph-based relation expansion for retrieval."""

from __future__ import annotations

import re

from app.core.thresholds import EXPANSION_GAIN
from app.models.graph_objects import File, Module, Relation, Symbol
from app.storage.repositories import GraphRepository

_CALLER_HINTS = ("谁调用", "谁在调用", "caller", "callers", "调用方")
_CALLEE_HINTS = ("调用了谁", "调用哪些", "callee", "callees", "依次调用")
_DEPENDENCY_HINTS = ("依赖", "depends on", "depend on")
_REVERSE_DEPENDENCY_HINTS = ("谁依赖", "被谁依赖", "reverse depends", "dependents")
_REFERENCE_HINTS = ("引用", "references", "reference", "谁用到")


class GraphExpander:
    """Expand retrieval candidates through graph relationships."""

    def __init__(self, repository: GraphRepository) -> None:
        self.repository = repository

    def expand(
        self,
        *,
        question: str,
        current_object: Module | File | Symbol | None,
        related_objects: list[Module | File | Symbol],
        relations: list[Relation],
        max_depth: int = 2,
    ) -> tuple[list[Module | File | Symbol], list[Relation], list[str], dict[str, int]]:
        related_map = {object_.id: object_ for object_ in related_objects}
        relation_map = {relation.id: relation for relation in relations}
        graph_distances = {object_.id: 1 for object_ in related_objects}
        expanded_object_ids: list[str] = []

        frontier = self._seed_symbols(current_object, related_objects)
        seen_symbols = {symbol.id for symbol in frontier}
        allowed_modes = self._allowed_expansions(question)
        depth = 1

        while frontier and depth <= max_depth:
            next_frontier: list[Symbol] = []
            new_objects: list[Module | File | Symbol] = []
            for symbol in frontier:
                for relation in self._load_relations(symbol, allowed_modes):
                    relation_map[relation.id] = relation
                    for related_symbol in self._resolve_symbols(symbol, relation, allowed_modes):
                        if related_symbol.id in seen_symbols:
                            continue
                        seen_symbols.add(related_symbol.id)
                        next_frontier.append(related_symbol)
                        new_objects.append(related_symbol)
                        graph_distances[related_symbol.id] = depth

            if depth == 2 and self._estimate_expansion_gain(question, new_objects) < EXPANSION_GAIN:
                break

            for object_ in new_objects:
                related_map[object_.id] = object_
                expanded_object_ids.append(object_.id)
                self._attach_symbol_containers(related_map, graph_distances, object_, depth)

            frontier = next_frontier
            depth += 1

        if current_object is not None:
            related_map.pop(current_object.id, None)

        return (
            list(related_map.values()),
            list(relation_map.values()),
            list(dict.fromkeys(expanded_object_ids)),
            graph_distances,
        )

    def _seed_symbols(
        self,
        current_object: Module | File | Symbol | None,
        related_objects: list[Module | File | Symbol],
    ) -> list[Symbol]:
        seeds: list[Symbol] = []
        if isinstance(current_object, Symbol):
            seeds.append(current_object)
        seeds.extend(object_ for object_ in related_objects if isinstance(object_, Symbol))
        return list({symbol.id: symbol for symbol in seeds}.values())

    @staticmethod
    def _allowed_expansions(question: str) -> set[str]:
        normalized = question.lower()
        modes: set[str] = set()
        if any(hint in normalized for hint in _CALLER_HINTS):
            modes.add("callers")
        if any(hint in normalized for hint in _CALLEE_HINTS):
            modes.add("callees")
        if any(hint in normalized for hint in _DEPENDENCY_HINTS):
            modes.add("depends_on")
        if any(hint in normalized for hint in _REVERSE_DEPENDENCY_HINTS):
            modes.add("reverse_depends_on")
        if any(hint in normalized for hint in _REFERENCE_HINTS):
            modes.add("references")
        if not modes:
            modes.update({"callers", "callees", "depends_on", "reverse_depends_on", "references"})
        return modes

    def _load_relations(self, symbol: Symbol, allowed_modes: set[str]) -> list[Relation]:
        relations = self.repository.get_relations_by_source(symbol.id)
        relations.extend(self.repository.get_relations_by_target(symbol.id))
        return [
            relation
            for relation in relations
            if self._relation_matches_mode(symbol, relation, allowed_modes)
        ]

    @staticmethod
    def _relation_matches_mode(symbol: Symbol, relation: Relation, allowed_modes: set[str]) -> bool:
        relation_type = relation.relation_type.lower()
        is_source = relation.source_id == symbol.id
        is_target = relation.target_id == symbol.id

        if relation_type == "calls":
            return ("callees" in allowed_modes and is_source) or ("callers" in allowed_modes and is_target)
        if relation_type == "depends_on":
            return ("depends_on" in allowed_modes and is_source) or (
                "reverse_depends_on" in allowed_modes and is_target
            )
        if relation_type in {"references", "reference"}:
            return "references" in allowed_modes
        return False

    def _resolve_symbols(self, symbol: Symbol, relation: Relation, allowed_modes: set[str]) -> list[Symbol]:
        _ = allowed_modes
        candidate_ids = [relation.target_id] if relation.source_id == symbol.id else [relation.source_id]
        resolved: list[Symbol] = []
        for symbol_id in candidate_ids:
            candidate = self.repository.get_symbol_by_id(symbol_id)
            if candidate is not None:
                resolved.append(candidate)
        return resolved

    def _attach_symbol_containers(
        self,
        related_map: dict[str, Module | File | Symbol],
        graph_distances: dict[str, int],
        object_: Module | File | Symbol,
        depth: int,
    ) -> None:
        if not isinstance(object_, Symbol):
            return

        file_obj = self.repository.get_file_by_id(object_.file_id)
        module = self.repository.get_module_by_id(object_.module_id)
        if file_obj is not None:
            related_map[file_obj.id] = file_obj
            graph_distances[file_obj.id] = min(graph_distances.get(file_obj.id, depth), depth)
        if module is not None:
            related_map[module.id] = module
            graph_distances[module.id] = min(graph_distances.get(module.id, depth), depth)

    def _estimate_expansion_gain(self, question: str, new_objects: list[Module | File | Symbol]) -> float:
        if not new_objects:
            return 0.0

        terms = [term.lower() for term in re.findall(r"[A-Za-z_][\w./:-]*", question)]
        if not terms:
            return 1.0 if any(isinstance(object_, Symbol) for object_ in new_objects) else 0.0

        relevant = 0
        for object_ in new_objects:
            values = [getattr(object_, "name", "").lower()]
            if isinstance(object_, Symbol):
                values.append(object_.qualified_name.lower())
            if isinstance(object_, (Module, File)):
                values.append(object_.path.lower())
            if any(term in value for term in terms for value in values):
                relevant += 1
        return relevant / len(new_objects)
