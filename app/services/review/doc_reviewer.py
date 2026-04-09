"""Document consistency reviewer."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.doc_models import DocumentResult, DocumentSkeleton, SectionContent, SectionPlan
from app.storage.repositories import GraphRepository

_SECTION_LINK_PATTERN = re.compile(r"\(#([a-zA-Z0-9_-]+)\)")
_BACKTICK_PATTERN = re.compile(r"`([^`]+)`")
_PLANTUML_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_PLANTUML_KEYWORDS = {
    "@startuml",
    "@enduml",
    "startuml",
    "enduml",
    "actor",
    "agent",
    "artifact",
    "as",
    "class",
    "component",
    "database",
    "enum",
    "folder",
    "frame",
    "interface",
    "left",
    "node",
    "note",
    "of",
    "package",
    "participant",
    "queue",
    "rectangle",
    "right",
    "together",
}
_OVERVIEW_SECTION_TYPES = {"overview", "architecture"}


class ReviewIssue(BaseModel):
    """Single issue produced by the document reviewer."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["error", "warning", "info"]
    section_id: str | None = None
    category: Literal["structure", "content", "diagram"]
    message: str


class ReviewResult(BaseModel):
    """Aggregate review result."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    issues: list[ReviewIssue] = Field(default_factory=list)


class DocumentReviewer:
    """Run deterministic document consistency checks."""

    def __init__(self, repository: GraphRepository | None = None) -> None:
        self.repository = repository

    def review(self, skeleton: DocumentSkeleton, document: DocumentResult) -> ReviewResult:
        """Review a generated document against its skeleton and repository graph."""

        issues: list[ReviewIssue] = []
        issues.extend(self._check_structure(skeleton, document))
        issues.extend(self._check_content(skeleton, document))
        issues.extend(self._check_diagrams(skeleton, document))
        return ReviewResult(
            passed=not any(issue.severity == "error" for issue in issues),
            issues=issues,
        )

    def _check_structure(
        self,
        skeleton: DocumentSkeleton,
        document: DocumentResult,
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        planned_sections = {section.section_id: section for section in skeleton.sections}
        generated_sections = {section.section_id: section for section in document.sections}

        for section in skeleton.sections:
            if section.section_id not in generated_sections:
                issues.append(
                    ReviewIssue(
                        severity="error",
                        section_id=section.section_id,
                        category="structure",
                        message="Planned section was not generated.",
                    )
                )

        for section in document.sections:
            if section.section_id not in planned_sections:
                issues.append(
                    ReviewIssue(
                        severity="warning",
                        section_id=section.section_id,
                        category="structure",
                        message="Generated section is not defined in the document skeleton.",
                    )
                )

        previous_level: int | None = None
        for section in skeleton.sections:
            if previous_level is not None and section.level > previous_level + 1:
                issues.append(
                    ReviewIssue(
                        severity="error",
                        section_id=section.section_id,
                        category="structure",
                        message=f"Section level jumps from {previous_level} to {section.level}.",
                    )
                )
            previous_level = section.level

        section_types = {section.section_type for section in skeleton.sections}
        if not section_types.intersection(_OVERVIEW_SECTION_TYPES):
            issues.append(
                ReviewIssue(
                    severity="error",
                    section_id=None,
                    category="structure",
                    message="Document skeleton is missing an overview section.",
                )
            )
        if "summary" not in section_types:
            issues.append(
                ReviewIssue(
                    severity="error",
                    section_id=None,
                    category="structure",
                    message="Document skeleton is missing a summary section.",
                )
            )

        return issues

    def _check_content(
        self,
        skeleton: DocumentSkeleton,
        document: DocumentResult,
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        planned_sections = {section.section_id: section for section in skeleton.sections}
        existing_section_ids = set(planned_sections)
        object_names = self._build_object_name_map(skeleton.repo_id, skeleton.sections, document.sections)

        for section in document.sections:
            issues.extend(self._check_section_links(section, existing_section_ids))
            issues.extend(self._check_used_objects(section, object_names))
            issues.extend(self._check_terminology(section, planned_sections.get(section.section_id), object_names))

        return issues

    def _check_diagrams(
        self,
        skeleton: DocumentSkeleton,
        document: DocumentResult,
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        object_names = self._build_object_name_map(skeleton.repo_id, skeleton.sections, document.sections)
        known_terms = {name.lower() for name in object_names.values()}

        for section in document.sections:
            for diagram in section.diagrams:
                if not diagram.strip():
                    issues.append(
                        ReviewIssue(
                            severity="warning",
                            section_id=section.section_id,
                            category="diagram",
                            message="Diagram content is empty.",
                        )
                    )
                    continue

                diagram_terms = self._extract_diagram_terms(diagram)
                unknown_terms = sorted(term for term in diagram_terms if term.lower() not in known_terms)
                if unknown_terms:
                    issues.append(
                        ReviewIssue(
                            severity="error",
                            section_id=section.section_id,
                            category="diagram",
                            message=(
                                "Diagram references unknown entities: "
                                + ", ".join(unknown_terms)
                                + "."
                            ),
                        )
                    )

                content_text = section.content.lower()
                undocumented_terms = sorted(term for term in diagram_terms if term.lower() not in content_text)
                if undocumented_terms:
                    issues.append(
                        ReviewIssue(
                            severity="warning",
                            section_id=section.section_id,
                            category="diagram",
                            message=(
                                "Diagram entities are not described in the section text: "
                                + ", ".join(undocumented_terms)
                                + "."
                            ),
                        )
                    )

        return issues

    def _check_section_links(
        self,
        section: SectionContent,
        existing_section_ids: set[str],
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        for target_section_id in _SECTION_LINK_PATTERN.findall(section.content):
            if target_section_id not in existing_section_ids:
                issues.append(
                    ReviewIssue(
                        severity="error",
                        section_id=section.section_id,
                        category="content",
                        message=f"Cross-reference points to unknown section `{target_section_id}`.",
                    )
                )
        return issues

    def _check_used_objects(
        self,
        section: SectionContent,
        object_names: dict[str, str],
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        for object_id in section.used_objects:
            if object_id not in object_names:
                issues.append(
                    ReviewIssue(
                        severity="error",
                        section_id=section.section_id,
                        category="content",
                        message=f"Section references unknown object `{object_id}`.",
                    )
                )
        return issues

    def _check_terminology(
        self,
        section: SectionContent,
        planned_section: SectionPlan | None,
        object_names: dict[str, str],
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        if planned_section is None:
            return issues

        expected_names = [
            object_names[object_id]
            for object_id in planned_section.target_object_ids
            if object_id in object_names
        ]
        if not expected_names:
            return issues

        normalized_content = section.content.lower()
        if not any(name.lower() in normalized_content for name in expected_names):
            issues.append(
                ReviewIssue(
                    severity="warning",
                    section_id=section.section_id,
                    category="content",
                    message=(
                        "Section terminology does not mention any planned object names: "
                        + ", ".join(expected_names)
                        + "."
                    ),
                )
            )

        referenced_terms = {token.strip() for token in _BACKTICK_PATTERN.findall(section.content)}
        normalized_expected = {name.lower() for name in expected_names}
        normalized_known_names = {name.lower() for name in object_names.values()}
        for term in sorted(referenced_terms):
            if term in object_names:
                continue
            if term.lower() in normalized_expected:
                continue
            if term.lower() in normalized_known_names:
                continue
            if term.lower().startswith("section "):
                continue
            issues.append(
                ReviewIssue(
                    severity="info",
                    section_id=section.section_id,
                    category="content",
                    message=f"Section uses non-canonical terminology `{term}`.",
                )
            )
        return issues

    def _build_object_name_map(
        self,
        repo_id: str,
        planned_sections: list[SectionPlan],
        generated_sections: list[SectionContent],
    ) -> dict[str, str]:
        object_ids = {
            object_id
            for section in planned_sections
            for object_id in section.target_object_ids
        }
        object_ids.update(
            object_id
            for section in generated_sections
            for object_id in section.used_objects
        )

        object_names: dict[str, str] = {}
        for object_id in object_ids:
            resolved_name = self._resolve_object_name(repo_id, object_id)
            if resolved_name:
                object_names[object_id] = resolved_name
        return object_names

    def _resolve_object_name(self, repo_id: str, object_id: str) -> str | None:
        if self.repository is None:
            return object_id

        module = self.repository.get_module_by_id(object_id)
        if module is not None:
            return module.name

        file_obj = self.repository.get_file_by_id(object_id)
        if file_obj is not None:
            return file_obj.path

        symbol = self.repository.get_symbol_by_id(object_id)
        if symbol is not None:
            return symbol.qualified_name

        relation = self.repository.get_relation_by_id(object_id)
        if relation is not None:
            return relation.id

        for section in self.repository.list_modules(repo_id):
            if section.id == object_id:
                return section.name
        return None

    def _extract_diagram_terms(self, diagram: str) -> set[str]:
        terms: set[str] = set()
        for token in _PLANTUML_TOKEN_PATTERN.findall(diagram):
            normalized = token.strip()
            if not normalized:
                continue
            if normalized.lower() in _PLANTUML_KEYWORDS:
                continue
            if normalized.isupper() and "." not in normalized:
                continue
            terms.add(normalized)
        return terms
