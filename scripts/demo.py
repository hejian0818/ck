"""End-to-end demo: graph → skeleton → document generation → QA.

Usage: python3 scripts/demo.py
No external dependencies required (uses stubs for DB and LLM).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.graph_objects import File, Module, Relation, Symbol
from app.models.doc_models import SectionPlan
from app.services.agents.doc_agent import DocAgent, DeterministicDocLLMClient, SkeletonPlanner
from app.services.retrieval.doc_retriever import DocRetriever, SectionRetrievalResult
from app.services.review.doc_reviewer import DocumentReviewer


# ---------------------------------------------------------------------------
# Stub repository (no real database)
# ---------------------------------------------------------------------------

class _DemoRepo:
    """In-memory repository for demo purposes."""

    _modules = [
        Module(id="M_core", name="core", path="core", summary='{"summary":"Core business logic."}', metadata={}),
        Module(id="M_api", name="api", path="api", summary='{"summary":"HTTP API layer."}', metadata={}),
        Module(id="M_storage", name="storage", path="storage", summary='{"summary":"Persistence layer."}', metadata={}),
    ]
    _files = [
        File(id="F_service", name="service.py", path="core/service.py", module_id="M_core",
             language="python", summary='{"summary":"Main service implementation."}', start_line=1, end_line=50),
        File(id="F_models", name="models.py", path="core/models.py", module_id="M_core",
             language="python", summary='{"summary":"Domain models."}', start_line=1, end_line=30),
        File(id="F_router", name="router.py", path="api/router.py", module_id="M_api",
             language="python", summary='{"summary":"FastAPI route definitions."}', start_line=1, end_line=40),
        File(id="F_handler", name="handler.py", path="api/handler.py", module_id="M_api",
             language="python", summary='{"summary":"Request handlers."}', start_line=1, end_line=35),
        File(id="F_repo", name="repo.py", path="storage/repo.py", module_id="M_storage",
             language="python", summary='{"summary":"Repository pattern implementation."}', start_line=1, end_line=60),
    ]
    _symbols = [
        Symbol(id="S_Service", name="Service", qualified_name="core.Service", type="class",
               signature="class Service", file_id="F_service", module_id="M_core",
               summary='{"summary":"Main business service class."}',
               start_line=5, end_line=45, visibility="public", doc=""),
        Symbol(id="S_Service.run", name="run", qualified_name="core.Service.run", type="method",
               signature="run(self, data: dict) -> dict", file_id="F_service", module_id="M_core",
               summary='{"summary":"Execute the main processing pipeline."}',
               start_line=10, end_line=30, visibility="public", doc=""),
        Symbol(id="S_Model", name="Model", qualified_name="core.Model", type="class",
               signature="class Model(BaseModel)", file_id="F_models", module_id="M_core",
               start_line=1, end_line=20, visibility="public", doc=""),
        Symbol(id="S_router", name="router", qualified_name="api.router", type="route",
               signature="router = APIRouter()", file_id="F_router", module_id="M_api",
               summary='{"summary":"API router instance."}',
               start_line=1, end_line=5, visibility="public", doc=""),
        Symbol(id="S_handle_request", name="handle_request", qualified_name="api.handle_request",
               type="function", signature="handle_request(request: Request) -> Response",
               file_id="F_handler", module_id="M_api",
               start_line=5, end_line=25, visibility="public", doc=""),
        Symbol(id="S_Repository", name="Repository", qualified_name="storage.Repository", type="class",
               signature="class Repository", file_id="F_repo", module_id="M_storage",
               summary='{"summary":"Database access object."}',
               start_line=5, end_line=55, visibility="public", doc=""),
        Symbol(id="S_Repository.save", name="save", qualified_name="storage.Repository.save", type="method",
               signature="save(self, entity: Model) -> None", file_id="F_repo", module_id="M_storage",
               start_line=20, end_line=35, visibility="public", doc=""),
        Symbol(id="S_Repository.find", name="find", qualified_name="storage.Repository.find", type="method",
               signature="find(self, id: str) -> Model", file_id="F_repo", module_id="M_storage",
               start_line=36, end_line=50, visibility="public", doc=""),
    ]
    _relations = [
        Relation(id="R1", relation_type="calls", source_id="S_handle_request", target_id="S_Service.run",
                 source_type="symbol", target_type="symbol", source_module_id="M_api", target_module_id="M_core",
                 summary="API handler calls service."),
        Relation(id="R2", relation_type="calls", source_id="S_Service.run", target_id="S_Repository.save",
                 source_type="symbol", target_type="symbol", source_module_id="M_core", target_module_id="M_storage",
                 summary="Service persists results."),
        Relation(id="R3", relation_type="calls", source_id="S_Service.run", target_id="S_Repository.find",
                 source_type="symbol", target_type="symbol", source_module_id="M_core", target_module_id="M_storage",
                 summary="Service queries data."),
        Relation(id="R4", relation_type="depends_on", source_id="S_Service", target_id="S_Model",
                 source_type="symbol", target_type="symbol", source_module_id="M_core", target_module_id="M_core",
                 summary="Service uses Model."),
        Relation(id="R5", relation_type="depends_on", source_id="S_Repository.save", target_id="S_Model",
                 source_type="symbol", target_type="symbol", source_module_id="M_storage", target_module_id="M_core",
                 summary="Repository serializes Model."),
        Relation(id="R6", relation_type="inherits", source_id="S_Model", target_id="S_Model",
                 source_type="symbol", target_type="symbol", source_module_id="M_core", target_module_id="M_core",
                 summary="Model extends BaseModel."),
    ]

    def list_modules(self, repo_id: str):
        return list(self._modules)

    def list_files(self, repo_id: str):
        return list(self._files)

    def list_files_by_module(self, module_id: str):
        return [f for f in self._files if f.module_id == module_id]

    def list_symbols_by_module(self, module_id: str):
        return [s for s in self._symbols if s.module_id == module_id]

    def list_symbols_by_file(self, file_id: str):
        return [s for s in self._symbols if s.file_id == file_id]

    def list_relations(self, repo_id: str):
        return list(self._relations)

    def get_module_by_id(self, oid: str):
        return next((m for m in self._modules if m.id == oid), None)

    def get_file_by_id(self, oid: str):
        return next((f for f in self._files if f.id == oid), None)

    def get_symbol_by_id(self, oid: str):
        return next((s for s in self._symbols if s.id == oid), None)

    def get_relation_by_id(self, oid: str):
        return next((r for r in self._relations if r.id == oid), None)

    def get_relations_by_source(self, source_id: str):
        return [r for r in self._relations if r.source_id == source_id]

    def get_relations_by_target(self, target_id: str):
        return [r for r in self._relations if r.target_id == target_id]

    def get_repo_path(self, repo_id: str):
        return "/demo/project"

    def find_span(self, *_a, **_kw):
        return []


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------

def main() -> None:
    repo = _DemoRepo()
    repo_id = "demo-repo"
    output_dir = Path(PROJECT_ROOT / "data" / "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("CK Demo - Code Knowledge Graph Analysis")
    print("=" * 60)

    # Step 1: Plan skeleton
    print("\n[1/4] Planning document skeleton ...")
    planner = SkeletonPlanner(repo)
    skeleton = planner.plan(repo_id)
    print(f"  Generated {len(skeleton.sections)} sections:")
    for section in skeleton.sections:
        indent = "  " * section.level
        print(f"  {indent}{section.section_id} ({section.section_type})")

    # Step 2: Generate document
    print("\n[2/4] Generating document ...")
    retriever = DocRetriever(repo)
    agent = DocAgent(
        repository=repo,
        planner=planner,
        retriever=retriever,
        llm_client=DeterministicDocLLMClient(),
    )
    document = agent.generate(repo_id, skeleton)
    print(f"  Generated {len(document.sections)} sections with title: {document.title}")

    # Step 3: Review document
    print("\n[3/4] Reviewing document consistency ...")
    reviewer = DocumentReviewer(repo)
    review = reviewer.review(skeleton, document)
    print(f"  Review passed: {review.passed}")
    if review.issues:
        for issue in review.issues:
            print(f"  [{issue.severity}] {issue.section_id or 'global'}: {issue.message}")

    # Step 4: Write output
    print("\n[4/4] Writing output ...")
    output_path = output_dir / "demo_document.md"
    lines = [f"# {document.title}", ""]
    for section in document.sections:
        lines.append(section.content)
        for diagram in section.diagrams:
            lines.extend(["", "```plantuml", diagram, "```"])
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Document written to: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Modules: {len(repo._modules)}")
    print(f"  Files: {len(repo._files)}")
    print(f"  Symbols: {len(repo._symbols)}")
    print(f"  Relations: {len(repo._relations)}")
    print(f"  Sections: {len(document.sections)}")
    print(f"  Review issues: {len(review.issues)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
