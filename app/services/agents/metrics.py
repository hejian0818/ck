"""Metrics calculation for QA strategy routing."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core import thresholds
from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Symbol


class Metrics(BaseModel):
    """A/C/E/G/R metrics used for strategy routing."""

    model_config = ConfigDict(extra="forbid")

    A: float = 0.0
    C: float = 0.0
    E: float = 0.0
    G: float = 1.0
    R: float = 1.0


class MetricsCalculator:
    """Calculate QA routing metrics from anchor and retrieval results."""

    def calculate(
        self,
        anchor: Anchor,
        initial_result: Any,
        final_result: Any,
        expanded_object_ids: list[str] | None = None,
    ) -> Metrics:
        return Metrics(
            A=self.calculate_anchor_confidence(anchor),
            C=self.calculate_concentration(initial_result),
            E=self.calculate_evidence(final_result),
            G=self.calculate_expansion_gain(
                initial_object_ids=self._result_object_ids(initial_result),
                final_result=final_result,
                expanded_object_ids=expanded_object_ids or [],
            ),
            R=self.calculate_consistency(final_result),
        )

    @staticmethod
    def calculate_anchor_confidence(anchor: Anchor) -> float:
        return round(anchor.confidence, 4)

    def calculate_concentration(self, retrieval_result: Any) -> float:
        objects = self._ordered_objects(retrieval_result)[: thresholds.METRICS_TOP_K]
        if not objects:
            return 0.0

        module_counter: Counter[str] = Counter()
        file_counter: Counter[str] = Counter()
        for object_ in objects:
            module_id = self._module_id_for_object(object_)
            file_id = self._file_id_for_object(object_)
            if module_id:
                module_counter[module_id] += 1
            if file_id:
                file_counter[file_id] += 1

        total = len(objects)
        module_concentration = max(module_counter.values(), default=0) / total
        file_concentration = max(file_counter.values(), default=0) / total
        return round(max(module_concentration, file_concentration), 4)

    def calculate_evidence(self, retrieval_result: Any) -> float:
        scores = list(getattr(retrieval_result, "object_scores", {}).values())
        if not scores:
            return 0.0

        matched_objects = sum(
            1
            for score in scores
            if score >= thresholds.EVIDENCE_RELEVANCE_THRESHOLD
        )
        if matched_objects == 0:
            return 0.0

        relevance_avg = sum(scores) / len(scores)
        evidence = (matched_objects * relevance_avg) / thresholds.EVIDENCE_REQUIRED_THRESHOLD
        return round(min(1.0, evidence), 4)

    def calculate_expansion_gain(
        self,
        initial_object_ids: list[str],
        final_result: Any,
        expanded_object_ids: list[str],
    ) -> float:
        if not expanded_object_ids:
            return 1.0

        initial_set = set(initial_object_ids)
        scores = getattr(final_result, "object_scores", {})
        new_relevant_objects = [
            object_id
            for object_id in expanded_object_ids
            if object_id not in initial_set
            and scores.get(object_id, 0.0) >= thresholds.EVIDENCE_RELEVANCE_THRESHOLD
        ]
        gain = len(new_relevant_objects) / max(len(set(expanded_object_ids)), 1)
        return round(gain, 4)

    def calculate_consistency(self, retrieval_result: Any) -> float:
        objects = self._ordered_objects(retrieval_result)
        if len(objects) <= 1:
            return 1.0 if objects else 0.0

        module_counter: Counter[str] = Counter()
        for object_ in objects:
            module_id = self._module_id_for_object(object_)
            if module_id:
                module_counter[module_id] += 1

        if len(module_counter) <= 1:
            return 1.0

        total = sum(module_counter.values())
        module_entropy = 0.0
        for count in module_counter.values():
            probability = count / total
            module_entropy -= probability * math.log(probability, 2)

        max_entropy = math.log(len(module_counter), 2)
        if max_entropy == 0.0:
            return 1.0
        consistency = 1.0 - (module_entropy / max_entropy)
        return round(max(consistency, 0.0), 4)

    def _ordered_objects(self, retrieval_result: Any) -> list[Module | File | Symbol]:
        objects: list[Module | File | Symbol] = []
        current_object = getattr(retrieval_result, "current_object", None)
        if current_object is not None:
            objects.append(current_object)
        objects.extend(getattr(retrieval_result, "related_objects", []))
        return objects

    def _result_object_ids(self, retrieval_result: Any) -> list[str]:
        return [object_.id for object_ in self._ordered_objects(retrieval_result)]

    @staticmethod
    def _module_id_for_object(object_: Module | File | Symbol) -> str | None:
        if isinstance(object_, Module):
            return object_.id
        return getattr(object_, "module_id", None)

    @staticmethod
    def _file_id_for_object(object_: Module | File | Symbol) -> str | None:
        if isinstance(object_, File):
            return object_.id
        if isinstance(object_, Symbol):
            return object_.file_id
        return None
