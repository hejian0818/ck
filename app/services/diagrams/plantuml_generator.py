"""Generate PlantUML diagrams from repository graph objects."""

from __future__ import annotations

from collections import defaultdict, deque

from app.models.graph_objects import Module, Relation, Symbol

_CLASS_SYMBOL_TYPES = {"class", "interface"}
_CLASS_RELATION_ALIASES = {
    "inherits": "<|--",
    "extends": "<|--",
    "implements": "<|..",
    "realizes": "<|..",
    "association": "-->",
    "associates": "-->",
    "uses": "-->",
    "depends_on": "..>",
}


class PlantUMLGenerator:
    """Build PlantUML source for document diagrams."""

    def generate_component_diagram(self, modules: list[Module], relations: list[Relation]) -> str:
        """Generate a module dependency component diagram."""

        lines = ["@startuml", "skinparam componentStyle rectangle"]
        for module in sorted(modules, key=lambda item: item.name):
            alias = self._alias(module.id)
            lines.append(f'component "{module.name}" as {alias}')

        for relation in self._unique_relations(relations):
            if relation.source_module_id == relation.target_module_id:
                continue
            source_alias = self._alias(relation.source_module_id)
            target_alias = self._alias(relation.target_module_id)
            label = self._escape_label(relation.relation_type)
            lines.append(f"{source_alias} --> {target_alias} : {label}")

        lines.append("@enduml")
        return "\n".join(lines)

    def generate_class_diagram(self, symbols: list[Symbol], relations: list[Relation]) -> str:
        """Generate a class relationship diagram for symbols and their links."""

        class_symbols = [symbol for symbol in symbols if symbol.type.lower() in _CLASS_SYMBOL_TYPES]
        lines = ["@startuml", "hide empty members"]
        for symbol in sorted(class_symbols, key=lambda item: item.qualified_name):
            alias = self._alias(symbol.id)
            keyword = "interface" if symbol.type.lower() == "interface" else "class"
            lines.append(f'{keyword} "{symbol.qualified_name}" as {alias}')
            if symbol.signature:
                lines.append(f"{alias} : {self._escape_label(symbol.signature)}")

        symbol_ids = {symbol.id for symbol in class_symbols}
        for relation in self._unique_relations(relations):
            if relation.source_id not in symbol_ids or relation.target_id not in symbol_ids:
                continue
            arrow = _CLASS_RELATION_ALIASES.get(relation.relation_type.lower(), "-->")
            source_alias = self._alias(relation.source_id)
            target_alias = self._alias(relation.target_id)
            label = self._escape_label(relation.relation_type)
            lines.append(f"{target_alias} {arrow} {source_alias} : {label}")

        lines.append("@enduml")
        return "\n".join(lines)

    def generate_sequence_diagram(self, entry_symbol: Symbol, call_chain: list[Relation]) -> str:
        """Generate a call flow sequence diagram, expanding at most three layers."""

        adjacency: dict[str, list[Relation]] = defaultdict(list)
        for relation in call_chain:
            if relation.relation_type.lower() != "calls":
                continue
            adjacency[relation.source_id].append(relation)

        lines = ["@startuml", "autonumber"]
        participants: list[str] = []
        participant_ids: set[str] = set()
        ordered_relations = self._walk_call_chain(entry_symbol.id, adjacency, max_depth=3)

        for relation in ordered_relations:
            for symbol_id in (relation.source_id, relation.target_id):
                if symbol_id in participant_ids:
                    continue
                participant_ids.add(symbol_id)
                participants.append(symbol_id)

        if entry_symbol.id not in participant_ids:
            participants.insert(0, entry_symbol.id)
            participant_ids.add(entry_symbol.id)

        for symbol_id in participants:
            alias = self._alias(symbol_id)
            label = entry_symbol.qualified_name if symbol_id == entry_symbol.id else symbol_id
            lines.append(f'participant "{label}" as {alias}')

        for relation in ordered_relations:
            source_alias = self._alias(relation.source_id)
            target_alias = self._alias(relation.target_id)
            label = self._escape_label(relation.relation_type)
            lines.append(f"{source_alias} -> {target_alias} : {label}")

        lines.append("@enduml")
        return "\n".join(lines)

    def _walk_call_chain(
        self,
        entry_symbol_id: str,
        adjacency: dict[str, list[Relation]],
        *,
        max_depth: int,
    ) -> list[Relation]:
        ordered: list[Relation] = []
        seen_relation_ids: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(entry_symbol_id, 0)])

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for relation in adjacency.get(current_id, []):
                if relation.id in seen_relation_ids:
                    continue
                seen_relation_ids.add(relation.id)
                ordered.append(relation)
                queue.append((relation.target_id, depth + 1))
        return ordered

    @staticmethod
    def _unique_relations(relations: list[Relation]) -> list[Relation]:
        return list({relation.id: relation for relation in relations}.values())

    @staticmethod
    def _alias(raw_value: str) -> str:
        normalized = "".join(char if char.isalnum() else "_" for char in raw_value)
        return f"node_{normalized}" if normalized else "node_unknown"

    @staticmethod
    def _escape_label(value: str) -> str:
        return value.replace('"', "'").replace("\n", " ").strip()
