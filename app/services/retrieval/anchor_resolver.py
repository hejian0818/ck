"""Resolve user selections into graph anchors."""

from __future__ import annotations

import re

from app.core.thresholds import (
    ANCHOR_CONFIDENCE_STRONG,
    ANCHOR_CONFIDENCE_WEAK,
    ANCHOR_INHERIT_DECAY,
    ANCHOR_NAME_MATCH_AMBIGUOUS,
    ANCHOR_NAME_MATCH_EXACT,
    FOLLOW_UP_MAX_TOKENS,
)
from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Symbol
from app.models.qa_models import CodeSelection
from app.services.memory.memory_manager import AnchorMemory
from app.storage.repositories import GraphRepository

_QUOTED_NAME_RE = re.compile(r"[`'\"“”‘’]([A-Za-z_][\w./:-]*)[`'\"“”‘’]")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][\w./:-]*")
_FOLLOW_UP_HINTS = (
    "它",
    "这个",
    "该",
    "这里",
    "上面",
    "上述",
    "that",
    "this",
    "it",
    "they",
    "them",
    "method",
    "class",
    "file",
)
_FOLLOW_UP_PHRASES = ("该方法", "这个类", "这个文件", "这个模块", "that method", "this class")
_NAME_STOPWORDS = {
    "what",
    "why",
    "how",
    "when",
    "where",
    "which",
    "who",
    "does",
    "show",
    "explain",
    "tell",
    "about",
    "实现",
    "作用",
    "为什么",
    "怎么",
    "如何",
    "哪个",
    "哪些",
}


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
        if not selection:
            name_anchor = self._resolve_name_match(question)
            if name_anchor is not None:
                return name_anchor
            if self._should_inherit_anchor(question, memory):
                return self._inherit_anchor(memory.current_anchor)
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

    def _resolve_name_match(self, question: str) -> Anchor | None:
        candidates = self._extract_name_candidates(question)
        if not candidates:
            return None

        ranked_matches: list[tuple[float, Module | File | Symbol]] = []
        seen_ids: set[str] = set()
        for index, candidate in enumerate(candidates):
            base_score = max(0.0, 1.0 - (index * 0.1))
            for object_ in self._lookup_candidate(candidate):
                if object_.id in seen_ids:
                    continue
                seen_ids.add(object_.id)
                ranked_matches.append((base_score + self._name_match_score(object_, candidate), object_))

        if not ranked_matches:
            return None

        ranked_matches.sort(key=lambda item: item[0], reverse=True)
        if len(ranked_matches) > 3:
            return None

        confidence = (
            ANCHOR_NAME_MATCH_EXACT
            if len(ranked_matches) == 1
            else ANCHOR_NAME_MATCH_AMBIGUOUS
        )
        return self._object_to_anchor(ranked_matches[0][1], confidence=confidence)

    def _lookup_candidate(self, candidate: str) -> list[Module | File | Symbol]:
        return [
            *self.repository.find_symbols_by_name(candidate, limit=4),
            *self.repository.find_files_by_name(candidate, limit=4),
            *self.repository.find_modules_by_name(candidate, limit=4),
        ]

    def _should_inherit_anchor(self, question: str, memory: AnchorMemory) -> bool:
        if memory.current_anchor is None or memory.current_anchor.level == "none":
            return False

        if self._extract_name_candidates(question):
            return False

        normalized_question = self._normalize_text(question)
        if not normalized_question:
            return False

        tokens = normalized_question.split()
        is_follow_up = (
            len(tokens) <= FOLLOW_UP_MAX_TOKENS
            and any(hint in normalized_question for hint in _FOLLOW_UP_HINTS)
        ) or any(phrase in question.lower() for phrase in _FOLLOW_UP_PHRASES)
        if not is_follow_up:
            return False

        current_focus = memory.focus_memory.current_focus
        if not current_focus:
            return True

        focus_tokens = set(current_focus.split())
        question_tokens = set(tokens)
        overlap = len(focus_tokens.intersection(question_tokens))
        return overlap > 0 or len(tokens) <= max(4, FOLLOW_UP_MAX_TOKENS // 2)

    @staticmethod
    def _inherit_anchor(anchor: Anchor | None) -> Anchor:
        if anchor is None:
            return Anchor(level="none", source="none", confidence=0.0)

        inherited_anchor = anchor.model_copy(deep=True)
        inherited_anchor.source = "memory_inherit"
        inherited_anchor.confidence = round(inherited_anchor.confidence * ANCHOR_INHERIT_DECAY, 4)
        return inherited_anchor

    @classmethod
    def _extract_name_candidates(cls, question: str) -> list[str]:
        raw_candidates = [
            *[match.group(1) for match in _QUOTED_NAME_RE.finditer(question)],
            *_IDENTIFIER_RE.findall(question),
        ]
        candidates: list[str] = []
        for raw_candidate in raw_candidates:
            candidate = raw_candidate.strip(".,:;()[]{}<>").lower()
            if not candidate or candidate in _NAME_STOPWORDS:
                continue
            if len(candidate) <= 1:
                continue
            if candidate.isdigit():
                continue
            if cls._looks_like_name(candidate):
                candidates.append(candidate)
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _looks_like_name(candidate: str) -> bool:
        return any(
            marker in candidate
            for marker in (".", "_", "/", ":", "-")
        ) or candidate[0].isalpha()

    @staticmethod
    def _name_match_score(object_: Module | File | Symbol, candidate: str) -> float:
        values = [getattr(object_, "name", "").lower()]
        if isinstance(object_, Symbol):
            values.append(object_.qualified_name.lower())
        if isinstance(object_, (Module, File)):
            values.append(object_.path.lower())

        if candidate in values:
            return 1.0
        if any(value.endswith(candidate) for value in values):
            return 0.7
        if any(candidate in value for value in values):
            return 0.4
        return 0.0

    def _object_to_anchor(self, object_: Module | File | Symbol, confidence: float) -> Anchor:
        if isinstance(object_, Symbol):
            file_obj = self.repository.get_file_by_id(object_.file_id)
            return Anchor(
                level="symbol",
                source="name_match",
                confidence=confidence,
                module_id=object_.module_id,
                file_id=object_.file_id,
                symbol_id=object_.id,
                file_path=file_obj.path if file_obj else None,
            )
        if isinstance(object_, File):
            return Anchor(
                level="file",
                source="name_match",
                confidence=confidence,
                module_id=object_.module_id,
                file_id=object_.id,
                file_path=object_.path,
            )
        return Anchor(
            level="module",
            source="name_match",
            confidence=confidence,
            module_id=object_.id,
            file_path=object_.path,
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text).strip().lower()
        return normalized
