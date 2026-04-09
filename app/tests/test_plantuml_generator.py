"""Tests for PlantUML diagram generation."""

from __future__ import annotations

import unittest

from app.models.graph_objects import Module, Relation, Symbol
from app.services.diagrams.plantuml_generator import PlantUMLGenerator


class PlantUMLGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = PlantUMLGenerator()
        self.module_api = Module(id="M_api", name="api", path="app/api", metadata={})
        self.module_core = Module(id="M_core", name="core", path="app/core", metadata={})
        self.service_symbol = Symbol(
            id="S_core.Service",
            name="Service",
            qualified_name="core.Service",
            type="class",
            signature="class Service",
            file_id="F_service",
            module_id="M_core",
            summary="",
            start_line=1,
            end_line=20,
            visibility="public",
            doc="",
        )
        self.repo_symbol = Symbol(
            id="S_core.Repository",
            name="Repository",
            qualified_name="core.Repository",
            type="interface",
            signature="interface Repository",
            file_id="F_repo",
            module_id="M_core",
            summary="",
            start_line=1,
            end_line=10,
            visibility="public",
            doc="",
        )

    def test_generate_component_diagram_returns_plantuml_block(self) -> None:
        diagram = self.generator.generate_component_diagram(
            [self.module_api, self.module_core],
            [
                Relation(
                    id="R_dep",
                    relation_type="depends_on",
                    source_id="S_api.Controller",
                    target_id="S_core.Service",
                    source_type="symbol",
                    target_type="symbol",
                    source_module_id="M_api",
                    target_module_id="M_core",
                    summary="",
                )
            ],
        )

        self.assertTrue(diagram.startswith("@startuml"))
        self.assertTrue(diagram.endswith("@enduml"))
        self.assertIn('component "api"', diagram)
        self.assertIn("depends_on", diagram)

    def test_generate_class_diagram_renders_class_relations(self) -> None:
        diagram = self.generator.generate_class_diagram(
            [self.service_symbol, self.repo_symbol],
            [
                Relation(
                    id="R_impl",
                    relation_type="implements",
                    source_id="S_core.Service",
                    target_id="S_core.Repository",
                    source_type="symbol",
                    target_type="symbol",
                    source_module_id="M_core",
                    target_module_id="M_core",
                    summary="",
                )
            ],
        )

        self.assertTrue(diagram.startswith("@startuml"))
        self.assertIn('class "core.Service"', diagram)
        self.assertIn('interface "core.Repository"', diagram)
        self.assertIn("<|..", diagram)

    def test_generate_sequence_diagram_limits_to_call_relations(self) -> None:
        entry = Symbol(
            id="S_api.Controller.list",
            name="list",
            qualified_name="api.Controller.list",
            type="controller",
            signature="list()",
            file_id="F_controller",
            module_id="M_api",
            summary="",
            start_line=1,
            end_line=10,
            visibility="public",
            doc="",
        )
        diagram = self.generator.generate_sequence_diagram(
            entry,
            [
                Relation(
                    id="R_call_1",
                    relation_type="calls",
                    source_id="S_api.Controller.list",
                    target_id="S_core.Service.run",
                    source_type="symbol",
                    target_type="symbol",
                    source_module_id="M_api",
                    target_module_id="M_core",
                    summary="",
                ),
                Relation(
                    id="R_dep",
                    relation_type="depends_on",
                    source_id="S_api.Controller.list",
                    target_id="S_core.Repository",
                    source_type="symbol",
                    target_type="symbol",
                    source_module_id="M_api",
                    target_module_id="M_core",
                    summary="",
                ),
            ],
        )

        self.assertTrue(diagram.startswith("@startuml"))
        self.assertIn('participant "api.Controller.list"', diagram)
        self.assertIn("->", diagram)
        self.assertNotIn("depends_on", diagram)


if __name__ == "__main__":
    unittest.main()
