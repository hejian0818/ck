"""Summary builder tests."""

from __future__ import annotations

import json
import unittest

from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.indexing.summary_builder import (
    FileSummaryBuilder,
    ModuleSummaryBuilder,
    RelationSummaryBuilder,
    SymbolSummaryBuilder,
)


class SummaryBuilderTests(unittest.TestCase):
    def test_module_summary_builder_outputs_required_fields(self) -> None:
        module = Module(id="M_service", name="user_service", path="app/service", metadata={})
        files = [
            File(
                id="F_1",
                name="service.py",
                path="app/service/service.py",
                module_id=module.id,
                summary="",
                language="python",
                start_line=1,
                end_line=20,
            ),
            File(
                id="F_2",
                name="helpers.py",
                path="app/service/helpers.py",
                module_id=module.id,
                summary="",
                language="python",
                start_line=1,
                end_line=10,
            ),
        ]
        symbols = [
            Symbol(
                id="S_1",
                name="UserService",
                qualified_name="UserService",
                type="class",
                signature="class UserService",
                file_id="F_1",
                module_id=module.id,
                summary="",
                start_line=1,
                end_line=10,
                visibility="public",
                doc="",
            ),
            Symbol(
                id="S_2",
                name="get_user",
                qualified_name="get_user",
                type="function",
                signature="get_user(user_id)",
                file_id="F_1",
                module_id=module.id,
                summary="",
                start_line=11,
                end_line=20,
                visibility="public",
                doc="",
            ),
        ]
        relations = [
            Relation(
                id="R_1",
                relation_type="depends_on",
                source_id="S_1",
                target_id="S_external",
                source_type="symbol",
                target_type="symbol",
                source_module_id=module.id,
                target_module_id="M_api",
                summary="",
            )
        ]

        summary = json.loads(
            ModuleSummaryBuilder().build(
                module=module,
                files=files,
                symbols=symbols,
                relations=relations,
            )
        )

        self.assertEqual(summary["module_path"], "app/service")
        self.assertEqual(summary["responsibility_label"], "Business Logic")
        self.assertEqual(summary["core_files"], ["app/service/service.py", "app/service/helpers.py"])
        self.assertEqual(summary["core_symbols"], ["UserService", "get_user"])
        self.assertEqual(summary["adjacent_modules"], ["M_api"])

    def test_file_summary_builder_detects_dependencies_and_label(self) -> None:
        module = Module(id="M_web", name="web", path="web", metadata={})
        file_obj = File(
            id="F_api",
            name="app.py",
            path="web/app.py",
            module_id=module.id,
            summary="",
            language="python",
            start_line=1,
            end_line=10,
        )
        symbols = [
            Symbol(
                id="S_api.fetch",
                name="fetch",
                qualified_name="fetch",
                type="function",
                signature="fetch()",
                file_id=file_obj.id,
                module_id=module.id,
                summary="",
                start_line=1,
                end_line=10,
                visibility="public",
                doc="",
            )
        ]
        relations = [
            Relation(
                id="R_1",
                relation_type="calls",
                source_id="S_api.fetch",
                target_id="S_domain.find_user",
                source_type="symbol",
                target_type="symbol",
                source_module_id="M_web",
                target_module_id="M_domain",
                summary="",
            )
        ]

        summary = json.loads(
            FileSummaryBuilder().build(
                file_obj=file_obj,
                module=module,
                symbols=symbols,
                relations=relations,
                object_names={"S_domain.find_user": "find_user"},
                object_file_ids={"S_api.fetch": "F_api", "S_domain.find_user": "F_domain"},
            )
        )

        self.assertEqual(summary["file_path"], "web/app.py")
        self.assertEqual(summary["module"], "web")
        self.assertEqual(summary["responsibility_label"], "Entry Point")
        self.assertEqual(summary["main_symbols"], ["fetch"])
        self.assertEqual(summary["dependencies"], ["find_user"])

    def test_symbol_summary_builder_parses_signature_and_external_dependencies(self) -> None:
        symbol = Symbol(
            id="S_service.get_user",
            name="get_user",
            qualified_name="service.get_user",
            type="function",
            signature="get_user(user_id: str) -> User",
            file_id="F_service",
            module_id="M_service",
            summary="",
            start_line=1,
            end_line=5,
            visibility="public",
            doc="",
        )
        relations = [
            Relation(
                id="R_1",
                relation_type="calls",
                source_id="S_controller.handle",
                target_id=symbol.id,
                source_type="symbol",
                target_type="symbol",
                source_module_id="M_controller",
                target_module_id="M_service",
                summary="",
            ),
            Relation(
                id="R_2",
                relation_type="calls",
                source_id=symbol.id,
                target_id="S_repo.find_user",
                source_type="symbol",
                target_type="symbol",
                source_module_id="M_service",
                target_module_id="M_repo",
                summary="",
            ),
        ]

        summary = json.loads(
            SymbolSummaryBuilder().build(
                symbol=symbol,
                relations=relations,
                file_path="service/user.py",
                module_path="service",
                object_names={
                    "S_controller.handle": "controller.handle",
                    "S_repo.find_user": "repo.find_user",
                },
            )
        )

        self.assertEqual(summary["name"], "get_user")
        self.assertEqual(summary["file"], "service/user.py")
        self.assertEqual(summary["module"], "service")
        self.assertEqual(summary["parameters"], ["user_id: str"])
        self.assertEqual(summary["return_value"], "User")
        self.assertEqual(summary["responsibility_label"], "Query")
        self.assertEqual(summary["callers"], ["controller.handle"])
        self.assertEqual(summary["callees"], ["repo.find_user"])
        self.assertEqual(summary["external_dependencies"], ["controller.handle", "repo.find_user"])

    def test_relation_summary_builder_formats_label(self) -> None:
        relation = Relation(
            id="R_1",
            relation_type="implements",
            source_id="S_service.UserService",
            target_id="S_contract.UserRepository",
            source_type="symbol",
            target_type="symbol",
            source_module_id="M_service",
            target_module_id="M_contract",
            summary="",
        )

        summary = json.loads(
            RelationSummaryBuilder().build(
                relation=relation,
                source_name="UserService",
                source_type="symbol",
                target_name="UserRepository",
                target_type="symbol",
                source_module="service",
                target_module="contract",
            )
        )

        self.assertEqual(summary["relation_type"], "implements")
        self.assertEqual(summary["source_name"], "UserService")
        self.assertEqual(summary["target_name"], "UserRepository")
        self.assertEqual(summary["relationship_label"], "UserService implements UserRepository")


if __name__ == "__main__":
    unittest.main()
