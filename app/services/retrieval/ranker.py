"""Candidate ranking for enhanced retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Symbol

_TYPE_HINTS = {
    "module": ("module", "模块", "package"),
    "file": ("file", "文件"),
    "class": ("class", "类"),
    "function": ("function", "func", "函数"),
    "method": ("method", "方法"),
}


@dataclass(slots=True)
class ScoredCandidate:
    """Compatibility wrapper for scored retrieval candidates."""

    object_id: str
    score: float


class Ranker:
    """Fuse structured and semantic candidates with multi-factor scoring."""

    def rank(
        self,
        *,
        anchor: Anchor,
        question: str,
        current_object: Module | File | Symbol | None,
        candidates: list[Module | File | Symbol],
        vector_scores: dict[str, float] | None = None,
        graph_distances: dict[str, int] | None = None,
        memory_object_ids: list[str] | None = None,
        top_k: int = 10,
    ) -> tuple[list[Module | File | Symbol], dict[str, float]]:
        vector_scores = vector_scores or {}
        graph_distances = graph_distances or {}
        memory_object_ids = memory_object_ids or []
        name_terms = self._extract_name_terms(question)
        current_id = current_object.id if current_object is not None else None

        deduped_candidates = {candidate.id: candidate for candidate in candidates}
        ranked = sorted(
            deduped_candidates.values(),
            key=lambda candidate: self._score_candidate(
                candidate=candidate,
                anchor=anchor,
                question=question,
                name_terms=name_terms,
                vector_score=vector_scores.get(candidate.id, 0.0),
                graph_distance=graph_distances.get(candidate.id),
                in_memory=candidate.id in memory_object_ids,
            ),
            reverse=True,
        )

        ordered: list[Module | File | Symbol] = []
        scores: dict[str, float] = {}
        if current_object is not None:
            ordered.append(current_object)
            scores[current_object.id] = 1.0

        for candidate in ranked:
            if candidate.id == current_id:
                continue
            ordered.append(candidate)
            scores[candidate.id] = self._score_candidate(
                candidate=candidate,
                anchor=anchor,
                question=question,
                name_terms=name_terms,
                vector_score=vector_scores.get(candidate.id, 0.0),
                graph_distance=graph_distances.get(candidate.id),
                in_memory=candidate.id in memory_object_ids,
            )
            if len(ordered) >= top_k + (1 if current_object is not None else 0):
                break

        if current_object is not None:
            return ordered[1:], scores
        return ordered, scores

    def _score_candidate(
        self,
        *,
        candidate: Module | File | Symbol,
        anchor: Anchor,
        question: str,
        name_terms: list[str],
        vector_score: float,
        graph_distance: int | None,
        in_memory: bool,
    ) -> float:
        anchor_proximity = self._anchor_proximity(anchor, candidate)
        name_hit = self._name_hit(candidate, name_terms)
        type_match = self._type_match(candidate, question)
        semantic_similarity = max(0.0, min(vector_score, 1.0))
        graph_score = self._graph_distance_score(graph_distance)
        memory_weight = 1.0 if in_memory else 0.0

        score = (
            (0.30 * anchor_proximity)
            + (0.15 * name_hit)
            + (0.10 * type_match)
            + (0.25 * semantic_similarity)
            + (0.10 * graph_score)
            + (0.10 * memory_weight)
        )
        return round(min(score, 1.0), 4)

    @staticmethod
    def _anchor_proximity(anchor: Anchor, candidate: Module | File | Symbol) -> float:
        if anchor.level == "none":
            return 0.1
        target_id = anchor.symbol_id or anchor.file_id or anchor.module_id
        if candidate.id == target_id:
            return 1.0

        candidate_file_id = getattr(candidate, "file_id", None)
        candidate_module_id = getattr(candidate, "module_id", None)
        if isinstance(candidate, File):
            candidate_file_id = candidate.id
        if isinstance(candidate, Module):
            candidate_module_id = candidate.id

        if anchor.file_id and (candidate_file_id == anchor.file_id or candidate.id == anchor.file_id):
            return 0.7
        if anchor.module_id and (candidate_module_id == anchor.module_id or candidate.id == anchor.module_id):
            return 0.4
        return 0.1

    @classmethod
    def _extract_name_terms(cls, question: str) -> list[str]:
        terms = []
        for raw in re.findall(r"[A-Za-z_][\w./:-]*", question):
            term = raw.strip(".,:;()[]{}<>").lower()
            if len(term) > 1:
                terms.append(term)
        return list(dict.fromkeys(terms))

    @staticmethod
    def _name_hit(candidate: Module | File | Symbol, terms: list[str]) -> float:
        if not terms:
            return 0.0

        values = [getattr(candidate, "name", "").lower()]
        if isinstance(candidate, Symbol):
            values.append(candidate.qualified_name.lower())
        if isinstance(candidate, (Module, File)):
            values.append(candidate.path.lower())

        if any(term in values for term in terms):
            return 1.0
        if any(term in value for term in terms for value in values):
            return 0.5
        return 0.0

    @staticmethod
    def _type_match(candidate: Module | File | Symbol, question: str) -> float:
        normalized = question.lower()
        requested_types = {
            key
            for key, hints in _TYPE_HINTS.items()
            if any(hint in normalized for hint in hints)
        }
        if not requested_types:
            return 0.0

        candidate_type = "module"
        if isinstance(candidate, File):
            candidate_type = "file"
        elif isinstance(candidate, Symbol):
            candidate_type = candidate.type.lower()

        if candidate_type in requested_types:
            return 1.0
        if candidate_type in {"class", "interface"} and "class" in requested_types:
            return 1.0
        if candidate_type in {"function", "method"} and requested_types.intersection({"function", "method"}):
            return 1.0
        return 0.0

    @staticmethod
    def _graph_distance_score(graph_distance: int | None) -> float:
        if graph_distance is None:
            return 0.0
        if graph_distance <= 0:
            return 1.0
        if graph_distance == 1:
            return 0.8
        if graph_distance == 2:
            return 0.4
        return 0.1
