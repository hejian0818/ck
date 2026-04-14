"""Summary pipeline and repo API integration tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models.graph_objects import GraphCode
from app.models.qa_models import RepoBuildResponse
from app.services.cleanarch.graph_builder import GraphBuilder
from app.storage.repositories import GraphRepository


class SummaryPipelineTests(unittest.TestCase):
    def _build_repository(self) -> GraphRepository:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        repository = GraphRepository(database_url="sqlite://", engine=engine)
        repository.initialize_schema()
        return repository

    def _build_graph(self) -> GraphCode:
        return GraphBuilder().build_graph(repo_path=str(Path("data/test_repo").resolve()))

    def test_graph_builder_generates_summaries_for_all_objects(self) -> None:
        graph = self._build_graph()

        self.assertTrue(graph.modules)
        self.assertTrue(graph.files)
        self.assertTrue(graph.symbols)
        self.assertTrue(graph.relations)
        self.assertTrue(all(json.loads(module.summary) for module in graph.modules))
        self.assertTrue(all(json.loads(file_obj.summary) for file_obj in graph.files))
        self.assertTrue(all(json.loads(symbol.summary) for symbol in graph.symbols))
        self.assertTrue(all(json.loads(relation.summary) for relation in graph.relations))

    def test_graph_builder_resolves_cross_file_call_relations(self) -> None:
        graph = self._build_graph()
        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        relations = [
            relation
            for relation in graph.relations
            if symbols_by_id.get(relation.source_id)
            and symbols_by_id[relation.source_id].qualified_name == "GreetingService.greet"
        ]

        self.assertTrue(relations)
        target_names = [
            symbols_by_id[relation.target_id].qualified_name
            for relation in relations
            if relation.target_id in symbols_by_id
        ]
        self.assertIn("build_message", target_names)

    def test_graph_builder_uses_import_alias_to_resolve_same_name_symbols(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            src_dir = repo_path / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / "main.js").write_text(
                'import { format as fmt } from "./util";\n'
                'export function helper(name) { return fmt(name); }\n',
                encoding="utf-8",
            )
            (src_dir / "util.js").write_text(
                "export function format(value) { return value.trim(); }\n",
                encoding="utf-8",
            )
            (src_dir / "other.js").write_text(
                "export function format(value) { return value.toUpperCase(); }\n",
                encoding="utf-8",
            )

            graph = GraphBuilder().build_graph(repo_path=str(repo_path))

        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        files_by_id = {file_obj.id: file_obj for file_obj in graph.files}
        helper_symbol = next(symbol for symbol in graph.symbols if symbol.qualified_name == "helper")
        helper_calls = [
            relation for relation in graph.relations
            if relation.source_id == helper_symbol.id and relation.relation_type == "calls"
        ]
        target_names = [symbols_by_id[relation.target_id].qualified_name for relation in helper_calls]

        self.assertEqual(target_names.count("format"), 1)
        resolved_targets = [relation.target_id for relation in helper_calls]
        util_format_id = next(
            symbol.id for symbol in graph.symbols
            if symbol.qualified_name == "format" and symbol.file_id != helper_symbol.file_id
            and files_by_id[symbol.file_id].path == "src/util.js"
        )
        self.assertIn(util_format_id, resolved_targets)

    def test_graph_builder_resolves_javascript_default_import_calls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            src_dir = repo_path / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / "main.ts").write_text(
                'import format from "./util";\n'
                "export function helper(name: string) { return format(name); }\n",
                encoding="utf-8",
            )
            (src_dir / "util.ts").write_text(
                "export default function format(value: string) { return value.trim(); }\n",
                encoding="utf-8",
            )
            (src_dir / "other.ts").write_text(
                "export default function format(value: string) { return value.toUpperCase(); }\n",
                encoding="utf-8",
            )

            graph = GraphBuilder().build_graph(repo_path=str(repo_path))

        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        files_by_id = {file_obj.id: file_obj for file_obj in graph.files}
        helper_symbol = next(symbol for symbol in graph.symbols if symbol.qualified_name == "helper")
        helper_calls = [
            relation for relation in graph.relations
            if relation.source_id == helper_symbol.id and relation.relation_type == "calls"
        ]

        self.assertEqual(len(helper_calls), 1)
        resolved_target = symbols_by_id[helper_calls[0].target_id]
        self.assertEqual(resolved_target.qualified_name, "format")
        self.assertEqual(files_by_id[resolved_target.file_id].path, "src/util.ts")

    def test_graph_builder_resolves_javascript_namespace_import_calls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            src_dir = repo_path / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / "main.js").write_text(
                'import * as util from "./util";\n'
                "export function helper(name) { return util.format(name); }\n",
                encoding="utf-8",
            )
            (src_dir / "util.js").write_text(
                "export function format(value) { return value.trim(); }\n",
                encoding="utf-8",
            )
            (src_dir / "other.js").write_text(
                "export function format(value) { return value.toUpperCase(); }\n",
                encoding="utf-8",
            )

            graph = GraphBuilder().build_graph(repo_path=str(repo_path))

        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        files_by_id = {file_obj.id: file_obj for file_obj in graph.files}
        helper_symbol = next(symbol for symbol in graph.symbols if symbol.qualified_name == "helper")
        helper_calls = [
            relation for relation in graph.relations
            if relation.source_id == helper_symbol.id and relation.relation_type == "calls"
        ]

        self.assertEqual(len(helper_calls), 1)
        resolved_target = symbols_by_id[helper_calls[0].target_id]
        self.assertEqual(resolved_target.qualified_name, "format")
        self.assertEqual(files_by_id[resolved_target.file_id].path, "src/util.js")

    def test_graph_builder_resolves_java_static_import_calls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            service_dir = repo_path / "src" / "demo" / "service"
            util_dir = repo_path / "src" / "demo" / "util"
            service_dir.mkdir(parents=True, exist_ok=True)
            util_dir.mkdir(parents=True, exist_ok=True)
            (service_dir / "Service.java").write_text(
                "package demo.service;\n\n"
                "import static demo.util.Helper.format;\n\n"
                "class Service {\n"
                "    void run() {\n"
                "        format();\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            (util_dir / "Helper.java").write_text(
                "package demo.util;\n\n"
                "class Helper {\n"
                "    static void format() {\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )

            graph = GraphBuilder().build_graph(repo_path=str(repo_path))

        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        service_run = next(symbol for symbol in graph.symbols if symbol.qualified_name == "demo.service.Service.run")
        calls = [
            relation for relation in graph.relations
            if relation.source_id == service_run.id and relation.relation_type == "calls"
        ]

        self.assertEqual(len(calls), 1)
        self.assertEqual(symbols_by_id[calls[0].target_id].qualified_name, "demo.util.Helper.format")

    def test_graph_builder_resolves_java_class_method_suffix_lookup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            service_dir = repo_path / "src" / "demo" / "service"
            util_dir = repo_path / "src" / "demo" / "util"
            service_dir.mkdir(parents=True, exist_ok=True)
            util_dir.mkdir(parents=True, exist_ok=True)
            (service_dir / "Service.java").write_text(
                "package demo.service;\n\n"
                "class Service {\n"
                "    void run() {\n"
                "        Helper.format();\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            (util_dir / "Helper.java").write_text(
                "package demo.util;\n\n"
                "class Helper {\n"
                "    static void format() {\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )

            graph = GraphBuilder().build_graph(repo_path=str(repo_path))

        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        service_run = next(symbol for symbol in graph.symbols if symbol.qualified_name == "demo.service.Service.run")
        calls = [
            relation for relation in graph.relations
            if relation.source_id == service_run.id and relation.relation_type == "calls"
        ]

        self.assertEqual(len(calls), 1)
        self.assertEqual(symbols_by_id[calls[0].target_id].qualified_name, "demo.util.Helper.format")

    def test_graph_builder_uses_python_import_alias_to_resolve_same_name_symbols(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            pkg_dir = repo_path / "pkg"
            pkg_dir.mkdir(parents=True, exist_ok=True)
            (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
            (pkg_dir / "main.py").write_text(
                "from .util import format_name as fmt\n\n"
                "def helper(name):\n"
                "    return fmt(name)\n",
                encoding="utf-8",
            )
            (pkg_dir / "util.py").write_text(
                "def format_name(value):\n"
                "    return value.strip()\n",
                encoding="utf-8",
            )
            (pkg_dir / "other.py").write_text(
                "def format_name(value):\n"
                "    return value.upper()\n",
                encoding="utf-8",
            )

            graph = GraphBuilder().build_graph(repo_path=str(repo_path))

        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        files_by_id = {file_obj.id: file_obj for file_obj in graph.files}
        helper_symbol = next(symbol for symbol in graph.symbols if symbol.qualified_name == "helper")
        helper_calls = [
            relation for relation in graph.relations
            if relation.source_id == helper_symbol.id and relation.relation_type == "calls"
        ]

        self.assertEqual(len(helper_calls), 1)
        resolved_target = symbols_by_id[helper_calls[0].target_id]
        self.assertEqual(resolved_target.qualified_name, "format_name")
        self.assertEqual(files_by_id[resolved_target.file_id].path, "pkg/util.py")

    def test_graph_builder_resolves_python_module_import_alias_calls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            pkg_dir = repo_path / "pkg"
            pkg_dir.mkdir(parents=True, exist_ok=True)
            (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
            (pkg_dir / "main.py").write_text(
                "import pkg.util as util_mod\n\n"
                "def helper(name):\n"
                "    return util_mod.format_name(name)\n",
                encoding="utf-8",
            )
            (pkg_dir / "util.py").write_text(
                "def format_name(value):\n"
                "    return value.strip()\n",
                encoding="utf-8",
            )
            (pkg_dir / "other.py").write_text(
                "def format_name(value):\n"
                "    return value.upper()\n",
                encoding="utf-8",
            )

            graph = GraphBuilder().build_graph(repo_path=str(repo_path))

        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        files_by_id = {file_obj.id: file_obj for file_obj in graph.files}
        helper_symbol = next(symbol for symbol in graph.symbols if symbol.qualified_name == "helper")
        helper_calls = [
            relation for relation in graph.relations
            if relation.source_id == helper_symbol.id and relation.relation_type == "calls"
        ]

        self.assertEqual(len(helper_calls), 1)
        resolved_target = symbols_by_id[helper_calls[0].target_id]
        self.assertEqual(resolved_target.qualified_name, "format_name")
        self.assertEqual(files_by_id[resolved_target.file_id].path, "pkg/util.py")

    def test_graph_builder_resolves_rust_nested_use_alias_calls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            src_dir = repo_path / "src"
            helpers_dir = src_dir / "helpers"
            src_dir.mkdir(parents=True, exist_ok=True)
            helpers_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / "main.rs").write_text(
                "use crate::helpers::format as fmt;\n\n"
                "fn run() {\n"
                "    fmt();\n"
                "}\n",
                encoding="utf-8",
            )
            (helpers_dir / "mod.rs").write_text(
                "pub fn format() {}\n",
                encoding="utf-8",
            )
            (src_dir / "other.rs").write_text(
                "fn format() {}\n",
                encoding="utf-8",
            )

            graph = GraphBuilder().build_graph(repo_path=str(repo_path))

        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        files_by_id = {file_obj.id: file_obj for file_obj in graph.files}
        run_symbol = next(symbol for symbol in graph.symbols if symbol.qualified_name == "run")
        run_calls = [
            relation for relation in graph.relations
            if relation.source_id == run_symbol.id and relation.relation_type == "calls"
        ]

        self.assertEqual(len(run_calls), 1)
        resolved_target = symbols_by_id[run_calls[0].target_id]
        self.assertEqual(resolved_target.qualified_name, "format")
        self.assertEqual(files_by_id[resolved_target.file_id].path, "src/helpers/mod.rs")

    def test_graph_builder_resolves_rust_type_method_calls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            src_dir = repo_path / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / "main.rs").write_text(
                "struct Worker;\n\n"
                "fn run() {\n"
                "    Worker::build();\n"
                "}\n",
                encoding="utf-8",
            )
            (src_dir / "worker.rs").write_text(
                "pub struct Worker;\n\n"
                "impl Worker {\n"
                "    pub fn build() {}\n"
                "}\n",
                encoding="utf-8",
            )
            (src_dir / "other.rs").write_text(
                "fn build() {}\n",
                encoding="utf-8",
            )

            graph = GraphBuilder().build_graph(repo_path=str(repo_path))

        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        files_by_id = {file_obj.id: file_obj for file_obj in graph.files}
        run_symbol = next(symbol for symbol in graph.symbols if symbol.qualified_name == "run")
        run_calls = [
            relation for relation in graph.relations
            if relation.source_id == run_symbol.id and relation.relation_type == "calls"
        ]

        self.assertEqual(len(run_calls), 1)
        resolved_target = symbols_by_id[run_calls[0].target_id]
        self.assertEqual(resolved_target.qualified_name, "Worker.build")
        self.assertEqual(files_by_id[resolved_target.file_id].path, "src/worker.rs")

    def test_graph_builder_resolves_cpp_namespace_class_method_calls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            src_dir = repo_path / "src"
            src_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / "main.cpp").write_text(
                "namespace demo {\n"
                "int run() {\n"
                "    return util::Helper::format();\n"
                "}\n"
                "}\n",
                encoding="utf-8",
            )
            (src_dir / "helper.cpp").write_text(
                "namespace util {\n"
                "class Helper {\n"
                "public:\n"
                "    static int format() { return 1; }\n"
                "};\n"
                "}\n",
                encoding="utf-8",
            )
            (src_dir / "other.cpp").write_text(
                "int format() { return 2; }\n",
                encoding="utf-8",
            )

            graph = GraphBuilder().build_graph(repo_path=str(repo_path))

        symbols_by_id = {symbol.id: symbol for symbol in graph.symbols}
        files_by_id = {file_obj.id: file_obj for file_obj in graph.files}
        run_symbol = next(symbol for symbol in graph.symbols if symbol.qualified_name == "demo::run")
        run_calls = [
            relation for relation in graph.relations
            if relation.source_id == run_symbol.id and relation.relation_type == "calls"
        ]

        self.assertEqual(len(run_calls), 1)
        resolved_target = symbols_by_id[run_calls[0].target_id]
        self.assertEqual(resolved_target.qualified_name, "util::Helper::format")
        self.assertEqual(files_by_id[resolved_target.file_id].path, "src/helper.cpp")

    def test_repository_persists_and_updates_summaries(self) -> None:
        repository = self._build_repository()
        graph = self._build_graph()
        repository.save_graphcode(graph)

        module = graph.modules[0]
        stored_summary = repository.get_summary("module", module.id)
        self.assertIsNotNone(stored_summary)
        self.assertEqual(json.loads(stored_summary or "")["module_path"], module.path)

        repository.update_summary("module", module.id, '{"module_path":"override"}')
        self.assertEqual(repository.get_summary("module", module.id), '{"module_path":"override"}')

    def test_summary_api_returns_persisted_summary(self) -> None:
        repository = self._build_repository()
        graph = self._build_graph()
        repository.save_graphcode(graph)
        module = graph.modules[0]

        with patch("app.api.repo.get_graph_repository", return_value=repository):
            client = TestClient(app)
            response = client.get(f"/repo/module/{module.id}/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object_type"], "module")
        self.assertEqual(payload["object_id"], module.id)
        self.assertEqual(json.loads(payload["summary"])["module_path"], module.path)

    def test_scan_api_builds_and_persists_repository_index(self) -> None:
        repository = self._build_repository()
        repo_path = str(Path("data/test_repo").resolve())

        with patch("app.api.repo.get_graph_repository", return_value=repository):
            client = TestClient(app)
            response = client.post("/repo/scan", json={"repo_path": repo_path, "branch": "main"})

        self.assertEqual(response.status_code, 200)
        payload = RepoBuildResponse.model_validate(response.json())
        self.assertEqual(payload.status, "success")
        self.assertTrue(payload.build_id)
        self.assertTrue(repository.list_modules(payload.build_id))

    def test_scan_api_rejects_missing_repository_path(self) -> None:
        client = TestClient(app)
        response = client.post("/repo/scan", json={"branch": "main"})

        self.assertEqual(response.status_code, 422)

    def test_scan_api_rejects_nonexistent_repository_path(self) -> None:
        client = TestClient(app)
        response = client.post("/repo/scan", json={"repo_path": "/path/that/does/not/exist", "branch": "main"})

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
