"""Document reviewer tests."""

from __future__ import annotations

import unittest

from app.models.doc_models import DocumentResult, DocumentSkeleton, SectionContent, SectionPlan
from app.models.graph_objects import File, Module, Symbol
from app.services.review.doc_reviewer import DocumentReviewer


class _ReviewRepoStub:
    module = Module(id="M_app", name="app", path="app", metadata={})
    file_obj = File(
        id="F_service",
        name="service.py",
        path="app/service.py",
        module_id="M_app",
        language="python",
        start_line=1,
        end_line=20,
    )
    symbol = Symbol(
        id="S_app.Service.run",
        name="run",
        qualified_name="Service.run",
        type="method",
        signature="run()",
        file_id="F_service",
        module_id="M_app",
        start_line=3,
        end_line=10,
        visibility="public",
        doc="",
    )

    def get_module_by_id(self, object_id: str):
        if object_id == self.module.id:
            return self.module
        return None

    def get_file_by_id(self, object_id: str):
        if object_id == self.file_obj.id:
            return self.file_obj
        return None

    def get_symbol_by_id(self, object_id: str):
        if object_id == self.symbol.id:
            return self.symbol
        return None

    def get_relation_by_id(self, object_id: str):  # noqa: ARG002
        return None

    def list_modules(self, repo_id: str):  # noqa: ARG002
        return [self.module]


class DocumentReviewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reviewer = DocumentReviewer(_ReviewRepoStub())
        self.skeleton = DocumentSkeleton(
            repo_id="repo-1",
            title="Repo Design Document",
            sections=[
                SectionPlan(
                    section_id="overview",
                    title="概述",
                    level=1,
                    section_type="overview",
                    target_object_ids=["M_app"],
                    description="概述 app 模块。",
                ),
                SectionPlan(
                    section_id="module-app",
                    title="app",
                    level=2,
                    section_type="module",
                    target_object_ids=["M_app"],
                    description="模块详情。",
                ),
                SectionPlan(
                    section_id="summary",
                    title="总结",
                    level=1,
                    section_type="summary",
                    target_object_ids=["M_app"],
                    description="总结模块信息。",
                ),
            ],
        )

    def test_review_passes_for_consistent_document(self) -> None:
        result = self.reviewer.review(
            self.skeleton,
            DocumentResult(
                repo_id="repo-1",
                title="Repo Design Document",
                sections=[
                    SectionContent(
                        section_id="overview",
                        title="概述",
                        content="概述 `app` 模块，并链接到 [详情](#module-app)。",
                        used_objects=["M_app"],
                        confidence=0.9,
                    ),
                    SectionContent(
                        section_id="module-app",
                        title="app",
                        content="`app` 模块实现了 `Service.run` 流程。",
                        diagrams=[
                            "@startuml\nclass app\nclass Service.run\napp --> Service.run\n@enduml"
                        ],
                        used_objects=["M_app", "S_app.Service.run"],
                        confidence=0.9,
                    ),
                    SectionContent(
                        section_id="summary",
                        title="总结",
                        content="总结 `app` 模块的实现边界。",
                        used_objects=["M_app"],
                        confidence=0.9,
                    ),
                ],
            ),
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.issues, [])

    def test_review_reports_missing_section_and_invalid_cross_reference(self) -> None:
        result = self.reviewer.review(
            self.skeleton,
            DocumentResult(
                repo_id="repo-1",
                title="Repo Design Document",
                sections=[
                    SectionContent(
                        section_id="overview",
                        title="概述",
                        content="见 [不存在的章节](#missing-section)。",
                        used_objects=["M_app"],
                        confidence=0.8,
                    ),
                    SectionContent(
                        section_id="module-app",
                        title="app",
                        content="`app` 模块详情。",
                        used_objects=["M_app"],
                        confidence=0.8,
                    ),
                ],
            ),
        )

        messages = {issue.message for issue in result.issues}
        self.assertFalse(result.passed)
        self.assertIn("Planned section was not generated.", messages)
        self.assertIn("Cross-reference points to unknown section `missing-section`.", messages)

    def test_review_reports_unknown_object_and_diagram_entity(self) -> None:
        result = self.reviewer.review(
            self.skeleton,
            DocumentResult(
                repo_id="repo-1",
                title="Repo Design Document",
                sections=[
                    SectionContent(
                        section_id="overview",
                        title="概述",
                        content="概述 `app` 模块。",
                        used_objects=["M_app"],
                        confidence=0.8,
                    ),
                    SectionContent(
                        section_id="module-app",
                        title="app",
                        content="`app` 模块依赖未知对象。",
                        diagrams=[
                            "@startuml\nclass app\nclass GhostService\napp --> GhostService\n@enduml"
                        ],
                        used_objects=["UNKNOWN_OBJECT"],
                        confidence=0.8,
                    ),
                    SectionContent(
                        section_id="summary",
                        title="总结",
                        content="总结 `app` 模块。",
                        used_objects=["M_app"],
                        confidence=0.8,
                    ),
                ],
            ),
        )

        messages = {issue.message for issue in result.issues}
        self.assertIn("Section references unknown object `UNKNOWN_OBJECT`.", messages)
        self.assertIn("Diagram references unknown entities: GhostService.", messages)


if __name__ == "__main__":
    unittest.main()
