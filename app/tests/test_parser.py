"""Parser tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.cleanarch.cdt_adapter import CDTAdapter
from app.services.cleanarch.spoon_adapter import SpoonAdapter
from app.services.cleanarch.treesitter_adapter import TreeSitterAdapter


class TreeSitterAdapterTests(unittest.TestCase):
    def test_parse_python_file_extracts_symbols_and_calls(self) -> None:
        path = Path("data/test_repo/app_core/services.py")
        result = TreeSitterAdapter().parse_file(str(path))
        names = [symbol.qualified_name for symbol in result.symbols]
        calls = [(relation.source_id, relation.target_id) for relation in result.relations]
        self.assertIn("GreetingService", names)
        self.assertIn("GreetingService.greet", names)
        self.assertIn(("GreetingService.greet", "build_message"), calls)

    def test_parse_python_file_tracks_relative_import_aliases(self) -> None:
        source = """
from .util import format_name as fmt

def helper(name):
    return fmt(name)
"""
        with TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "pkg"
            package_dir.mkdir()
            path = package_dir / "main.py"
            path.write_text(source, encoding="utf-8")
            result = TreeSitterAdapter().parse_file(str(path))

        self.assertEqual(result.import_aliases["fmt"], "util.format_name")

    def test_parse_python_file_tracks_module_import_aliases(self) -> None:
        source = """
import pkg.util as util_mod

def helper(name):
    return util_mod.format_name(name)
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "main.py"
            path.write_text(source, encoding="utf-8")
            result = TreeSitterAdapter().parse_file(str(path))

        self.assertEqual(result.import_aliases["util_mod"], "pkg.util")

    def test_parse_javascript_file_extracts_calls(self) -> None:
        source = """
export function helper(name) {
  return format(name);
}

function format(value) {
  return value.trim();
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.js"
            path.write_text(source, encoding="utf-8")
            result = TreeSitterAdapter().parse_file(str(path))

        calls = {(relation.source_id, relation.target_id) for relation in result.relations}
        self.assertIn(("helper", "format"), calls)

    def test_parse_javascript_file_tracks_import_aliases(self) -> None:
        source = """
import { format as fmt } from "./util";

export function helper(name) {
  return fmt(name);
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.js"
            path.write_text(source, encoding="utf-8")
            result = TreeSitterAdapter().parse_file(str(path))

        self.assertEqual(result.import_aliases["fmt"], "util.format")

    def test_parse_javascript_file_tracks_namespace_import_aliases(self) -> None:
        source = """
import * as util from "./util";

export function helper(name) {
  return util.format(name);
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.js"
            path.write_text(source, encoding="utf-8")
            result = TreeSitterAdapter().parse_file(str(path))

        self.assertEqual(result.import_aliases["util"], "util")

    def test_parse_javascript_file_tracks_default_and_named_import_aliases(self) -> None:
        source = """
import format, { normalize as clean } from "./util";

export function helper(name) {
  return clean(format(name));
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.ts"
            path.write_text(source, encoding="utf-8")
            result = TreeSitterAdapter().parse_file(str(path))

        self.assertEqual(result.import_aliases["format"], "util.default")
        self.assertEqual(result.import_aliases["clean"], "util.normalize")

    def test_parse_go_file_extracts_calls(self) -> None:
        source = """
package sample

func Helper(name string) string {
    return normalize(name)
}

func normalize(value string) string {
    return value
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.go"
            path.write_text(source, encoding="utf-8")
            result = TreeSitterAdapter().parse_file(str(path))

        calls = {(relation.source_id, relation.target_id) for relation in result.relations}
        self.assertIn(("Helper", "normalize"), calls)
        names = {symbol.qualified_name for symbol in result.symbols}
        self.assertIn("sample.Helper", names)
        self.assertIn("sample.normalize", names)

    def test_parse_rust_file_extracts_calls(self) -> None:
        source = """
struct Worker;

impl Worker {
    pub fn run(&self) {
        helper();
    }
}

fn helper() {}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.rs"
            path.write_text(source, encoding="utf-8")
            result = TreeSitterAdapter().parse_file(str(path))

        calls = {(relation.source_id, relation.target_id) for relation in result.relations}
        self.assertIn(("Worker.run", "helper"), calls)

    def test_parse_rust_file_tracks_use_aliases(self) -> None:
        source = """
use crate::helper as h;

fn run() {
    h();
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.rs"
            path.write_text(source, encoding="utf-8")
            result = TreeSitterAdapter().parse_file(str(path))

        self.assertEqual(result.import_aliases["h"], "helper")

    def test_parse_rust_file_tracks_nested_use_aliases(self) -> None:
        source = """
use crate::helpers::format as fmt;

fn run() {
    fmt();
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.rs"
            path.write_text(source, encoding="utf-8")
            result = TreeSitterAdapter().parse_file(str(path))

        self.assertEqual(result.import_aliases["fmt"], "helpers::format")


class SpoonAdapterTests(unittest.TestCase):
    def test_parse_java_file_uses_package_qualified_names(self) -> None:
        source = """
package demo.service;

class Service {
    void run() {
        helper();
    }

    void helper() {
    }
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Service.java"
            path.write_text(source, encoding="utf-8")
            result = SpoonAdapter().parse_file(str(path))

        names = {symbol.qualified_name for symbol in result.symbols}
        self.assertIn("demo.service.Service", names)
        self.assertIn("demo.service.Service.run", names)
        self.assertIn("demo.service.Service.helper", names)

    def test_parse_java_file_extracts_direct_calls(self) -> None:
        source = """
class Service {
    void run() {
        helper();
    }

    void helper() {
    }
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Service.java"
            path.write_text(source, encoding="utf-8")
            result = SpoonAdapter().parse_file(str(path))

        calls = {(relation.source_id, relation.target_id) for relation in result.relations}
        self.assertIn(("Service.run", "helper"), calls)

    def test_parse_java_file_tracks_static_import_aliases(self) -> None:
        source = """
import static demo.util.Helper.format;

class Service {
    void run() {
        format();
    }
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Service.java"
            path.write_text(source, encoding="utf-8")
            result = SpoonAdapter().parse_file(str(path))

        self.assertEqual(result.import_aliases["format"], "demo.util.Helper.format")


class CDTAdapterTests(unittest.TestCase):
    def test_parse_cpp_file_extracts_direct_calls(self) -> None:
        source = """
int helper() {
    return 1;
}

int run() {
    return helper();
}
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.cpp"
            path.write_text(source, encoding="utf-8")
            result = CDTAdapter().parse_file(str(path))

        calls = {(relation.source_id, relation.target_id) for relation in result.relations}
        self.assertIn(("run", "helper"), calls)


if __name__ == "__main__":
    unittest.main()
