"""Resolve user selections into graph anchors."""

from __future__ import annotations

from app.core.thresholds import ANCHOR_CONFIDENCE_STRONG, ANCHOR_CONFIDENCE_WEAK
from app.models.anchor import Anchor
from app.models.qa_models import CodeSelection
from app.services.memory.memory_manager import AnchorMemory
from app.storage.repositories import GraphRepository


class AnchorResolver:
    """Resolve explicit selections to the most specific anchor."""

    def __init__(self, repository: GraphRepository) -> None:
        self.repository = repository

    def resolve_anchor(
        self,
        question: str,
        selection: CodeSelection | None,
        memory: AnchorMemory,
    ) -> Anchor:
        _ = question
        if not selection:
            if memory.current_anchor is not None:
                inherited_anchor = memory.current_anchor.model_copy(deep=True)
                inherited_anchor.source = "memory_inherit"
                inherited_anchor.confidence = max(
                    inherited_anchor.confidence,
                    ANCHOR_CONFIDENCE_WEAK,
                )
                return inherited_anchor
            return Anchor(level="none", source="none", confidence=0.0)

        matches = self.repository.find_span(
            file_path=selection.file_path,
            line_start=selection.line_start,
            line_end=selection.line_end,
        )
        if not matches:
            return Anchor(
                level="none",
                source="none",
                confidence=0.0,
                file_path=selection.file_path,
                line_start=selection.line_start,
                line_end=selection.line_end,
            )

        best_match = self._pick_best_match(matches)
        if best_match.symbol_id:
            symbol = self.repository.get_symbol_by_id(best_match.symbol_id)
            if symbol:
                return Anchor(
                    level="symbol",
                    source="explicit_span",
                    confidence=ANCHOR_CONFIDENCE_STRONG,
                    module_id=best_match.module_id,
                    file_id=best_match.file_id,
                    symbol_id=best_match.symbol_id,
                    file_path=best_match.file_path,
                    line_start=selection.line_start,
                    line_end=selection.line_end,
                )

        if best_match.file_id:
            return Anchor(
                level="file",
                source="explicit_file",
                confidence=ANCHOR_CONFIDENCE_WEAK,
                module_id=best_match.module_id,
                file_id=best_match.file_id,
                file_path=best_match.file_path,
                line_start=selection.line_start,
                line_end=selection.line_end,
            )

        return Anchor(
            level="module",
            source="explicit_module",
            confidence=ANCHOR_CONFIDENCE_WEAK,
            module_id=best_match.module_id,
            file_path=best_match.file_path,
            line_start=selection.line_start,
            line_end=selection.line_end,
        )

    def _pick_best_match(self, matches):
        def sort_key(span):
            priority = 3
            if span.symbol_id:
                symbol = self.repository.get_symbol_by_id(span.symbol_id)
                symbol_type = symbol.type if symbol else ""
                if symbol_type in {"method", "function"}:
                    priority = 0
                elif symbol_type in {"class", "interface"}:
                    priority = 1
            elif span.node_type == "file":
                priority = 2
            return (priority, span.line_end - span.line_start)

        return sorted(matches, key=sort_key)[0]
